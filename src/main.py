import sys
import os

import devlog
devlog.maybe_enable_from_argv(sys.argv)

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import config
import workers
from downloader import DownloadManager
from pages import ContinueWatchingPage, LiveTVPage, MoviesPage, SeriesDetailPage, SeriesPage
from paths import APP_DIR, RESOURCE_DIR, purge_profile
from player import MpvPlayerOverlay
from xtream import XtreamClient

SIDEBAR_COLLAPSED_WIDTH = 72
SIDEBAR_TOGGLE_SIZE = 34


def _asset_path(*parts: str) -> str:
    return str(RESOURCE_DIR.joinpath(*parts))


def _load_svg_icon(path: str, size: int = 18) -> QIcon:
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return QIcon()
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


class XtreamLoginDialog(QDialog):
    def __init__(self, initial: dict | None = None, title: str = "Sign In"):
        super().__init__()
        self.credentials: dict | None = None
        self._busy = False
        self._pending: tuple | None = None
        self.setWindowTitle(f"Warrior IPTV Player - {title}")
        self.setFixedSize(460, 580)
        self.setObjectName("root")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(12)
        layout.addStretch()

        brand = QLabel("Warrior")
        brand.setObjectName("brand")
        brand.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand)

        subtitle = QLabel("Connect to your Xtream IPTV server")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #a1a1aa; font-size: 13px; padding-bottom: 8px;")
        layout.addWidget(subtitle)

        self.name = QLineEdit()
        self.name.setPlaceholderText("Playlist name (e.g. Home)")
        layout.addWidget(self.name)

        self.server = QLineEdit()
        self.server.setPlaceholderText("Server URL (e.g. http://example.com:8080)")
        layout.addWidget(self.server)

        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        layout.addWidget(self.username)

        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self._submit)
        layout.addWidget(self.password)

        if initial:
            self.name.setText(initial.get("name", ""))
            self.server.setText(initial.get("server", ""))
            self.username.setText(initial.get("username", ""))
            self.password.setText(initial.get("password", ""))

        self.error = QLabel("")
        self.error.setStyleSheet("color: #ef4444; padding: 4px; font-size: 12px;")
        self.error.setAlignment(Qt.AlignCenter)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        self.status_bar_wrap = QWidget()
        self.status_bar_wrap.setObjectName("loginStatusWrap")
        self.status_bar_wrap.setVisible(False)
        status_layout = QVBoxLayout(self.status_bar_wrap)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)

        self.status_label = QLabel("", self.status_bar_wrap)
        self.status_label.setObjectName("loginStatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        status_layout.addWidget(self.status_label)

        self.status_bar = QProgressBar(self.status_bar_wrap)
        self.status_bar.setObjectName("loginProgressBar")
        self.status_bar.setRange(0, 0)
        self.status_bar.setTextVisible(False)
        self.status_bar.setFixedHeight(4)
        status_layout.addWidget(self.status_bar)
        layout.addWidget(self.status_bar_wrap)

        self._status_steps = [
            (0, "Contacting server..."),
            (3000, "Still connecting, please wait..."),
            (8000, "Server is slow to respond. Hang on..."),
            (14000, "Almost at the timeout. Check your server address if this keeps happening."),
        ]
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(False)
        self._status_timer.timeout.connect(self._advance_status)
        self._status_elapsed_ms = 0
        self._status_step_idx = 0

        self.submit_btn = QPushButton("Sign In")
        self.submit_btn.setObjectName("submitBtn")
        self.submit_btn.clicked.connect(self._submit)
        layout.addWidget(self.submit_btn)
        layout.addStretch()

    def _submit(self):
        name = self.name.text().strip()
        server = self.server.text().strip()
        username = self.username.text().strip()
        password = self.password.text()
        if not name or not server or not username or not password:
            self.error.setText("All fields are required")
            return
        if server.startswith("http://") or server.startswith("https://"):
            candidates = [server]
        else:
            candidates = ["https://" + server, "http://" + server]
        self._set_busy(True)
        self._pending = (name, candidates[0], username, password)
        self._probe_candidates = candidates
        self._probe_next(candidates, username, password)

    def _probe_next(self, candidates: list, username: str, password: str):
        server = candidates[0]
        name = self._pending[0]
        self._pending = (name, server, username, password)
        workers.run_async(
            self._probe_credentials,
            on_done=self._on_probe_done,
            on_error=lambda msg, rest=candidates[1:]: self._on_probe_error_chain(msg, rest, username, password),
            server=server,
            username=username,
            password=password,
        )

    def _on_probe_error_chain(self, message: str, remaining: list, username: str, password: str):
        if not self._busy:
            return
        if remaining and self._is_scheme_retryable(message):
            self.status_label.setText(f"Retrying over {remaining[0].split('://', 1)[0].upper()}...")
            self._probe_next(remaining, username, password)
            return
        self._on_probe_error(message)

    @staticmethod
    def _is_scheme_retryable(message: str) -> bool:
        m = message.lower()
        return any(needle in m for needle in (
            "couldn't connect",
            "couldn't find",
            "refused",
            "secure connection",
            "network unreachable",
            "invalid response",
            "server endpoint not found",
            "unexpected response",
        ))

    @staticmethod
    def _probe_credentials(server: str, username: str, password: str) -> dict:
        client = XtreamClient(server, username, password)
        return client.authenticate()

    def _on_probe_done(self, data):
        if not self._busy:
            return
        if not isinstance(data, dict) or "user_info" not in data:
            self._on_probe_error("Unexpected server response")
            return
        status = (data.get("user_info") or {}).get("auth")
        if status in (0, "0"):
            self._on_probe_error("Invalid username or password")
            return
        name, server, username, password = self._pending
        self.credentials = {
            "name": name,
            "server": server,
            "username": username,
            "password": password,
        }
        self.accept()

    def _on_probe_error(self, message: str):
        if not self._busy:
            return
        self.error.setText(f"Sign in failed: {message}")
        self._set_busy(False)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.submit_btn.setEnabled(not busy)
        self.submit_btn.setText("Connecting..." if busy else "Sign In")
        for field in (self.name, self.server, self.username, self.password):
            field.setEnabled(not busy)
        if busy:
            self.error.setText("")
            self._status_elapsed_ms = 0
            self._status_step_idx = 0
            self.status_label.setText(self._status_steps[0][1])
            self.status_bar_wrap.setVisible(True)
            self._status_timer.start(500)
        else:
            self._status_timer.stop()
            self.status_bar_wrap.setVisible(False)

    def _advance_status(self):
        self._status_elapsed_ms += 500
        next_idx = self._status_step_idx + 1
        if next_idx < len(self._status_steps) and self._status_elapsed_ms >= self._status_steps[next_idx][0]:
            self._status_step_idx = next_idx
            self.status_label.setText(self._status_steps[next_idx][1])

    def reject(self):
        if self._busy:
            self._busy = False
        super().reject()


class MainWindow(QMainWindow):
    def __init__(self, cfg: dict, xtream: XtreamClient):
        super().__init__()
        self.config = cfg
        self.xtream = xtream
        self.setWindowTitle("Warrior IPTV Player")
        self.resize(1400, 900)
        self.setMinimumSize(920, 620)
        self._sidebar_labels = ("Live TV", "Movies", "Series", "Continue")
        self._sidebar_expanded = True
        self._sidebar_user_collapsed = False

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setMinimumWidth(164)
        self.sidebar.setMaximumWidth(220)
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        self.sidebar_header = QWidget(self.sidebar)
        self.sidebar_header.setObjectName("sidebarHeader")
        self._header_layout = QHBoxLayout(self.sidebar_header)
        self._header_layout.setContentsMargins(10, 6, 10, 6)
        self._header_layout.setSpacing(8)

        self.brand = QLabel("Warrior")
        self.brand.setObjectName("brand")
        self._header_layout.addWidget(self.brand, 1)

        self.sidebar_toggle = QPushButton(self.sidebar_header)
        self.sidebar_toggle.setObjectName("sidebarToggleBtn")
        self.sidebar_toggle.setCursor(Qt.PointingHandCursor)
        self.sidebar_toggle.setToolTip("Collapse sidebar")
        self.sidebar_toggle.setFixedSize(34, 34)
        self.sidebar_toggle.setIconSize(QPixmap(16, 16).size())
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        self._header_layout.addWidget(self.sidebar_toggle)

        sb_layout.addWidget(self.sidebar_header)

        self.nav_container = QWidget()
        self.nav_container.setObjectName("navContainer")
        nav_layout = QVBoxLayout(self.nav_container)
        nav_layout.setContentsMargins(8, 8, 8, 8)
        nav_layout.setSpacing(4)

        self.nav_buttons: list[QPushButton] = []
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for idx, (icon_name, label) in enumerate((
            ("live-tv.svg", self._sidebar_labels[0]),
            ("movies.svg", self._sidebar_labels[1]),
            ("series.svg", self._sidebar_labels[2]),
            ("continue.svg", self._sidebar_labels[3]),
        )):
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(_load_svg_icon(_asset_path("assets", "sidebar", icon_name), 20))
            btn.setIconSize(QPixmap(20, 20).size())
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(44)
            btn.clicked.connect(lambda _=False, i=idx: self._switch(i))
            self.nav_group.addButton(btn, idx)
            self.nav_buttons.append(btn)
            nav_layout.addWidget(btn)
        self.nav_buttons[0].setChecked(True)
        nav_layout.addStretch(1)

        self.profile_divider = QFrame()
        self.profile_divider.setObjectName("sidebarDivider")
        self.profile_divider.setFrameShape(QFrame.HLine)
        nav_layout.addWidget(self.profile_divider)

        self.profile_label = QLabel("PROFILE")
        self.profile_label.setObjectName("profileSectionLabel")
        nav_layout.addWidget(self.profile_label)

        self.profile_btn = QPushButton()
        self.profile_btn.setObjectName("profileBtn")
        self.profile_btn.setCursor(Qt.PointingHandCursor)
        self.profile_btn.setMinimumHeight(42)
        self.profile_btn.setIcon(_load_svg_icon(_asset_path("assets", "sidebar", "profile.svg"), 18))
        self.profile_btn.setIconSize(QPixmap(18, 18).size())
        self.profile_btn.clicked.connect(self._show_profile_menu)
        nav_layout.addWidget(self.profile_btn)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setObjectName("logoutBtn")
        self.logout_btn.setCursor(Qt.PointingHandCursor)
        self.logout_btn.setMinimumHeight(40)
        self.logout_btn.setToolTip("Sign out of current profile")
        self.logout_btn.setIcon(_load_svg_icon(_asset_path("assets", "sidebar", "logout.svg"), 18))
        self.logout_btn.setIconSize(QPixmap(18, 18).size())
        self.logout_btn.clicked.connect(self._logout)
        nav_layout.addWidget(self.logout_btn)

        sb_layout.addWidget(self.nav_container, 1)

        h.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.live = LiveTVPage(xtream)
        self.live.parent_window = self
        self.movies = MoviesPage(xtream)
        self.movies.parent_window = self
        self.series = SeriesPage(xtream)
        self.series.parent_window = self
        self.series_detail = SeriesDetailPage(xtream, self)
        self.series_detail.back.connect(lambda: self.stack.setCurrentWidget(self.series))
        self.continue_page = ContinueWatchingPage(xtream, self)

        self.stack.addWidget(self.live)
        self.stack.addWidget(self.movies)
        self.stack.addWidget(self.series)
        self.stack.addWidget(self.continue_page)
        self.stack.addWidget(self.series_detail)
        h.addWidget(self.stack, 1)

        self.setStatusBar(QStatusBar())

        focus_search = QShortcut(QKeySequence("Ctrl+F"), self)
        focus_search.activated.connect(self._focus_active_search)
        focus_search_alt = QShortcut(QKeySequence("Ctrl+K"), self)
        focus_search_alt.activated.connect(self._focus_active_search)
        self.player_overlay = None

        self._download_manager = DownloadManager(self)
        self._download_manager.download_progress.connect(self._on_download_progress)
        self._download_manager.download_done.connect(self._on_download_done)
        self._download_manager.download_error.connect(self._on_download_error)
        self._download_dir = str(APP_DIR / "downloads")

        self._sync_sidebar_visuals()
        self._update_responsive_shell()

    def _switch(self, idx: int):
        self.stack.setCurrentIndex(idx)
        if idx == 3:
            self.continue_page.refresh()

    def _focus_active_search(self):
        widget = self.stack.currentWidget()
        search = getattr(widget, "search", None)
        if search is not None:
            search.setFocus()
            search.selectAll()

    def _toggle_sidebar(self):
        self._sidebar_user_collapsed = self._sidebar_expanded
        self._update_responsive_shell()

    def _sync_sidebar_visuals(self):
        expanded = self._sidebar_expanded
        icon_name = "chevron-left.svg" if expanded else "chevron-right.svg"
        self.sidebar_toggle.setIcon(_load_svg_icon(_asset_path("assets", "sidebar", icon_name), 16))
        self.sidebar_toggle.setToolTip("Collapse sidebar" if expanded else "Expand sidebar")
        self.sidebar.setProperty("collapsed", not expanded)
        self.sidebar.style().unpolish(self.sidebar)
        self.sidebar.style().polish(self.sidebar)
        self.brand.setVisible(expanded)
        if expanded:
            self._header_layout.setContentsMargins(10, 6, 10, 6)
        else:
            side = max(0, (SIDEBAR_COLLAPSED_WIDTH - SIDEBAR_TOGGLE_SIZE) // 2)
            self._header_layout.setContentsMargins(side, 6, side, 6)
        for idx, btn in enumerate(self.nav_buttons):
            label = self._sidebar_labels[idx]
            btn.setText(label if expanded else "")
            btn.setToolTip(label)
            btn.setProperty("collapsed", not expanded)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.logout_btn.setText("Logout" if expanded else "")
        self.logout_btn.setProperty("collapsed", not expanded)
        self.logout_btn.style().unpolish(self.logout_btn)
        self.logout_btn.style().polish(self.logout_btn)
        active = config.get_active(self.config) or {}
        active_name = active.get("name", "Profile")
        self.profile_btn.setText(active_name if expanded else "")
        self.profile_btn.setToolTip(f"Profile: {active_name}")
        self.profile_btn.setProperty("collapsed", not expanded)
        self.profile_btn.style().unpolish(self.profile_btn)
        self.profile_btn.style().polish(self.profile_btn)
        self.profile_label.setVisible(expanded)

    def _update_responsive_shell(self):
        width = self.width()
        auto_collapsed = width < 980
        self._sidebar_expanded = False if auto_collapsed else not self._sidebar_user_collapsed
        self._sync_sidebar_visuals()
        if self._sidebar_expanded:
            if width < 1120:
                sidebar_width = 188
            else:
                sidebar_width = 220
        else:
            sidebar_width = SIDEBAR_COLLAPSED_WIDTH
        self.sidebar.setFixedWidth(sidebar_width)

    def open_series(self, show: dict):
        self.series_detail.load(show)
        self.stack.setCurrentWidget(self.series_detail)

    def _ensure_player_overlay(self):
        if self.player_overlay is None:
            overlay = MpvPlayerOverlay(self)
            overlay.closed.connect(self._release_player_overlay)
            self.player_overlay = overlay
        return self.player_overlay

    def _release_player_overlay(self):
        overlay = self.player_overlay
        self.player_overlay = None
        if overlay is not None:
            overlay.deleteLater()

    def play_in_app(
        self,
        url: str,
        title: str,
        is_live: bool,
        playlist: list[dict] | None = None,
        index: int = 0,
    ):
        overlay = self._ensure_player_overlay()
        ok = overlay.show_and_play(url, title, is_live, playlist, index)
        if not ok:
            self.statusBar().showMessage(
                "In-app player unavailable - falling back to VLC",
                4000,
            )
            self._release_player_overlay()
            self.play_in_vlc(url)

    def play_in_vlc(self, url: str):
        import vlc_launcher

        exe = vlc_launcher.find_vlc(self.config.get("vlc_path", ""))
        if not exe:
            QMessageBox.warning(
                self,
                "VLC not found",
                "VLC is not installed.\n\n"
                "Install VLC from https://www.videolan.org/vlc/ "
                "or use the built-in player instead.",
            )
            return
        ok = vlc_launcher.play(url, self.config.get("vlc_path", ""))
        if not ok:
            QMessageBox.warning(
                self,
                "Could not launch VLC",
                "VLC was found but failed to start. Please use the built-in player.",
            )

    def download_movie(self, url: str, title: str, ext: str = "mp4"):
        import re

        safe_title = re.sub(r'[\\/*?:"<>|]', "_", title).strip() or "movie"
        default_name = f"{safe_title}.{ext}"
        os.makedirs(self._download_dir, exist_ok=True)
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Save Movie",
            os.path.join(self._download_dir, default_name),
            f"Video Files (*.{ext});;All Files (*)",
        )
        if not dest:
            return
        self._download_dir = os.path.dirname(dest)
        download_id = self._download_manager.start_download(url, dest)
        self.statusBar().showMessage(
            f"Downloading '{title}'…  (0%)", 0
        )
        self._pending_downloads: dict = getattr(self, "_pending_downloads", {})
        self._pending_downloads[download_id] = {"title": title, "dest": dest}

    def _on_download_progress(self, download_id: str, done: int, total: int):
        pending = getattr(self, "_pending_downloads", {})
        info = pending.get(download_id, {})
        title = info.get("title", download_id)
        pct = int(done / total * 100) if total else 0
        self.statusBar().showMessage(
            f"Downloading '{title}'…  ({pct}%)", 0
        )

    def _on_download_done(self, download_id: str, dest_path: str):
        pending = getattr(self, "_pending_downloads", {})
        info = pending.pop(download_id, {})
        title = info.get("title", download_id)
        self.statusBar().showMessage(
            f"Download complete: '{title}'", 6000
        )

    def _on_download_error(self, download_id: str, message: str):
        pending = getattr(self, "_pending_downloads", {})
        info = pending.pop(download_id, {})
        title = info.get("title", download_id)
        self.statusBar().showMessage(
            f"Download failed for '{title}': {message}", 8000
        )
        QMessageBox.warning(
            self,
            "Download Failed",
            f"Could not download '{title}':\n{message}",
        )

    def _logout(self):
        active = config.get_active(self.config)
        if active:
            purge_profile(active.get("server", ""), active.get("username", ""))
        config.remove_active()
        QApplication.instance().exit(42)
        self.close()

    def _show_profile_menu(self):
        menu = QMenu(self)
        menu.setObjectName("profileMenu")
        profiles = self.config.get("profiles") or []
        active_idx = self.config.get("active_profile", 0)
        for idx, profile in enumerate(profiles):
            label = profile.get("name", f"Profile {idx + 1}")
            if idx == active_idx:
                label = f"  {label}  (active)"
            action = menu.addAction(label)
            action.triggered.connect(lambda _=False, i=idx: self._switch_profile(i))
        if profiles:
            menu.addSeparator()
            rename_action = menu.addAction("Rename active profile")
            rename_action.triggered.connect(self._rename_active_profile)
            if len(profiles) > 1:
                delete_menu = menu.addMenu("Delete profile")
                for idx, profile in enumerate(profiles):
                    act = delete_menu.addAction(profile.get("name", f"Profile {idx + 1}"))
                    act.triggered.connect(lambda _=False, i=idx: self._delete_profile(i))
            menu.addSeparator()
        add_action = menu.addAction("+ Add Profile")
        add_action.triggered.connect(self._add_profile)
        menu.exec(self.profile_btn.mapToGlobal(self.profile_btn.rect().bottomLeft()))

    def _rename_active_profile(self):
        idx = self.config.get("active_profile", 0)
        active = config.get_active(self.config)
        if not active:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename profile", "New name:", text=active.get("name", "")
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        self.config = config.update_profile(idx, {"name": new_name})
        self._sync_sidebar_visuals()

    def _delete_profile(self, idx: int):
        profiles = self.config.get("profiles") or []
        if not (0 <= idx < len(profiles)):
            return
        name = profiles[idx].get("name", f"Profile {idx + 1}")
        resp = QMessageBox.question(
            self,
            "Delete profile",
            f"Delete profile '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        active_idx = self.config.get("active_profile", 0)
        purge_profile(profiles[idx].get("server", ""), profiles[idx].get("username", ""))
        config.remove_profile(idx)
        if idx == active_idx:
            QApplication.instance().exit(42)
            self.close()
        else:
            self.config = config.load()
            self._sync_sidebar_visuals()

    def _switch_profile(self, idx: int):
        if idx == self.config.get("active_profile", 0):
            return
        config.set_active(idx)
        QApplication.instance().exit(42)
        self.close()

    def _add_profile(self):
        dialog = XtreamLoginDialog(title="Add Profile")
        _enable_dark_titlebar(dialog)
        if dialog.exec() != QDialog.Accepted or not dialog.credentials:
            return
        config.add_profile(dialog.credentials)
        QApplication.instance().exit(42)
        self.close()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._update_responsive_shell()


def _enable_dark_titlebar(win):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = int(win.winId())
        value = ctypes.c_int(1)
        dwmapi = ctypes.windll.dwmapi
        for attr in (20, 19):
            if dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(attr),
                ctypes.byref(value),
                ctypes.sizeof(value),
            ) == 0:
                break
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        ctypes.windll.user32.SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(0),
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )
    except Exception:
        pass


