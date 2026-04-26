# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — macOS .app bundle
#
# Usage (from repo root):
#     bash build/build_mac.sh
# or manually:
#     pyinstaller packaging/mac.spec --noconfirm

import subprocess
from pathlib import Path

REPO_ROOT = Path(SPECPATH).resolve().parent  # type: ignore[name-defined]
SRC = REPO_ROOT / "src"
RESOURCES = REPO_ROOT / "resources"
PACKAGING = REPO_ROOT / "packaging"

# ── Locate libmpv.dylib ──────────────────────────────────────────────────────
def _find_libmpv() -> str:
    brew_prefix = "/opt/homebrew"  # Apple Silicon default
    try:
        brew_prefix = subprocess.check_output(
            ["brew", "--prefix"], text=True
        ).strip()
    except Exception:
        pass
    candidates = [
        Path(brew_prefix) / "lib" / "libmpv.dylib",
        Path("/usr/local/lib") / "libmpv.dylib",
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    raise SystemExit(
        "libmpv.dylib not found. Install mpv via Homebrew: brew install mpv"
    )

LIBMPV = _find_libmpv()

# ── Icon ─────────────────────────────────────────────────────────────────────
ICNS = str(RESOURCES / "icon.icns")
if not Path(ICNS).exists():
    # Fall back to no icon rather than hard-failing
    ICNS = None

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],
    binaries=[
        (LIBMPV, "."),
    ],
    datas=[
        (str(RESOURCES / "styles.qss"), "resources"),
        (str(RESOURCES / "assets"), "resources/assets"),
        (str(REPO_ROOT / "LICENSE"), "."),
        (str(REPO_ROOT / "LICENSES"), "LICENSES"),
    ],
    hiddenimports=[
        "keyring",
        "keyring.backends",
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        "keyring.backends.fail",
        "keyring.backends.null",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(PACKAGING / "rthook_mac_mpv.py")],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)  # type: ignore[name-defined]

exe = EXE(  # type: ignore[name-defined]
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
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICNS,
)

coll = COLLECT(  # type: ignore[name-defined]
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="WarriorIPTV",
)

app = BUNDLE(  # type: ignore[name-defined]
    coll,
    name="Warrior IPTV Player.app",
    icon=ICNS,
    bundle_identifier="com.warrior.iptv.player",
    info_plist={
        "CFBundleName": "Warrior IPTV Player",
        "CFBundleDisplayName": "Warrior IPTV Player",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,  # allow dark mode
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "© 2025 Warrior IPTV Player contributors",
    },
)
