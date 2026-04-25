"""Download libmpv (mpv-2.dll) into resources/ for local development.

Usage:
    python scripts/fetch_mpv.py

Downloads a pinned libmpv Windows x86_64 build and extracts mpv-2.dll
into ./resources/. Safe to re-run; skips download if the file already
exists and --force is not passed.

Modern mpv-winbuild archives use BCJ2-filtered LZMA2, which py7zr cannot
decode. This script therefore extracts via 7-Zip's official standalone
extractor (`7zr.exe`): it uses an installed copy if present, or fetches
the small (~600 KB) standalone binary from 7-zip.org on demand.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

# Pinned mirror. Update URL + SHA256 together when bumping libmpv.
MPV_URL = (
    "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/"
    "20260421/mpv-dev-x86_64-20260421-git-5921fe5.7z"
)
MPV_SHA256 = ""  # leave empty to skip verification

# 7-Zip standalone console extractor (LGPL). Tiny (~600 KB) and supports BCJ2.
SEVENZR_URL = "https://www.7-zip.org/a/7zr.exe"

REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "resources" / "mpv-2.dll"
MANUAL_INSTRUCTIONS = f"""
Manual fallback:
  1. Download a recent 'mpv-dev-x86_64-*.7z' from
     https://github.com/shinchiro/mpv-winbuild-cmake/releases
  2. Extract mpv-2.dll (some builds name it 'libmpv-2.dll' - rename it).
  3. Place it at: {TARGET}
"""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "warrior-iptv-player-fetch"})
    with urllib.request.urlopen(req) as resp, dest.open("wb") as out:
        shutil.copyfileobj(resp, out)


def _find_seven_zip() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\7-Zip\7z.exe"),
        Path(r"C:\Program Files (x86)\7-Zip\7z.exe"),
    ]
    for c in candidates:
        if c.exists():
            return c
    on_path = shutil.which("7z") or shutil.which("7zr") or shutil.which("7za")
    return Path(on_path) if on_path else None


def _ensure_extractor(scratch: Path) -> Path:
    found = _find_seven_zip()
    if found:
        print(f"Using {found}")
        return found
    extractor = scratch / "7zr.exe"
    print("7-Zip not found locally; fetching standalone 7zr.exe from 7-zip.org")
    _download(SEVENZR_URL, extractor)
    return extractor


def _extract_mpv_dll(archive: Path, target: Path, extractor: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as extract_dir:
        # `e` extracts ignoring directory structure so mpv-2.dll lands at top.
        result = subprocess.run(
            [str(extractor), "e", str(archive), "mpv-2.dll", "libmpv-2.dll",
             f"-o{extract_dir}", "-y", "-r"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(
                f"7-Zip extraction failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}\n"
                f"{MANUAL_INSTRUCTIONS}"
            )
        for name in ("mpv-2.dll", "libmpv-2.dll"):
            extracted = Path(extract_dir) / name
            if extracted.exists():
                shutil.copy2(extracted, target)
                print(f"Wrote {target} ({target.stat().st_size / 1024 / 1024:.1f} MiB)")
                return
    raise SystemExit(
        f"mpv-2.dll not found inside archive after extraction.\n{MANUAL_INSTRUCTIONS}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch libmpv for this project")
    parser.add_argument("--force", action="store_true", help="Re-download even if mpv-2.dll exists")
    args = parser.parse_args()

    if TARGET.exists() and not args.force:
        print(f"{TARGET} already exists. Use --force to re-download.")
        return 0

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        scratch = Path(tmp)
        archive = scratch / "mpv.7z"
        try:
            _download(MPV_URL, archive)
        except Exception as exc:
            print(f"Download failed: {exc}", file=sys.stderr)
            print(MANUAL_INSTRUCTIONS, file=sys.stderr)
            return 1

        if MPV_SHA256:
            actual = _sha256(archive)
            if actual.lower() != MPV_SHA256.lower():
                print(f"SHA256 mismatch:\n  expected {MPV_SHA256}\n  actual   {actual}", file=sys.stderr)
                return 1

        try:
            extractor = _ensure_extractor(scratch)
            _extract_mpv_dll(archive, TARGET, extractor)
        except SystemExit:
            raise
        except Exception as exc:
            print(f"Extraction failed: {exc}", file=sys.stderr)
            print(MANUAL_INSTRUCTIONS, file=sys.stderr)
            return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
