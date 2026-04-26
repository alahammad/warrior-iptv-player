import os
import subprocess
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.2f} GB"


def _open_folder(path: str):
    folder = os.path.dirname(os.path.abspath(path))
    try:
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception:
        pass


class _DownloadRow(QFrame):
    cancel_requested = Signal(str)

    def __init__(self, download_id: str, title: str, dest: str, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadRow")
        self._download_id = download_id
        self._dest = dest
        self._done = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(6)

        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("downloadTitle")
        self._title_label.setWordWrap(False)
        self._title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        outer.addWidget(self._title_label)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 0, 0, 0)

        self._progress = QProgressBar(self)
        self._progress.setObjectName("downloadProgress")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        row.addWidget(self._progress, 1)

        self._size_label = QLabel("Starting…", self)
        self._size_label.setObjectName("downloadSize")
        self._size_label.setFixedWidth(150)
        self._size_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(self._size_label)

        self._action_btn = QPushButton("✕", self)
        self._action_btn.setObjectName("downloadCancelBtn")
        self._action_btn.setFixedSize(28, 28)
        self._action_btn.setCursor(Qt.PointingHandCursor)
        self._action_btn.setToolTip("Cancel download")
        self._action_btn.clicked.connect(self._on_cancel)
        row.addWidget(self._action_btn)

        outer.addLayout(row)

    def update_progress(self, done_bytes: int, total_bytes: int):
        if total_bytes > 0:
            self._progress.setValue(int(done_bytes / total_bytes * 100))
        self._size_label.setText(f"{_fmt_bytes(done_bytes)} / {_fmt_bytes(total_bytes)}")

    def mark_done(self, dest: str):
        self._done = True
        self._dest = dest
        self._progress.setValue(100)
        size = os.path.getsize(dest) if os.path.exists(dest) else 0
        self._size_label.setText(f"Done  —  {_fmt_bytes(size)}")
        self._action_btn.setText("⏏")
        self._action_btn.setToolTip("Show in folder")
        self._action_btn.setObjectName("downloadOpenBtn")
        self._action_btn.style().unpolish(self._action_btn)
        self._action_btn.style().polish(self._action_btn)
        try:
            self._action_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._action_btn.clicked.connect(lambda: _open_folder(self._dest))

    def mark_error(self, message: str):
        self._progress.setProperty("failed", True)
        self._progress.style().unpolish(self._progress)
        self._progress.style().polish(self._progress)
        short = message[:60] + "…" if len(message) > 60 else message
        self._size_label.setText(f"Failed: {short}")
        self._action_btn.setVisible(False)

    def _on_cancel(self):
        if not self._done:
            self.cancel_requested.emit(self._download_id)
            self.setVisible(False)


class DownloadsPage(QWidget):
    cancel_download = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: dict[str, _DownloadRow] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 24)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Downloads", self)
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()
        self._clear_btn = QPushButton("Clear done", self)
        self._clear_btn.setObjectName("chip")
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_done)
        header.addWidget(self._clear_btn)
        outer.addLayout(header)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content = QWidget(self._scroll)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll, 1)

        self._empty = self._make_empty()
        self._layout.addWidget(self._empty)
        self._layout.addStretch()

    def _make_empty(self) -> QWidget:
        box = QWidget(self._content)
        box.setObjectName("emptyState")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(28, 28, 28, 28)
        lay.setSpacing(8)
        t = QLabel("No downloads yet", box)
        t.setObjectName("emptyStateTitle")
        b = QLabel("Click the DL button on any movie card to save it locally.", box)
        b.setObjectName("emptyStateBody")
        b.setWordWrap(True)
        lay.addWidget(t)
        lay.addWidget(b)
        return box

    def _refresh_empty(self):
        visible_rows = [r for r in self._rows.values() if r.isVisible()]
        self._empty.setVisible(len(visible_rows) == 0)

    def add_download(self, download_id: str, title: str, dest: str):
        row = _DownloadRow(download_id, title, dest, self._content)
        row.cancel_requested.connect(self.cancel_download)
        self._rows[download_id] = row
        # Insert before the stretch (last item)
        self._layout.insertWidget(self._layout.count() - 1, row)
        self._empty.setVisible(False)

    def on_progress(self, download_id: str, done: int, total: int):
        row = self._rows.get(download_id)
        if row:
            row.update_progress(done, total)

    def on_done(self, download_id: str, dest: str):
        row = self._rows.get(download_id)
        if row:
            row.mark_done(dest)

    def on_error(self, download_id: str, message: str):
        row = self._rows.get(download_id)
        if row:
            row.mark_error(message)

    def _clear_done(self):
        for row in list(self._rows.values()):
            if row._done:
                row.setVisible(False)
        self._refresh_empty()

    @property
    def active_count(self) -> int:
        return sum(1 for r in self._rows.values() if r.isVisible() and not r._done)
