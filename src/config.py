import json
import logging

import keyring

from paths import APP_DIR, DATA_DIR

_log = logging.getLogger(__name__)

CONFIG_PATH = DATA_DIR / "config.json"
_LEGACY_CONFIG_PATH = APP_DIR / "config.json"

KEYRING_SERVICE = "warrior-iptv-player"


def _migrate_legacy_location() -> None:
    if CONFIG_PATH.exists() or not _LEGACY_CONFIG_PATH.exists():
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _LEGACY_CONFIG_PATH.replace(CONFIG_PATH)
    except OSError:
        pass


DEFAULTS = {
    "profiles": [],
    "active_profile": 0,
    "vlc_path": "",
}

PROFILE_DEFAULTS = {
    "name": "",
    "server": "",
    "username": "",
    "live_ext": "ts",
}


def _cred_key(server: str, username: str) -> str:
    return f"{server.rstrip('/').lower()}|{username.lower()}"


def get_password(profile: dict) -> str:
    server = profile.get("server", "")
    username = profile.get("username", "")
    if not server or not username:
        return ""
    try:
        return keyring.get_password(KEYRING_SERVICE, _cred_key(server, username)) or ""
    except Exception:
        _log.exception("keyring get_password failed")
        return ""


def _store_password(profile: dict, password: str) -> None:
    if not password:
        return
    server = profile.get("server", "")
    username = profile.get("username", "")
    if not server or not username:
        return
    try:
        keyring.set_password(KEYRING_SERVICE, _cred_key(server, username), password)
    except Exception:
        _log.exception("keyring set_password failed")


def _delete_password(server: str, username: str) -> None:
    if not server or not username:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, _cred_key(server, username))
    except Exception:
        _log.debug("keyring delete_password failed", exc_info=True)


def _migrate(data: dict) -> dict:
    if "profiles" in data and isinstance(data["profiles"], list):
        return data
    server = data.get("server", "")
    username = data.get("username", "")
    password = data.get("password", "")
    profiles: list[dict] = []
    if server and username and password:
        profiles.append({
            **PROFILE_DEFAULTS,
            "name": data.get("profile_name") or "Default",
            "server": server,
            "username": username,
            "password": password,
        })
    return {
        "profiles": profiles,
        "active_profile": 0,
        "vlc_path": data.get("vlc_path", ""),
    }


def _normalize_profile(profile: dict) -> dict:
    merged = {**PROFILE_DEFAULTS, **profile}
    merged.pop("password", None)
    return merged


def _extract_plaintext_passwords(profiles: list[dict]) -> tuple[list[dict], bool]:
    # Move any inline "password" field into the keyring and drop it from the profile.
    changed = False
    cleaned: list[dict] = []
    for p in profiles:
        if "password" in p:
            pw = p.get("password", "")
            if pw:
                _store_password(p, pw)
            p = {k: v for k, v in p.items() if k != "password"}
            changed = True
        cleaned.append(p)
    return cleaned, changed


def load() -> dict:
    _migrate_legacy_location()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            merged = {**DEFAULTS, **_migrate(data)}
            profiles = merged.get("profiles", [])
            profiles, changed = _extract_plaintext_passwords(profiles)
            merged["profiles"] = [_normalize_profile(p) for p in profiles]
            if changed:
                save(merged)
            return merged
        except (OSError, ValueError):
            pass
    save(DEFAULTS)
    return DEFAULTS.copy()


def save(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def get_active(cfg: dict) -> dict | None:
    profiles = cfg.get("profiles") or []
    if not profiles:
        return None
    idx = cfg.get("active_profile", 0)
    if idx < 0 or idx >= len(profiles):
        idx = 0
    return profiles[idx]


def has_profiles(cfg: dict) -> bool:
    return bool(cfg.get("profiles"))


def add_profile(profile: dict) -> dict:
    cfg = load()
    password = profile.get("password", "")
    normalized = _normalize_profile(profile)
    _store_password(normalized, password)
    cfg.setdefault("profiles", []).append(normalized)
    cfg["active_profile"] = len(cfg["profiles"]) - 1
    save(cfg)
    return cfg


def update_profile(idx: int, patch: dict) -> dict:
    cfg = load()
    profiles = cfg.get("profiles") or []
    if 0 <= idx < len(profiles):
        password = patch.get("password", "")
        merged = _normalize_profile({**profiles[idx], **patch})
        if password:
            _store_password(merged, password)
        profiles[idx] = merged
        save(cfg)
    return cfg


def remove_profile(idx: int) -> dict:
    cfg = load()
    profiles = cfg.get("profiles") or []
    if 0 <= idx < len(profiles):
        removed = profiles.pop(idx)
        _delete_password(removed.get("server", ""), removed.get("username", ""))
    cfg["profiles"] = profiles
    active = cfg.get("active_profile", 0)
    if active >= len(profiles):
        active = max(0, len(profiles) - 1)
    cfg["active_profile"] = active
    save(cfg)
    return cfg


def set_active(idx: int) -> dict:
    cfg = load()
    profiles = cfg.get("profiles") or []
    if 0 <= idx < len(profiles):
        cfg["active_profile"] = idx
        save(cfg)
    return cfg


def remove_active() -> dict:
    cfg = load()
    return remove_profile(cfg.get("active_profile", 0))
