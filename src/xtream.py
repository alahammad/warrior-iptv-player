import hashlib
import json
import logging
import requests
from pathlib import Path
from time import time

from paths import profile_cache_dir

log = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 6 * 3600

USER_AGENT = "VLC/3.0.20 LibVLC/3.0.20"


class XtreamClient:
    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        live_ext: str = "ts",
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ):
        self.server = server.rstrip("/")
        self.username = username
        self.password = password
        self.live_ext = live_ext or "ts"
        self.ttl_seconds = ttl_seconds
        self.base_url = f"{self.server}/player_api.php"
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
        })
        self.cache_dir: Path = profile_cache_dir(self.server, self.username)

    def _key(self, action, **params) -> str:
        raw = f"{action}:{sorted(params.items())}"
        return hashlib.sha1(raw.encode()).hexdigest()

    def _cache_path(self, action, **params) -> Path:
        return self.cache_dir / f"{self._key(action, **params)}.json"

    def cache_timestamp(self, action, **params) -> float | None:
        p = self._cache_path(action, **params)
        if p.exists():
            try:
                return json.loads(p.read_text()).get("ts")
            except (OSError, ValueError) as exc:
                log.debug("cache_timestamp read failed: %s", exc)
                return None
        return None

    def purge_cache(self) -> None:
        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
            except OSError as exc:
                log.debug("purge_cache unlink failed: %s", exc)

    def _get(self, action=None, force=False, **params) -> dict | list:
        path = self._cache_path(action, **params)
        if not force and path.exists():
            try:
                payload = json.loads(path.read_text())
                ts = payload.get("ts", 0)
                if time() - ts <= self.ttl_seconds:
                    return payload["data"]
            except (OSError, ValueError, KeyError) as exc:
                log.debug("cache read failed, refetching: %s", exc)
        p = {"username": self.username, "password": self.password}
        if action:
            p["action"] = action
        p.update(params)
        resp = self._session.get(self.base_url, params=p, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        try:
            path.write_text(json.dumps({"ts": time(), "data": data}))
        except OSError as exc:
            log.debug("cache write failed: %s", exc)
        return data

    def get_live_categories(self, force=False): return self._get("get_live_categories", force=force)
    def get_live_streams(self, force=False): return self._get("get_live_streams", force=force)
    def get_vod_categories(self, force=False): return self._get("get_vod_categories", force=force)
    def get_vod_streams(self, force=False): return self._get("get_vod_streams", force=force)
    def get_vod_info(self, vod_id, force=False): return self._get("get_vod_info", force=force, vod_id=vod_id)
    def get_series_categories(self, force=False): return self._get("get_series_categories", force=force)
    def get_series(self, force=False): return self._get("get_series", force=force)
    def get_series_info(self, series_id, force=False): return self._get("get_series_info", force=force, series_id=series_id)
    def get_short_epg(self, stream_id, limit: int = 4, force=False):
        return self._get("get_short_epg", force=force, stream_id=stream_id, limit=limit)

    def authenticate(self) -> dict:
        """Force a fresh player_api call; returns parsed response.

        Raises ConnectionError with a human-readable message on network/HTTP issues.
        """
        p = {"username": self.username, "password": self.password}
        try:
            resp = self._session.get(self.base_url, params=p, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectTimeout:
            raise ConnectionError("Server took too long to respond. Check your connection and try again.")
        except requests.exceptions.ReadTimeout:
            raise ConnectionError("Server stopped responding mid-request. Try again in a moment.")
        except requests.exceptions.SSLError:
            raise ConnectionError("Secure connection to the server failed. The server's certificate may be invalid.")
        except requests.exceptions.ConnectionError as exc:
            msg = str(exc).lower()
            if "getaddrinfo" in msg or "name or service not known" in msg or "nameresolution" in msg:
                raise ConnectionError(f"Couldn't find the server '{self.server}'. Check the address for typos.")
            if "refused" in msg:
                raise ConnectionError(f"Server '{self.server}' refused the connection. Check the port is correct.")
            if "unreachable" in msg:
                raise ConnectionError("Network unreachable. Check your internet connection.")
            raise ConnectionError("Couldn't connect to the server. Check your internet connection and server address.")
        except requests.exceptions.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code == 401 or code == 403:
                raise ConnectionError("Server rejected the credentials.")
            if code == 404:
                raise ConnectionError("Server endpoint not found. The URL may be wrong or this isn't an Xtream server.")
            if 500 <= code < 600:
                raise ConnectionError(f"Server error ({code}). Try again later.")
            raise ConnectionError(f"Unexpected response from server (HTTP {code}).")
        except ValueError:
            raise ConnectionError("Server returned an invalid response. This may not be an Xtream-compatible server.")
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"Network error: {exc}")

    def stream_url(self, stream_type: str, stream_id, ext: str | None = None) -> str:
        type_map = {"live": "live", "vod": "movie", "series": "series"}
        path = type_map.get(stream_type, stream_type)
        if ext is None:
            ext = self.live_ext if stream_type == "live" else "ts"
        return f"{self.server}/{path}/{self.username}/{self.password}/{stream_id}.{ext}"
