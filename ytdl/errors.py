"""Internal exceptions for ytdl."""


class YtdlError(Exception):
    """Base class for all ytdl errors."""


class ConfigError(YtdlError):
    """Raised when configuration (CLI args, env, config file) is invalid."""


class VpnError(YtdlError):
    """Raised when VPN setup/teardown or WireGuard config parsing fails."""


class DownloadError(YtdlError):
    """Raised when the download ultimately fails after all retries."""
