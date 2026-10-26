"""Remote Dial: device WebSocket (auth, frames, ack/status) + cabinet API."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Device, OperatorProfile, User
from apps.companies.models import Company
from apps.core.models import AuditLog
from apps.dial import consumers, services
from apps.dial.models import DialCommand
from apps.dial.routing import websocket_urlpatterns

from .conftest import client_for, make_operator

# Consumers use database_sync_to_async, which closes non-autocommit
# connections (close_old_connections) — so no wrapping test transaction.
pytestmark = pytest.mark.django_db(transaction=True)

APP = URLRouter(websocket_urlpatterns)
WS = "/api/call/v1/ws"
DIAL = "/api/web/v1/dial"


def run(scenario: Callable[[], Awaitable[None]]) -> None:
    async_to_sync(scenario)()


def socket(host: bytes = b"api.doocall.local") -> WebsocketCommunicator:
    return WebsocketCommunicator(APP, WS, headers=[(b"host", host)])


async def connect(op: OperatorProfile, device_id: str | None = None) -> WebsocketCommunicator:
    ws = socket()
    connected, _ = await ws.connect()
    assert connected
    await ws.send_json_to(
        {"type": "auth", "api_key": op.api_key, "device_id": device_id or await _device(op)}
    )
    assert await ws.receive_json_from() == {"type": "auth.ok"}
    return ws


@database_sync_to_async
def _device(op: OperatorProfile) -> str:
    return str(Device.all_objects.filter(operator=op).values_list("device_id", flat=True).first())


async def post(client: APIClient, path: str, body: dict[str, Any] | None = None) -> Any:
    return await database_sync_to_async(client.post)(path, body or {}, format="json")


async def get(client: APIClient, path: str) -> Any:
    return await database_sync_to_async(client.get)(path)


async def settle(client: APIClient, cid: str, status: str) -> dict[str, Any]:
    """Frames are handled asynchronously by the consumer: poll the API."""
    detail: dict[str, Any] = {}
    for _ in range(100):
        detail = (await get(client, f"{DIAL}/{cid}")).json()["command"]
        if detail["status"] == status:
            return detail
        await asyncio.sleep(0.02)
    return detail


async def closed(ws: WebsocketCommunicator) -> bool:
    output = await ws.receive_output(timeout=2)
    return bool(output["type"] == "websocket.close")


# ── WebSocket auth ────────────────────────────────────────────────────────
class TestSocketAuth:
    def test_auth_ok_marks_online(self, op_a: OperatorProfile) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            marker = services.online(op_a.company_id, "aaaa1111bbbb2222")
            assert marker and marker["operator_id"] == op_a.pk and marker["channel"]
            assert marker["connected_at"] and marker["last_seen"]
            await ws.disconnect()
            assert services.online(op_a.company_id, "aaaa1111bbbb2222") is None

        run(scenario)

    @pytest.mark.parametrize(
        "frame",
        [
            {"type": "auth", "api_key": "wrong", "device_id": "x1"},
            {"type": "auth", "device_id": "x1"},
            {"type": "auth", "api_key": "key-ali", "device_id": "!!!"},
        ],
    )
    def test_auth_error_then_close(self, op_a: OperatorProfile, frame: dict[str, Any]) -> None:
        async def scenario() -> None:
            ws = socket()
            await ws.connect()
            await ws.send_json_to(frame)
            assert await ws.receive_json_from() == {"type": "auth.error", "reason": "invalid_token"}
            assert await closed(ws)

        run(scenario)

    def test_suspended_company_is_refused(self, op_a: OperatorProfile, company: Company) -> None:
        Company.objects.filter(pk=company.pk).update(status=Company.Status.SUSPENDED)

        async def scenario() -> None:
            ws = socket()
            await ws.connect()
            await ws.send_json_to({"type": "auth", "api_key": op_a.api_key, "device_id": "d1"})
            assert (await ws.receive_json_from())["type"] == "auth.error"

        run(scenario)

    def test_portal_host_is_refused(self, op_a: OperatorProfile, settings: Any) -> None:
        settings.DOMAIN_ROOT, settings.DOMAIN_APP = "doocall.uz", "app.doocall.uz"

        async def scenario() -> None:
            ws = socket(b"app.doocall.uz")
            await ws.connect()
            await ws.send_json_to({"type": "auth", "api_key": op_a.api_key, "device_id": "d1"})
            assert (await ws.receive_json_from())["type"] == "auth.error"

        run(scenario)

    def test_auth_timeout_closes(
        self, op_a: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consumers, "AUTH_TIMEOUT_SECONDS", 0.05)

        async def scenario() -> None:
            ws = socket()
            await ws.connect()
            output = await ws.receive_output(timeout=2)
            assert output == {"type": "websocket.close", "code": consumers.CLOSE_AUTH_TIMEOUT}

        run(scenario)

    @pytest.mark.parametrize(
        "frame",
        [
            json.dumps({"type": "pong", "ts": 1}),
            json.dumps({"type": "call.dial.ack", "command_id": "x", "status": "received"}),
            "not json",
            json.dumps(["auth"]),
            json.dumps({"type": "auth", "api_key": "x" * 9000, "device_id": "d"}),
        ],
    )
    def test_anything_before_auth_closes(self, op_a: OperatorProfile, frame: str) -> None:
        async def scenario() -> None:
            ws = socket()
            await ws.connect()
            await ws.send_to(text_data=frame)
            assert await closed(ws)

        run(scenario)

    def test_auth_creates_unknown_device_row(self, op_a: OperatorProfile) -> None:
        async def scenario() -> None:
            ws = await connect(op_a, "newphone0000ffff")
            await ws.disconnect()

        run(scenario)
        assert Device.all_objects.filter(operator=op_a, device_id="newphone0000ffff").exists()

    def test_old_connection_does_not_clear_new_marker(self, op_a: OperatorProfile) -> None:
        async def scenario() -> None:
            first = await connect(op_a)
            second = await connect(op_a)  # reconnect before the old socket closed
            await first.disconnect()
            marker = services.online(op_a.company_id, "aaaa1111bbbb2222")
            assert marker is not None
            await second.disconnect()
            assert services.online(op_a.company_id, "aaaa1111bbbb2222") is None

        run(scenario)

    def test_ping_loop_sends_ping(
        self, op_a: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consumers, "PING_INTERVAL_SECONDS", 0.05)

        async def scenario() -> None:
            ws = await connect(op_a)
            ping = await ws.receive_json_from(timeout=2)
            assert ping["type"] == "ping" and isinstance(ping["ts"], int)
            await ws.send_json_to({"type": "pong", "ts": ping["ts"]})
            await ws.send_json_to({"type": "something.new"})  # unknown → ignored
            await ws.disconnect()

        run(scenario)


# ── Dial end-to-end ───────────────────────────────────────────────────────
class TestDial:
    def test_online_dial_ack_and_status(
        self, op_a: OperatorProfile, admin_client: APIClient, admin: User
    ) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            response = await post(
                admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "90 123-45-67"}
            )
            assert response.status_code == 200
            body = response.json()
            assert body["success"] is True and body["status"] == "sent"
            frame = await ws.receive_json_from()
            assert frame["type"] == "call.dial"
            assert frame["command_id"] == body["command_id"]
            assert frame["number"] == "+998901234567"
            assert frame["issued_at"].endswith("Z")
            assert set(frame) == {
                "type",
                "command_id",
                "number",
                "issued_at",
                "requested_by",
            }  # no sim_slot
            assert frame["requested_by"] == "boss@dial-co.uz"

            cid = body["command_id"]
            await ws.send_json_to(
                {
                    "type": "call.dial.ack",
                    "command_id": cid,
                    "status": "received",
                    "sim_mode": "auto",
                    "used_sim_slot": 0,
                }
            )
            await ws.send_json_to({"type": "call.status", "command_id": cid, "state": "dialing"})
            await ws.send_json_to({"type": "call.status", "command_id": cid, "state": "active"})
            await ws.send_json_to(
                {
                    "type": "call.status",
                    "command_id": cid,
                    "state": "disconnected",
                    "duration_sec": 42,
                    "cause": "answered",
                }
            )
            await ws.send_json_to(
                {"type": "call.status", "command_id": cid, "state": "dialing"}
            )  # late: ignored
            await ws.send_json_to({"type": "pong", "ts": 1})
            detail = await settle(admin_client, cid, "disconnected")
            await asyncio.sleep(0.2)  # the late "dialing" frame must not regress it
            detail = (await get(admin_client, f"{DIAL}/{cid}")).json()["command"]
            assert detail["status"] == "disconnected"
            assert detail["sim_mode"] == "auto" and detail["used_sim_slot"] == 0
            assert detail["duration_sec"] == 42 and detail["cause"] == "answered"
            assert detail["acked_at"] and detail["operator"] == {"id": op_a.pk, "full_name": "Ali"}
            await ws.disconnect()

        run(scenario)
        log = AuditLog.objects.get(action="dial.requested")
        assert log.actor == admin and log.changes["number"] == "+998901234567"

    def test_rejected_ack(self, op_a: OperatorProfile, admin_client: APIClient) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            cid = (
                await post(
                    admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
                )
            ).json()["command_id"]
            await ws.receive_json_from()
            await ws.send_json_to(
                {
                    "type": "call.dial.ack",
                    "command_id": cid,
                    "status": "rejected",
                    "reason": "sim_disabled",
                }
            )
            await ws.send_json_to({"type": "call.status", "command_id": cid, "state": "dialing"})
            await ws.send_json_to({"type": "pong"})
            await settle(admin_client, cid, "rejected")
            await asyncio.sleep(0.2)
            detail = (await get(admin_client, f"{DIAL}/{cid}")).json()["command"]
            assert detail["status"] == "rejected" and detail["reject_reason"] == "sim_disabled"
            await ws.disconnect()

        run(scenario)

    def test_acks_only_touch_own_device_commands(
        self, op_a: OperatorProfile, op_b: OperatorProfile, admin_client: APIClient
    ) -> None:
        async def scenario() -> None:
            ws_a = await connect(op_a)
            ws_b = await connect(op_b)
            cid = (
                await post(
                    admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
                )
            ).json()["command_id"]
            assert (await ws_a.receive_json_from())["command_id"] == cid
            assert await ws_b.receive_nothing(timeout=0.2)  # only the target device
            await ws_b.send_json_to(
                {
                    "type": "call.dial.ack",
                    "command_id": cid,
                    "status": "rejected",
                    "reason": "duplicate",
                }
            )
            await ws_b.send_json_to(
                {"type": "call.status", "command_id": cid, "state": "disconnected"}
            )
            await ws_b.send_json_to({"type": "pong"})
            await asyncio.sleep(0.3)
            assert (await get(admin_client, f"{DIAL}/{cid}")).json()["command"]["status"] == "sent"
            await ws_a.disconnect()
            await ws_b.disconnect()

        run(scenario)

    def test_cross_company_isolation(self, op_a: OperatorProfile, admin_client: APIClient) -> None:
        other = Company.objects.create(name="Other", slug="other-co", status=Company.Status.ACTIVE)
        intruder = make_operator(other, "spy", "aaaa1111bbbb2222")  # same device id!
        other_admin = User.objects.create_user(
            username="x@other", company=other, is_company_admin=True
        )

        async def scenario() -> None:
            ws_a = await connect(op_a)
            ws_x = await connect(intruder)
            cid = (
                await post(
                    admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
                )
            ).json()["command_id"]
            await ws_a.receive_json_from()
            assert await ws_x.receive_nothing(timeout=0.2)
            await ws_x.send_json_to(
                {"type": "call.dial.ack", "command_id": cid, "status": "rejected"}
            )
            await ws_x.send_json_to({"type": "pong"})
            await asyncio.sleep(0.3)
            assert (await get(admin_client, f"{DIAL}/{cid}")).json()["command"]["status"] == "sent"
            assert (await get(client_for(other_admin), f"{DIAL}/{cid}")).status_code == 404
            await ws_a.disconnect()
            await ws_x.disconnect()

        run(scenario)

    def test_offline_dial_is_409_and_not_queued(
        self, op_a: OperatorProfile, admin_client: APIClient
    ) -> None:
        async def scenario() -> None:
            response = await post(
                admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
            )
            assert response.status_code == 409
            body = response.json()
            assert body == {
                "success": False,
                "error_code": "device_offline",
                "command_id": body["command_id"],
                "status": "offline",
            }
            ws = await connect(op_a)  # coming online later must NOT dial
            assert await ws.receive_nothing(timeout=0.2)
            await ws.disconnect()

        run(scenario)
        assert DialCommand.all_objects.get().status == "offline"

    def test_operator_can_only_dial_own_device(
        self, op_a: OperatorProfile, op_b: OperatorProfile
    ) -> None:
        async def scenario() -> None:
            ws_a = await connect(op_a)
            ws_b = await connect(op_b)
            client_a = client_for(op_a.user)
            other = await post(
                client_a, DIAL, {"device_id": "cccc3333dddd4444", "number": "+998901234567"}
            )
            assert other.status_code == 403 and other.json()["error_code"] == "forbidden"
            own = await post(
                client_a, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
            )
            assert own.status_code == 200
            assert (await ws_a.receive_json_from())["type"] == "call.dial"
            assert await ws_b.receive_nothing(timeout=0.2)
            await ws_a.disconnect()
            await ws_b.disconnect()

        run(scenario)

    def test_member_without_operator_cannot_dial(
        self, op_a: OperatorProfile, company: Company
    ) -> None:
        member = User.objects.create_user(username="m@dial-co", company=company)
        response = client_for(member).post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}, format="json"
        )
        assert response.status_code == 403

    def test_unknown_device_404(self, op_a: OperatorProfile, admin_client: APIClient) -> None:
        response = admin_client.post(
            DIAL, {"device_id": "nope", "number": "+998901234567"}, format="json"
        )
        assert response.status_code == 404 and response.json()["error_code"] == "device_not_found"


class TestValidationAndLimits:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("901234567", "+998901234567"),
            ("+998 90 123 45 67", "+998901234567"),
            ("998901234567", "+998901234567"),
            ("*100#", None),
            ("#31#901234567", None),
            ("2212345", None),
            ("1234", None),
            ("", None),
            ("+12", None),
        ],
    )
    def test_number_normalization(
        self, op_a: OperatorProfile, admin_client: APIClient, raw: str, expected: str | None
    ) -> None:
        response = admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": raw}, format="json"
        )
        if expected is None:
            assert response.status_code == 400 and response.json()["error_code"] == "invalid_number"
        else:
            assert response.status_code == 409  # offline, but the number was accepted
            assert DialCommand.all_objects.get().number == expected

    def test_company_phone_code(
        self, op_a: OperatorProfile, admin_client: APIClient, company: Company
    ) -> None:
        company.phone_code = "992"
        company.save()
        admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": "921234567"}, format="json"
        )
        assert DialCommand.all_objects.get().number == "+992921234567"

    def test_device_rate_limit(self, op_a: OperatorProfile, admin_client: APIClient) -> None:
        body = {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
        assert admin_client.post(DIAL, body, format="json").status_code == 409
        again = admin_client.post(DIAL, body, format="json")
        assert again.status_code == 429 and again.json()["error_code"] == "rate_limited"
        # 30/hour per device.
        DialCommand.all_objects.update(created_at=timezone.now() - timedelta(minutes=10))
        for _ in range(19):
            DialCommand.all_objects.create(
                company=op_a.company,
                device_id="aaaa1111bbbb2222",
                number="+998901234567",
                status="offline",
            )
        DialCommand.all_objects.update(created_at=timezone.now() - timedelta(minutes=10))
        assert admin_client.post(DIAL, body, format="json").status_code == 429

    def test_user_rate_limit(
        self, op_a: OperatorProfile, op_b: OperatorProfile, admin_client: APIClient
    ) -> None:
        assert (
            admin_client.post(
                DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}, format="json"
            ).status_code
            == 409
        )
        other_device = admin_client.post(
            DIAL, {"device_id": "cccc3333dddd4444", "number": "+998901234567"}, format="json"
        )
        assert other_device.status_code == 429  # same admin, < 2 s

    def test_idempotency_key_dedupes(self, op_a: OperatorProfile, admin_client: APIClient) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            body = {
                "device_id": "aaaa1111bbbb2222",
                "number": "+998901234567",
                "idempotency_key": "click-1",
            }
            first = (await post(admin_client, DIAL, body)).json()
            second = (await post(admin_client, DIAL, body)).json()
            assert first["command_id"] == second["command_id"]
            await ws.receive_json_from()
            assert await ws.receive_nothing(timeout=0.2)  # dialled once
            await ws.disconnect()

        run(scenario)
        assert DialCommand.all_objects.count() == 1

    def test_failed_attempt_does_not_block_retry_with_same_key(
        self, op_a: OperatorProfile, admin_client: APIClient
    ) -> None:
        bad = {"device_id": "aaaa1111bbbb2222", "number": "*100#", "idempotency_key": "k"}
        assert admin_client.post(DIAL, bad, format="json").status_code == 400
        good = {**bad, "number": "+998901234567"}
        assert admin_client.post(DIAL, good, format="json").status_code == 409  # offline, accepted

    def test_expiry_and_late_ack(self, op_a: OperatorProfile, admin_client: APIClient) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            cid = (
                await post(
                    admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
                )
            ).json()["command_id"]
            await ws.receive_json_from()
            await database_sync_to_async(
                lambda: DialCommand.all_objects.filter(pk=cid).update(
                    created_at=timezone.now() - timedelta(seconds=61)
                )
            )()
            assert (await get(admin_client, f"{DIAL}/{cid}")).json()["command"][
                "status"
            ] == "expired"
            await ws.send_json_to(
                {
                    "type": "call.dial.ack",
                    "command_id": cid,
                    "status": "received",
                    "sim_mode": "device_picker",
                    "used_sim_slot": None,
                }
            )
            detail = await settle(admin_client, cid, "received")
            assert detail["status"] == "received" and detail["used_sim_slot"] is None
            await ws.disconnect()

        run(scenario)


class TestDevicesList:
    def test_admin_sees_all_operator_sees_own(
        self,
        op_a: OperatorProfile,
        op_b: OperatorProfile,
        admin_client: APIClient,
        company: Company,
    ) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            rows = (await get(admin_client, f"{DIAL}/devices")).json()["devices"]
            by_id = {r["device_id"]: r for r in rows}
            assert by_id["aaaa1111bbbb2222"]["online"] is True
            assert by_id["cccc3333dddd4444"]["online"] is False
            assert by_id["aaaa1111bbbb2222"]["operator"] == {"id": op_a.pk, "full_name": "Ali"}
            assert by_id["aaaa1111bbbb2222"]["model"] == "Samsung A54"
            assert by_id["aaaa1111bbbb2222"]["last_seen"]
            own = (await get(client_for(op_b.user), f"{DIAL}/devices")).json()["devices"]
            assert [r["device_id"] for r in own] == ["cccc3333dddd4444"]
            await ws.disconnect()

        run(scenario)
        member = User.objects.create_user(username="m2@dial-co", company=company)
        assert client_for(member).get(f"{DIAL}/devices").json()["devices"] == []

    def test_device_logged_in_as_other_operator_is_not_online_for_old_owner(
        self, op_a: OperatorProfile, op_b: OperatorProfile, admin_client: APIClient
    ) -> None:
        async def scenario() -> None:
            ws = await connect(op_b, "aaaa1111bbbb2222")  # op_b logs in on op_a's phone
            rows = (await get(admin_client, f"{DIAL}/devices")).json()["devices"]
            online = {(r["device_id"], r["operator"]["id"]): r["online"] for r in rows}
            assert online[("aaaa1111bbbb2222", op_a.pk)] is False
            assert online[("aaaa1111bbbb2222", op_b.pk)] is True
            await ws.disconnect()

        run(scenario)


class TestHardening:
    """Defence in depth against USSD/MMI, pauses and premium/foreign numbers."""

    @pytest.mark.parametrize(
        "raw",
        [
            "*100#",
            "*#21#",
            "#31#901234567",
            "*#06#",
            "**21*901234567#",
            "901234567,1234",  # pause + DTMF
            "901234567;1234",
            "+998901234567p123",
            "+998901234567w",
            "90123456a",
            "call me",
            "1234",  # short code
            "0800",
            "+998",
            "1234567890123456",  # 16 digits
            "++998901234567",
            "+998 90 123 45 67 ext 5",
        ],
    )
    def test_rejected_inputs(
        self, op_a: OperatorProfile, admin_client: APIClient, raw: str
    ) -> None:
        response = admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": raw}, format="json"
        )
        assert response.status_code == 400, raw
        body = response.json()
        assert body["error_code"] == "invalid_number"
        assert body["message"] == services.INVALID_NUMBER_MESSAGE
        assert not DialCommand.all_objects.exists()

    @pytest.mark.parametrize(
        "raw",
        ["+447911123456", "+12025550123", "+8613800138000", "+22512345678", "+3712345678"],
    )
    def test_foreign_destinations_blocked(
        self, op_a: OperatorProfile, admin_client: APIClient, raw: str
    ) -> None:
        response = admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": raw}, format="json"
        )
        assert response.status_code == 400
        body = response.json()
        assert body["error_code"] == "destination_not_allowed"
        assert body["message"] == "Bu yo'nalishga masofaviy qo'ng'iroq ruxsat etilmagan"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("(90) 123-45-67", "+998901234567"),
            ("+998 90 123 45 67", "+998901234567"),
            ("+992 92 123 4567", "+992921234567"),  # TJ in the default allowlist
            ("+996555123456", "+996555123456"),
            ("+77012345678", "+77012345678"),
            ("+99312345678", "+99312345678"),
        ],
    )
    def test_allowed_destinations(
        self, op_a: OperatorProfile, admin_client: APIClient, raw: str, expected: str
    ) -> None:
        response = admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": raw}, format="json"
        )
        assert response.status_code == 409  # offline — but the number was accepted
        assert DialCommand.all_objects.get().number == expected

    def test_tj_company_local_number(
        self, op_a: OperatorProfile, admin_client: APIClient, company: Company
    ) -> None:
        company.phone_code = "992"
        company.save()
        admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": "92 123 45 67"}, format="json"
        )
        assert DialCommand.all_objects.get().number == "+992921234567"

    def test_empty_allowlist_means_company_code_only(
        self, op_a: OperatorProfile, admin_client: APIClient, settings: Any
    ) -> None:
        settings.DIAL_ALLOWED_CODES = ""
        tj = admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+992921234567"}, format="json"
        )
        assert tj.json()["error_code"] == "destination_not_allowed"
        uz = admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}, format="json"
        )
        assert uz.status_code == 409

    def test_allowlist_override_from_env(
        self, op_a: OperatorProfile, admin_client: APIClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIAL_ALLOWED_CODES", "44")
        assert services.allowed_codes("998") == {"44", "998"}
        uk = admin_client.post(
            DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+447911123456"}, format="json"
        )
        assert uk.status_code == 409

    @pytest.mark.parametrize(
        "reason", ["user_declined", "timeout", "expired", "rate_limited", "feature_disabled"]
    )
    def test_new_reject_reasons_are_stored(
        self, op_a: OperatorProfile, admin_client: APIClient, reason: str
    ) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            cid = (
                await post(
                    admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
                )
            ).json()["command_id"]
            await ws.receive_json_from()
            await ws.send_json_to(
                {"type": "call.dial.ack", "command_id": cid, "status": "rejected", "reason": reason}
            )
            detail = await settle(admin_client, cid, "rejected")
            assert detail["reject_reason"] == reason
            await ws.disconnect()

        run(scenario)

    def test_unknown_reason_is_stored_as_unknown(
        self, op_a: OperatorProfile, admin_client: APIClient
    ) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            cid = (
                await post(
                    admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
                )
            ).json()["command_id"]
            await ws.receive_json_from()
            await ws.send_json_to(
                {
                    "type": "call.dial.ack",
                    "command_id": cid,
                    "status": "rejected",
                    "reason": "<script>",
                }
            )
            detail = await settle(admin_client, cid, "rejected")
            assert detail["reject_reason"] == "unknown"
            await ws.disconnect()

        run(scenario)

    def test_requested_by_uses_full_name(
        self, op_a: OperatorProfile, admin: User, admin_client: APIClient
    ) -> None:
        admin.first_name, admin.last_name = "Jonibek", "Yorqulov"
        admin.save()

        async def scenario() -> None:
            ws = await connect(op_a)
            await post(
                admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
            )
            assert (await ws.receive_json_from())["requested_by"] == "Jonibek Yorqulov"
            await ws.disconnect()

        run(scenario)


class TestMobile1161:
    """Contract of mobile 1.16.1: confirmation before the ack, issued_at,
    requested_by, device-side rate limit."""

    def test_awaiting_confirmation_stays_sent_until_60s(
        self, op_a: OperatorProfile, admin_client: APIClient
    ) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            cid = (
                await post(
                    admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
                )
            ).json()["command_id"]
            await ws.receive_json_from()

            def age(seconds: int) -> None:
                DialCommand.all_objects.filter(pk=cid).update(
                    created_at=timezone.now() - timedelta(seconds=seconds)
                )

            await database_sync_to_async(age)(45)  # operator still deciding
            assert (await get(admin_client, f"{DIAL}/{cid}")).json()["command"]["status"] == "sent"
            # Confirmed at 45 s → the ack still counts.
            await ws.send_json_to(
                {
                    "type": "call.dial.ack",
                    "command_id": cid,
                    "status": "received",
                    "sim_mode": "auto",
                    "used_sim_slot": 1,
                }
            )
            assert (await settle(admin_client, cid, "received"))["used_sim_slot"] == 1
            await ws.disconnect()

        run(scenario)

    def test_issued_at_is_fresh_utc(self, op_a: OperatorProfile, admin_client: APIClient) -> None:
        from datetime import UTC, datetime

        async def scenario() -> None:
            ws = await connect(op_a)
            await post(
                admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
            )
            frame = await ws.receive_json_from()
            issued = datetime.strptime(frame["issued_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            assert abs((timezone.now() - issued).total_seconds()) < 5
            await ws.disconnect()

        run(scenario)

    def test_requested_by_is_plain_and_capped(
        self, op_a: OperatorProfile, admin: User, admin_client: APIClient
    ) -> None:
        admin.first_name = "Ali\n\t<b>Boss</b>" + "x" * 80
        admin.last_name = ""
        admin.save()

        async def scenario() -> None:
            ws = await connect(op_a)
            await post(
                admin_client, DIAL, {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
            )
            name = (await ws.receive_json_from())["requested_by"]
            assert "\n" not in name and "\t" not in name and len(name) <= 64
            assert name.startswith("Ali <b>Boss</b>")  # plain text; the app renders it as text
            await ws.disconnect()

        run(scenario)

    def test_device_limit_matches_the_phone(
        self, op_a: OperatorProfile, admin_client: APIClient
    ) -> None:
        body = {"device_id": "aaaa1111bbbb2222", "number": "+998901234567"}
        assert admin_client.post(DIAL, body, format="json").status_code == 409
        DialCommand.all_objects.update(created_at=timezone.now() - timedelta(seconds=7))
        assert admin_client.post(DIAL, body, format="json").status_code == 429  # < 10 s
        DialCommand.all_objects.update(created_at=timezone.now() - timedelta(seconds=11))
        assert admin_client.post(DIAL, body, format="json").status_code == 409
