# Warrior IPTV Player — Project Overview

A desktop IPTV client for Windows that connects to **Xtream Codes**-compatible providers and plays Live TV, Movies (VOD), and Series through an embedded **mpv** player or an external **VLC** install.

## What it does

- Log in with one or more Xtream profiles (server URL, username, password).
- Browse **Live TV**, **Movies**, and **Series** catalogs grouped by provider categories, with an auto-generated **"All"** row per section that aggregates everything.
- Multi-lingual fuzzy search (English, Arabic, accented Latin, etc.).
- Play content in the built-in mpv-based player (with seek, volume, fullscreen, next/previous, playlist) or hand the stream to VLC.
- **Continue Watching** row that tracks what you've opened.
- Per-profile caching of category/stream listings so navigation stays fast.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| UI framework | PySide6 (Qt 6) |
| Video backend (in-app) | mpv via `python-mpv` + bundled `mpv-2.dll` |
| Video backend (external) | VLC via subprocess |
| HTTP | `requests` |
| Packaging | PyInstaller (single-file `.exe`) |

## Repository layout

```
warrior-iptv-player/
├── src/                 # All Python source
│   ├── main.py              # App entry, window shell, sidebar, routing
│   ├── pages.py             # Live TV / Movies / Series / Continue Watching / Series Detail pages
│   ├── player.py            # In-app mpv overlay player + controls
│   ├── widgets.py           # Reusable UI widgets (PosterCard, Hero, Row, VirtualPosterGrid, skeletons)
│   ├── xtream.py            # Xtream Codes API client + on-disk response cache
│   ├── search.py            # Unicode-aware normalization, scoring, ranking
│   ├── history.py           # Continue-watching persistence
│   ├── config.py            # Profiles + preferences in config.json
│   ├── paths.py             # APP_DIR / RESOURCE_DIR resolution (dev vs frozen exe)
│   ├── vlc_launcher.py      # Finds VLC (CANDIDATES → PATH → registry) and launches it
│   └── workers.py           # Thread pool + async helpers for non-blocking I/O
├── resources/           # Static runtime assets
│   ├── styles.qss           # Qt stylesheet (dark theme)
│   ├── icon.ico             # App icon
│   └── assets/              # SVGs for sidebar + player controls
├── build/               # Build tooling
│   ├── build.bat            # One-click build script
│   └── WarriorIPTV.spec     # PyInstaller spec
├── docs/                # Documentation
│   ├── overview.md          # (this file)
│   └── build-exe.md         # How to build the .exe
├── mpv-2.dll            # mpv runtime library (required to play video)
├── config.json          # User profiles + VLC path (created/populated at runtime)
├── requirements.txt     # Python dependencies
└── .gitignore
```

## How the pieces fit

1. **`main.py`** boots Qt, loads `config.json`, constructs the sidebar + pages, and wires navigation signals. It also owns `play_in_app` / `play_in_vlc`.
2. **`xtream.py`** is the API layer. Every call (`get_live_streams`, `get_vod_categories`, `get_series_info`, …) hashes the request and caches the JSON response under `.cache/<profile_key>/`, so reopening a page is instant.
3. **`workers.py`** dispatches those API calls to a thread pool via `run_async(func, on_done=…, on_error=…)` so the UI never blocks.
4. **`pages.py`** subclasses share a `_BasePage` that renders a hero, an "All" row, then per-category rows lazily as the user scrolls. Clicking a row expands into a virtualized grid (`VirtualPosterGrid`) to handle thousands of items without frame drops.
5. **`search.py`** normalizes query + title (NFKC → lowercase → strip Arabic diacritics → unify alef/yeh variants → drop Latin accents → strip ASCII stopwords + Arabic "ال") then scores with substring / token-prefix / fuzzy-ratio heuristics.
6. **`player.py`** creates an mpv overlay widget on top of the Qt window, renders its own control bar (SVG icons from `resources/assets/player/`), and implements auto-hide, seek-on-drag, volume, fullscreen, and playlist next/prev.
7. **`history.py`** appends plays to `.data/<profile_key>/history.json`, powering the Continue Watching page.
8. **`vlc_launcher.py`** resolves a VLC executable by trying: user-provided path → known install dirs → `PATH` → Windows registry → Windows default file handler.

## Runtime data

Created next to the executable (or project root in dev):

- `config.json` — profiles + `vlc_path`.
- `.cache/<profile_key>/` — Xtream API response cache.
- `.data/<profile_key>/` — watch history.

`<profile_key>` is a short SHA-1 of `server|username`, so multiple logins don't collide.

## Dev vs. bundled behavior

`src/paths.py` resolves `APP_DIR` and `RESOURCE_DIR` differently depending on mode:

| Mode | `APP_DIR` | `RESOURCE_DIR` |
|---|---|---|
| Dev (`python src/main.py`) | project root | `project_root/resources` |
| Frozen exe (PyInstaller) | folder of `.exe` | PyInstaller's `_MEIPASS` temp extraction dir |

This lets the same code locate `styles.qss`, icons, and SVGs whether you're running from source or from the bundled executable.

## Running

```cmd
pip install -r requirements.txt
python src/main.py
```

## Building a standalone .exe

See [build-exe.md](build-exe.md).
