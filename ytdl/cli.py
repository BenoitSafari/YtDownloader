"""Command-line entry point and orchestration (retry + VPN rotation)."""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import Optional, Sequence

from ytdl import __version__
from ytdl.config import find_vpn_configs, resolve_config
from ytdl.downloader import DownloadJob, build_ytdl_argv, resolve_output, run
from ytdl.errors import ConfigError, DownloadError, VpnError, YtdlError
from ytdl.vpn import WireGuardNetns, WgConfig, parse_wg_config

MODE_TOKENS = {
    "-mp3": "mp3", "--mp3": "mp3",
    "-mkv": "mkv", "--mkv": "mkv",
}
PROG = "ytdl"


def _extract_mode(argv: list[str]) -> tuple[Optional[str], list[str]]:
    """Pull the first ``-mp3``/``-mkv`` (or ``--`` variants) token out of ``argv``.

    Returns ``(mode, remaining_args)``. argparse cannot represent a single-dash
    multi-char flag, so we strip it before handing the rest to argparse.
    """
    mode = None
    rest: list[str] = []
    for tok in argv:
        if mode is None and tok in MODE_TOKENS:
            mode = MODE_TOKENS[tok]
        else:
            rest.append(tok)
    return mode, rest


def is_playlist_url(url: str) -> bool:
    """Heuristic: a URL is treated as a playlist when it carries a list id."""
    lowered = url.lower()
    return "list=" in lowered or "/playlist" in lowered


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        usage=f"{PROG} -mp3|-mkv URL OUT [options]",
        description="Download YouTube videos/playlists in best quality. "
                    "MKV keeps every audio and subtitle track; MP3 keeps the best audio only.",
    )
    p.add_argument("url", help="YouTube video or playlist URL")
    p.add_argument("out", help="output file or directory (directory for playlists)")
    p.add_argument("--vpn-dir", help="directory of WireGuard .conf files "
                                     "(default: ~/.config/ytdl/vpn/ or $YTDL_VPN_DIR)")
    p.add_argument("--no-vpn", action="store_true",
                   help="force downloading without VPN even if configs exist")
    p.add_argument("--require-vpn", action="store_true",
                   help="fail if no VPN config is found (instead of running without VPN)")
    p.add_argument("--netns", help="network namespace name (default: ytdlvpn)")
    p.add_argument("--max-vpn-cycles", type=int,
                   help="how many times to loop over all configs before giving up (default: 2)")
    p.add_argument("--ordered", action="store_true",
                   help="prefix each playlist item with its index (playlists only)")
    p.add_argument("--auto-subs", action="store_true",
                   help="also fetch auto-generated subtitles (MKV mode)")
    p.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _log(msg: str) -> None:
    print(f"[ytdl] {msg}", file=sys.stderr, flush=True)


def _backoff(attempt: int) -> float:
    return float(min(2 ** attempt, 16))


def _run_direct(argv: Sequence[str]) -> int:
    _log("downloading without VPN")
    return run(argv)


def _run_with_vpn(argv: Sequence[str], configs: list[Path], netns: str,
                  max_cycles: int, verbose: bool) -> int:
    parsed: list[WgConfig] = [parse_wg_config(p) for p in configs]  # validate up front
    random.shuffle(parsed)

    mgr = WireGuardNetns(netns, verbose=verbose)
    total = len(parsed) * max(1, max_cycles)
    last_rc = 1

    try:
        for attempt in range(total):
            cfg = parsed[attempt % len(parsed)]
            _log(f"VPN attempt {attempt + 1}/{total} via config '{cfg.name}'")
            try:
                mgr.setup(cfg)
            except VpnError as exc:
                _log(f"VPN setup failed for '{cfg.name}': {exc}")
                time.sleep(_backoff(attempt))
                continue

            ip = mgr.public_ip()
            if ip:
                _log(f"tunnel up — external IP: {ip}")

            last_rc = run(argv, prefix=mgr.exec_prefix())
            mgr.teardown()

            if last_rc == 0:
                _log("download completed successfully")
                return 0

            _log(f"download failed (exit {last_rc}); rotating VPN connection")
            time.sleep(_backoff(attempt))
        raise DownloadError(
            f"download still failing after {total} VPN attempts (last exit {last_rc})"
        )
    finally:
        mgr.teardown()


def main(argv: Optional[list[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    mode, rest = _extract_mode(raw)

    parser = _build_parser()
    if mode is None:
        parser.print_usage(sys.stderr)
        _log("error: you must pass a mode flag: -mp3 or -mkv")
        return 2
    args = parser.parse_args(rest)

    try:
        cfg = resolve_config(
            cli_vpn_dir=args.vpn_dir,
            cli_netns=args.netns,
            cli_max_vpn_cycles=args.max_vpn_cycles,
        )

        playlist = is_playlist_url(args.url)
        job = DownloadJob(
            mode=mode,
            url=args.url,
            out=Path(args.out).expanduser(),
            is_playlist=playlist,
            ordered=args.ordered,
            auto_subs=args.auto_subs,
        )

        # Ensure the output directory exists (archive lives there too).
        output_dir, _ = resolve_output(job)
        output_dir.mkdir(parents=True, exist_ok=True)

        ytdl_argv = build_ytdl_argv(job)
        if args.verbose:
            _log("yt-dlp command: " + " ".join(ytdl_argv))

        vpn_configs = [] if args.no_vpn else find_vpn_configs(cfg.vpn_dir)

        if args.no_vpn:
            rc = _run_direct(ytdl_argv)
        elif vpn_configs:
            _log(f"found {len(vpn_configs)} VPN config(s) in {cfg.vpn_dir}")
            rc = _run_with_vpn(ytdl_argv, vpn_configs, cfg.netns,
                               cfg.max_vpn_cycles, args.verbose)
        elif args.require_vpn:
            raise ConfigError(
                f"--require-vpn set but no *.conf found in {cfg.vpn_dir}"
            )
        else:
            _log(f"no VPN config found in {cfg.vpn_dir}")
            rc = _run_direct(ytdl_argv)

        if rc != 0:
            raise DownloadError(f"yt-dlp exited with code {rc}")
        return 0

    except FileNotFoundError as exc:
        _log(f"error: required program not found: {exc.filename or exc}. "
             "Install yt-dlp, ffmpeg and (for VPN) wireguard-tools/iproute2.")
        return 1
    except YtdlError as exc:
        _log(f"error: {exc}")
        return 1
    except KeyboardInterrupt:
        _log("interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
