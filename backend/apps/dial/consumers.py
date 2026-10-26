"""wss://…/api/call/v1/ws — the operator phone's always-open channel.

Frames (SocketContract.kt): app → server ``auth`` (first, within 10 s),
``pong``, ``call.dial.ack``, ``call.status``; server → app ``auth.ok`` /
``auth.error`` (``reason: "invalid_token"``), ``ping`` (every 25 s),
``call.dial``. Nothing but ``auth`` is accepted before ``auth.ok``; unknown
types are ignored afterwards. Frames over 8 KB or not a JSON object close
the socket (before auth) or are dropped (after).

Access is re-checked on every ping (operator active, api_key unchanged,
company usable) and revoked at once by ``session.revoke`` group events
(key rotation, operator deactivation/deletion, company suspension —
apps.dial.signals): the socket closes with 4001 and goes offline.
Failed logins are counted per client IP; over the limit new sockets are
refused before the handshake.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from . import services

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10.0
PING_INTERVAL_SECONDS = 25.0
MAX_FRAME_BYTES = 8 * 1024

CLOSE_REVOKED = 4001  # access withdrawn after login
CLOSE_POLICY = 4003  # protocol misuse / bad login
CLOSE_AUTH_TIMEOUT = 4008
CLOSE_TOO_BIG = 1009


class DeviceConsumer(AsyncWebsocketConsumer):  # type: ignore[misc]
    session: services.DeviceSession | None = None
    _auth_deadline: asyncio.Task[None] | None = None
    _pinger: asyncio.Task[None] | None = None
    _groups: tuple[str, ...] = ()
    _connected_at = ""
    _ip = ""

    async def connect(self) -> None:
        self._ip = services.client_ip(self.scope)
        if await database_sync_to_async(services.auth_blocked)(self._ip):
            await self.close()  # before accept → handshake refused (403)
            return
        await self.accept()
        self._auth_deadline = asyncio.ensure_future(self._close_unless_authed())

    async def _close_unless_authed(self) -> None:
        await asyncio.sleep(AUTH_TIMEOUT_SECONDS)
        if self.session is None:
            await database_sync_to_async(services.note_auth_failure)(self._ip)
            await self.close(code=CLOSE_AUTH_TIMEOUT)

    async def disconnect(self, code: int) -> None:
        for task in (self._auth_deadline, self._pinger):
            if task is not None:
                task.cancel()
        await self._leave()

    async def _leave(self) -> None:
        session, self.session = self.session, None
        for group in self._groups:
            await self.channel_layer.group_discard(group, self.channel_name)
        self._groups = ()
        if session is not None:
            await database_sync_to_async(services.mark_offline)(session)
            logger.info(
                "dial ws offline company=%s operator=%s device=%s",
                session.company_id,
                session.operator_id,
                session.device_id,
            )

    async def receive(self, text_data: str | None = None, bytes_data: bytes | None = None) -> None:
        size = len(text_data.encode()) if text_data is not None else 0
        frame: Any = None
        if text_data is not None and size <= MAX_FRAME_BYTES:
            with contextlib.suppress(ValueError):
                frame = json.loads(text_data)
        if not isinstance(frame, dict):
            if self.session is None or size > MAX_FRAME_BYTES:
                await self.close(code=CLOSE_TOO_BIG if size > MAX_FRAME_BYTES else CLOSE_POLICY)
            return  # after auth: drop junk frames
        kind = frame.get("type")
        if self.session is None:
            if kind != "auth":
                await self.close(code=CLOSE_POLICY)  # nothing before auth.ok
                return
            await self._authenticate(frame)
            return
        session = self.session
        await database_sync_to_async(services.mark_online)(session, self._connected_at)
        if kind == "call.dial.ack":
            await database_sync_to_async(services.apply_ack)(session, frame)
        elif kind == "call.status":
            await database_sync_to_async(services.apply_status)(session, frame)
        # "pong" (marker refreshed above), repeated "auth", unknown types: ignored.

    async def _authenticate(self, frame: dict[str, Any]) -> None:
        host = dict(self.scope.get("headers") or []).get(b"host", b"").decode(errors="replace")
        result = await database_sync_to_async(services.authenticate_socket)(
            frame.get("api_key"), frame.get("device_id"), host
        )
        if result is None:
            await database_sync_to_async(services.note_auth_failure)(self._ip)
            await self.send(text_data=json.dumps({"type": "auth.error", "reason": "invalid_token"}))
            await self.close(code=CLOSE_POLICY)
            return
        company_id, operator_id, device_id, hashed = result
        if self._auth_deadline is not None:
            self._auth_deadline.cancel()
        self.session = services.DeviceSession(
            company_id, operator_id, device_id, self.channel_name, hashed
        )
        self._connected_at = timezone.now().isoformat()
        self._groups = (
            services.group_name(company_id, operator_id, device_id),
            services.operator_group(company_id, operator_id),
            services.company_group(company_id),
        )
        for group in self._groups:
            await self.channel_layer.group_add(group, self.channel_name)
        await database_sync_to_async(services.mark_online)(self.session, self._connected_at)
        await self.send(text_data=json.dumps({"type": "auth.ok"}))
        self._pinger = asyncio.ensure_future(self._ping_loop())
        logger.info(
            "dial ws online company=%s operator=%s device=%s", company_id, operator_id, device_id
        )

    async def _ping_loop(self) -> None:
        while True:
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            session = self.session
            if session is None:
                return
            if not await database_sync_to_async(services.session_valid)(session):
                await self._revoked("recheck")
                return
            await self.send(text_data=json.dumps({"type": "ping", "ts": int(time.time())}))
            await database_sync_to_async(services.mark_online)(session, self._connected_at)

    async def _revoked(self, why: str) -> None:
        session = self.session
        if session is not None:
            logger.info(
                "dial ws revoked company=%s operator=%s device=%s via=%s",
                session.company_id,
                session.operator_id,
                session.device_id,
                why,
            )
        await self._leave()  # offline at once, before the close handshake
        await self.close(code=CLOSE_REVOKED)

    async def session_revoke(self, event: dict[str, Any]) -> None:
        """group_send({"type": "session.revoke"}) → close now."""
        await self._revoked("event")

    async def dial_command(self, event: dict[str, Any]) -> None:
        """group_send({"type": "dial.command", "payload": {call.dial …}})."""
        if self.session is not None:
            await self.send(text_data=json.dumps(event["payload"]))
