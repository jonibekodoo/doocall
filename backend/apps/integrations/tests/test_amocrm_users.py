"""amoCRM per-operator manager mapping: config validation, sender
responsible_user_id (+ fallback on reject), users endpoint."""

from __future__ import annotations

import json
from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import OperatorProfile, SimCard, User
from apps.calls.models import CallRecord
from apps.companies.models import Company
from apps.integrations import providers, tasks
from apps.integrations.models import CrmIntegration

pytestmark = pytest.mark.django_db

URL = "/api/web/v1/settings/integrations/amocrm"
BASE = "https://acme.amocrm.ru"
TOKEN = "amo-secret-token-123456"
LANDED = {"_embedded": {"calls": [{"id": 1, "entity_id": 77}]}}


@pytest.fixture
def amo(company: Company) -> CrmIntegration:
    return CrmIntegration.all_objects.create(
        company=company,
        provider="amocrm",
        is_enabled=True,
        config={"base_url": BASE, "access_token": TOKEN, "responsible_user_id": "500"},
    )


def _op(company: Company, user_name: str, full_name: str, email: str = "") -> OperatorProfile:
    user = User.objects.create_user(
        username=f"{user_name}@{company.slug}", email=email, company=company
    )
    op = OperatorProfile.all_objects.create(
        company=company, user=user, user_name=user_name, full_name=full_name
    )
    SimCard.all_objects.create(company=company, operator=op, sim_slot=0, number="+998901110000")
    return op


class FakeAmo:
    """Queue of responses per path ("/api/v4/calls", …); Exception → raised."""

    def __init__(self, **queues: list[Any]) -> None:
        self.queues = {f"/api/v4/{k}": list(v) for k, v in queues.items()}
        self.calls: list[tuple[str, Any, Any]] = []

    def __call__(self, url: str, payload: Any = None, *, headers: Any = None, **_: Any) -> Any:
        path = url.removeprefix(BASE).split("?", 1)[0]
        self.calls.append((url, payload, headers))
        body = self.queues[path].pop(0)
        if isinstance(body, Exception):
            raise body
        return body

    def payloads(self, path: str) -> list[Any]:
        return [p for u, p, _ in self.calls if u.removeprefix(BASE).startswith(f"/api/v4/{path}")]


def _install(monkeypatch: pytest.MonkeyPatch, **queues: list[Any]) -> FakeAmo:
    fake = FakeAmo(**queues)
    monkeypatch.setattr(providers, "_http_json", fake)
    return fake


def _config(**extra: Any) -> dict[str, Any]:
    return {"base_url": BASE, "access_token": TOKEN, "responsible_user_id": "500", **extra}


