# Building Warrior IPTV Player as a Windows Executable

This guide explains how to turn the source code into a standalone `WarriorIPTV.exe` that you can run or share without needing Python installed.

## Prerequisites

1. **Windows 10 or 11** (64-bit).
2. **Python 3.12** reachable through the `py` launcher (`py -3.12 --version`). Download from [python.org](https://www.python.org/downloads/). During install, tick **"Add Python to PATH"** and **"py launcher"**.
3. **`mpv-2.dll`** at the repo root. Run `python scripts/fetch_mpv.py` once to download it (the file is not committed for LGPL/size reasons).
4. **VLC** (optional) — only needed if users want the "Play in VLC" feature. Install from [videolan.org](https://www.videolan.org/vlc/).

## Building

Easiest way:

```cmd
cd build
build.bat
```

The script will:

1. Create an isolated virtualenv at `build/pyi-venv/` (first run only).
2. Install PyInstaller and project dependencies into that venv.
3. Clean any previous build output.
4. Run PyInstaller against `WarriorIPTV.spec`.
5. Write the finished `WarriorIPTV.exe` to `dist/` at the project root.

When it finishes, you should see:

```
Build complete:
  dist\WarriorIPTV.exe
```

## Manual build (alternative)

If you prefer to run the commands yourself:

```cmd
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install PyInstaller -r requirements.txt
cd build
pyinstaller --noconfirm --workpath pyi-build --distpath ..\dist WarriorIPTV.spec
```

## Output

- **`dist/WarriorIPTV.exe`** — the final executable. This is what you ship to users. It bundles all Python code, Qt libraries, `mpv-2.dll`, styles, icons, and SVG assets into a single file.
- **`build/pyi-build/`** — PyInstaller's temporary working directory. Safe to delete.
- **`build/pyi-venv/`** — the isolated build virtualenv. Safe to delete; will be recreated on next build.

## Running the built executable

Double-click `dist/WarriorIPTV.exe`. On first launch the app will create a `.cache/` and `.data/` folder next to the exe to store cached listings and watch history.

No Python install is required on the target machine.

## Troubleshooting

**"Failed to create virtualenv"**
Make sure Python 3.12 is installed and the `py` launcher is on your PATH. Verify with `py -3.12 --version`.

**"Failed to install build dependencies"**
Check your internet connection. You can also install manually inside `build/pyi-venv/Scripts/activate` then `pip install PyInstaller -r ..\requirements.txt`.

**"mpv-2.dll not found"**
Run `python scripts/fetch_mpv.py` from the repo root. It downloads the correct Windows x86_64 build.

**App starts but no video plays**
In a bundled `.exe` build, `mpv-2.dll` is embedded — no action needed. When running from source (`python src/main.py`), `mpv-2.dll` must sit at the repo root.

**SmartScreen warning on first launch**
Unsigned executables trigger Windows SmartScreen. Click **More info → Run anyway**. To avoid this for distribution, sign the binary with a code-signing certificate.

**Build succeeds but exe is huge (~90 MB)**
Expected — PySide6 and mpv are large. UPX compression is enabled in the spec, but Qt cannot be shrunk much further.
