"""Command-line entry point and orchestration (retry + VPN rotation)."""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from ytdl import __version__
from ytdl.batch import parse_batch_file
from ytdl.config import find_vpn_configs, resolve_config
from ytdl.downloader import (
    DownloadJob,
    auth_hint,
    build_ytdl_argv,
    is_retryable,
    resolve_output,
    run,
)
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


def sanitize_url(raw: str) -> str:
    """Strip surrounding whitespace and one layer of matching quotes.

    Users often paste a URL still wrapped in quotes (e.g. ``"'https://...'"``),
    which yt-dlp then rejects as an invalid URL.
    """
    url = raw.strip()
    for _ in range(2):  # handle at most one nested pair, e.g. "'...'"
        if len(url) >= 2 and url[0] == url[-1] and url[0] in "\"'":
            url = url[1:-1].strip()
        else:
            break
    return url


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
    p.add_argument("--cookies", metavar="FILE",
                   help="cookies.txt for YouTube auth (default: ~/.config/ytdl/cookies.txt "
                        "if present). Needed for age-restricted videos.")
    p.add_argument("--cookies-from-browser", metavar="BROWSER",
                   help="read cookies from a browser, e.g. 'firefox' or 'chrome:Default' "
                        "(takes precedence over --cookies)")
    p.add_argument("-v", "--verbose", action="store_true", help="verbose logging")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _log(msg: str) -> None:
    print(f"[ytdl] {msg}", file=sys.stderr, flush=True)


def _backoff(attempt: int) -> float:
    return float(min(2 ** attempt, 16))


# An item is a (label, yt-dlp argv) pair. Single-URL mode is a one-item list.
Item = Tuple[str, List[str]]


def _run_direct(items: Sequence[Item]) -> int:
    _log("downloading without VPN")
    failed = 0
    for label, argv in items:
        _log(f"→ {label}")
        rc, output = run(argv)
        if rc != 0:
            failed += 1
            hint = auth_hint(output)
            _log(f"failed: {label}" + (f" — {hint}" if hint else f" (exit {rc})"))
    return 1 if failed else 0


def _run_with_vpn(items: Sequence[Item], configs: list[Path], netns: str,
                  max_cycles: int, verbose: bool) -> int:
    parsed: list[WgConfig] = [parse_wg_config(p) for p in configs]  # validate up front
    random.shuffle(parsed)

    mgr = WireGuardNetns(netns, verbose=verbose)
    total = len(parsed) * max(1, max_cycles)
    pending: list[Item] = list(items)
    failed_hard: list[str] = []

    try:
        for attempt in range(total):
            if not pending:
                break
            cfg = parsed[attempt % len(parsed)]
            _log(f"VPN attempt {attempt + 1}/{total} via config '{cfg.name}' "
                 f"({len(pending)} item(s) pending)")
            try:
                mgr.setup(cfg)
            except VpnError as exc:
                _log(f"VPN setup failed for '{cfg.name}': {exc}")
                time.sleep(_backoff(attempt))
                continue

            ip = mgr.public_ip()
            if ip:
                _log(f"tunnel up — external IP: {ip}")

            prefix = mgr.exec_prefix()
            still: list[Item] = []
            for label, argv in pending:
                _log(f"→ {label}")
                rc, output = run(argv, prefix=prefix)
                if rc == 0:
                    continue
                # Retry transient/geo/rate-limit/bot failures under another
                # server; a permanent error (invalid URL, auth/age) fails on
                # every server, so drop that item and keep going with the rest.
                if is_retryable(output):
                    _log(f"retryable failure: {label} (exit {rc})")
                    still.append((label, argv))
                else:
                    hint = auth_hint(output)
                    _log(f"skipping (non-recoverable): {label}"
                         + (f" — {hint}" if hint else f" (exit {rc})"))
                    failed_hard.append(label)
            mgr.teardown()

            pending = still
            if pending:
                _log("rotating VPN connection")
                time.sleep(_backoff(attempt))

        if pending:
            _log(f"giving up on {len(pending)} item(s) after {total} VPN attempts")
            failed_hard.extend(label for label, _ in pending)
        return 1 if failed_hard else 0
    finally:
        mgr.teardown()


def _build_single_item(url: str, mode: str, out: Path, cfg, args) -> List[Item]:
    job = DownloadJob(
        mode=mode,
        url=url,
        out=out,
        is_playlist=is_playlist_url(url),
        ordered=args.ordered,
        auto_subs=args.auto_subs,
        cookies_file=cfg.cookies_file,
        cookies_from_browser=cfg.cookies_from_browser,
    )
    # Ensure the output directory exists (the archive lives there too).
    output_dir, _ = resolve_output(job)
    output_dir.mkdir(parents=True, exist_ok=True)
    return [(url, build_ytdl_argv(job))]


def _build_batch_items(path: Path, mode: str, out: Path, cfg, args) -> List[Item]:
    if out.is_file():
        raise ConfigError(f"in batch mode, OUT must be a directory, not a file: {out}")
    out.mkdir(parents=True, exist_ok=True)

    entries = parse_batch_file(path)
    items: List[Item] = []
    skipped = 0
    for entry in entries:
        # Playlists are out of scope for batch mode; detected by URL shape only
        # (no network request).
        if is_playlist_url(entry.url):
            _log(f"playlist detected: skip: {entry.url}")
            skipped += 1
            continue
        job = DownloadJob(
            mode=mode,
            url=entry.url,
            out=out,
            is_playlist=False,
            auto_subs=args.auto_subs,
            cookies_file=cfg.cookies_file,
            cookies_from_browser=cfg.cookies_from_browser,
            output_name=entry.title,
        )
        items.append((entry.title or entry.url, build_ytdl_argv(job)))

    _log(f"batch: {len(items)} item(s) to download, {skipped} playlist(s) skipped")
    return items


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
            cli_cookies=args.cookies,
            cli_cookies_from_browser=args.cookies_from_browser,
        )

        if cfg.cookies_from_browser:
            _log(f"using cookies from browser: {cfg.cookies_from_browser}")
        elif cfg.cookies_file:
            _log(f"using cookies file: {cfg.cookies_file}")

        url = sanitize_url(args.url)
        out = Path(args.out).expanduser()

        # Batch mode is auto-detected: the positional "URL" is actually a file.
        if Path(url).expanduser().is_file():
            items = _build_batch_items(Path(url).expanduser(), mode, out, cfg, args)
            if not items:
                _log("nothing to download")
                return 0
        else:
            items = _build_single_item(url, mode, out, cfg, args)

        if args.verbose:
            for label, argv in items:
                _log(f"yt-dlp command [{label}]: " + " ".join(argv))

        vpn_configs = [] if args.no_vpn else find_vpn_configs(cfg.vpn_dir)

        if args.no_vpn:
            rc = _run_direct(items)
        elif vpn_configs:
            _log(f"found {len(vpn_configs)} VPN config(s) in {cfg.vpn_dir}")
            rc = _run_with_vpn(items, vpn_configs, cfg.netns,
                               cfg.max_vpn_cycles, args.verbose)
        elif args.require_vpn:
            raise ConfigError(
                f"--require-vpn set but no *.conf found in {cfg.vpn_dir}"
            )
        else:
            _log(f"no VPN config found in {cfg.vpn_dir}")
            rc = _run_direct(items)

        if rc != 0:
            raise DownloadError("one or more downloads failed")
        _log("done")
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
