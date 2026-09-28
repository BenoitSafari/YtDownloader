"""Per-process VPN isolation via WireGuard inside a Linux network namespace.

Only the ``yt-dlp`` process runs inside the namespace, so the rest of the
machine keeps its normal connection. Each WireGuard ``.conf`` is a candidate
"connection"; on failure the caller tears down and brings up the next one.

Privileged operations (``ip``/``wg``) require root: when the tool is not run as
root they are prefixed with ``sudo``. yt-dlp itself is executed inside the
namespace but dropped back to the unprivileged user so downloaded files are not
owned by root.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ytdl.errors import VpnError

WG_IFACE = "wg-ytdl"  # <= 15 chars (kernel limit)


@dataclass
class WgConfig:
    """Parsed WireGuard configuration file."""

    name: str
    private_key: str
    address: list[str] = field(default_factory=list)
    dns: list[str] = field(default_factory=list)
    public_key: str = ""
    endpoint: str = ""
    allowed_ips: list[str] = field(default_factory=lambda: ["0.0.0.0/0", "::/0"])
    preshared_key: Optional[str] = None
    persistent_keepalive: Optional[str] = None
    mtu: Optional[str] = None
    path: Optional[Path] = None


def _split_values(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def parse_wg_config(path: Path) -> WgConfig:
    """Parse a WireGuard ``.conf`` into a :class:`WgConfig`."""
    text = Path(path).read_text(encoding="utf-8")
    section = None
    cfg = WgConfig(name=Path(path).stem, private_key="", path=Path(path))

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip().lower()
        val = val.strip()

        if section == "interface":
            if key == "privatekey":
                cfg.private_key = val
            elif key == "address":
                cfg.address = _split_values(val)
            elif key == "dns":
                cfg.dns = _split_values(val)
            elif key == "mtu":
                cfg.mtu = val
        elif section == "peer":
            if key == "publickey":
                cfg.public_key = val
            elif key == "presharedkey":
                cfg.preshared_key = val
            elif key == "endpoint":
                cfg.endpoint = val
            elif key == "allowedips":
                cfg.allowed_ips = _split_values(val)
            elif key == "persistentkeepalive":
                cfg.persistent_keepalive = val

    if not cfg.private_key:
        raise VpnError(f"{path}: missing [Interface] PrivateKey")
    if not cfg.public_key or not cfg.endpoint:
        raise VpnError(f"{path}: missing [Peer] PublicKey/Endpoint")
    if not cfg.address:
        raise VpnError(f"{path}: missing [Interface] Address")
    return cfg


def stripped_config_text(cfg: WgConfig) -> str:
    """Config text accepted by ``wg setconf`` (no Address/DNS/MTU, only crypto)."""
    lines = ["[Interface]", f"PrivateKey = {cfg.private_key}", "", "[Peer]",
             f"PublicKey = {cfg.public_key}"]
    if cfg.preshared_key:
        lines.append(f"PresharedKey = {cfg.preshared_key}")
    lines.append(f"Endpoint = {cfg.endpoint}")
    lines.append(f"AllowedIPs = {', '.join(cfg.allowed_ips)}")
    if cfg.persistent_keepalive:
        lines.append(f"PersistentKeepalive = {cfg.persistent_keepalive}")
    return "\n".join(lines) + "\n"


class WireGuardNetns:
    """Manage a WireGuard-backed network namespace and run commands inside it."""

    def __init__(self, netns: str, iface: str = WG_IFACE, verbose: bool = False):
        self.netns = netns
        self.iface = iface
        self.verbose = verbose
        self._sudo = [] if os.geteuid() == 0 else ["sudo"]
        self._active = False

    # -- privileged command helpers ------------------------------------

    def _run(self, args: list[str], *, check: bool = True,
             input_text: Optional[str] = None) -> subprocess.CompletedProcess:
        cmd = self._sudo + args
        if self.verbose:
            print("+ " + " ".join(cmd))
        result = subprocess.run(
            cmd, input=input_text, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if check and result.returncode != 0:
            raise VpnError(
                f"command failed ({result.returncode}): {' '.join(cmd)}\n{result.stdout}"
            )
        return result

    def _target_user(self) -> str:
        """The unprivileged user that should own downloaded files."""
        if os.geteuid() == 0:
            return os.environ.get("SUDO_USER") or "root"
        return getpass.getuser()

    # -- lifecycle -----------------------------------------------------

    def setup(self, cfg: WgConfig) -> None:
        """Create the namespace and bring the WireGuard interface up for ``cfg``."""
        self.teardown()  # ensure a clean slate

        self._run(["ip", "netns", "add", self.netns])
        self._active = True
        try:
            self._run(["ip", "link", "add", self.iface, "type", "wireguard"])
            self._run(["ip", "link", "set", self.iface, "netns", self.netns])

            for addr in cfg.address:
                self._run(["ip", "-n", self.netns, "addr", "add", addr, "dev", self.iface])

            # Load the crypto config via a temp file readable by wg.
            with tempfile.NamedTemporaryFile(
                "w", suffix=".conf", delete=False, encoding="utf-8"
            ) as fh:
                fh.write(stripped_config_text(cfg))
                tmp_conf = fh.name
            try:
                self._run(["ip", "netns", "exec", self.netns, "wg", "setconf",
                           self.iface, tmp_conf])
            finally:
                try:
                    os.unlink(tmp_conf)
                except OSError:
                    pass

            if cfg.mtu:
                self._run(["ip", "-n", self.netns, "link", "set", "mtu", cfg.mtu,
                           "dev", self.iface])

            self._run(["ip", "-n", self.netns, "link", "set", self.iface, "up"])
            self._run(["ip", "-n", self.netns, "link", "set", "lo", "up"])
            self._run(["ip", "-n", self.netns, "route", "add", "default", "dev", self.iface])

            self._configure_dns(cfg)
        except Exception:
            self.teardown()
            raise

    def _configure_dns(self, cfg: WgConfig) -> None:
        dns = cfg.dns or ["1.1.1.1"]
        netns_dir = f"/etc/netns/{self.netns}"
        content = "".join(f"nameserver {d}\n" for d in dns)
        self._run(["mkdir", "-p", netns_dir])
        # Write resolv.conf via tee so it works with or without sudo.
        self._run(["tee", f"{netns_dir}/resolv.conf"], input_text=content)

    def teardown(self) -> None:
        """Remove the namespace (also deletes the interface) and DNS config."""
        # `ip netns del` fails harmlessly if the namespace does not exist.
        self._run(["ip", "netns", "del", self.netns], check=False)
        self._run(["rm", "-rf", f"/etc/netns/{self.netns}"], check=False)
        self._active = False

    # -- running commands inside the namespace -------------------------

    def exec_prefix(self) -> list[str]:
        """Command prefix that runs a program inside the namespace as the user."""
        user = self._target_user()
        prefix = self._sudo + ["ip", "netns", "exec", self.netns]
        # Drop back to the unprivileged user; preserve PATH/HOME so ffmpeg and
        # yt-dlp's config/cache are found. Proxy vars are intentionally dropped.
        prefix += ["sudo", "-u", user, "--preserve-env=PATH,HOME", "--"]
        return prefix

    def public_ip(self) -> Optional[str]:
        """Best-effort external IP as seen from inside the namespace."""
        res = self._run(
            ["ip", "netns", "exec", self.netns, "curl", "-s", "--max-time", "10",
             "https://api.ipify.org"],
            check=False,
        )
        ip = (res.stdout or "").strip()
        return ip or None

    def __enter__(self) -> "WireGuardNetns":
        return self

    def __exit__(self, *exc) -> None:
        self.teardown()
