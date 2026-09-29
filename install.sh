#!/usr/bin/env bash
#
# Install ytdl and its dependencies on Arch Linux.
#
#   - system tools via pacman: ffmpeg, wireguard-tools, iproute2, yt-dlp, pipx
#   - the ytdl CLI itself via pipx (isolated venv, no externally-managed error)
#
# Re-run it any time to update; it is idempotent.

set -euo pipefail

# Work from the repository root (this script's directory), whatever the cwd.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v pacman >/dev/null 2>&1; then
    echo "error: pacman not found — this script targets Arch Linux." >&2
    echo "On other distros, install: ffmpeg wireguard-tools iproute2 pipx, then 'pipx install -e .'" >&2
    exit 1
fi

echo "==> Installing system dependencies (pacman)"
# yt-dlp is installed system-wide so it is on PATH for both your user and, under
# the VPN, the sudo/netns download process.
sudo pacman -S --needed --noconfirm \
    ffmpeg \
    wireguard-tools \
    iproute2 \
    yt-dlp \
    python-pipx

echo "==> Installing the ytdl CLI (pipx)"
pipx install --force -e .

# Ensure ~/.local/bin (where pipx puts the 'ytdl' command) is on PATH.
pipx ensurepath >/dev/null 2>&1 || true

echo
echo "==> Done."
if command -v ytdl >/dev/null 2>&1; then
    echo "    'ytdl' is ready: $(command -v ytdl)"
else
    echo "    'ytdl' was installed to ~/.local/bin — open a NEW shell (or run"
    echo "    'hash -r') so it is picked up on your PATH."
fi
