import logging
import os
import threading
from pathlib import Path

import requests
from PySide6.QtCore import QObject, Qt, Signal

_log = logging.getLogger(__name__)

# Mimic a real video player so IPTV servers don't block the request.
# Many Xtream servers check User-Agent and return 403/520 for plain HTTP clients.
_DOWNLOAD_HEADERS = {
    "User-Agent": "VLC/3.0.20 LibVLC/3.0.20",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Icy-MetaData": "1",
}


def _friendly_error(exc: Exception) -> str:
    """Convert a requests exception into a short, human-readable message."""
    if isinstance(exc, requests.exceptions.HTTPError):
        code = exc.response.status_code if exc.response is not None else 0
        descriptions = {
            403: "Access denied (403) — the server blocked the download.",
            404: "File not found (404) — the stream may have expired.",
            429: "Too many requests (429) — try again in a moment.",
            500: "Server error (500) — the streaming server is having issues.",
            502: "Bad gateway (502) — the streaming server is unreachable.",
            503: "Service unavailable (503) — the server is overloaded.",
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
    ):
        self.download_id = download_id
        self.url = url
        self.dest_path = dest_path
        self._signals = signals
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
            r = requests.get(self.url, stream=True, timeout=(15, 60), headers=_DOWNLOAD_HEADERS)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if self._cancelled:
                        return
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self._signals.progress.emit(self.download_id, downloaded, total)
            if self._cancelled:
                return
            os.replace(tmp_path, self.dest_path)
            self._signals.done.emit(self.download_id, self.dest_path)
        except Exception as exc:
            failed = True
            msg = _friendly_error(exc)
            _log.debug("Download failed id=%s: %s", self.download_id, exc)
            if not self._cancelled:
                self._signals.error.emit(self.download_id, msg)
        finally:
            if self._cancelled or failed:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


class DownloadManager(QObject):
    download_progress = Signal(str, int, int)  # id, bytes_done, total_bytes
    download_done = Signal(str, str)           # id, dest_path
    download_error = Signal(str, str)          # id, message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._signals = _DownloadSignals()
        self._signals.progress.connect(self.download_progress, Qt.QueuedConnection)
        self._signals.done.connect(self._on_done, Qt.QueuedConnection)
        self._signals.error.connect(self._on_error, Qt.QueuedConnection)
        self._tasks: dict[str, _DownloadTask] = {}
        self._counter = 0

    def start_download(self, url: str, dest_path: str) -> str:
        self._counter += 1
        download_id = f"dl_{self._counter}"
        task = _DownloadTask(download_id, url, dest_path, self._signals)
        self._tasks[download_id] = task
        task.start()
        _log.info("Download started id=%s → %s", download_id, dest_path)
        return download_id

    def cancel(self, download_id: str):
        task = self._tasks.pop(download_id, None)
        if task:
            task.cancel()

    def cancel_all(self):
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()

    def _on_done(self, download_id: str, dest_path: str):
        self._tasks.pop(download_id, None)
        self.download_done.emit(download_id, dest_path)

    def _on_error(self, download_id: str, message: str):
        self._tasks.pop(download_id, None)
        self.download_error.emit(download_id, message)

    @property
    def active_count(self) -> int:
        return len(self._tasks)
