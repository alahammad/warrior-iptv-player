"""Tests for the DownloadManager and _DownloadTask."""
import os
import threading
from unittest.mock import MagicMock, patch

import pytest

pyside6 = pytest.importorskip  # alias for clarity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockSignals:
    """Drop-in replacement for _DownloadSignals that works without Qt."""

    class _MockSignal:
        def __init__(self):
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, *args):
            for cb in self._callbacks:
                cb(*args)

    def __init__(self):
        self.progress = self._MockSignal()
        self.done = self._MockSignal()
        self.error = self._MockSignal()


def _fake_response(content: bytes, report_length: bool = True):
    """Build a mock requests.Response that streams content in 1-KB chunks."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    chunks = [content[i : i + 1024] for i in range(0, len(content), 1024)] or [b""]
    resp.iter_content = MagicMock(return_value=iter(chunks))
    resp.headers = {"content-length": str(len(content))} if report_length else {}
    return resp


# ---------------------------------------------------------------------------
# _DownloadTask — uses _MockSignals so no Qt required
# ---------------------------------------------------------------------------

class TestDownloadTask:
    def test_successful_download_creates_file(self, tmp_path):
        from downloader import _DownloadTask

        signals = _MockSignals()
        dest = str(tmp_path / "movie.mp4")
        content = b"fake video content " * 200

        with patch("downloader.requests.get", return_value=_fake_response(content)):
            _DownloadTask("dl_1", "http://x.com/m.mp4", dest, signals)._run()

        assert os.path.exists(dest)
        assert open(dest, "rb").read() == content

    def test_no_partial_file_remains_after_success(self, tmp_path):
        from downloader import _DownloadTask

        dest = str(tmp_path / "movie.mp4")
        content = b"data" * 50

        with patch("downloader.requests.get", return_value=_fake_response(content)):
            _DownloadTask("dl_1", "http://x.com/m.mp4", dest, _MockSignals())._run()

        assert not os.path.exists(dest + ".part")

    def test_cancellation_leaves_no_files(self, tmp_path):
        from downloader import _DownloadTask

        dest = str(tmp_path / "movie.mp4")
        task = _DownloadTask("dl_2", "http://x.com/m.mp4", dest, _MockSignals())
        task._cancelled = True

        with patch("downloader.requests.get", return_value=_fake_response(b"x" * 5000)):
            task._run()

        assert not os.path.exists(dest)
        assert not os.path.exists(dest + ".part")

    def test_http_error_emits_error_signal(self, tmp_path):
        import requests as req
        from downloader import _DownloadTask

        signals = _MockSignals()
        errors = []
        signals.error.connect(lambda id_, msg: errors.append(msg))

        resp = MagicMock()
        resp.raise_for_status.side_effect = req.HTTPError("404")

        with patch("downloader.requests.get", return_value=resp):
            _DownloadTask("dl_3", "http://x.com/m.mp4", str(tmp_path / "m.mp4"), signals)._run()

        assert len(errors) == 1
        assert not os.path.exists(str(tmp_path / "m.mp4"))

    def test_progress_emitted_when_content_length_known(self, tmp_path):
        from downloader import _DownloadTask

        signals = _MockSignals()
        calls = []
        signals.progress.connect(lambda id_, done, total: calls.append((done, total)))

        content = b"A" * 3000
        with patch("downloader.requests.get", return_value=_fake_response(content)):
            _DownloadTask("dl_4", "http://x.com/m.mp4", str(tmp_path / "m.mp4"), signals)._run()

        assert len(calls) > 0
        for done, total in calls:
            assert 0 < done <= total

    def test_no_progress_without_content_length(self, tmp_path):
        from downloader import _DownloadTask

        signals = _MockSignals()
        calls = []
        signals.progress.connect(lambda *a: calls.append(a))

        content = b"B" * 2000
        with patch(
            "downloader.requests.get",
            return_value=_fake_response(content, report_length=False),
        ):
            _DownloadTask("dl_5", "http://x.com/m.mp4", str(tmp_path / "m.mp4"), signals)._run()

        assert calls == []

    def test_done_signal_carries_dest_path(self, tmp_path):
        from downloader import _DownloadTask

        signals = _MockSignals()
        done_args = []
        signals.done.connect(lambda id_, path: done_args.append((id_, path)))

        dest = str(tmp_path / "movie.mp4")
        with patch("downloader.requests.get", return_value=_fake_response(b"ok")):
            _DownloadTask("dl_6", "http://x.com/m.mp4", dest, signals)._run()

        assert done_args == [("dl_6", dest)]


# ---------------------------------------------------------------------------
# DownloadManager — requires Qt; skipped when PySide6 is absent
# ---------------------------------------------------------------------------

PySide6 = pytest.importorskip("PySide6", reason="PySide6 not installed")


@pytest.fixture(scope="module")
def qt_app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class TestDownloadManager:
    def test_initial_active_count_is_zero(self, qt_app):
        from downloader import DownloadManager
        assert DownloadManager().active_count == 0

    def test_start_download_returns_unique_ids(self, tmp_path, qt_app):
        from downloader import DownloadManager

        mgr = DownloadManager()
        with patch("downloader.requests.get", return_value=_fake_response(b"v")):
            id1 = mgr.start_download("http://x.com/a.mp4", str(tmp_path / "a.mp4"))
            id2 = mgr.start_download("http://x.com/b.mp4", str(tmp_path / "b.mp4"))
        assert id1 != id2

    def test_cancel_removes_task(self, tmp_path, qt_app):
        from downloader import DownloadManager

        started = threading.Event()
        released = threading.Event()

        def slow_get(*a, **kw):
            started.set()
            released.wait(timeout=2)
            raise ConnectionError("cancelled")

        mgr = DownloadManager()
        dest = str(tmp_path / "movie.mp4")
        with patch("downloader.requests.get", side_effect=slow_get):
            dl_id = mgr.start_download("http://x.com/m.mp4", dest)
            started.wait(timeout=2)
            mgr.cancel(dl_id)
            released.set()

        assert dl_id not in mgr._tasks

    def test_cancel_all_clears_tasks(self, tmp_path, qt_app):
        from downloader import DownloadManager

        blocker = threading.Event()

        def blocked_get(*a, **kw):
            blocker.wait(timeout=2)
            raise ConnectionError("aborted")

        mgr = DownloadManager()
        with patch("downloader.requests.get", side_effect=blocked_get):
            mgr.start_download("http://x.com/a.mp4", str(tmp_path / "a.mp4"))
            mgr.start_download("http://x.com/b.mp4", str(tmp_path / "b.mp4"))
            mgr.cancel_all()
            blocker.set()

        assert mgr.active_count == 0
