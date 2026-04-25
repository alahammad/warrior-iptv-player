import hashlib
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    RESOURCE_DIR = APP_DIR / "resources"

CACHE_DIR = APP_DIR / ".cache"
DATA_DIR = APP_DIR / ".data"


def profile_key(server: str, username: str) -> str:
    raw = f"{server.rstrip('/').lower()}|{username.lower()}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def profile_cache_dir(server: str, username: str) -> Path:
    path = CACHE_DIR / profile_key(server, username)
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_data_dir(server: str, username: str) -> Path:
    path = DATA_DIR / profile_key(server, username)
    path.mkdir(parents=True, exist_ok=True)
    return path


def purge_profile(server: str, username: str) -> None:
    import shutil
    key = profile_key(server, username)
    for base in (CACHE_DIR, DATA_DIR):
        target = base / key
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
