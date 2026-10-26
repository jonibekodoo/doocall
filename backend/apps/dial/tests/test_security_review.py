"""Security review of f1ff7e2: revoked phones are disconnected (Medium),
device takeover (Low), exact national length (Low), failed-login limit
per IP (Low)."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile
from apps.companies.models import Company
from apps.dial import consumers, services
from apps.dial.models import DialCommand

from .test_remote_dial import APP, DIAL, WS, connect, post, run

pytestmark = pytest.mark.django_db(transaction=True)

DEVICE_A = "aaaa1111bbbb2222"


async def close_code(ws: WebsocketCommunicator, timeout: float = 3) -> int | None:
    """Next close code, skipping pings."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        output = await ws.receive_output(timeout=timeout)
        if output["type"] == "websocket.close":
            return int(output.get("code") or 1000)
    return None


def _online(op: OperatorProfile) -> bool:
    return services.online(op.company_id, DEVICE_A) is not None


class TestRevocation:
    """Medium: access withdrawn after login closes the socket (4001)."""

    @pytest.mark.parametrize("change", ["deactivate", "rotate", "suspend", "trial_expired"])
    def test_ping_recheck_closes_without_any_event(
        self,
        op_a: OperatorProfile,
        company: Company,
        monkeypatch: pytest.MonkeyPatch,
        change: str,
    ) -> None:
        monkeypatch.setattr(consumers, "PING_INTERVAL_SECONDS", 0.05)

        def withdraw() -> None:  # .update(): no signals → only the re-check catches it
            if change == "deactivate":
                OperatorProfile.all_objects.filter(pk=op_a.pk).update(is_active=False)
            elif change == "rotate":
                OperatorProfile.all_objects.filter(pk=op_a.pk).update(api_key="rotated-key")
            elif change == "suspend":
                Company.objects.filter(pk=company.pk).update(status=Company.Status.SUSPENDED)
            else:
                Company.objects.filter(pk=company.pk).update(
                    status=Company.Status.TRIAL, trial_ends_at=timezone.now() - timedelta(days=1)
                )

        async def scenario() -> None:
            ws = await connect(op_a)
            await database_sync_to_async(withdraw)()
            assert await close_code(ws) == consumers.CLOSE_REVOKED
            assert not await database_sync_to_async(_online)(op_a)

        run(scenario)

    @pytest.mark.parametrize("change", ["rotate", "deactivate", "delete", "suspend"])
    def test_save_paths_kick_immediately(
        self, op_a: OperatorProfile, company: Company, change: str
    ) -> None:
        def withdraw() -> None:  # real save()/delete() paths → signals
            if change == "rotate":
                op = OperatorProfile.all_objects.get(pk=op_a.pk)
                op.api_key = "new-key-xyz"
                op.save(update_fields=["api_key"])
            elif change == "deactivate":
                op = OperatorProfile.all_objects.get(pk=op_a.pk)
                op.is_active = False
                op.save()
            elif change == "delete":
                OperatorProfile.all_objects.get(pk=op_a.pk).user.delete()
            else:
                fresh = Company.objects.get(pk=company.pk)
                fresh.status = Company.Status.SUSPENDED
                fresh.save()

        async def scenario() -> None:
            ws = await connect(op_a)  # default 25 s ping: only the event can close it
            await database_sync_to_async(withdraw)()
            assert await close_code(ws, timeout=2) == consumers.CLOSE_REVOKED

        run(scenario)

    def test_unrelated_saves_do_not_kick(self, op_a: OperatorProfile, company: Company) -> None:
        def harmless() -> None:
            op = OperatorProfile.all_objects.get(pk=op_a.pk)
            op.full_name = "Ali Renamed"
            op.save()
            fresh = Company.objects.get(pk=company.pk)
            fresh.name = "Dial Co 2"
            fresh.save()

        async def scenario() -> None:
            ws = await connect(op_a)
            await database_sync_to_async(harmless)()
            assert await ws.receive_nothing(timeout=0.3)
            await ws.disconnect()

        run(scenario)

    def test_dial_revalidates_target_before_sending(
        self, op_a: OperatorProfile, admin_client: APIClient
    ) -> None:
        async def scenario() -> None:
            ws = await connect(op_a)
            # Key rotated without a signal and before the next ping.
            await database_sync_to_async(
                lambda: OperatorProfile.all_objects.filter(pk=op_a.pk).update(api_key="rotated")
            )()
            response = await post(
                admin_client, DIAL, {"device_id": DEVICE_A, "number": "+998901234567"}
            )
            assert response.status_code == 409 and response.json()["status"] == "offline"
            # Never dialled; the stale socket is kicked instead.
            assert await close_code(ws, timeout=2) == consumers.CLOSE_REVOKED

        run(scenario)

    def test_dial_refused_when_company_trial_expired(
        self, op_a: OperatorProfile, company: Company, admin_client: APIClient
    ) -> None:
        # The instance the authenticated admin holds (requests load it fresh).
        company.status = Company.Status.TRIAL
        company.trial_ends_at = timezone.now() - timedelta(days=1)
        company.save()
        response = admin_client.post(
            DIAL, {"device_id": DEVICE_A, "number": "+998901234567"}, format="json"
        )
        assert response.status_code == 402
        assert response.json()["error_code"] == "subscription_inactive"


