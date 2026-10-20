"""Audio helpers — probe the real format and transcode to MP3 with ffmpeg.

Used where a third party only plays mp3/wav (Bitrix24's call player). Phones
upload .ogg (and the odd .m4a mislabelled as ogg), so the format is detected
by probing the bytes, never from the file name.

The bytes come from the device upload API, i.e. any self-registered company,
and ffmpeg runs in the Celery worker that holds DB/MinIO secrets — so it is
locked down (defence in depth against ffmpeg's playlist demuxers and parser
bugs):

* ``-protocol_whitelist file`` and ``-format_whitelist`` (real audio
  containers only) on BOTH ffprobe and ffmpeg — hls, dash, concat, sdp, rtp,
  rtsp, image2, lavfi, subfile, data, tee … can never be opened, so a crafted
  playlist/manifest can't make ffmpeg fetch URLs or read other local files;
* the probe must report an allowed container with at least one audio
  stream; ffmpeg is then told that container explicitly (``-f`` before
  ``-i``) so it can't re-detect something else;
* absolute binary, fixed argument list, never ``shell=True``; the only
  caller-controlled input is the bytes, written to a private (0700) temp dir;
* minimal environment, ``-nostdin``, 25 MB input cap, 50 MB output cap
  (``-fs`` + check), 60 s timeout, and RLIMIT_AS/RLIMIT_CPU on the child.

Not sandboxed further (no network namespace/seccomp in our image): with the
protocol whitelist ffmpeg has no way to open sockets; a separate
credential-less worker would be the next step if ever needed.
"""

from __future__ import annotations

import json
import os
import resource
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_INPUT_BYTES = 25 * 1024 * 1024
MAX_OUTPUT_BYTES = 50 * 1024 * 1024
TIMEOUT_SECONDS = 60
MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024  # address space for ffmpeg/ffprobe
# Demuxers we accept (``ffmpeg -demuxers``): ogg, mp3, wav, "mov,mp4,m4a,
# 3gp,3g2,mj2", "matroska,webm", raw aac/amr/flac. Whitelist entries match
# any name in a demuxer's comma list.
ALLOWED_FORMATS = ("ogg", "mp3", "wav", "mov", "matroska", "aac", "amr", "amrnb", "amrwb", "flac")
FORMAT_WHITELIST = ",".join(ALLOWED_FORMATS)
# Formats Bitrix24's player accepts as-is (first ffprobe format name).
PASSTHROUGH = {"mp3": "mp3", "wav": "wav"}
_LOCKDOWN = ["-protocol_whitelist", "file", "-format_whitelist", FORMAT_WHITELIST]


class AudioError(Exception):
    """Probe/transcode failed; ``str(exc)`` is safe to log (no paths/data)."""


def _binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise AudioError(f"{name} is not installed")
    return path


def _limit_child() -> None:  # pragma: no cover - runs in the forked child
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_SECONDS, TIMEOUT_SECONDS))


def _run(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(  # noqa: S603 - absolute binary, fixed args, no shell
            args,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            env={"PATH": os.defpath, "LC_ALL": "C"},  # nothing inherited
            preexec_fn=_limit_child,  # noqa: PLW1509 - celery prefork, no threads
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
    """Allowed container name (first ffprobe name) of a file with audio."""
    result = _run(
        [
            _binary("ffprobe"),
            "-hide_banner",
            "-loglevel",
            "error",
            *_LOCKDOWN,
            "-show_entries",
            "format=format_name:stream=codec_type",
            "-of",
            "json",
            str(path),
        ]
    )
    if result.returncode != 0:
        raise AudioError("not a readable audio file")
    try:
        info = json.loads(result.stdout or b"{}")
    except ValueError:
        raise AudioError("not a readable audio file") from None
    names = str((info.get("format") or {}).get("format_name") or "").lower().split(",")
    fmt = names[0].strip()
    if fmt not in ALLOWED_FORMATS:
        raise AudioError("unsupported audio container")
    streams = info.get("streams") or []
    if not any(isinstance(s, dict) and s.get("codec_type") == "audio" for s in streams):
        raise AudioError("no audio stream")
    return fmt


def probe_format(data: bytes) -> str:
    """Container of ``data`` ("ogg", "mp3", "wav", "mov", …) — only
    allow-listed audio containers with an audio stream, else AudioError."""
    _guard(data)
    with tempfile.TemporaryDirectory(prefix="doocall-audio-") as tmp:
        src = Path(tmp) / "input"
        src.write_bytes(data)
        return _probe(src)


def _transcode(src: Path, fmt: str, dst: Path, src_ext: str) -> bytes:
    result = _run(
        [
            _binary("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            *_LOCKDOWN,
            "-f",
            fmt,  # the probed, allow-listed container — no re-detection
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "22050",
            "-b:a",
            "64k",
            "-fs",
            str(MAX_OUTPUT_BYTES),
            "-f",
            "mp3",
            str(dst),
        ]
    )
    if result.returncode != 0 or not dst.exists() or dst.stat().st_size == 0:
        raise AudioError(f"transcode failed (source {src_ext or 'unknown'})")
    if dst.stat().st_size >= MAX_OUTPUT_BYTES:
        raise AudioError("transcoded audio too large")
    return dst.read_bytes()


def to_mp3(data: bytes, src_ext: str = "") -> bytes:
    """Transcode allow-listed audio to mono 64 kbps / 22.05 kHz MP3.

    ``src_ext`` is informational only — the container is probed."""
    _guard(data)
    with tempfile.TemporaryDirectory(prefix="doocall-audio-") as tmp:
        src = Path(tmp) / "input"
        src.write_bytes(data)
        return _transcode(src, _probe(src), Path(tmp) / "output.mp3", src_ext)


def playable(data: bytes, src_ext: str = "") -> tuple[bytes, str]:
    """(bytes, "mp3"|"wav") a mp3/wav-only player can use: mp3/wav pass
    through untouched, every other allowed container becomes mp3."""
    _guard(data)
    with tempfile.TemporaryDirectory(prefix="doocall-audio-") as tmp:
        src = Path(tmp) / "input"
        src.write_bytes(data)
        fmt = _probe(src)
        if fmt in PASSTHROUGH:
            return data, PASSTHROUGH[fmt]
        return _transcode(src, fmt, Path(tmp) / "output.mp3", src_ext), "mp3"
