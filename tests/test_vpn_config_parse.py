import pytest

from ytdl.errors import VpnError
from ytdl.vpn import parse_wg_config, stripped_config_text

SAMPLE = """\
[Interface]
# Bouncing = 1
PrivateKey = aPrivateKeyValue123=
Address = 10.2.0.2/32
DNS = 10.2.0.1
MTU = 1420

[Peer]
PublicKey = aPublicKeyValue456=
PresharedKey = aPresharedKeyValue789=
AllowedIPs = 0.0.0.0/0
Endpoint = 1.2.3.4:51820
PersistentKeepalive = 25
"""


def _write(tmp_path, text, name="NL-FREE-1.conf"):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_parse_full_config(tmp_path):
    cfg = parse_wg_config(_write(tmp_path, SAMPLE))
    assert cfg.name == "NL-FREE-1"
    assert cfg.private_key == "aPrivateKeyValue123="
    assert cfg.address == ["10.2.0.2/32"]
    assert cfg.dns == ["10.2.0.1"]
    assert cfg.mtu == "1420"
    assert cfg.public_key == "aPublicKeyValue456="
    assert cfg.preshared_key == "aPresharedKeyValue789="
    assert cfg.endpoint == "1.2.3.4:51820"
    assert cfg.allowed_ips == ["0.0.0.0/0"]
    assert cfg.persistent_keepalive == "25"


def test_stripped_config_excludes_address_and_dns(tmp_path):
    cfg = parse_wg_config(_write(tmp_path, SAMPLE))
    stripped = stripped_config_text(cfg)
    assert "Address" not in stripped
    assert "DNS" not in stripped
    assert "MTU" not in stripped
    assert "PrivateKey = aPrivateKeyValue123=" in stripped
    assert "PublicKey = aPublicKeyValue456=" in stripped
    assert "PresharedKey = aPresharedKeyValue789=" in stripped
    assert "Endpoint = 1.2.3.4:51820" in stripped
    assert "AllowedIPs = 0.0.0.0/0" in stripped
    assert "PersistentKeepalive = 25" in stripped


def test_missing_private_key_raises(tmp_path):
    text = SAMPLE.replace("PrivateKey = aPrivateKeyValue123=", "")
    with pytest.raises(VpnError):
        parse_wg_config(_write(tmp_path, text))


def test_missing_peer_raises(tmp_path):
    text = SAMPLE.split("[Peer]")[0]
    with pytest.raises(VpnError):
        parse_wg_config(_write(tmp_path, text))


def test_multiple_addresses(tmp_path):
    text = SAMPLE.replace("Address = 10.2.0.2/32",
                          "Address = 10.2.0.2/32, fd00::2/128")
    cfg = parse_wg_config(_write(tmp_path, text))
    assert cfg.address == ["10.2.0.2/32", "fd00::2/128"]
