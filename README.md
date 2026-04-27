# Warrior IPTV Player

A desktop IPTV player for Xtream-Codes accounts. Built with PySide6 and
libmpv. Supports Live TV, Movies, and Series with per-profile continue
watching, VLC hand-off, and background downloads.

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

### Playback
- In-app player powered by libmpv — hardware decoding, seeking, variable speed.
- VLC hand-off for channels that don't play well in the embedded player.
  VLC is auto-detected on Windows (registry + default paths) and macOS
  (`/Applications/VLC.app`).
- **Resume playback** — position saved every 5 seconds. Re-opening a movie or
  episode resumes from where you left off, with an in-player toast and a
  "Start over" option.
- **Continue Watching** tab across Live TV, Movies, and Series.

### Downloads
- **Download movies and series episodes** — click **▶ Play** / **↓** on any
  card or episode row to save to disk.
- **Background downloads** — switching screens or navigating away never pauses
  a download. A live red badge on the sidebar Downloads button shows how many
  are active or queued, from any screen.
- **Server-safe download behavior:**
  - Sends a VLC `User-Agent` header so IPTV servers treat requests as normal
    playback rather than scraping.
  - Speed-limited to **5 MB/s** to mimic real streaming traffic.
  - **Resumable** — if a download is interrupted, it restarts from the last
    byte received via HTTP `Range` requests.
  - **Auto-retry** on `429 Too Many Requests` and `503 Service Unavailable`
    with exponential back-off (5 s → 10 s → 20 s, up to 3 attempts).
  - Maximum **one concurrent download** — extra requests are queued and start
    automatically when the slot opens.
- Progress shown in the window status bar and the Downloads page; completed
  files can be revealed in Finder / Explorer with one click.

### Accounts & Security
- Multiple Xtream profiles — passwords stored in the OS keyring
  (Windows Credential Manager / macOS Keychain / Secret Service).
- No telemetry. All network traffic goes exclusively to your configured
  Xtream server.

### UI / UX
- **Horizontal carousels** — overlaid ‹ › arrow buttons float on the card
  strip (no wasted space). Trackpad two-finger swipe and mouse wheel both
  scroll horizontally without holding any modifier key.
- Smooth animated scrolling (220 ms, cubic ease-out).
- Lazy, cached poster loading with synopsis overlay on hover.
- Responsive layout: sidebar collapses automatically on narrow windows.
- Dark theme with eye-friendly rose-crimson accent colour.

---

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
python src/main.py --dev      # dev mode: colored logs on stderr
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

On subsequent launches you can skip the setup step:

```bash
./setup_mac.sh --run
```

#### What the script does

1. Checks for Homebrew — installs it if missing.
2. Finds or installs Python 3.10+ (`python@3.12` via Homebrew if needed).
3. Installs `mpv` via Homebrew (provides `libmpv.dylib`).
4. Creates a `.venv` virtual environment and installs `requirements.txt`.
5. Detects ARM64 / x86_64 architecture mismatch between Python and libmpv
   and exits with a clear error if they don't match.
6. Runs a `python -c "import mpv"` smoke test and captures any library
   errors before they crash the app silently.
7. Sets `DYLD_LIBRARY_PATH` and `LC_NUMERIC=C`, then launches the app.

#### Manual macOS setup (optional)

```bash
brew install mpv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

#### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

Install `libmpv-dev` if playback is needed (`sudo apt install libmpv-dev` on
Debian/Ubuntu).

---

On first launch you will see a sign-in dialog. Your server URL and username
are stored in `.data/config.json`; the password goes into the OS keyring.

---

## Downloading movies & episodes

### Movies

Each movie card shows three action buttons:

| Button | Action |
|--------|--------|
| **▶  Play** | Play in the embedded mpv player |
| **VLC** | Hand off to VLC |
| **↓** | Download the file to disk |

### Series episodes

Open any series, select a season, and each episode row has two buttons:

| Button | Action |
|--------|--------|
| **▶  Play** | Stream the episode in-app |
| **DL** | Download the episode to disk |

### Download behaviour

Clicking **↓** / **DL** opens a save-file dialog pre-filled with the title
and container extension. The download then runs entirely in the background:

- The Downloads sidebar button shows a red badge with the count of
  active + queued downloads — visible from any screen.
- The window status bar shows `Downloading 'Title'… (42%)` while active.
- Navigate freely — switching to Movies, Series, or any other screen has
  no effect on running downloads.
- Downloads are speed-throttled to 5 MB/s and resume automatically after
  network interruptions.
- On completion, a status bar message confirms success. Failures show an
  error dialog with a plain-language description (e.g. "Access denied (403)
  — the server blocked the download.").

Completed downloads can be revealed in Finder / Explorer via the ⏏ button in
the Downloads tab. Downloaded files default to `<app dir>/downloads/`.

---

## Dev mode / debugging

Pass `--dev` (or `dev`) on the command line:

```bash
# Source run
python src/main.py --dev

# macOS setup script
./setup_mac.sh --run --dev

