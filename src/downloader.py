import logging
import os
import threading
import time

import requests
from PySide6.QtCore import QObject, Qt, Signal

_log = logging.getLogger(__name__)

# Mimic a real video player so IPTV servers don't block the request.
_DOWNLOAD_HEADERS = {
    "User-Agent": "VLC/3.0.20 LibVLC/3.0.20",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Icy-MetaData": "1",
}

# Max download speed in bytes/sec (default 5 MB/s — looks like normal playback,
# not a scraper pulling at line speed). Set to 0 to disable throttling.
DEFAULT_SPEED_LIMIT = 5 * 1024 * 1024  # 5 MB/s

# Only one download runs at a time so the server sees a single stream session.
MAX_CONCURRENT = 1

# Retry config for transient server errors (429 / 503).
_RETRY_STATUSES = {429, 503}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 5.0  # seconds; doubles each attempt


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.HTTPError):
        code = exc.response.status_code if exc.response is not None else 0
        descriptions = {
            403: "Access denied (403) — the server blocked the download.",
            404: "File not found (404) — the stream may have expired.",
            429: "Too many requests (429) — server rate-limited; will retry.",
            500: "Server error (500) — the streaming server is having issues.",
            502: "Bad gateway (502) — the streaming server is unreachable.",
            503: "Service unavailable (503) — server overloaded; will retry.",
            520: "Server error (520) — the streaming server returned an unknown error.",
        }
        return descriptions.get(code, f"Server error ({code}).")
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return "Connection timed out. Check your network."
    if isinstance(exc, requests.exceptions.ReadTimeout):
        return "Download stalled — the server stopped sending data."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "Connection lost. Check your network and try again."
    return str(exc)


class _DownloadSignals(QObject):
    progress = Signal(str, int, int)  # id, bytes_done, total_bytes
    done = Signal(str, str)           # id, dest_path
    error = Signal(str, str)          # id, message


class _DownloadTask:
    def __init__(
        self,
        download_id: str,
        url: str,
        dest_path: str,
        signals: "_DownloadSignals",
        speed_limit: int = DEFAULT_SPEED_LIMIT,
    ):
        self.download_id = download_id
        self.url = url
        self.dest_path = dest_path
        self._signals = signals
        self._speed_limit = speed_limit  # bytes/sec; 0 = unlimited
        self._cancelled = False

    def start(self):
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def cancel(self):
        self._cancelled = True

    def _run(self):
        tmp_path = self.dest_path + ".part"
        failed = False
        try:
            self._download_with_resume(tmp_path)
            if self._cancelled:
                return
            os.replace(tmp_path, self.dest_path)
            self._signals.done.emit(self.download_id, self.dest_path)
        except Exception as exc:
            failed = True
            _log.debug("Download failed id=%s: %s", self.download_id, exc)
            if not self._cancelled:
                self._signals.error.emit(self.download_id, _friendly_error(exc))
        finally:
            if self._cancelled or failed:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _download_with_resume(self, tmp_path: str):
        """Stream to tmp_path, resuming from existing partial file if possible."""
        for attempt in range(_MAX_RETRIES + 1):
            if self._cancelled:
                return

            # Resume: if a .part file already exists, request only the remainder.
            resume_from = 0
            headers = dict(_DOWNLOAD_HEADERS)
            if os.path.exists(tmp_path):
                resume_from = os.path.getsize(tmp_path)
                if resume_from > 0:
                    headers["Range"] = f"bytes={resume_from}-"
                    _log.debug("Resuming id=%s from byte %d", self.download_id, resume_from)

            try:
                r = requests.get(
                    self.url,
                    stream=True,
                    timeout=(15, 60),
                    headers=headers,
                )

                # Server rejected the range request — start over.
                if resume_from > 0 and r.status_code == 200:
                    resume_from = 0

                # Transient errors worth retrying.
                if r.status_code in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                    wait = _RETRY_BASE_DELAY * (2 ** attempt)
                    _log.debug("id=%s got %d, retrying in %.0fs", self.download_id, r.status_code, wait)
                    for _ in range(int(wait * 10)):
                        if self._cancelled:
                            return
                        time.sleep(0.1)
                    continue

                r.raise_for_status()

                total_from_header = int(r.headers.get("content-length", 0))
                total = resume_from + total_from_header if total_from_header else 0
                downloaded = resume_from

                mode = "ab" if resume_from > 0 else "wb"
                with open(tmp_path, mode) as f:
                    self._stream_chunks(r, f, downloaded, total)
                return  # success

            except requests.exceptions.HTTPError:
                raise
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as exc:
                if attempt < _MAX_RETRIES and not self._cancelled:
                    wait = _RETRY_BASE_DELAY * (2 ** attempt)
                    _log.debug("id=%s network error (%s), retrying in %.0fs", self.download_id, exc, wait)
                    for _ in range(int(wait * 10)):
                        if self._cancelled:
                            return
                        time.sleep(0.1)
                else:
                    raise

    def _stream_chunks(self, response, fh, downloaded: int, total: int):
        """Write chunks to fh, honouring speed limit and emitting progress."""
        chunk_size = 65536
        window_start = time.monotonic()
        window_bytes = 0

        for chunk in response.iter_content(chunk_size=chunk_size):
            if self._cancelled:
                return
            if not chunk:
                continue

            fh.write(chunk)
            downloaded += len(chunk)
            window_bytes += len(chunk)

            if total > 0:
                self._signals.progress.emit(self.download_id, downloaded, total)

            # Throttle: if we've sent more than the speed limit allows in the
            # current 1-second window, sleep off the remainder.
            if self._speed_limit > 0:
                elapsed = time.monotonic() - window_start
                if elapsed < 1.0 and window_bytes >= self._speed_limit:
                    time.sleep(max(0.0, 1.0 - elapsed))
                    window_start = time.monotonic()
                    window_bytes = 0
                elif elapsed >= 1.0:
                    window_start = time.monotonic()
                    window_bytes = 0


