"""Mobile APK release pipeline: admin upload → public latest/download."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.core.models import AppRelease
from apps.partners.models import Integrator

from .conftest import client_for

pytestmark = pytest.mark.django_db

FAKE_APK = b"PK\x03\x04" + b"\x00" * 512  # apk = zip container


def _upload(client: APIClient, version: str = "1.0.0", **extra: object):
    return client.post(
        "/api/admin/v1/app-releases",
        {
            "version": version,
            "notes": "test build",
            "file": SimpleUploadedFile(
                f"doocall-{version}.apk",
                FAKE_APK,
                content_type="application/vnd.android.package-archive",
            ),
            **extra,
        },
        format="multipart",
    )


class TestAppReleases:
    def test_upload_list_latest_download(self, platform_admin: User) -> None:
        client = client_for(platform_admin)
        created = _upload(client)
        assert created.status_code == 201

        listing = client.get("/api/admin/v1/app-releases").json()
        assert listing["releases"][0]["version"] == "1.0.0"
        assert listing["releases"][0]["size_bytes"] == len(FAKE_APK)

        public = APIClient().get("/api/public/app/latest").json()
        assert public["release"]["version"] == "1.0.0"

        download = APIClient().get("/api/public/app/download")
        assert download.status_code == 302
        assert "app-releases/doocall-1.0.0.apk" in download["Location"]

    def test_latest_is_newest(self, platform_admin: User) -> None:
        client = client_for(platform_admin)
        assert _upload(client, "1.0.0").status_code == 201
        assert _upload(client, "1.1.0").status_code == 201
        public = APIClient().get("/api/public/app/latest").json()
        assert public["release"]["version"] == "1.1.0"

    def test_validation(self, platform_admin: User) -> None:
        client = client_for(platform_admin)
        assert _upload(client, "2.0.0").status_code == 201
        # duplicate version
        assert _upload(client, "2.0.0").status_code == 400
        # wrong extension
        bad = client.post(
            "/api/admin/v1/app-releases",
            {"version": "2.1.0", "file": SimpleUploadedFile("app.exe", FAKE_APK)},
            format="multipart",
        )
        assert bad.status_code == 400
        # missing file
        assert (
            client.post(
                "/api/admin/v1/app-releases", {"version": "2.2.0"}, format="multipart"
            ).status_code
            == 400
        )

    def test_delete_superadmin_only(self, superadmin: User, platform_admin: User) -> None:
        client = client_for(platform_admin)
        release_id = _upload(client, "3.0.0").json()["release"]["id"]

        assert client.delete(f"/api/admin/v1/app-releases/{release_id}").status_code == 403
        assert (
            client_for(superadmin).delete(f"/api/admin/v1/app-releases/{release_id}").status_code
            == 200
        )
        assert not AppRelease.objects.filter(pk=release_id).exists()

    def test_public_empty_state(self, db: object) -> None:
        assert APIClient().get("/api/public/app/latest").json()["release"] is None
        assert APIClient().get("/api/public/app/download").status_code == 404

    def test_upload_requires_staff(self, integrator: Integrator) -> None:
        assert _upload(client_for(integrator.user), "9.9.9").status_code == 403
