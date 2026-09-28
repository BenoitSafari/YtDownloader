"""Build and run yt-dlp commands for the two supported modes (mp3 / mkv)."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

YTDLP_BIN = "yt-dlp"
ARCHIVE_NAME = ".ytdl-archive.txt"

# Name templates (the directory is prepended separately).
_NAME_TEMPLATE = "%(title)s [%(id)s].%(ext)s"
_NAME_TEMPLATE_ORDERED = "%(playlist_index)03d - %(title)s [%(id)s].%(ext)s"


@dataclass
class DownloadJob:
    """Everything needed to build a yt-dlp invocation."""

    mode: str  # "mp3" | "mkv"
    url: str
    out: Path
    is_playlist: bool
    ordered: bool = False
    auto_subs: bool = False


def resolve_output(job: DownloadJob) -> tuple[Path, str]:
    """Return ``(output_dir, output_template)`` for a job.

    - Playlist: ``out`` is always a directory; files land inside it.
    - Single video with a file-like ``out`` (has a suffix): that exact file is
      produced (yt-dlp manages the final extension).
    - Single video with a directory-like ``out``: files land inside it.
    """
    out = job.out

    if job.is_playlist:
        output_dir = out
        name = _NAME_TEMPLATE_ORDERED if job.ordered else _NAME_TEMPLATE
        return output_dir, str(output_dir / name)

    # Single video.
    if out.suffix:  # explicit file target, e.g. "clip.mp3"
        output_dir = out.parent if str(out.parent) else Path(".")
        template = str(output_dir / f"{out.stem}.%(ext)s")
        return output_dir, template

    # Directory target for a single video.
    return out, str(out / _NAME_TEMPLATE)


def _mode_argv(mode: str, auto_subs: bool) -> list[str]:
    """Format-selection and post-processing flags specific to each mode."""
    if mode == "mkv":
        argv = [
            # Best video + ALL audio-only tracks (e.g. YouTube dubs), then mux.
            "-f", "bv*+mergeall[vcodec=none]/b",
            "--audio-multistreams",
            "--merge-output-format", "mkv",
            # ALL subtitle tracks, embedded in the container.
            "--sub-langs", "all",
            "--write-subs",
            "--embed-subs",
            "--embed-metadata",
            "--embed-chapters",
            "--embed-thumbnail",
        ]
        if auto_subs:
            argv.append("--write-auto-subs")
        return argv
    if mode == "mp3":
        return [
            "-f", "bestaudio/best",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",  # best VBR (~V0 / up to 320k)
            "--embed-metadata",
            "--embed-thumbnail",
        ]
    raise ValueError(f"unknown mode: {mode!r}")


def build_ytdl_argv(job: DownloadJob, extra: Optional[Sequence[str]] = None) -> list[str]:
    """Build the full yt-dlp argv (starting with the binary name) for ``job``."""
    output_dir, output_template = resolve_output(job)
    archive_path = output_dir / ARCHIVE_NAME

    argv: list[str] = [YTDLP_BIN]
    argv += _mode_argv(job.mode, job.auto_subs)
    argv += [
        # Resume / skip already-completed items (keyed by video id, not filename).
        "--download-archive", str(archive_path),
        "--no-overwrites",
        "--continue",
        # Keep going past a broken playlist item (still exits non-zero if any
        # failed); completed items stay recorded in the archive, so retries
        # resume. Line-based progress so output can be streamed and captured.
        "--no-abort-on-error",
        "--newline",
        "-o", output_template,
    ]
    if extra:
        argv += list(extra)
    argv.append(job.url)
    return argv


# Substrings (case-insensitive) that indicate a transient/geo/rate-limit/bot
# failure worth retrying under a different VPN connection. Anything else (invalid
# URL, private/deleted video, unsupported URL, ...) is treated as permanent.
_RETRYABLE_MARKERS = (
    "http error 429",
    "http error 403",
    "too many requests",
    "confirm you're not a bot",
    "confirm you are not a bot",
    "available in your country",
    "available from your location",
    "geo-restrict",
    "geo restrict",
    "geoblock",
    "blocked it in your country",
    "blocked in your country",
    "unable to download",
    "unable to connect",
    "timed out",
    "connection reset",
    "connection refused",
    "getaddrinfo",
    "temporary failure",
    "sslerror",
    "ssl error",
    "ssl:",
    "remote end closed",
    "read timed out",
)


def is_retryable(output: str) -> bool:
    """Whether ``output`` from a failed yt-dlp run warrants a VPN rotation."""
    low = output.lower()
    return any(marker in low for marker in _RETRYABLE_MARKERS)


def run(argv: Sequence[str], prefix: Optional[Sequence[str]] = None) -> tuple[int, str]:
    """Run ``argv`` (optionally wrapped by ``prefix``, e.g. an ``ip netns exec`` runner).

    Streams the process output to this terminal while capturing it, and returns
    ``(returncode, captured_output)``.
    """
    cmd = list(prefix or []) + list(argv)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
    )
    captured: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        captured.append(line)
    proc.wait()
    return proc.returncode, "".join(captured)
