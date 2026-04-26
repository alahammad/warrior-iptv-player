# Warrior IPTV Player

A desktop IPTV player for Xtream-Codes accounts. Built with PySide6 and
libmpv. Supports Live TV, Movies, and Series, with per-profile continue
watching, VLC hand-off, and movie downloads.

> **Supported platforms:** Windows (x86_64) and macOS (Intel & Apple Silicon).
> Linux works for playback when mpv and VLC are installed, but has no official
> build script yet.

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

- Multiple Xtream profiles — passwords stored in the OS keyring
  (Windows Credential Manager / macOS Keychain / Secret Service).
- In-app player powered by libmpv (hardware decoding, seeking, speed).
- **macOS support** — automatically discovers `libmpv.dylib` installed via
  Homebrew (both Intel `/usr/local/lib` and Apple Silicon `/opt/homebrew/lib`).
- VLC hand-off for channels that don't play well in the embedded player.
  VLC is auto-detected on Windows (registry + default paths) and macOS
  (`/Applications/VLC.app`).
- **Download movies** — click the **DL** button on any movie card to save it
  locally. A save-file dialog lets you choose the destination; progress is
  shown live in the status bar.
- Continue Watching across Live / Movies / Series.
- Lazy, cached poster loading.

## Run from source

### Windows

```powershell
git clone https://github.com/<you>/warrior-iptv-player.git
cd warrior-iptv-player
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Fetch `mpv-2.dll` (not committed — LGPL redistribution + size):

```powershell
python scripts/fetch_mpv.py
```

The script downloads a pinned libmpv build and extracts `mpv-2.dll` into
`resources/`. It uses 7-Zip if installed, otherwise auto-fetches `7zr.exe`.

```powershell
python src/main.py            # normal run
python src/main.py dev        # dev mode: colored logs on stderr
```

### macOS — one-command setup

A setup script handles everything: Homebrew, Python, mpv, the virtual
environment, and dependencies — then launches the app.

```bash
git clone https://github.com/<you>/warrior-iptv-player.git
cd warrior-iptv-player
chmod +x setup_mac.sh
./setup_mac.sh
```

That's it. On subsequent launches you can skip the setup step:

```bash
./setup_mac.sh --run
```

#### What the script does

1. Checks for Homebrew — installs it if missing.
2. Finds or installs Python 3.10+ (`python@3.12` via Homebrew if needed).
3. Installs `mpv` via Homebrew (provides `libmpv.dylib`).
4. Creates a `.venv` virtual environment and installs `requirements.txt`.
5. Verifies the `python-mpv` bindings can load the library.
6. Sets `DYLD_LIBRARY_PATH` if needed and launches the app.

#### Manual macOS setup (optional)

If you prefer to control each step yourself:

```bash
brew install mpv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

The app finds `libmpv.dylib` automatically under the Homebrew prefix. If you
use a non-standard location, set `DYLD_LIBRARY_PATH` to the directory that
contains `libmpv.dylib` before launching.

---

On first launch you'll see a sign-in dialog. Your server URL and username land
in `.data/config.json`; the password is stored in your OS keyring.

## Downloading movies

On the **Movies** page, each movie card shows three action buttons:

| Button | Action |
|--------|--------|
| **In App** | Play in the embedded mpv player |
| **In VLC** | Hand off to VLC |
| **DL** | Download the movie file to disk |

Clicking **DL** opens a save-file dialog pre-filled with the movie title and
its container extension (e.g. `.mp4`). The download runs in the background;
progress (`Downloading 'Title'…  (42%)`) is shown in the window status bar.
Completed downloads show a confirmation message; failures show an error dialog.

Downloaded files are saved to `<app dir>/downloads/` by default. The last
chosen directory is remembered for the session.

## Dev mode logging

Pass `dev` (or `--dev`) on the command line to enable:

- Root logger at DEBUG, colored output to stderr.
- Unhandled exceptions (main thread and background threads) logged with
  full tracebacks.
- mpv log messages routed through the `mpv` logger.
- Every play and download request logs the URL.

Level colors: **gray** DEBUG · **cyan** INFO · **yellow** WARNING ·
**red** ERROR · **bold red** CRITICAL.

## Project layout

```
src/             application code
  downloader.py  background download manager (new)
resources/       icons, stylesheet, mpv-2.dll / libmpv.dylib (gitignored)
scripts/         developer helpers (fetch_mpv.py, ...)
build/           Windows build script + PyInstaller spec
packaging/       alternative PyInstaller spec (folder distribution)
tests/           pytest test suite
docs/            design / notes
LICENSES/        third-party license texts (LGPL, THIRD_PARTY.md)
.data/           runtime state — config.json, history (gitignored)
.cache/          cached API responses and images (gitignored)
```

## Running the tests

```bash
pip install pytest
pytest tests/ -v
```

The suite covers cross-platform VLC detection, download task logic, and
profile-key utilities. Tests that require PySide6 (Qt signal integration)
are automatically skipped when PySide6 is not installed.

## Building a Windows executable

Single-file `WarriorIPTV.exe` via the bundled batch script:

```powershell
cd build
.\build.bat
```

Requires Python 3.12 reachable through the `py` launcher. The script will:

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
- **Download directory:** last-used directory remembered per session;
  defaults to `<app dir>/downloads/`.

## Licensing

- This project is licensed under the [MIT License](./LICENSE).
- Bundled libmpv is **LGPL-2.1-or-later**. The license text is in
  [`LICENSES/LGPL-2.1.txt`](./LICENSES/LGPL-2.1.txt); see
  [`LICENSES/THIRD_PARTY.md`](./LICENSES/THIRD_PARTY.md) for the full
  third-party list and redistribution notes.
- python-mpv is **AGPLv3** — if you intend to ship closed-source binaries,
  review whether AGPL obligations apply.
