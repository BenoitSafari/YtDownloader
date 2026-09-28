from pathlib import Path

import pytest

from ytdl.downloader import (
    ARCHIVE_NAME,
    DownloadJob,
    build_ytdl_argv,
    resolve_output,
)


def _argv(job):
    return build_ytdl_argv(job)


def _pairs(argv, flag):
    """All values that immediately follow ``flag`` in ``argv``."""
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag and i + 1 < len(argv)]


def test_resolve_output_playlist_plain(tmp_path):
    job = DownloadJob("mkv", "url", tmp_path, is_playlist=True)
    out_dir, template = resolve_output(job)
    assert out_dir == tmp_path
    assert template == str(tmp_path / "%(title)s [%(id)s].%(ext)s")


def test_resolve_output_playlist_ordered(tmp_path):
    job = DownloadJob("mkv", "url", tmp_path, is_playlist=True, ordered=True)
    _, template = resolve_output(job)
    assert template == str(tmp_path / "%(playlist_index)03d - %(title)s [%(id)s].%(ext)s")


def test_ordered_ignored_for_single_video(tmp_path):
    job = DownloadJob("mp3", "url", tmp_path, is_playlist=False, ordered=True)
    _, template = resolve_output(job)
    # No playlist_index in a single-video directory template.
    assert "playlist_index" not in template


def test_resolve_output_single_file_target(tmp_path):
    target = tmp_path / "clip.mp3"
    job = DownloadJob("mp3", "url", target, is_playlist=False)
    out_dir, template = resolve_output(job)
    assert out_dir == tmp_path
    assert template == str(tmp_path / "clip.%(ext)s")


def test_archive_in_output_dir(tmp_path):
    job = DownloadJob("mkv", "url", tmp_path, is_playlist=True)
    argv = _argv(job)
    assert _pairs(argv, "--download-archive") == [str(tmp_path / ARCHIVE_NAME)]


def test_mkv_argv_has_all_tracks(tmp_path):
    job = DownloadJob("mkv", "https://x/y", tmp_path, is_playlist=False)
    argv = _argv(job)
    assert "bv*+mergeall[vcodec=none]/b" in argv
    assert "--audio-multistreams" in argv
    assert _pairs(argv, "--merge-output-format") == ["mkv"]
    assert _pairs(argv, "--sub-langs") == ["all"]
    assert "--embed-subs" in argv
    # auto-subs off by default
    assert "--write-auto-subs" not in argv
    assert argv[-1] == "https://x/y"


def test_mkv_auto_subs_toggle(tmp_path):
    job = DownloadJob("mkv", "url", tmp_path, is_playlist=False, auto_subs=True)
    assert "--write-auto-subs" in _argv(job)


def test_mp3_argv_best_quality_audio_only(tmp_path):
    job = DownloadJob("mp3", "url", tmp_path, is_playlist=False)
    argv = _argv(job)
    assert _pairs(argv, "-f") == ["bestaudio/best"]
    assert "-x" in argv
    assert _pairs(argv, "--audio-format") == ["mp3"]
    assert _pairs(argv, "--audio-quality") == ["0"]
    # mp3 must not pull video/subtitle tracks
    assert "--sub-langs" not in argv
    assert "--merge-output-format" not in argv


def test_unknown_mode_raises(tmp_path):
    job = DownloadJob("wav", "url", tmp_path, is_playlist=False)
    with pytest.raises(ValueError):
        _argv(job)
