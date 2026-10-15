"""Bitrix24 per-operator user mapping: config validation, sender USER_ID,
users endpoint (pagination, suggestions, scope error)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, SimCard, User
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.integrations import providers
from apps.integrations.models import CrmIntegration

pytestmark = pytest.mark.django_db

URL = "/api/web/v1/settings/integrations/bitrix24"
HOOK = "https://b24.x.ru/rest/1/secrettok/"
REGISTERED = {"result": {"CALL_ID": "EC1", "CRM_ENTITY_TYPE": "LEAD", "CRM_ENTITY_ID": 42}}


@pytest.fixture
def bitrix(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="bitrix24",
        is_enabled=True,
        config={"webhook_url": HOOK, "user_id": "7"},
    )


def _op(company: Company, user_name: str, full_name: str, *phones: str) -> OperatorProfile:
    user = User.objects.create_user(username=f"{user_name}@{company.slug}", company=company)
    op = OperatorProfile.all_objects.create(
        company=company, user=user, user_name=user_name, full_name=full_name
    )
    for slot, number in enumerate(phones):
        SimCard.all_objects.create(company=company, operator=op, sim_slot=slot, number=number)
    return op


class FakeBitrix:
    """Records (method, payload); answers per method from queued bodies."""

    def __init__(self, **bodies: list[Any]) -> None:
        self.bodies = {k.replace("_", "."): list(v) for k, v in bodies.items()}
        self.calls: list[tuple[str, Any]] = []
        self.urls: list[str] = []

    def __call__(self, url: str, payload: Any = None, **_: Any) -> Any:
        method = url.rsplit("/", 1)[-1].removesuffix(".json")
        self.calls.append((method, payload))
        self.urls.append(url)
        body = self.bodies[method].pop(0)
        if isinstance(body, Exception):
            raise body
        return body


def _install(monkeypatch: pytest.MonkeyPatch, **bodies: list[Any]) -> FakeBitrix:
    fake = FakeBitrix(**bodies)
    monkeypatch.setattr(providers, "_http_json", fake)
    return fake


class TestUserMapConfig:
    def test_save_and_get_user_map(
        self, client: APIClient, bitrix: CrmIntegration, operator: OperatorProfile
    ) -> None:
        response = client.put(
            URL,
            {"config": {"user_map": {str(operator.pk): " 12 ", "": ""}}},
            format="json",
        )
        assert response.status_code == 200, response.content
        assert response.json()["integration"]["config"]["user_map"] == {str(operator.pk): "12"}
        bitrix.refresh_from_db()
        assert bitrix.config["user_map"] == {str(operator.pk): "12"}
        assert bitrix.config["user_id"] == "7"  # fallback untouched
        listing = client.get("/api/web/v1/settings/integrations").json()["integrations"]
        row = next(r for r in listing if r["provider"] == "bitrix24")
        assert row["config"]["user_map"] == {str(operator.pk): "12"}

    def test_empty_values_are_dropped(
        self, client: APIClient, bitrix: CrmIntegration, operator: OperatorProfile
    ) -> None:
        client.put(URL, {"config": {"user_map": {str(operator.pk): ""}}}, format="json")
        bitrix.refresh_from_db()
        assert bitrix.config["user_map"] == {}

    def test_unset_map_reads_as_empty_object(self, client: APIClient) -> None:
        listing = client.get("/api/web/v1/settings/integrations").json()["integrations"]
        assert next(r for r in listing if r["provider"] == "bitrix24")["config"]["user_map"] == {}

    @pytest.mark.parametrize(
        "user_map",
        [
            {"OP": "12"},
            {"999999": "12"},
            "not-an-object",
            ["1"],
        ],
    )
    def test_invalid_keys_rejected(
        self, client: APIClient, bitrix: CrmIntegration, user_map: Any
    ) -> None:
        response = client.put(URL, {"config": {"user_map": user_map}}, format="json")
        assert response.status_code == 400
        bitrix.refresh_from_db()
        assert "user_map" not in bitrix.config

    @pytest.mark.parametrize("value", ["abc", "0", "-3", "1.5", "12345678901"])
    def test_invalid_values_rejected(
        self,
        client: APIClient,
        bitrix: CrmIntegration,
        operator: OperatorProfile,
        value: str,
    ) -> None:
        response = client.put(
            URL, {"config": {"user_map": {str(operator.pk): value}}}, format="json"
        )
        assert response.status_code == 400

    def test_foreign_company_operator_rejected(
        self, client: APIClient, bitrix: CrmIntegration
    ) -> None:
        other = Company.objects.create(name="Other", slug="other-co")
        foreign = _op(other, "x", "X Y")
        response = client.put(URL, {"config": {"user_map": {str(foreign.pk): "5"}}}, format="json")
        assert response.status_code == 400
        assert str(foreign.pk) in response.json()["message"]


class TestSenderUser:
    def _config(self, operator: OperatorProfile, **extra: Any) -> dict[str, Any]:
        return {"webhook_url": HOOK, "user_id": "7", **extra}

    def test_mapped_operator_uses_mapped_user(
        self, call: CallRecord, operator: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _install(
            monkeypatch,
            telephony_externalcall_register=[REGISTERED],
            telephony_externalcall_finish=[{"result": True}],
        )
        config = self._config(operator, user_map={str(operator.pk): "21"})
        providers.send_call("bitrix24", config, call, None)
        assert [m for m, _ in fake.calls] == [
            "telephony.externalcall.register",
            "telephony.externalcall.finish",
        ]
        assert fake.calls[0][1]["USER_ID"] == 21 and fake.calls[1][1]["USER_ID"] == 21

    def test_unmapped_operator_uses_fallback(
        self, call: CallRecord, operator: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _install(
            monkeypatch,
            telephony_externalcall_register=[REGISTERED],
            telephony_externalcall_finish=[{"result": True}],
        )
        providers.send_call(
            "bitrix24", self._config(operator, user_map={"99999": "21"}), call, None
        )
        assert fake.calls[0][1]["USER_ID"] == 7 and fake.calls[1][1]["USER_ID"] == 7

    def test_no_user_id_defaults_to_1(
        self, call: CallRecord, operator: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _install(
            monkeypatch,
            telephony_externalcall_register=[REGISTERED],
            telephony_externalcall_finish=[{"result": True}],
        )
        providers.send_call("bitrix24", {"webhook_url": HOOK}, call, None)
        assert fake.calls[0][1]["USER_ID"] == 1

    def test_rejected_mapped_user_falls_back_once(
        self,
        call: CallRecord,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        fake = _install(
            monkeypatch,
            telephony_externalcall_register=[
                {"error": "ERROR_CORE", "error_description": "User not found"},
                REGISTERED,
            ],
            telephony_externalcall_finish=[{"result": True}],
        )
        config = self._config(operator, user_map={str(operator.pk): "21"})
        providers.send_call("bitrix24", config, call, None)  # no exception
        users = [p["USER_ID"] for _, p in fake.calls]
        assert users == [21, 7, 7]
        assert "mapped user 21 rejected" in caplog.text
        assert "secrettok" not in caplog.text

    def test_fallback_failure_still_raises(
        self, call: CallRecord, operator: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        error = {"error": "ERROR_CORE", "error_description": "boom"}
        _install(monkeypatch, telephony_externalcall_register=[error, error])
        config = self._config(operator, user_map={str(operator.pk): "21"})
        with pytest.raises(providers.ProviderError, match="boom"):
            providers.send_call("bitrix24", config, call, None)

    def test_dispatch_records_success_after_fallback(
        self,
        bitrix: CrmIntegration,
        call: CallRecord,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from apps.integrations import tasks

        bitrix.config = {**bitrix.config, "user_map": {str(operator.pk): "21"}}
        bitrix.save()
        call.audios.all().delete()  # no recording → register + finish only
        _install(
            monkeypatch,
            telephony_externalcall_register=[{"error": "USER_NOT_FOUND"}, REGISTERED],
            telephony_externalcall_finish=[{"result": True}],
        )
        assert tasks.dispatch_call(call.pk) == 1
        bitrix.refresh_from_db()
        assert bitrix.last_status == "ok" and bitrix.last_error == ""


def _user(uid: int, name: str, last: str, **extra: Any) -> dict[str, Any]:
    return {"ID": str(uid), "NAME": name, "LAST_NAME": last, **extra}


class TestUsersEndpoint:
    def test_lists_users_paginated_with_suggestions(
        self,
        client: APIClient,
        bitrix: CrmIntegration,
        company: Company,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        by_phone = _op(company, "ali", "Ali Valiyev", "+998901112233")
        by_name = _op(company, "dilnoza", "Dilnoza Karimova")
        reversed_name = _op(company, "bek", "Bek Tursunov")
        ambiguous = _op(company, "sardor", "Sardor Aliev")
        nothing = _op(company, "nobody", "No Match")
        page1 = [
            _user(
                1,
                "Boss",
                "Admin",
                EMAIL="boss@x.uz",
                WORK_POSITION="CEO",
                PERSONAL_MOBILE="90 111-22-33",  # Ali by phone, though name differs
            ),
            _user(2, "Dilnoza", "Karimova", WORK_PHONE="+998 93 000 00 00"),
        ]
        page2 = [
            _user(3, "TURSUNOV", "Bek"),  # last/first swapped, other case
            _user(4, "Sardor", "Aliev"),
            _user(5, "sardor", "aliev"),  # two Bitrix24 users with that name
        ]
        fake = _install(
            monkeypatch,
            user_get=[
                {"result": page1, "next": 2, "total": 5},
                {"result": page2, "total": 5},
            ],
        )
        body = client.get(f"{URL}/users").json()
        assert body["success"] is True
        assert [c[1]["start"] for c in fake.calls] == [0, 2]
        assert fake.calls[0][1]["FILTER"] == {"ACTIVE": True}
        assert [u["id"] for u in body["users"]] == ["1", "2", "3", "4", "5"]
        assert body["users"][0] == {
            "id": "1",
            "name": "Boss Admin",
            "email": "boss@x.uz",
            "phone": "90 111-22-33",
            "position": "CEO",
        }
        assert body["suggestions"] == {
            str(by_phone.pk): "1",
            str(by_name.pk): "2",
            str(reversed_name.pk): "3",
        }
        assert str(ambiguous.pk) not in body["suggestions"]
        assert str(nothing.pk) not in body["suggestions"]
        ops = {o["id"]: o for o in body["operators"]}
        assert ops[by_phone.pk] == {
            "id": by_phone.pk,
            "full_name": "Ali Valiyev",
            "user_name": "ali",
            "phones": ["+998901112233"],
        }
        assert "secrettok" not in json.dumps(body)

    def test_same_phone_on_two_operators_is_ambiguous(
        self,
        client: APIClient,
        bitrix: CrmIntegration,
        company: Company,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _op(company, "a", "A A", "+998901112233")
        _op(company, "b", "B B", "+998901112233")
        _install(monkeypatch, user_get=[{"result": [_user(1, "X", "Y", WORK_PHONE="901112233")]}])
        assert client.get(f"{URL}/users").json()["suggestions"] == {}

    def test_phone_uses_company_code(
        self,
        client: APIClient,
        bitrix: CrmIntegration,
        company: Company,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        company.phone_code = "992"
        company.save()
        op = _op(company, "tj", "Tj Op", "+992921234567")
        _install(
            monkeypatch, user_get=[{"result": [_user(8, "Q", "W", PERSONAL_MOBILE="921234567")]}]
        )
        assert client.get(f"{URL}/users").json()["suggestions"] == {str(op.pk): "8"}

    def test_cap_stops_paging(
        self, client: APIClient, bitrix: CrmIntegration, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pages = [
            {
                "result": [_user(n * 50 + i + 1, "U", str(n * 50 + i)) for i in range(50)],
                "next": (n + 1) * 50,
            }
            for n in range(12)
        ]
        fake = _install(monkeypatch, user_get=pages)
        body = client.get(f"{URL}/users").json()
        assert len(body["users"]) == providers.B24_USERS_CAP
        assert len(fake.calls) == providers.B24_USERS_CAP // 50

    def test_scope_error_returns_operators(
        self,
        client: APIClient,
        bitrix: CrmIntegration,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install(
            monkeypatch,
            user_get=[
                {
                    "error": "insufficient_scope",
                    "error_description": "The request requires higher privileges",
                }
            ],
        )
        response = client.get(f"{URL}/users")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert "«user»" in body["error"]
        assert [o["id"] for o in body["operators"]] == [operator.pk]
        assert "users" not in body and "secrettok" not in json.dumps(body)

    def test_http_error_is_reported_without_webhook(
        self,
        client: APIClient,
        bitrix: CrmIntegration,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _install(monkeypatch, user_get=[providers.ProviderError("connection failed: timeout")])
        body = client.get(f"{URL}/users").json()
        assert body["success"] is False and "timeout" in body["error"]
        assert "secrettok" not in json.dumps(body)

    def test_not_configured_400(self, client: APIClient) -> None:
        assert client.get(f"{URL}/users").status_code == 400

    def test_admin_only(self, company: Company, bitrix: CrmIntegration) -> None:
        member = User.objects.create_user(username="m@integr-co.uz", company=company)
        api = APIClient()
        api.force_authenticate(user=member)
        assert api.get(f"{URL}/users").status_code == 403

    def test_tenant_isolation(
        self,
        client: APIClient,
        bitrix: CrmIntegration,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        other = Company.objects.create(name="Other", slug="other-co")
        foreign = _op(other, "spy", "Op One", "+998901112233")
        CrmIntegration.all_objects.create(
            company=other,
            provider="bitrix24",
            config={"webhook_url": "https://other.b24/rest/9/othertok/"},
        )
        fake = _install(monkeypatch, user_get=[{"result": [_user(1, "Op", "One")]}])
        body = client.get(f"{URL}/users").json()
        assert [o["id"] for o in body["operators"]] == [operator.pk]
        assert foreign.pk not in [o["id"] for o in body["operators"]]
        assert body["suggestions"] == {str(operator.pk): "1"}
        assert fake.urls and all(u.startswith(HOOK.rstrip("/")) for u in fake.urls)
