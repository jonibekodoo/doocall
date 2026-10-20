"""apps.core.audio: format probing + ffmpeg transcode to MP3."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from apps.core import audio

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


def make_audio(tmp_path: Path, codec: str, fmt: str) -> bytes:
    """One second of a 440 Hz tone in the given codec/container."""
    out = tmp_path / f"tone.{fmt}"
    subprocess.run(  # noqa: S603 - test helper, fixed args
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:a",
            codec,
            "-f",
            fmt,
            "-y",
            str(out),
        ],
        check=True,
        timeout=60,
    )
    return out.read_bytes()


@needs_ffmpeg
class TestRealFfmpeg:
    def test_ogg_becomes_mp3(self, tmp_path: Path) -> None:
        ogg = make_audio(tmp_path, "libopus", "ogg")
        assert audio.probe_format(ogg) == "ogg"
        data, ext = audio.playable(ogg, "ogg")
        assert ext == "mp3" and audio.probe_format(data) == "mp3"

    def test_m4a_named_ogg_is_detected_and_transcoded(self, tmp_path: Path) -> None:
        m4a = make_audio(tmp_path, "aac", "ipod")  # .m4a container
        assert audio.probe_format(m4a) == "mov"  # "mov,mp4,m4a,…"
        data, ext = audio.playable(m4a, "ogg")  # mislabelled
        assert ext == "mp3" and audio.probe_format(data) == "mp3"

    def test_wav_and_mp3_pass_through_untouched(self, tmp_path: Path) -> None:
        wav = make_audio(tmp_path, "pcm_s16le", "wav")
        assert audio.playable(wav, "wav") == (wav, "wav")
        mp3 = make_audio(tmp_path, "libmp3lame", "mp3")
        assert audio.playable(mp3, "bin") == (mp3, "mp3")

    def test_mp3_output_is_mono_22k(self, tmp_path: Path) -> None:
        data = audio.to_mp3(make_audio(tmp_path, "libopus", "ogg"))
        src = tmp_path / "out.mp3"
        src.write_bytes(data)
        probe = subprocess.run(  # noqa: S603 - test helper
            [
                shutil.which("ffprobe") or "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=channels,sample_rate",
                "-of",
                "default=nw=1",
                str(src),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "channels=1" in probe and "sample_rate=22050" in probe

    def test_garbage_is_rejected(self) -> None:
        with pytest.raises(audio.AudioError):
            audio.playable(b"definitely not audio" * 100, "ogg")


class TestGuards:
    def test_size_guard_runs_no_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(audio, "MAX_INPUT_BYTES", 10)

        def no_run(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("ffmpeg must not run")

        monkeypatch.setattr(subprocess, "run", no_run)
        with pytest.raises(audio.AudioError, match="larger than"):
            audio.to_mp3(b"x" * 11)
        with pytest.raises(audio.AudioError, match="larger than"):
            audio.probe_format(b"x" * 11)

    def test_empty_input(self) -> None:
        with pytest.raises(audio.AudioError, match="empty"):
            audio.to_mp3(b"")

    def test_timeout_is_an_audio_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(audio, "_binary", lambda name: f"/usr/bin/{name}")

        def slow(args: list[str], **kwargs: Any) -> Any:
            assert kwargs["timeout"] == audio.TIMEOUT_SECONDS
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])

        monkeypatch.setattr(subprocess, "run", slow)
        with pytest.raises(audio.AudioError, match="timed out"):
            audio.to_mp3(b"abc")

    def test_missing_binary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda name: None)
        with pytest.raises(audio.AudioError, match="not installed"):
            audio.to_mp3(b"abc")

    def test_locked_down_args_no_shell_bytes_via_private_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        runs: list[tuple[list[str], dict[str, Any]]] = []
        monkeypatch.setattr(audio, "_binary", lambda name: f"/usr/bin/{name}")

        def fake_run(args: list[str], **kwargs: Any) -> Any:
            runs.append((args, kwargs))
            src = Path(args[-1] if args[0].endswith("ffprobe") else args[args.index("-i") + 1])
            runs[-1][1]["_mode"] = oct(src.parent.stat().st_mode & 0o777)
            runs[-1][1]["_input"] = src.read_bytes()
            if args[0].endswith("ffprobe"):
                probe = {"format": {"format_name": "ogg"}, "streams": [{"codec_type": "audio"}]}
                return subprocess.CompletedProcess(args, 0, json.dumps(probe).encode(), b"")
            Path(args[-1]).write_bytes(b"ID3fake")
            return subprocess.CompletedProcess(args, 0, b"", b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert audio.to_mp3(b"; rm -rf / #", "ogg") == b"ID3fake"
        (probe_args, probe_kw), (ff_args, ff_kw) = runs
        assert probe_args[0] == "/usr/bin/ffprobe" and ff_args[0] == "/usr/bin/ffmpeg"
        for args, kwargs in runs:
            assert "shell" not in kwargs
            assert kwargs["env"] == {"PATH": os.defpath, "LC_ALL": "C"}
            assert kwargs["preexec_fn"] is audio._limit_child
            assert kwargs["_input"] == b"; rm -rf / #"  # bytes only ever go to the file
            assert kwargs["_mode"] == "0o700"
            wl = args.index("-protocol_whitelist")
            assert args[wl + 1] == "file"
            fw = args.index("-format_whitelist")
            assert args[fw + 1] == audio.FORMAT_WHITELIST
            assert "hls" not in args[fw + 1] and "dash" not in args[fw + 1]
        # The probed container is forced before -i (no re-detection).
        assert ff_args[ff_args.index("-i") - 2 : ff_args.index("-i")] == ["-f", "ogg"]
        assert ff_args.index("-protocol_whitelist") < ff_args.index("-i")
        assert ff_args[ff_args.index("-fs") + 1] == str(audio.MAX_OUTPUT_BYTES)
        assert "-nostdin" in ff_args
        assert ff_args[ff_args.index("-ac") : ff_args.index("-ac") + 2] == ["-ac", "1"]
        assert "64k" in ff_args

    @pytest.mark.parametrize(
        ("probe", "message"),
        [
            (
                {"format": {"format_name": "hls"}, "streams": [{"codec_type": "audio"}]},
                "unsupported",
            ),
            (
                {"format": {"format_name": "image2"}, "streams": [{"codec_type": "video"}]},
                "unsupported",
            ),
            ({"format": {"format_name": "ogg"}, "streams": [{"codec_type": "video"}]}, "no audio"),
            ({"format": {"format_name": "ogg"}, "streams": []}, "no audio"),
        ],
    )
    def test_probe_result_must_be_allowed_audio(
        self, monkeypatch: pytest.MonkeyPatch, probe: dict[str, Any], message: str
    ) -> None:
        monkeypatch.setattr(audio, "_binary", lambda name: f"/usr/bin/{name}")
        calls: list[str] = []

        def fake_run(args: list[str], **kwargs: Any) -> Any:
            calls.append(args[0])
            return subprocess.CompletedProcess(args, 0, json.dumps(probe).encode(), b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(audio.AudioError, match=message):
            audio.playable(b"bytes", "ogg")
        assert calls == ["/usr/bin/ffprobe"]  # ffmpeg never runs

    def test_output_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(audio, "_binary", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(audio, "MAX_OUTPUT_BYTES", 4)

        def fake_run(args: list[str], **kwargs: Any) -> Any:
            if args[0].endswith("ffprobe"):
                probe = {"format": {"format_name": "ogg"}, "streams": [{"codec_type": "audio"}]}
                return subprocess.CompletedProcess(args, 0, json.dumps(probe).encode(), b"")
            Path(args[-1]).write_bytes(b"ID3-way-too-long")
            return subprocess.CompletedProcess(args, 0, b"", b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(audio.AudioError, match="too large"):
            audio.to_mp3(b"x")


# ── Hostile inputs: playlist/manifest demuxers must never run ─────────────
class _Canary(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        _Canary.hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def canary() -> Iterator[str]:
    _Canary.hits = []
    httpd = HTTPServer(("127.0.0.1", 0), _Canary)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def _hostile(url: str) -> dict[str, bytes]:
    return {
        "dash": (
            '<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" '
            'mediaPresentationDuration="PT1S"><Period><AdaptationSet><Representation id="1" '
            f'bandwidth="1" mimeType="audio/mp4"><BaseURL>{url}/dash.m4s</BaseURL>'
            "</Representation></AdaptationSet></Period></MPD>"
        ).encode(),
        "dash_file": (
            b'<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static">'
            b'<Period><AdaptationSet><Representation id="1" bandwidth="1">'
            b"<BaseURL>file:///etc/passwd</BaseURL></Representation></AdaptationSet>"
            b"</Period></MPD>"
        ),
        "hls": (
            f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\n{url}/seg.ts\n#EXT-X-ENDLIST\n"
        ).encode(),
        "hls_local": b"#EXTM3U\n#EXTINF:1,\n/etc/passwd\n#EXT-X-ENDLIST\n",
        "ffconcat": f"ffconcat version 1.0\nfile '{url}/a.ogg'\nfile '/etc/passwd'\n".encode(),
        "sdp": (
            b"v=0\no=- 0 0 IN IP4 127.0.0.1\ns=x\nc=IN IP4 127.0.0.1\nt=0 0\n"
            b"m=audio 5004 RTP/AVP 0\n"
        ),
    }


@needs_ffmpeg
@pytest.mark.parametrize("kind", ["dash", "dash_file", "hls", "hls_local", "ffconcat", "sdp"])
@pytest.mark.parametrize("ext", ["", "m3u8", "mpd", "ogg"])
def test_playlists_and_manifests_are_rejected_without_network(
    canary: str, kind: str, ext: str
) -> None:
    data = _hostile(canary)[kind]
    with pytest.raises(audio.AudioError):
        audio.playable(data, ext)
    with pytest.raises(audio.AudioError):
        audio.to_mp3(data, ext)
    assert _Canary.hits == []


@needs_ffmpeg
def test_whitelist_itself_blocks_valid_but_unlisted_containers(tmp_path: Path) -> None:
    """Proof the format whitelist does the work (newer ffmpeg builds also
    refuse some playlists on their own): a perfectly valid CAF file opens
    with plain ffprobe but is refused by our locked-down probe."""
    caf = make_audio(tmp_path, "pcm_s16le", "caf")
    src = tmp_path / "plain"
    src.write_bytes(caf)
    plain = subprocess.run(  # noqa: S603 - test helper
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=format_name",
            "-of",
            "default=nw=1:nk=1",
            str(src),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert plain.stdout.strip() == "caf"
    with pytest.raises(audio.AudioError):
        audio.playable(caf, "ogg")
