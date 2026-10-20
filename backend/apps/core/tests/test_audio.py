"""apps.core.audio: format probing + ffmpeg transcode to MP3."""

from __future__ import annotations

import shutil
import subprocess
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

    def test_fixed_args_no_shell_bytes_via_private_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}
        monkeypatch.setattr(audio, "_binary", lambda name: f"/usr/bin/{name}")

        def fake_run(args: list[str], **kwargs: Any) -> Any:
            seen["args"], seen["kwargs"] = args, kwargs
            src = Path(args[args.index("-i") + 1])
            seen["mode"] = oct(src.parent.stat().st_mode & 0o777)
            seen["input"] = src.read_bytes()
            Path(args[-1]).write_bytes(b"ID3fake")
            return subprocess.CompletedProcess(args, 0, b"", b"")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert audio.to_mp3(b"; rm -rf / #", "ogg") == b"ID3fake"
        assert seen["args"][0] == "/usr/bin/ffmpeg"
        assert "shell" not in seen["kwargs"]
        assert seen["input"] == b"; rm -rf / #"  # bytes only ever go to the file
        assert seen["mode"] == "0o700"
        assert seen["args"][seen["args"].index("-ac") : seen["args"].index("-ac") + 2] == [
            "-ac",
            "1",
        ]
        assert "64k" in seen["args"]