# macOS .app from Terminal
/Applications/Warrior\ IPTV\ Player.app/Contents/MacOS/WarriorIPTV --dev
```

Dev mode enables:

- Root logger at DEBUG with timestamped, coloured output to stderr.
- Unhandled exceptions in main thread **and** background threads logged with
  full tracebacks.
- mpv log messages routed through the `mpv` logger.
- Every play and download request logs the stream URL.

Level colours: **gray** DEBUG · **cyan** INFO · **yellow** WARNING ·
**red** ERROR · **bold red** CRITICAL.

---

## Project layout

```
src/                   application code
  main.py              app entry point, main window, download wiring
  downloader.py        background download manager (throttle, resume, retry, queue)
  downloads_page.py    download queue panel widget
  pages.py             Live TV / Movies / Series / Continue Watching pages
  player.py            embedded mpv player overlay
  widgets.py           shared widgets: PosterCard, Row carousel, Hero
  workers.py           async worker thread pool
  xtream.py            Xtream-Codes API client
  config.py            profile config helpers
  history.py           continue-watching persistence
resources/             icons, stylesheet, mpv-2.dll / libmpv.dylib (gitignored)
scripts/               developer helpers (fetch_mpv.py, create_icns.sh)
build/                 build scripts (build.bat, build_mac.sh) + Windows spec
packaging/             PyInstaller specs: build.spec (Windows), mac.spec (.app),
                         rthook_mac_mpv.py (runtime hook for bundled libmpv)
tests/                 pytest test suite
docs/                  screenshots and notes
LICENSES/              third-party license texts (LGPL, THIRD_PARTY.md)
.data/                 runtime state — config.json, history (gitignored)
.cache/                cached API responses and images (gitignored)
```

---

## Running the tests

```bash
pip install pytest
pytest tests/ -v
```

The suite covers cross-platform VLC detection, download task logic (throttle,
resume, retry, queue), and profile-key utilities. Tests requiring PySide6 are
automatically skipped when it is not installed.

---

## Building a macOS .app / DMG

Produces a **fully self-contained** `Warrior IPTV Player.app` — Python,
libmpv, FFmpeg, and every other C library bundled inside. End users need
nothing installed; just drag to `/Applications`.

### Prerequisites (developer machine only)

- macOS 11 or later
- Homebrew with `mpv` installed: `brew install mpv`
- Python 3.10+ (installed by `setup_mac.sh` or Homebrew)

### Build

```bash
bash build/build_mac.sh          # → dist/Warrior IPTV Player.app
bash build/build_mac.sh --dmg    # → dist/WarriorIPTV.dmg  (drag-to-install)
```

### What the build script does

1. Locates `libmpv.dylib` under the Homebrew prefix.
2. Creates `.venv`, installs `pyinstaller` and
   [`delocate`](https://github.com/matthew-brett/delocate).
3. Optionally converts `resources/icon.ico` → `resources/icon.icns` via
   macOS `sips` + `iconutil`.
4. Runs **PyInstaller** (`packaging/mac.spec`) — bundles Python + all
   packages + `libmpv.dylib` into `Warrior IPTV Player.app`.
5. Runs **`delocate-path`** on `Contents/MacOS/` — walks every dylib's
   dependency tree, copies missing libraries (FFmpeg, libass, …) into the
   bundle, and rewrites all `@rpath`/`@loader_path` references so nothing
   external is needed at runtime.
6. Optionally wraps the `.app` in a compressed DMG via `hdiutil`.

### Gatekeeper / "App is damaged" warning

Apps without an Apple Developer ID are quarantined. To bypass on first launch:

```bash
xattr -cr "/Applications/Warrior IPTV Player.app"
open "/Applications/Warrior IPTV Player.app"
```

Or right-click → **Open** in Finder.

---

## Building a Windows executable

```powershell
cd build
.\build.bat
```

Requires Python 3.12 reachable via the `py` launcher. The script:

1. Creates `build/pyi-venv/` if missing.
2. Installs PyInstaller + project dependencies.
3. Runs PyInstaller against `build/WarriorIPTV.spec`.
4. Outputs `dist/WarriorIPTV.exe`.

You must have `resources/mpv-2.dll` in place before building
(`python scripts/fetch_mpv.py` once).

Alternative folder-distribution build:

```powershell
pip install pyinstaller
pyinstaller packaging/build.spec
```

---

## Configuration

| Location | Contents |
|----------|----------|
| `.data/config.json` | Server URLs, usernames, active profile |
| OS keyring | Passwords (service name `warrior-iptv-player`) |
| `.cache/<profile-hash>/` | Cached API responses and poster images |
| `.data/<profile-hash>/history.json` | Continue-watching positions |
| Last download directory | Remembered per session; defaults to `<app dir>/downloads/` |

---

## Licensing

- This project is licensed under the [MIT License](./LICENSE).
- Bundled libmpv is **LGPL-2.1-or-later**. The license text is in
  [`LICENSES/LGPL-2.1.txt`](./LICENSES/LGPL-2.1.txt); see
  [`LICENSES/THIRD_PARTY.md`](./LICENSES/THIRD_PARTY.md) for the full
  third-party list and redistribution notes.
- python-mpv is **AGPLv3** — if you intend to ship closed-source binaries,
  review whether AGPL obligations apply.
