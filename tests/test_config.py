import pytest

from ytdl.config import resolve_config
from ytdl.errors import ConfigError


@pytest.fixture()
def clean_env(monkeypatch, tmp_path):
    # Isolate config resolution from the real machine: point config home into
    # tmp and clear ytdl env vars.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    for var in ("YTDL_VPN_DIR", "YTDL_NETNS", "YTDL_MAX_VPN_CYCLES",
                "YTDL_COOKIES", "YTDL_COOKIES_FROM_BROWSER"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_no_cookies_by_default(clean_env):
    cfg = resolve_config(config_file=clean_env / "missing.toml")
    assert cfg.cookies_file is None
    assert cfg.cookies_from_browser is None


def test_default_cookies_used_when_present(clean_env):
    cookies = clean_env / "ytdl" / "cookies.txt"
    cookies.parent.mkdir(parents=True)
    cookies.write_text("# cookies")
    cfg = resolve_config(config_file=clean_env / "missing.toml")
    assert cfg.cookies_file == cookies


def test_explicit_cookies_missing_raises(clean_env):
    with pytest.raises(ConfigError):
        resolve_config(cli_cookies=str(clean_env / "nope.txt"),
                       config_file=clean_env / "missing.toml")


def test_env_cookies_from_browser(clean_env, monkeypatch):
    monkeypatch.setenv("YTDL_COOKIES_FROM_BROWSER", "firefox")
    cfg = resolve_config(config_file=clean_env / "missing.toml")
    assert cfg.cookies_from_browser == "firefox"


def test_flag_beats_env_for_browser(clean_env, monkeypatch):
    monkeypatch.setenv("YTDL_COOKIES_FROM_BROWSER", "chrome")
    cfg = resolve_config(cli_cookies_from_browser="firefox",
                         config_file=clean_env / "missing.toml")
    assert cfg.cookies_from_browser == "firefox"
