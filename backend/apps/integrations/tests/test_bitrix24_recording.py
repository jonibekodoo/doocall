"""Bitrix24 recordings: sent as FILE_CONTENT; .ogg/.m4a transcoded to mp3 so
the call player shows; RECORD_URL / timeline-comment fallbacks."""

from __future__ import annotations

import base64
import logging
import shutil
from pathlib import Path
from typing import Any

import pytest

from apps.calls.models import CallRecord
from apps.core import audio as audio_tools
from apps.integrations import providers
from apps.integrations.providers import _read_audio as real_read_audio

from .test_bitrix24_cards import HOOK, Bitrix

pytestmark = pytest.mark.django_db

ATTACH = "telephony.externalcall.attachrecord"
COMMENT = "crm.timeline.comment.add"
REC_URL = "https://integr-co.doocall.uz/api/public/rec/abc?sig=def"


@pytest.fixture
def b24(monkeypatch: pytest.MonkeyPatch) -> Bitrix:
    fake = Bitrix()
    monkeypatch.setattr(providers, "_http_json", fake)
    return fake


def _bytes(monkeypatch: pytest.MonkeyPatch, data: bytes = b"OggS-raw-audio") -> list[str]:
    keys: list[str] = []

    def read(object_key: str) -> bytes:
        keys.append(object_key)
        return data

    monkeypatch.setattr(providers, "_read_audio", read)
    return keys


def _send(call: CallRecord) -> None:
    providers.send_call(
        "bitrix24",
        {"webhook_url": HOOK, "user_id": "7", "create_card": "none"},
        call,
        REC_URL,
    )


def _attached(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage().split("attached=")[1]
        for r in caplog.records
        if r.getMessage().startswith("bitrix24 record ")
    ]


def test_ogg_is_transcoded_and_sent_as_file_content(
    b24: Bitrix, call: CallRecord, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    keys = _bytes(monkeypatch)
    seen: list[tuple[bytes, str]] = []

    def fake_playable(data: bytes, src_ext: str = "") -> tuple[bytes, str]:
        seen.append((data, src_ext))
        return b"ID3-mp3-bytes", "mp3"

    monkeypatch.setattr(audio_tools, "playable", fake_playable)
    with caplog.at_level(logging.INFO, logger="apps.integrations.providers"):
        _send(call)
    assert keys == [call.audios.get().object_key]
    assert seen == [(b"OggS-raw-audio", "ogg")]
    attach = b24.payload(ATTACH)
    assert attach["FILENAME"] == f"doocall-{call.server_id.hex}.mp3"
    assert base64.b64decode(attach["FILE_CONTENT"]) == b"ID3-mp3-bytes"
    assert "RECORD_URL" not in attach
    assert COMMENT not in b24.methods()
    assert _attached(caplog) == ["mp3"]


def test_transcode_failure_falls_back_to_comment(
    b24: Bitrix, call: CallRecord, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _bytes(monkeypatch)

    def broken(data: bytes, src_ext: str = "") -> tuple[bytes, str]:
        raise audio_tools.AudioError("transcode failed (source ogg)")

    monkeypatch.setattr(audio_tools, "playable", broken)
    with caplog.at_level(logging.INFO, logger="apps.integrations.providers"):
        _send(call)
    assert ATTACH not in b24.methods()  # an .ogg is never sent by URL
    assert REC_URL in b24.payload(COMMENT)["fields"]["COMMENT"]
    assert _attached(caplog) == ["comment"]
    warning = next(r.getMessage() for r in caplog.records if "not attached" in r.getMessage())
    assert "AudioError" in warning and "http" not in warning and "998" not in warning


def test_wav_passthrough(b24: Bitrix, call: CallRecord, monkeypatch: pytest.MonkeyPatch) -> None:
    call.audios.update(filename="rec.wav")
    _bytes(monkeypatch, b"RIFF-wav")
    monkeypatch.setattr(audio_tools, "playable", lambda data, ext="": (data, "wav"))
    _send(call)
    attach = b24.payload(ATTACH)
    assert attach["FILENAME"].endswith(".wav")
    assert base64.b64decode(attach["FILE_CONTENT"]) == b"RIFF-wav"


def test_mp3_file_content_rejected_falls_back_to_record_url(
    b24: Bitrix, call: CallRecord, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    call.audios.update(filename="rec.mp3")
    _bytes(monkeypatch, b"ID3")
    monkeypatch.setattr(audio_tools, "playable", lambda data, ext="": (data, "mp3"))
    b24.fail[ATTACH] = 1
    with caplog.at_level(logging.INFO, logger="apps.integrations.providers"):
        _send(call)
    attaches = [p for m, p in b24.calls if m == ATTACH]
    assert "FILE_CONTENT" in attaches[0]
    assert attaches[1]["RECORD_URL"] == REC_URL and attaches[1]["FILENAME"].endswith(".mp3")
    assert _attached(caplog) == ["mp3"]


def test_storage_failure_mp3_uses_record_url_ogg_uses_comment(
    b24: Bitrix, call: CallRecord
) -> None:
    # Default test stub: object storage unavailable.
    _send(call)
    assert ATTACH not in b24.methods() and COMMENT in b24.methods()

    call.audios.update(filename="rec.mp3")
    b24.calls.clear()
    _send(call)
    assert b24.payload(ATTACH)["RECORD_URL"] == REC_URL


def test_no_entity_and_no_attach_reports_none(call: CallRecord) -> None:
    assert (
        providers._b24_attach_recording({"webhook_url": HOOK}, {"CALL_ID": "EC1"}, call, REC_URL)
        == "none"
    )


def test_no_audio_row_reports_comment_or_none(b24: Bitrix, call: CallRecord) -> None:
    call.audios.all().delete()
    assert (
        providers._b24_attach_recording(
            {"webhook_url": HOOK}, {"CALL_ID": "EC1", "CRM_ENTITY_ID": 4}, call, REC_URL
        )
        == "comment"
    )


class _Response:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.closed = self.released = False

    def read(self, amount: int) -> bytes:
        return self.data[:amount]

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


def test_read_audio_caps_size_and_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api import storage

    big = _Response(b"x" * 50)
    monkeypatch.setattr(audio_tools, "MAX_INPUT_BYTES", 10)

    class Client:
        def get_object(self, bucket: str, key: str) -> Any:
            return big

    monkeypatch.setattr(storage, "client", lambda: Client())
    with pytest.raises(providers.AudioReadError, match="larger than"):
        real_read_audio("1/c-1/primary/rec.ogg")
    assert big.closed and big.released

    small = _Response(b"OggS")
    monkeypatch.setattr(Client, "get_object", lambda self, b, k: small)
    assert real_read_audio("k") == b"OggS"


def test_read_audio_error_hides_details(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api import storage

    class Client:
        def get_object(self, bucket: str, key: str) -> Any:
            raise RuntimeError(f"S3 error for {key} at http://minio:9000")

    monkeypatch.setattr(storage, "client", lambda: Client())
    with pytest.raises(providers.AudioReadError) as exc:
        real_read_audio("1/1724495961-998901234567/primary/rec.ogg")
    assert str(exc.value) == "RuntimeError"


@pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="ffmpeg not installed",
)
def test_real_ogg_end_to_end(
    b24: Bitrix, call: CallRecord, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from apps.core.tests.test_audio import make_audio

    _bytes(monkeypatch, make_audio(tmp_path, "libopus", "ogg"))
    _send(call)
    mp3 = base64.b64decode(b24.payload(ATTACH)["FILE_CONTENT"])
    assert audio_tools.probe_format(mp3) == "mp3"
