# ytdl

## Requirements

Python ≥ 3.9, plus `ffmpeg` and (for VPN mode) `wireguard-tools` / `iproute2`:
`sudo apt install ffmpeg wireguard-tools iproute2`.

## Installation

```bash
pip install -e .
```

## Usage

```
ytdl -mp3|-mkv "VIDEO_OR_PLAYLIST_URL" "OUTPUT_PATH" [options]
```

Examples:

```bash
# Single video to MP3 (best quality) into a folder
ytdl -mp3 "https://www.youtube.com/watch?v=xxxx" ./music

# Single video to MKV (all audio + subtitle tracks)
ytdl -mkv "https://www.youtube.com/watch?v=xxxx" ./films

# Playlist to MKV, into a folder, with an index prefix
ytdl -mkv "https://www.youtube.com/playlist?list=PLxxxx" ./my_playlist --ordered
```

For a **playlist**, `OUTPUT_PATH` is a **folder**. Re-running the same command resumes the
job: already-downloaded items are skipped.

### Options

| Option | Description |
|--------|-------------|
| `-mp3` / `-mkv` | output mode (required) |
| `--ordered` | prefix each file with its playlist index (playlists only) |
| `--auto-subs` | also fetch auto-generated subtitles (MKV) |
| `--vpn-dir DIR` | directory of WireGuard configs (default `~/.config/ytdl/vpn/`) |
| `--no-vpn` | force downloading without VPN |
| `--require-vpn` | fail if no VPN config is found |
| `--netns NAME` | network namespace name (default `ytdlvpn`) |
| `--max-vpn-cycles N` | how many times to loop over all configs before giving up (default 2) |
| `-v`, `--verbose` | verbose logging |

## VPN (ProtonVPN via WireGuard)

Provide one WireGuard `.conf` per server; VPN is auto-detected when the config directory
contains at least one `.conf` (each failure rotates to the next one). Requires `sudo`.

1. Sign in at <https://account.protonvpn.com>.
2. **Downloads → WireGuard configuration**.
3. Platform **GNU/Linux**, pick a server, **Create** → **Download** the `.conf`.
4. Repeat for several servers, then drop them into the config directory:

```bash
mkdir -p ~/.config/ytdl/vpn
mv ~/Downloads/*.conf ~/.config/ytdl/vpn/
chmod 600 ~/.config/ytdl/vpn/*.conf   # these files contain your private key
```

> Never commit your `.conf` files — they contain your private key (already excluded by
> `.gitignore`).
