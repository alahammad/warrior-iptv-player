# PyInstaller spec for Warrior IPTV Player.
#
# Usage:
#     pip install pyinstaller
#     pyinstaller packaging/build.spec
#
# Output: dist/WarriorIPTV/
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

REPO_ROOT = Path(SPECPATH).resolve().parent  # type: ignore[name-defined]
SRC = REPO_ROOT / "src"
RESOURCES = REPO_ROOT / "resources"
MPV_DLL = RESOURCES / "mpv-2.dll"

if not MPV_DLL.exists():
    raise SystemExit(
        f"mpv-2.dll not found at {MPV_DLL}. "
        "Run `python scripts/fetch_mpv.py` before building."
    )

hiddenimports = []
hiddenimports += collect_submodules("keyring.backends")

datas = [
    (str(RESOURCES / "styles.qss"), "resources"),
    (str(RESOURCES / "icon.ico"),   "resources"),
    (str(RESOURCES / "assets"),     "resources/assets"),
    (str(REPO_ROOT / "LICENSE"),    "."),
    (str(REPO_ROOT / "LICENSES"),   "LICENSES"),
]

binaries = [
    (str(MPV_DLL), "."),
]

block_cipher = None

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WarriorIPTV",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(RESOURCES / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WarriorIPTV",
)
