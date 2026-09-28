"""Resolution of runtime configuration.

Precedence (highest first):
    1. CLI flags
    2. Environment variables (YTDL_VPN_DIR, YTDL_NETNS, YTDL_MAX_VPN_CYCLES)
    3. Config file (~/.config/ytdl/config.toml)
    4. Built-in defaults
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

# tomllib is stdlib since 3.11; fall back to the tomli backport, else skip.
try:  # pragma: no cover - trivial import shim
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as _toml  # type: ignore
    except ModuleNotFoundError:
        _toml = None  # type: ignore

DEFAULT_NETNS = "ytdlvpn"
DEFAULT_MAX_VPN_CYCLES = 2


def _config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ytdl"


def default_vpn_dir() -> Path:
    """Default location scanned for WireGuard *.conf files."""
    return _config_home() / "vpn"


def default_config_file() -> Path:
    return _config_home() / "config.toml"


def _load_config_file(path: Path) -> dict[str, Any]:
    if _toml is None or not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            return _toml.load(fh)
    except Exception:
        # A malformed config file must not crash the tool; ignore it.
        return {}


@dataclass
class Config:
    """Resolved configuration used by the rest of the program."""

    vpn_dir: Path
    netns: str
    max_vpn_cycles: int


def resolve_config(
    *,
    cli_vpn_dir: Optional[str] = None,
    cli_netns: Optional[str] = None,
    cli_max_vpn_cycles: Optional[int] = None,
    config_file: Optional[Path] = None,
) -> Config:
    """Merge CLI args, env vars, config file and defaults into a :class:`Config`."""
    file_data = _load_config_file(config_file or default_config_file())

    # vpn_dir
    if cli_vpn_dir is not None:
        vpn_dir = Path(cli_vpn_dir)
    elif os.environ.get("YTDL_VPN_DIR"):
        vpn_dir = Path(os.environ["YTDL_VPN_DIR"])
    elif file_data.get("vpn_dir"):
        vpn_dir = Path(str(file_data["vpn_dir"]))
    else:
        vpn_dir = default_vpn_dir()
    vpn_dir = vpn_dir.expanduser()

    # netns
    netns = (
        cli_netns
        or os.environ.get("YTDL_NETNS")
        or file_data.get("netns")
        or DEFAULT_NETNS
    )

    # max_vpn_cycles
    if cli_max_vpn_cycles is not None:
        max_cycles = cli_max_vpn_cycles
    elif os.environ.get("YTDL_MAX_VPN_CYCLES"):
        max_cycles = int(os.environ["YTDL_MAX_VPN_CYCLES"])
    elif file_data.get("max_vpn_cycles") is not None:
        max_cycles = int(file_data["max_vpn_cycles"])
    else:
        max_cycles = DEFAULT_MAX_VPN_CYCLES

    return Config(vpn_dir=vpn_dir, netns=str(netns), max_vpn_cycles=int(max_cycles))


def find_vpn_configs(vpn_dir: Path) -> list[Path]:
    """Return sorted list of WireGuard ``*.conf`` files in ``vpn_dir`` (empty if none)."""
    if not vpn_dir.is_dir():
        return []
    return sorted(p for p in vpn_dir.glob("*.conf") if p.is_file())
