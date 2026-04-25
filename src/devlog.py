import logging
import os
import sys
import threading

_enabled = False

_COLORS = {
    logging.DEBUG: "\033[90m",
    logging.INFO: "\033[36m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;31m",
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        color = _COLORS.get(record.levelno, "")
        if not color:
            return base
        return f"{color}{base}{_RESET}"


def _enable_ansi_on_windows() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        for handle_id in (-11, -12):  # stdout, stderr
            handle = kernel32.GetStdHandle(handle_id)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def is_enabled() -> bool:
    return _enabled


def enable() -> None:
    global _enabled
    if _enabled:
        return
    _enabled = True

    _enable_ansi_on_windows()

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(_ColorFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)

    def _excepthook(exc_type, exc, tb):
        logging.getLogger("uncaught").error(
            "Unhandled exception", exc_info=(exc_type, exc, tb)
        )

    sys.excepthook = _excepthook

    def _thread_excepthook(args):
        logging.getLogger("uncaught.thread").error(
            "Unhandled exception in thread %s" % args.thread.name,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_excepthook

    logging.getLogger(__name__).info("Dev mode enabled")


def maybe_enable_from_argv(argv: list[str]) -> bool:
    if "dev" in argv[1:] or "--dev" in argv[1:]:
        enable()
        return True
    return False