class TestDeviceTakeover:
    """Low: another operator of the company can't hijack a phone's channel."""

    def test_second_operator_cannot_claim_a_live_device(
        self, op_a: OperatorProfile, op_b: OperatorProfile
    ) -> None:
        async def scenario() -> None:
            ws_a = await connect(op_a)
            ws_b = WebsocketCommunicator(APP, WS, headers=[(b"host", b"api.doocall.local")])
            await ws_b.connect()
            await ws_b.send_json_to(
                {"type": "auth", "api_key": op_b.api_key, "device_id": DEVICE_A}
            )
            assert await ws_b.receive_json_from() == {
                "type": "auth.error",
                "reason": "invalid_token",
            }
            marker = await database_sync_to_async(services.online)(op_a.company_id, DEVICE_A)
            assert marker and marker["operator_id"] == op_a.pk  # claim untouched
            await ws_a.disconnect()

        run(scenario)

    def test_acks_must_come_from_the_addressed_operator(
        self, op_a: OperatorProfile, op_b: OperatorProfile, admin_client: APIClient
    ) -> None:
        async def scenario() -> None:
            ws_a = await connect(op_a)
            cid = (
                await post(admin_client, DIAL, {"device_id": DEVICE_A, "number": "+998901234567"})
            ).json()["command_id"]
            await ws_a.receive_json_from()
            await ws_a.disconnect()
            # op_b now logs in on that phone and forges a status for op_a's command.
            ws_b = await connect(op_b, DEVICE_A)
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
            await asyncio.sleep(0.3)
            status = await database_sync_to_async(
                lambda: DialCommand.all_objects.get(pk=cid).status
            )()
            assert status == "sent"
            await ws_b.disconnect()

        run(scenario)

    def test_dial_goes_only_to_the_logged_in_operator_group(
        self, op_a: OperatorProfile, op_b: OperatorProfile, admin_client: APIClient
    ) -> None:
        assert services.group_name(1, op_a.pk, DEVICE_A) != services.group_name(
            1, op_b.pk, DEVICE_A
        )


class TestNationalLength:
    """Low: exact national length for the destination country."""

    @pytest.mark.parametrize(
        "raw",
        ["+99890123456", "+9989012345678", "+7701234567", "+770123456789", "+9921234567"],
    )
    def test_wrong_length_rejected(
        self, op_a: OperatorProfile, admin_client: APIClient, raw: str
    ) -> None:
        response = admin_client.post(DIAL, {"device_id": DEVICE_A, "number": raw}, format="json")
        assert response.status_code == 400 and response.json()["error_code"] == "invalid_number"

    @pytest.mark.parametrize(
        "raw", ["+998901234567", "+77012345678", "+99312345678", "+992921234567"]
    )
    def test_exact_length_accepted(
        self, op_a: OperatorProfile, admin_client: APIClient, raw: str
    ) -> None:
        response = admin_client.post(DIAL, {"device_id": DEVICE_A, "number": raw}, format="json")
        assert response.status_code == 409  # offline, number accepted


class TestFailedAuthLimit:
    """Low: failed socket logins per IP — over the limit the handshake is refused."""

    def test_limit_blocks_new_sockets_from_that_ip(
        self, op_a: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(services, "AUTH_FAIL_LIMIT", 2)
        attacker = [(b"host", b"api.doocall.local"), (b"x-real-ip", b"203.0.113.9")]
        other = [(b"host", b"api.doocall.local"), (b"x-real-ip", b"198.51.100.7")]

        async def scenario() -> None:
            for _ in range(2):
                ws = WebsocketCommunicator(APP, WS, headers=attacker)
                await ws.connect()
                await ws.send_json_to({"type": "auth", "api_key": "guess", "device_id": "d1"})
                assert (await ws.receive_json_from())["type"] == "auth.error"
                await ws.disconnect()
            blocked = WebsocketCommunicator(APP, WS, headers=attacker)
            connected, _ = await blocked.connect()
            assert connected is False
            fine = WebsocketCommunicator(APP, WS, headers=other)
            connected, _ = await fine.connect()
            assert connected is True
            await fine.disconnect()

        run(scenario)

    def test_auth_timeout_counts_as_failure(
        self, op_a: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consumers, "AUTH_TIMEOUT_SECONDS", 0.05)
        headers = [(b"host", b"api.doocall.local"), (b"x-real-ip", b"203.0.113.10")]

        async def scenario() -> None:
            ws = WebsocketCommunicator(APP, WS, headers=headers)
            await ws.connect()
            assert await close_code(ws) == consumers.CLOSE_AUTH_TIMEOUT

        run(scenario)
        assert services.client_ip({"headers": headers}) == "203.0.113.10"
        assert int(cache.get("dial:wsfail:203.0.113.10")) == 1

    def test_client_ip_falls_back_to_peer(self) -> None:
        scope: dict[str, Any] = {"headers": [], "client": ("10.1.2.3", 5555)}
        assert services.client_ip(scope) == "10.1.2.3"
