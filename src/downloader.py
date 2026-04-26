import logging
import os
import threading
from pathlib import Path

import requests
from PySide6.QtCore import QObject, Qt, Signal

_log = logging.getLogger(__name__)


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
        try:
            r = requests.get(self.url, stream=True, timeout=(15, 60))
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
            _log.exception("Download failed for %s", self.url)
            if not self._cancelled:
                self._signals.error.emit(self.download_id, str(exc))
        finally:
            if self._cancelled:
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
