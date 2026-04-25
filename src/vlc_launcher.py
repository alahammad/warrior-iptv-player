import os
import shutil
import subprocess
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
]

_REGISTRY_KEYS = [
    (r"SOFTWARE\VideoLAN\VLC", "InstallDir"),
    (r"SOFTWARE\WOW6432Node\VideoLAN\VLC", "InstallDir"),
]


def _lookup_registry() -> str | None:
    try:
        import winreg
    except ImportError:
        return None
    for root in (getattr(winreg, "HKEY_LOCAL_MACHINE", None), getattr(winreg, "HKEY_CURRENT_USER", None)):
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
    for p in CANDIDATES:
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
    try:
        os.startfile(url)
        return True
    except Exception:
        return False