class DownloadManager(QObject):
    download_progress = Signal(str, int, int)
    download_done = Signal(str, str)
    download_error = Signal(str, str)
    active_count_changed = Signal(int)  # emitted whenever in-flight + queued count changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._signals = _DownloadSignals()
        self._signals.progress.connect(self.download_progress, Qt.QueuedConnection)
        self._signals.done.connect(self._on_done, Qt.QueuedConnection)
        self._signals.error.connect(self._on_error, Qt.QueuedConnection)
        self._tasks: dict[str, _DownloadTask] = {}
        self._queue: list[tuple[str, str, str]] = []  # (id, url, dest)
        self._counter = 0
        self._lock = threading.Lock()

    def start_download(self, url: str, dest_path: str) -> str:
        self._counter += 1
        download_id = f"dl_{self._counter}"
        with self._lock:
            if self._active_count() < MAX_CONCURRENT:
                task = _DownloadTask(download_id, url, dest_path, self._signals)
                self._tasks[download_id] = task
                task.start()
                _log.info("Download started id=%s → %s", download_id, dest_path)
            else:
                # Queue it; will start automatically when a slot opens.
                self._queue.append((download_id, url, dest_path))
                _log.info("Download queued id=%s (slot busy)", download_id)
        self.active_count_changed.emit(self.active_count)
        return download_id

    def cancel(self, download_id: str):
        with self._lock:
            # Remove from queue if not yet started.
            self._queue = [(i, u, d) for i, u, d in self._queue if i != download_id]
            task = self._tasks.pop(download_id, None)
        if task:
            task.cancel()
        self.active_count_changed.emit(self.active_count)

    def cancel_all(self):
        with self._lock:
            self._queue.clear()
            tasks = list(self._tasks.values())
            self._tasks.clear()
        for task in tasks:
            task.cancel()
        self.active_count_changed.emit(0)

    def _active_count(self) -> int:
        return len(self._tasks)

    def _on_done(self, download_id: str, dest_path: str):
        with self._lock:
            self._tasks.pop(download_id, None)
        self.download_done.emit(download_id, dest_path)
        self._start_next()
        self.active_count_changed.emit(self.active_count)

    def _on_error(self, download_id: str, message: str):
        with self._lock:
            self._tasks.pop(download_id, None)
        self.download_error.emit(download_id, message)
        self._start_next()
        self.active_count_changed.emit(self.active_count)

    def _start_next(self):
        with self._lock:
            if not self._queue or self._active_count() >= MAX_CONCURRENT:
                return
            download_id, url, dest_path = self._queue.pop(0)
            task = _DownloadTask(download_id, url, dest_path, self._signals)
            self._tasks[download_id] = task
        task.start()
        _log.info("Download started (from queue) id=%s", download_id)

    @property
    def active_count(self) -> int:
        return len(self._tasks) + len(self._queue)
