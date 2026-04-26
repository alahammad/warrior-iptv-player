import os
import shutil
import subprocess
import sys
from pathlib import Path

_WIN_CANDIDATES = [
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
]

_MAC_CANDIDATES = [
    "/Applications/VLC.app/Contents/MacOS/VLC",
    str(Path.home() / "Applications/VLC.app/Contents/MacOS/VLC"),
]

_REGISTRY_KEYS = [
    (r"SOFTWARE\VideoLAN\VLC", "InstallDir"),
    (r"SOFTWARE\WOW6432Node\VideoLAN\VLC", "InstallDir"),
]


def _lookup_registry() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    for root in (
        getattr(winreg, "HKEY_LOCAL_MACHINE", None),
        getattr(winreg, "HKEY_CURRENT_USER", None),
    ):
        if root is None:
            continue
        for subkey, value in _REGISTRY_KEYS:
            try:
                with winreg.OpenKey(root, subkey) as key:
                    install_dir, _ = winreg.QueryValueEx(key, value)
            except OSError:
                continue
            exe = Path(install_dir) / "vlc.exe"
            if exe.exists():
                return str(exe)
    return None


def find_vlc(custom: str = "") -> str | None:
    if custom and Path(custom).exists():
        return custom
    candidates = _WIN_CANDIDATES if sys.platform == "win32" else _MAC_CANDIDATES
    for p in candidates:
        if Path(p).exists():
            return p
    found = shutil.which("vlc")
    if found:
        return found
    return _lookup_registry()


def play(url: str, vlc_path: str = "") -> bool:
    exe = find_vlc(vlc_path)
    if exe:
        subprocess.Popen([exe, url], close_fds=True)
        return True
    # Platform-specific fallback: open with the OS default handler
    try:
        if sys.platform == "win32":
            os.startfile(url)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
        return True
    except Exception:
        return False
