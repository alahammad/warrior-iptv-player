# PyInstaller runtime hook — macOS only.
# Makes the bundled libmpv.dylib visible to ctypes before python-mpv loads it.
import os
import sys

if sys.platform == "darwin" and hasattr(sys, "_MEIPASS"):
    _meipass = sys._MEIPASS
    _existing = os.environ.get("DYLD_LIBRARY_PATH", "")
    os.environ["DYLD_LIBRARY_PATH"] = (
        _meipass + (":" + _existing if _existing else "")
    )
