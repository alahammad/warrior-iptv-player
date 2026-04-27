import logging
from collections import OrderedDict

import requests
from PySide6.QtCore import (
    QByteArray,
    QBuffer,
    QIODevice,
    QObject,
    QRunnable,
    QThreadPool,
    Signal,
    QSize,
    Qt,
)
from PySide6.QtGui import QImage, QImageReader, QPixmap


_log = logging.getLogger(__name__)

_pool: QThreadPool | None = None
_api_pool: QThreadPool | None = None

_IMAGE_CACHE_LIMIT_BYTES = 96 * 1024 * 1024
_image_cache: OrderedDict[tuple[str, tuple[int, int] | None], QPixmap] = OrderedDict()
_image_cache_bytes = 0
_image_pending: dict[tuple[str, tuple[int, int] | None], list] = {}
_shutting_down = False


class _GuiDispatcher(QObject):
    invoke = Signal(object)

    def __init__(self):
        super().__init__()
        self.invoke.connect(self._run, Qt.QueuedConnection)

    def _run(self, fn):
        fn()


_gui_dispatcher = _GuiDispatcher()


def _dispatch_gui(fn):
    _gui_dispatcher.invoke.emit(fn)


def _estimate_pixmap_bytes(pm: QPixmap) -> int:
    img = pm.toImage()
    return max(1, img.width() * img.height() * max(1, img.depth() // 8))


def _evict_image_cache():
    global _image_cache_bytes
    while _image_cache and _image_cache_bytes > _IMAGE_CACHE_LIMIT_BYTES:
        _, pm = _image_cache.popitem(last=False)
        _image_cache_bytes -= _estimate_pixmap_bytes(pm)


def _cache_put(key: tuple[str, tuple[int, int] | None], pm: QPixmap):
    global _image_cache_bytes
    if key in _image_cache:
        old = _image_cache.pop(key)
        _image_cache_bytes -= _estimate_pixmap_bytes(old)
    _image_cache[key] = pm
    _image_cache_bytes += _estimate_pixmap_bytes(pm)
    _evict_image_cache()


def _cache_get(key: tuple[str, tuple[int, int] | None]) -> QPixmap | None:
    pm = _image_cache.pop(key, None)
    if pm is None:
        return None
    _image_cache[key] = pm
    return pm


def _normalize_size(size_hint: tuple[int, int] | None) -> tuple[int, int] | None:
    if not size_hint:
        return None
    w, h = size_hint
    if w <= 0 or h <= 0:
        return None
    # Bucket to reduce duplicate cache variants from near-identical sizes.
    return (max(32, ((w + 31) // 32) * 32), max(32, ((h + 31) // 32) * 32))


def _get_pool() -> QThreadPool:
    global _pool
    if _pool is None:
        _pool = QThreadPool.globalInstance()
        _pool.setMaxThreadCount(6)
    return _pool


def _get_api_pool() -> QThreadPool:
    global _api_pool
    if _api_pool is None:
        _api_pool = QThreadPool()
        _api_pool.setMaxThreadCount(3)
    return _api_pool


def shutdown_workers(timeout_ms: int = 500) -> bool:
    global _shutting_down
    _shutting_down = True
    _image_pending.clear()
    _active_runners.clear()

    ok = True
    if _pool is not None:
        _pool.clear()
        ok = _pool.waitForDone(timeout_ms) and ok
    if _api_pool is not None:
        _api_pool.clear()
        ok = _api_pool.waitForDone(timeout_ms) and ok
    return ok


class WorkerSignals(QObject):
    done = Signal(object)
    error = Signal(str)

    def emit_done(self, payload):
        try:
            self.done.emit(payload)
        except RuntimeError:
            pass

    def emit_error(self, message: str):
        try:
            self.error.emit(message)
        except RuntimeError:
            pass


class FuncRunner(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.setAutoDelete(False)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        if _shutting_down:
            return
        try:
            result = self.fn(*self.args, **self.kwargs)
            if _shutting_down:
                return
            self.signals.emit_done(result)
        except Exception as e:
            # Expected network/IO errors — no traceback spam, just a debug line.
            # The error message is forwarded to on_error which shows it in the UI.
            if isinstance(e, (ConnectionError, TimeoutError, OSError)):
                _log.debug("run_async %s: %s", getattr(self.fn, "__name__", "<fn>"), e)
            else:
                _log.exception("run_async task failed in %s", getattr(self.fn, "__name__", "<fn>"))
            self.signals.emit_error(str(e))


_active_runners: list[QRunnable] = []


def run_async(fn, on_done=None, on_error=None, *args, **kwargs):
    if _shutting_down:
        return
    runner = FuncRunner(fn, *args, **kwargs)

    def _cleanup(*_a):
        try:
            _active_runners.remove(runner)
        except ValueError:
            pass

    if on_done:
        runner.signals.done.connect(on_done)
    if on_error:
        runner.signals.error.connect(on_error)
    runner.signals.done.connect(_cleanup)
    runner.signals.error.connect(_cleanup)
    _active_runners.append(runner)
    _get_api_pool().start(runner)


class _ImageRunner(QRunnable):
    def __init__(self, url: str, cache_size: tuple[int, int] | None):
        super().__init__()
        self.setAutoDelete(False)
        self.url = url
        self.cache_size = cache_size
        self.signals = WorkerSignals()

    def run(self):
        if _shutting_down:
            return
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            try:
                r = requests.get(self.url, timeout=(1.5, 3), headers=headers)
                r.raise_for_status()
            except requests.RequestException as e:
                # Many IPTV servers provide https:// URLs but only support HTTP,
                # causing timeouts and clogged thread pools. Try HTTP fallback.
                if self.url.startswith("https://"):
                    fallback_url = "http://" + self.url[8:]
                    r = requests.get(fallback_url, timeout=(1.5, 3), headers=headers)
                    r.raise_for_status()
                else:
                    raise e
            
            if _shutting_down:
                return

            raw = QByteArray(r.content)
            img = QImage()
            if self.cache_size:
                buf = QBuffer()
                buf.setData(raw)
                buf.open(QIODevice.ReadOnly)
                reader = QImageReader(buf)
                source_size = reader.size()
                if source_size.isValid():
                    source = QSize(source_size.width(), source_size.height())
                    target = QSize(*self.cache_size)
                    scaled = source.scaled(target, Qt.KeepAspectRatio)
                    reader.setScaledSize(scaled)
                img = reader.read()
            if img.isNull():
                img.loadFromData(raw)
            if _shutting_down:
                return
            self.signals.emit_done(img)
        except Exception as e:
            _log.debug("image load failed for %s: %s", self.url, e)
            self.signals.emit_error(str(e))


def load_image(url: str, callback, size_hint: tuple[int, int] | None = None):
    if not url or _shutting_down:
        return

    cache_size = _normalize_size(size_hint)
    cache_key = (url, cache_size)

    cached = _cache_get(cache_key)
    if cached is not None:
        _dispatch_gui(lambda pm=cached: callback(pm))
        return

    if cache_key in _image_pending:
        _image_pending[cache_key].append(callback)
        return

    _image_pending[cache_key] = [callback]
    runner = _ImageRunner(url, cache_size)

    def _done(img: QImage):
        def _deliver():
            pm = QPixmap.fromImage(img)
            if not pm.isNull():
                _cache_put(cache_key, pm)
            for cb in _image_pending.pop(cache_key, []):
                try:
                    cb(pm)
                except Exception:
                    pass
            try:
                _active_runners.remove(runner)
            except ValueError:
                pass

        _dispatch_gui(_deliver)

    def _err(_msg: str):
        def _cleanup():
            _image_pending.pop(cache_key, None)
            try:
                _active_runners.remove(runner)
            except ValueError:
                pass

        _dispatch_gui(_cleanup)

    runner.signals.done.connect(_done)
    runner.signals.error.connect(_err)
    _active_runners.append(runner)
    _get_pool().start(runner)
