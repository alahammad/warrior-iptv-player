import json
import logging
import time
from pathlib import Path

from paths import profile_data_dir

log = logging.getLogger(__name__)

MAX_ENTRIES = 40


def _history_path(server: str, username: str) -> Path:
    return profile_data_dir(server, username) / "history.json"


def load(server: str, username: str) -> list[dict]:
    path = _history_path(server, username)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
    except (OSError, ValueError) as exc:
        log.debug("history load failed: %s", exc)
    return []


def _save(server: str, username: str, entries: list[dict]) -> None:
    path = _history_path(server, username)
    try:
        path.write_text(json.dumps(entries[:MAX_ENTRIES], indent=2))
    except OSError as exc:
        log.debug("history save failed: %s", exc)


def record(
    server: str,
    username: str,
    kind: str,
    item_id: str,
    name: str,
    cover: str | None = None,
    position: float = 0.0,
    duration: float = 0.0,
    extra: dict | None = None,
) -> None:
    entries = load(server, username)
    entries = [e for e in entries if not (e.get("kind") == kind and str(e.get("id")) == str(item_id))]
    entry = {
        "kind": kind,
        "id": str(item_id),
        "name": name,
        "cover": cover or "",
        "position": float(position),
        "duration": float(duration),
        "updated_at": time.time(),
    }
    if extra:
        entry.update(extra)
    entries.insert(0, entry)
    _save(server, username, entries)


def remove(server: str, username: str, kind: str, item_id: str) -> None:
    entries = [
        e for e in load(server, username)
        if not (e.get("kind") == kind and str(e.get("id")) == str(item_id))
    ]
    _save(server, username, entries)


def clear(server: str, username: str) -> None:
    _save(server, username, [])
