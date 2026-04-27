import json
import logging
from pathlib import Path

from paths import profile_data_dir

_log = logging.getLogger(__name__)


def _path(server: str, username: str) -> Path:
    return profile_data_dir(server, username) / "favorites.json"


def load(server: str, username: str) -> dict:
    p = _path(server, username)
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        _log.exception("favorites.load failed")
    return {}


def _save(server: str, username: str, data: dict) -> None:
    try:
        _path(server, username).write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        _log.exception("favorites._save failed")


def is_favorite(server: str, username: str, kind: str, item_id: str) -> bool:
    return bool(load(server, username).get(kind, {}).get(str(item_id)))


def toggle(
    server: str, username: str, kind: str, item_id: str,
    name: str = "", cover: str = "",
) -> bool:
    """Toggle favorite. Returns True if now favorited, False if removed."""
    data = load(server, username)
    bucket = data.setdefault(kind, {})
    sid = str(item_id)
    if sid in bucket:
        del bucket[sid]
        result = False
    else:
        bucket[sid] = {"name": name, "cover": cover}
        result = True
    _save(server, username, data)
    return result


def get_favorites(
    server: str, username: str, kind: str,
    all_items: list, id_fn,
) -> list:
    """Return subset of all_items that are favorited for kind."""
    bucket = load(server, username).get(kind, {})
    if not bucket:
        return []
    return [item for item in all_items if str(id_fn(item)) in bucket]
