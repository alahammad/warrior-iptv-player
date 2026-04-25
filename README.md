# Warrior IPTV Player

A desktop IPTV player for Xtream-Codes accounts. Built with PySide6 and
libmpv. Supports Live TV, Movies, and Series, with per-profile continue
watching and VLC hand-off.

> **Windows-only** for now. The bundled player is `mpv-2.dll`
> (Windows x86_64). Cross-platform support is not implemented.

## Preview

<p align="center">
  <img src="docs/screenshots/login.jpg" width="420">
</p>

<p align="center">
  <img src="docs/screenshots/movies.jpg" width="280">
  <img src="docs/screenshots/series.jpg" width="280">
  <img src="docs/screenshots/player.jpg" width="280">
</p>

## Features

- Multiple Xtream profiles, passwords stored in the OS keyring
  (Windows Credential Manager / macOS Keychain / Secret Service).
- In-app player powered by libmpv (hardware decoding, seeking, speed).
- VLC hand-off for channels that don't play well in the embedded player.
- Continue Watching across Live / Movies / Series.
- Lazy, cached poster loading.

## Run from source

### 1. Clone and set up a venv

```powershell
git clone https://github.com/<you>/warrior-iptv-player.git
cd warrior-iptv-player
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.10+ works; 3.12 is recommended (matches the build script).

### 2. Fetch libmpv

`mpv-2.dll` is not committed to the repo (LGPL redistribution + size).
Grab it once with the helper script — no extra Python deps required:

```powershell
python scripts/fetch_mpv.py
```

The script downloads a pinned libmpv build and extracts `mpv-2.dll`
into `resources/`. It uses 7-Zip if installed, otherwise auto-fetches
the official standalone `7zr.exe` (~600 KB) from 7-zip.org. If anything
fails, follow the manual instructions it prints.

### 3. Run

```powershell
python src/main.py            # normal run
python src/main.py dev        # dev mode: colored logs on stderr
```

On first launch you'll see a sign-in dialog. Your server URL and
username land in `.data/config.json`; the password is stored in your
OS keyring.

## Dev mode logging

Pass `dev` (or `--dev`) on the command line to enable:

- Root logger at DEBUG, colored output to stderr.
- Unhandled exceptions (main thread and background threads) logged with
  full tracebacks.
- mpv log messages routed through the `mpv` logger.
- Every play request logs the URL.

Level colors: **gray** DEBUG · **cyan** INFO · **yellow** WARNING ·
**red** ERROR · **bold red** CRITICAL.

## Project layout

```
src/             application code
resources/       icons, stylesheet, mpv-2.dll (gitignored)
scripts/         developer helpers (fetch_mpv.py, ...)
build/           Windows build script + PyInstaller spec
packaging/       alternative PyInstaller spec (folder distribution)
docs/            design / notes
LICENSES/        third-party license texts (LGPL, THIRD_PARTY.md)
.data/           runtime state — config.json, history (gitignored)
.cache/          cached API responses and images (gitignored)
```

## Building a Windows executable

The easy path — single-file `WarriorIPTV.exe` via the bundled batch
script (uses an isolated venv so it can't be poisoned by other Python
installs on your machine):

```powershell
cd build
.\build.bat
```

Requires Python 3.12 reachable through the `py` launcher
(`py -3.12 --version`). The script will:

1. Create `build/pyi-venv/` if missing.
2. Install PyInstaller + project dependencies into that venv.
3. Run PyInstaller against `build/WarriorIPTV.spec`.
4. Drop the result at `dist/WarriorIPTV.exe`.

You must have `resources/mpv-2.dll` in place before building (run
`python scripts/fetch_mpv.py` once).

Alternative folder-distribution build (`dist/WarriorIPTV/`):

```powershell
pip install pyinstaller
pyinstaller packaging/build.spec
```

## Configuration

- **Profiles & server URL:** `.data/config.json`
- **Passwords:** OS keyring under service `warrior-iptv-player`.
- **API cache:** `.cache/<profile-hash>/*.json` — safe to delete.
- **Continue-watching history:** `.data/<profile-hash>/history.json`.

## Licensing

- This project is licensed under the [MIT License](./LICENSE).
- Bundled libmpv is **LGPL-2.1-or-later**. The license text is in
  [`LICENSES/LGPL-2.1.txt`](./LICENSES/LGPL-2.1.txt); see
  [`LICENSES/THIRD_PARTY.md`](./LICENSES/THIRD_PARTY.md) for the full
  third-party list and redistribution notes.
- python-mpv is **AGPLv3** — note that if you intend to ship closed-source
  binaries, you should review whether AGPL obligations apply.