def run_app():
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(lambda: workers.shutdown_workers(250))
    qss = (RESOURCE_DIR / "styles.qss").read_text()
    app.setStyleSheet(qss)

    icon_path = RESOURCE_DIR / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    while True:
        cfg = config.load()
        if not config.has_profiles(cfg):
            dialog = XtreamLoginDialog()
            _enable_dark_titlebar(dialog)
            if dialog.exec() != QDialog.Accepted or not dialog.credentials:
                shutdown_ok = workers.shutdown_workers(250)
                return 0, shutdown_ok
            cfg = config.add_profile(dialog.credentials)

        active = config.get_active(cfg)
        if not active:
            continue
        try:
            password = config.get_password(active)
            if not password:
                QMessageBox.critical(
                    None,
                    "Error",
                    "Saved password not found in system keyring. Please sign in again.",
                )
                config.remove_active()
                continue
            xtream = XtreamClient(
                active["server"],
                active["username"],
                password,
                live_ext=active.get("live_ext", "ts"),
            )
        except Exception as exc:
            QMessageBox.critical(None, "Error", f"Failed to init Xtream client: {exc}")
            config.remove_active()
            continue

        win = MainWindow(cfg, xtream)
        _enable_dark_titlebar(win)
        win.show()
        exit_code = app.exec()
        if exit_code == 42:
            continue
        shutdown_ok = workers.shutdown_workers(250)
        return exit_code, shutdown_ok


if __name__ == "__main__":
    code, shutdown_ok = run_app()
    if not shutdown_ok:
        os._exit(code)
    sys.exit(code)
