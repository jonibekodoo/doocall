"""Audio helpers — probe the real format and transcode to MP3 with ffmpeg.

Used where a third party only plays mp3/wav (Bitrix24's call player). Phones
upload .ogg (and the odd .m4a mislabelled as ogg), so the format is detected
by probing the bytes, never from the file name.

Safety: ffmpeg/ffprobe run from an absolute path with a fixed argument list
(never ``shell=True``); the only caller-controlled input is the audio bytes,
written to a private temp dir (mode 0700). Input is capped at
``MAX_INPUT_BYTES`` and every run has a hard timeout.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_INPUT_BYTES = 25 * 1024 * 1024
TIMEOUT_SECONDS = 60
# Formats Bitrix24's player accepts as-is (ffprobe format names).
PASSTHROUGH = {"mp3": "mp3", "wav": "wav"}


class AudioError(Exception):
    """Probe/transcode failed; ``str(exc)`` is safe to log (no paths/data)."""


def _binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise AudioError(f"{name} is not installed")
    return path


def _run(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(  # noqa: S603 - absolute binary, fixed args, no shell
            args,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise AudioError(f"{Path(args[0]).name} timed out after {TIMEOUT_SECONDS}s") from None
    except OSError as exc:
        raise AudioError(f"{Path(args[0]).name} could not run: {exc.strerror}") from None


def _guard(data: bytes) -> None:
    if not data:
        raise AudioError("empty audio")
    if len(data) > MAX_INPUT_BYTES:
        raise AudioError(f"audio larger than {MAX_INPUT_BYTES // (1024 * 1024)} MB")


def _probe(path: Path) -> str:
    result = _run(
        [
            _binary("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=format_name",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    names = result.stdout.decode(errors="replace").strip()
    if result.returncode != 0 or not names:
        raise AudioError("not a readable audio file")
    return names.split(",")[0].strip().lower()


def probe_format(data: bytes) -> str:
    """ffprobe's container name for ``data`` ("ogg", "mp3", "wav", "mov", …)."""
    _guard(data)
    with tempfile.TemporaryDirectory(prefix="doocall-audio-") as tmp:
        src = Path(tmp) / "input"
        src.write_bytes(data)
        return _probe(src)


def to_mp3(data: bytes, src_ext: str = "") -> bytes:
    """Transcode any audio ffmpeg can read to mono 64 kbps / 22.05 kHz MP3.

    ``src_ext`` is informational only — ffmpeg probes the real format."""
    _guard(data)
    with tempfile.TemporaryDirectory(prefix="doocall-audio-") as tmp:
        src = Path(tmp) / "input"
        dst = Path(tmp) / "output.mp3"
        src.write_bytes(data)
        result = _run(
            [
                _binary("ffmpeg"),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-y",
                "-i",
                str(src),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                "-b:a",
                "64k",
                "-f",
                "mp3",
                str(dst),
            ]
        )
        if result.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
            raise AudioError(f"transcode failed (source {src_ext or 'unknown'})")
        return dst.read_bytes()


def playable(data: bytes, src_ext: str = "") -> tuple[bytes, str]:
    """(bytes, "mp3"|"wav") a mp3/wav-only player can use: mp3/wav pass
    through untouched, everything else becomes mp3."""
    fmt = probe_format(data)
    if fmt in PASSTHROUGH:
        return data, PASSTHROUGH[fmt]
    return to_mp3(data, src_ext), "mp3"