class TestSender:
    def test_mapped_operator_is_responsible(
        self, call: CallRecord, operator: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _install(monkeypatch, calls=[LANDED])
        providers.send_call("amocrm", _config(user_map={str(operator.pk): "21"}), call, None)
        assert fake.payloads("calls")[0][0]["responsible_user_id"] == 21

    def test_unmapped_operator_uses_fallback(
        self, call: CallRecord, operator: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _install(monkeypatch, calls=[LANDED])
        providers.send_call("amocrm", _config(user_map={"99999": "21"}), call, None)
        assert fake.payloads("calls")[0][0]["responsible_user_id"] == 500

    def test_no_responsible_at_all_omits_field(
        self, call: CallRecord, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _install(monkeypatch, calls=[LANDED])
        providers.send_call("amocrm", {"base_url": BASE, "access_token": TOKEN}, call, None)
        assert "responsible_user_id" not in fake.payloads("calls")[0][0]

    def test_contact_creation_uses_mapped_user(
        self, call: CallRecord, operator: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        not_landed = {"errors": [{"detail": "Entity not found"}], "_embedded": {"calls": []}}
        fake = _install(
            monkeypatch,
            calls=[not_landed, LANDED],
            contacts=[{"_embedded": {"contacts": [{"id": 9}]}}],
        )
        providers.send_call("amocrm", _config(user_map={str(operator.pk): "21"}), call, None)
        assert fake.payloads("contacts")[0][0]["responsible_user_id"] == 21
        assert [p[0]["responsible_user_id"] for p in fake.payloads("calls")] == [21, 21]

    def test_rejected_mapped_user_falls_back_once(
        self,
        call: CallRecord,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        reject = providers.ProviderError(
            "HTTP 400: Bad Request; responsible_user_id: NotSupportedChoice"
        )
        fake = _install(monkeypatch, calls=[reject, LANDED])
        providers.send_call("amocrm", _config(user_map={str(operator.pk): "21"}), call, None)
        assert [p[0]["responsible_user_id"] for p in fake.payloads("calls")] == [21, 500]
        assert "mapped user 21 rejected" in caplog.text and TOKEN not in caplog.text

    def test_other_errors_are_not_retried(
        self, call: CallRecord, operator: OperatorProfile, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install(monkeypatch, calls=[providers.ProviderError("HTTP 401")])
        with pytest.raises(providers.ProviderError, match="401"):
            providers.send_call("amocrm", _config(user_map={str(operator.pk): "21"}), call, None)

    def test_validation_error_summary_names_the_field(self) -> None:
        body = {
            "title": "Bad Request",
            "validation-errors": [
                {
                    "request_id": "0",
                    "errors": [{"code": "NotSupportedChoice", "path": "responsible_user_id"}],
                }
            ],
        }
        summary = providers._error_summary(json.dumps(body).encode())
        assert "responsible_user_id: NotSupportedChoice" in summary

    def test_dispatch_succeeds_after_fallback(
        self,
        amo: CrmIntegration,
        call: CallRecord,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        amo.config = {**amo.config, "user_map": {str(operator.pk): "21"}}
        amo.save()
        reject = providers.ProviderError("HTTP 400: responsible_user_id: NotSupportedChoice")
        _install(monkeypatch, calls=[reject, LANDED])
        assert tasks.dispatch_call(call.pk) == 1
        amo.refresh_from_db()
        assert amo.last_status == "ok"


class TestUserMapConfig:
    def test_save_and_get(
        self, client: APIClient, amo: CrmIntegration, operator: OperatorProfile
    ) -> None:
        response = client.put(
            URL, {"config": {"user_map": {str(operator.pk): " 21 ", "": ""}}}, format="json"
        )
        assert response.status_code == 200, response.content
        assert response.json()["integration"]["config"]["user_map"] == {str(operator.pk): "21"}
        amo.refresh_from_db()
        assert amo.config["user_map"] == {str(operator.pk): "21"}
        assert amo.config["responsible_user_id"] == "500"
        # Omitted → kept.
        client.put(URL, {"config": {"responsible_user_id": "501"}}, format="json")
        amo.refresh_from_db()
        assert amo.config["user_map"] == {str(operator.pk): "21"}

    @pytest.mark.parametrize("user_map", [{"999999": "1"}, {"x": "1"}, "nope"])
    def test_invalid_keys(self, client: APIClient, amo: CrmIntegration, user_map: Any) -> None:
        assert client.put(URL, {"config": {"user_map": user_map}}, format="json").status_code == 400

    @pytest.mark.parametrize("value", ["abc", "0", "-1", "1.5"])
    def test_invalid_values(
        self, client: APIClient, amo: CrmIntegration, operator: OperatorProfile, value: str
    ) -> None:
        response = client.put(
            URL, {"config": {"user_map": {str(operator.pk): value}}}, format="json"
        )
        assert response.status_code == 400

    def test_foreign_operator_rejected(self, client: APIClient, amo: CrmIntegration) -> None:
        other = Company.objects.create(name="Other", slug="other-co")
        foreign = _op(other, "spy", "Spy")
        response = client.put(URL, {"config": {"user_map": {str(foreign.pk): "5"}}}, format="json")
        assert response.status_code == 400


def _amo_user(
    uid: int, name: str, email: str = "", *, active: bool = True, role: str | None = None
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": uid, "name": name, "email": email, "rights": {"is_active": active}}
    if role:
        row["_embedded"] = {"roles": [{"id": 1, "name": role}]}
    return row


class TestUsersEndpoint:
    def test_pagination_and_suggestions(
        self,
        client: APIClient,
        amo: CrmIntegration,
        company: Company,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        by_email = _op(company, "ali", "Somebody Else", "ali@acme.uz")
        by_name = _op(company, "dilnoza", "Dilnoza Karimova")
        reversed_name = _op(company, "bek", "Bek Tursunov")
        ambiguous = _op(company, "sardor", "Sardor Aliev")
        page1 = {
            "_links": {"next": {"href": "https://evil.example/api/v4/users?page=2"}},
            "_embedded": {
                "users": [
                    _amo_user(1, "Ali V", "ALI@acme.uz", role="Menejer"),
                    _amo_user(2, "dilnoza karimova"),
                    _amo_user(9, "Gone User", active=False),
                ]
            },
        }
        page2 = {
            "_embedded": {
                "users": [
                    _amo_user(3, "Tursunov Bek"),
                    _amo_user(4, "Sardor Aliev"),
                    _amo_user(5, "Sardor Aliev"),
                    {"id": "6", "name": "string id"},
                    {"id": True, "name": "bool id"},
                ]
            }
        }
        fake = _install(monkeypatch, users=[page1, page2])
        body = client.get(f"{URL}/users").json()
        assert body["success"] is True
        urls = [u for u, _, _ in fake.calls]
        assert urls == [
            f"{BASE}/api/v4/users?limit=250&page=1&with=role",
            f"{BASE}/api/v4/users?limit=250&page=2&with=role",
        ]  # never the _links.next host
        assert fake.calls[0][2] == {"Authorization": f"Bearer {TOKEN}"}
        assert [u["id"] for u in body["users"]] == ["1", "2", "3", "4", "5"]
        assert body["users"][0] == {
            "id": "1",
            "name": "Ali V",
            "email": "ALI@acme.uz",
            "phone": None,
            "position": "Menejer",
        }
        assert body["suggestions"] == {
            str(by_email.pk): "1",
            str(by_name.pk): "2",
            str(reversed_name.pk): "3",
        }
        assert str(ambiguous.pk) not in body["suggestions"]
        op_row = next(o for o in body["operators"] if o["id"] == by_email.pk)
        assert op_row == {
            "id": by_email.pk,
            "full_name": "Somebody Else",
            "user_name": "ali",
            "phones": ["+998901110000"],
        }
        assert TOKEN not in json.dumps(body)

    def test_stops_when_no_next(
        self, client: APIClient, amo: CrmIntegration, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _install(monkeypatch, users=[{"_embedded": {"users": [_amo_user(1, "A")]}}])
        client.get(f"{URL}/users")
        assert len(fake.calls) == 1

    def test_paging_is_bounded(
        self, client: APIClient, amo: CrmIntegration, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        page = {"_links": {"next": {}}, "_embedded": {"users": [_amo_user(1, "A")]}}
        fake = _install(monkeypatch, users=[page] * 10)
        client.get(f"{URL}/users")
        assert len(fake.calls) == providers.AMO_USERS_MAX_PAGES

    @pytest.mark.parametrize("code", [401, 403])
    def test_auth_error_returns_operators(
        self,
        client: APIClient,
        amo: CrmIntegration,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
        code: int,
    ) -> None:
        _install(monkeypatch, users=[providers.ProviderError(f"HTTP {code}")])
        response = client.get(f"{URL}/users")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is False
        assert body["error"].startswith("amoCRM foydalanuvchilar ro'yxatini olib bo'lmadi")
        assert [o["id"] for o in body["operators"]] == [operator.pk]
        assert "users" not in body and TOKEN not in json.dumps(body)

    def test_non_object_body_is_an_error(
        self, client: APIClient, amo: CrmIntegration, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install(monkeypatch, users=[["not", "an", "object"]])
        assert client.get(f"{URL}/users").json()["success"] is False

    def test_not_configured_400(self, client: APIClient) -> None:
        assert client.get(f"{URL}/users").status_code == 400

    def test_admin_only(self, company: Company, amo: CrmIntegration) -> None:
        member = User.objects.create_user(username="m@integr-co.uz", company=company)
        api = APIClient()
        api.force_authenticate(user=member)
        assert api.get(f"{URL}/users").status_code == 403

    def test_tenant_isolation(
        self,
        client: APIClient,
        amo: CrmIntegration,
        operator: OperatorProfile,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        other = Company.objects.create(name="Other", slug="other-co")
        foreign = _op(other, "x", "Op One")
        CrmIntegration.all_objects.create(
            company=other,
            provider="amocrm",
            config={"base_url": "https://other.amocrm.ru", "access_token": "othertoken"},
        )
        fake = _install(monkeypatch, users=[{"_embedded": {"users": [_amo_user(1, "Op One")]}}])
        body = client.get(f"{URL}/users").json()
        assert [o["id"] for o in body["operators"]] == [operator.pk]
        assert foreign.pk not in [o["id"] for o in body["operators"]]
        assert body["suggestions"] == {str(operator.pk): "1"}
        assert all(u.startswith(BASE) for u, _, _ in fake.calls)
