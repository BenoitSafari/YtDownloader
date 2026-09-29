# ytdl

## Requirements

Python ≥ 3.9, plus `ffmpeg` and (for VPN mode) `wireguard-tools` / `iproute2`:
`sudo apt install ffmpeg wireguard-tools iproute2`.

## Installation

On **Arch Linux**, run the install script (pacman deps + pipx, avoids the
`externally-managed-environment` error):

```bash
./install.sh
```

Otherwise, install the deps from *Requirements* and:

```bash
pipx install -e .   # or, inside a venv: pip install -e .
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

### Batch mode

If the first argument is a **file** instead of a URL, `ytdl` runs in batch mode and
`OUTPUT_PATH` is a folder. Each line is `"title",url` (title optional):

```
"1. Ichor",https://www.youtube.com/watch?v=eqwbRd-QhS4
"5. Burn Under My Skin (with Bailzwil)",https://www.youtube.com/watch?v=zzzz
https://www.youtube.com/watch?v=yyyy
```

```bash
ytdl -mp3 tracks.txt ./album
```

- A titled line is saved as `title.<ext>` → `1. Ichor.mp3`; a bare URL uses the YouTube
  title. Blank lines and `#` comments are ignored.
- **Playlist URLs are skipped** (logged `playlist detected: skip`), detected by URL shape —
  no request is made. Batch mode downloads individual videos only.
- Resume works like a playlist (archive + no-overwrite in the output folder), so a broken
  batch continues where it stopped.

### Options

| Option | Description |
|--------|-------------|
| `-mp3` / `-mkv` | output mode (required) |
| `--ordered` | prefix each file with its playlist index (playlists only) |
| `--auto-subs` | also fetch auto-generated subtitles (MKV) |
| `--cookies FILE` | cookies.txt for YouTube auth (default `~/.config/ytdl/cookies.txt` if present) |
| `--cookies-from-browser BROWSER` | read cookies from a browser, e.g. `firefox` or `chrome:Default` |
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

## Authentication (age-restricted videos)

Some videos require a signed-in (adult) YouTube account. Provide cookies from a logged-in
session — auto-detected the same way as the VPN configs.

**Option A — cookies from your browser** (closest to an "auto-login"; stay logged in to
YouTube in that browser):

```bash
ytdl -mkv "<url>" ./out --cookies-from-browser firefox
```

Under the VPN (which runs as `sudo`), **Firefox** works reliably; Chrome may fail to decrypt
its cookies as root.

**Option B — a cookies.txt file** (most robust with VPN + sudo). Export it once with a browser
extension (e.g. *Get cookies.txt LOCALLY*) while logged in to YouTube, then:

```bash
mkdir -p ~/.config/ytdl
mv ~/Downloads/cookies.txt ~/.config/ytdl/cookies.txt
chmod 600 ~/.config/ytdl/cookies.txt
```

Once `~/.config/ytdl/cookies.txt` exists it is used automatically (no flag needed). Re-export
it when the session expires.

> Never commit your cookies — they contain session tokens (already excluded by `.gitignore`).
> Without cookies, an age-restricted item is skipped (the rest of the playlist still
> downloads) and `ytdl` prints a hint instead of pointlessly rotating the VPN.
