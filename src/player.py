import logging
import os
import sys

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QPoint, QParallelAnimationGroup, QPropertyAnimation, QSignalBlocker, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSizePolicy,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from paths import APP_DIR, RESOURCE_DIR

# Windows: add dll directories so mpv-2.dll is found
_dll_dirs = {str(APP_DIR), str(RESOURCE_DIR)}
os.environ["PATH"] = os.pathsep.join(_dll_dirs) + os.pathsep + os.environ.get("PATH", "")
if hasattr(os, "add_dll_directory"):
    for _d in _dll_dirs:
        try:
            os.add_dll_directory(_d)
        except (OSError, FileNotFoundError):
            pass

# macOS: add Homebrew library paths so libmpv.dylib is found
if sys.platform == "darwin":
    _mac_lib_dirs = ["/opt/homebrew/lib", "/usr/local/lib"]
    _existing_dyld = os.environ.get("DYLD_LIBRARY_PATH", "")
    _extra = os.pathsep.join(d for d in _mac_lib_dirs if os.path.isdir(d))
    if _extra:
        os.environ["DYLD_LIBRARY_PATH"] = (
            _extra + (os.pathsep + _existing_dyld if _existing_dyld else "")
        )


def _asset_path(*parts: str) -> str:
    return str(RESOURCE_DIR.joinpath(*parts))

try:
    import mpv

    MPV_AVAILABLE = True
    MPV_IMPORT_ERROR = ""
except Exception as exc:
    mpv = None
    MPV_AVAILABLE = False
    MPV_IMPORT_ERROR = str(exc)


_log = logging.getLogger(__name__)
_mpv_log = logging.getLogger("mpv")
_MPV_LEVELS = {
    "fatal": logging.CRITICAL,
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "info": logging.INFO,
    "status": logging.INFO,
    "v": logging.DEBUG,
    "debug": logging.DEBUG,
    "trace": logging.DEBUG,
}


def _mpv_log_handler(level: str, prefix: str, text: str) -> None:
    if not _mpv_log.isEnabledFor(logging.WARNING) and level not in ("fatal", "error"):
        return
    _mpv_log.log(_MPV_LEVELS.get(level, logging.INFO), "%s: %s", prefix, text.rstrip())


class MpvPlayerOverlay(QWidget):
    closed = Signal()
    SEEK_SCALE = 1000
    SPEED_STEPS = (0.75, 1.0, 1.25, 1.5, 1.75, 2.0)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("playerOverlay")
        self.setMouseTracking(True)
        self.hide()

        self._mpv = None
        self._is_live = False
        self._playlist: list[dict] = []
        self._index = 0
        self._controls_visible = True
        self._saved_volume = 100
        self._duration = 0.0
        self._seeking = False
        self._loading_visible = False
        self._loading_base_text = "Loading stream"
        self._loading_dots = 0
        self._waiting_for_start = False
        self._playback_rate = 1.0
        self._controls_target_visible = True
        self._controls_hide_ms = 3200
        self._controls_hide_live_ms = 4400
        self._controls_hide_paused_ms = 6800
        self._top_bar_height = 0
        self._bottom_bar_height = 0
        self._top_slide_offset = 12
        self._bottom_slide_offset = 20
        self._controls_anim_ms = 210
        self.setFocusPolicy(Qt.StrongFocus)

        self._controls_timer = QTimer(self)
        self._controls_timer.setSingleShot(True)
        self._controls_timer.setInterval(self._controls_hide_ms)
        self._controls_timer.timeout.connect(self._hide_controls)

        self._position_timer = QTimer(self)
        self._position_timer.setInterval(300)
        self._position_timer.timeout.connect(self._sync_playback_ui)

        self._loading_anim_timer = QTimer(self)
        self._loading_anim_timer.setInterval(380)
        self._loading_anim_timer.timeout.connect(self._tick_loading_indicator)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.top_bar = QWidget(self)
        self.top_bar.setObjectName("playerTopBar")
        top = QHBoxLayout(self.top_bar)
        top.setContentsMargins(22, 16, 22, 12)
        top.setSpacing(14)

        self.title_label = QLabel("")
        self.title_label.setObjectName("playerTitle")
        self.title_label.setWordWrap(False)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(self.title_label)

        top.addStretch()

        self.close_btn = self._make_icon_button(
            "close",
            self.stop_and_hide,
            object_name="playerCloseBtn",
            button_size=QSize(48, 38),
            icon_size=QSize(16, 16),
            tooltip="Close player",
            fallback="X",
        )
        top.addWidget(self.close_btn)
        self.video = QWidget(self)
        self.video.setObjectName("playerVideoSurface")
        self.video.setAttribute(Qt.WA_NativeWindow)
        self.video.setMouseTracking(True)
        layout.addWidget(self.video, 1)

        self.loading_panel = QWidget(self)
        self.loading_panel.setObjectName("playerLoadingPanel")
        self.loading_panel.setAttribute(Qt.WA_TransparentForMouseEvents)
        loading_layout = QVBoxLayout(self.loading_panel)
        loading_layout.setContentsMargins(20, 18, 20, 18)
        loading_layout.setSpacing(6)

        self.loading_title = QLabel("Loading stream", self.loading_panel)
        self.loading_title.setObjectName("playerLoadingTitle")
        self.loading_title.setAlignment(Qt.AlignCenter)
        loading_layout.addWidget(self.loading_title)

        self.loading_subtitle = QLabel("Preparing playback...", self.loading_panel)
        self.loading_subtitle.setObjectName("playerLoadingSubtitle")
        self.loading_subtitle.setAlignment(Qt.AlignCenter)
        loading_layout.addWidget(self.loading_subtitle)
        self.loading_panel.hide()

        self.bottom_bar = QWidget(self)
        self.bottom_bar.setObjectName("playerControlsBar")
        bottom_outer = QVBoxLayout(self.bottom_bar)
        bottom_outer.setContentsMargins(22, 14, 22, 18)
        bottom_outer.setSpacing(12)

        self.seek_row = QHBoxLayout()
        self.seek_row.setSpacing(12)

        self.current_time_label = QLabel("00:00")
        self.current_time_label.setObjectName("playerTimeLabel")
        self.seek_row.addWidget(self.current_time_label)

        self.seek_slider = ClickSeekSlider(Qt.Horizontal)
        self.seek_slider.setObjectName("playerSeekSlider")
        self.seek_slider.setCursor(Qt.PointingHandCursor)
        self.seek_slider.setMouseTracking(True)
        self.seek_slider.setRange(0, self.SEEK_SCALE)
        self.seek_slider.setValue(0)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.valueChanged.connect(self._on_seek_value_changed)
        self.seek_row.addWidget(self.seek_slider, 1)

        self.duration_label = QLabel("00:00")
        self.duration_label.setObjectName("playerTimeLabel")
        self.seek_row.addWidget(self.duration_label)
        bottom_outer.addLayout(self.seek_row)

        self.seek_preview = QLabel("", self.bottom_bar)
        self.seek_preview.setObjectName("playerSeekPreview")
        self.seek_preview.hide()

        self.controls_row = QHBoxLayout()
        self.controls_row.setSpacing(12)
        self.controls_row.addStretch()

        self.prev_btn = self._make_control_button("prev", self.play_prev, tooltip="Previous item", fallback="<<")
        self.play_btn = self._make_control_button(
            "pause",
            self._toggle_pause,
            primary=True,
            tooltip="Play or pause",
            fallback="||",
        )
        self.next_btn = self._make_control_button("next", self.play_next, tooltip="Next item", fallback=">>")
        self.fs_btn = self._make_control_button(
            "fullscreen-enter",
            self.toggle_fullscreen,
            tooltip="Toggle fullscreen",
            fallback="",
        )
        self.mute_btn = self._make_control_button("volume", self.toggle_mute, tooltip="Mute", fallback="VOL")

        self.controls_row.addWidget(self.prev_btn)
        self.controls_row.addWidget(self.play_btn)
        self.controls_row.addWidget(self.next_btn)
        self.controls_row.addSpacing(14)
        self.controls_row.addWidget(self.mute_btn)

        self.rate_btn = QPushButton("1.0x", self.bottom_bar)
        self.rate_btn.setObjectName("playerRateBtn")
        self.rate_btn.setCursor(Qt.PointingHandCursor)
        self.rate_btn.setToolTip("Playback speed")
        self.rate_btn.clicked.connect(self._cycle_playback_rate)
        self.controls_row.addWidget(self.rate_btn)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setObjectName("playerVolumeSlider")
        self.volume_slider.setCursor(Qt.PointingHandCursor)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(140)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.controls_row.addWidget(self.volume_slider)

        self.volume_value = QLabel("100%")
        self.volume_value.setObjectName("playerVolumeValue")
        self.controls_row.addWidget(self.volume_value)

        self.controls_row.addSpacing(14)
        self.controls_row.addWidget(self.fs_btn)
        self.controls_row.addStretch()
        bottom_outer.addLayout(self.controls_row)

        if parent is not None:
            parent.installEventFilter(self)
            self.setGeometry(parent.rect())

        self._init_control_fade()
        self.installEventFilter(self)
        self.video.installEventFilter(self)
        self.top_bar.installEventFilter(self)
        self.bottom_bar.installEventFilter(self)
        self.seek_slider.installEventFilter(self)
        self._set_seek_enabled(False)
        self._reset_ui_state()
        self._apply_window_mode_state()
        self._show_controls()
        self._update_responsive_controls_layout()

    def _make_icon_button(
        self,
        icon_name: str,
        slot,
        *,
        object_name: str,
        button_size: QSize,
        icon_size: QSize,
        tooltip: str = "",
        fallback: str = "",
        primary: bool = False,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setCursor(Qt.PointingHandCursor)
        btn.setProperty("variant", "primary" if primary else "default")
        btn.setObjectName(object_name)
        btn.setFixedSize(button_size)
        btn.setIconSize(icon_size)
        btn.setToolTip(tooltip)
        btn.clicked.connect(slot)
        self._set_button_icon(btn, icon_name, fallback)
        return btn

    def _make_control_button(
        self,
        icon_name: str,
        slot,
        primary: bool = False,
        tooltip: str = "",
        fallback: str = "",
    ) -> QPushButton:
        return self._make_icon_button(
            icon_name,
            slot,
            object_name="playerControlBtn",
            button_size=QSize(60 if not primary else 78, 44 if not primary else 54),
            icon_size=QSize(20 if not primary else 24, 20 if not primary else 24),
            tooltip=tooltip,
            fallback=fallback,
            primary=primary,
        )

    def _set_button_icon(self, button: QPushButton, icon_name: str, fallback: str = ""):
        icon_path = _asset_path("assets", "player", f"{icon_name}.svg")
        icon = self._load_svg_icon(icon_path, button.iconSize())
        if icon is None:
            button.setIcon(QIcon())
            button.setText(fallback)
            return
        button.setIcon(icon)
        button.setText("")

    def _load_svg_icon(self, path: str, size: QSize) -> QIcon | None:
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return None
        pixmap = QPixmap(max(1, size.width()), max(1, size.height()))
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _update_play_icon(self, paused: bool):
        self._set_button_icon(self.play_btn, "play" if paused else "pause", ">" if paused else "||")

    def _update_fullscreen_icon(self):
        icon_name = "fullscreen-exit" if self.window().isFullScreen() else "fullscreen-enter"
        fallback = ""
        self._set_button_icon(self.fs_btn, icon_name, fallback)

    def _refresh_button_icons(self):
        self._set_button_icon(self.close_btn, "close", "X")
        self._set_button_icon(self.prev_btn, "prev", "<<")
        paused = False
        if self._mpv is not None:
            try:
                paused = bool(self._get_mpv_prop("pause"))
            except Exception:
                paused = False
        self._update_play_icon(paused)
        self._set_button_icon(self.next_btn, "next", ">>")
        self._sync_volume_ui()
        self._update_fullscreen_icon()

    def _update_nav_buttons(self):
        has_playlist = len(self._playlist) > 1
        self.prev_btn.setEnabled(has_playlist and self._index > 0)
        self.next_btn.setEnabled(has_playlist and self._index < len(self._playlist) - 1)

    def _set_button_metrics(self, button: QPushButton, *, primary: bool, compact: bool):
        if primary:
            button.setFixedSize(QSize(70, 50) if compact else QSize(78, 54))
            button.setIconSize(QSize(22, 22) if compact else QSize(24, 24))
        else:
            button.setFixedSize(QSize(52, 40) if compact else QSize(60, 44))
            button.setIconSize(QSize(18, 18) if compact else QSize(20, 20))

    def _apply_window_mode_state(self):
        fullscreen = bool(self.window() and self.window().isFullScreen())
        for widget in (self, self.top_bar, self.bottom_bar):
            widget.setProperty("fullscreen", fullscreen)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _update_responsive_controls_layout(self):
        width = max(320, self.width())
        compact = width < 760
        ultra_compact = width < 560

        self._set_button_metrics(self.play_btn, primary=True, compact=compact)
        self._set_button_metrics(self.prev_btn, primary=False, compact=compact)
        self._set_button_metrics(self.next_btn, primary=False, compact=compact)
        self._set_button_metrics(self.mute_btn, primary=False, compact=compact)
        self._set_button_metrics(self.fs_btn, primary=False, compact=compact)
        self.close_btn.setFixedSize(QSize(42, 34) if compact else QSize(48, 38))
        self.close_btn.setIconSize(QSize(14, 14) if compact else QSize(16, 16))
        self.rate_btn.setFixedHeight(40 if compact else 44)
        self.rate_btn.setFixedWidth(58 if compact else 64)
        self.seek_row.setSpacing(8 if compact else 12)
        self.controls_row.setSpacing(8 if compact else 12)

        self.prev_btn.setVisible(not ultra_compact)
        self.next_btn.setVisible(not ultra_compact)
        self.volume_slider.setVisible(not ultra_compact)
        self.rate_btn.setVisible((not ultra_compact) and (not self._is_live))

        if ultra_compact:
            volume_width = 0
            self.volume_value.hide()
        elif width < 760:
            volume_width = 78
            self.volume_value.hide()
        elif width < 940:
            volume_width = 104
            self.volume_value.show()
        else:
            volume_width = 140
            self.volume_value.show()
        if not ultra_compact:
            self.volume_slider.setFixedWidth(volume_width)
        rate_width = 0 if ultra_compact or self._is_live else self.rate_btn.width() + 12
        reserved_width = 180 + (0 if ultra_compact else volume_width) + rate_width
        self.title_label.setMaximumWidth(max(160, width - reserved_width))
        self._refresh_button_icons()

    def _controls_hide_interval(self) -> int:
        if self._mpv is not None:
            try:
                if bool(self._get_mpv_prop("pause")):
                    return self._controls_hide_paused_ms
            except Exception:
                pass
        return self._controls_hide_live_ms if self._is_live else self._controls_hide_ms

    def _sync_rate_ui(self):
        self.rate_btn.setText(f"{self._playback_rate:g}x")
        self.rate_btn.setVisible(not self._is_live)

    def _set_playback_rate(self, value: float):
        self._playback_rate = value
        self._sync_rate_ui()
        if self._mpv is None:
            return
        try:
            self._mpv["speed"] = value
        except Exception:
            pass

    def _cycle_playback_rate(self):
        if self._is_live:
            return
        try:
            idx = self.SPEED_STEPS.index(self._playback_rate)
        except ValueError:
            idx = 1
        idx = (idx + 1) % len(self.SPEED_STEPS)
        self._set_playback_rate(self.SPEED_STEPS[idx])
        self._show_controls()
        self._arm_controls_hide()

    def _seek_value_from_position(self, pos_x: int) -> int:
        option = QStyleOptionSlider()
        self.seek_slider.initStyleOption(option)
        return QStyle.sliderValueFromPosition(
            self.seek_slider.minimum(),
            self.seek_slider.maximum(),
            max(0, min(self.seek_slider.width(), pos_x)),
            max(1, self.seek_slider.width()),
            option.upsideDown,
        )

    def _show_seek_preview(self, value: int):
        if self._is_live or self._duration <= 0 or not self.seek_slider.isEnabled():
            self.seek_preview.hide()
            return
        preview = (value / self.SEEK_SCALE) * self._duration
        self.seek_preview.setText(self._format_time(preview))
        self.seek_preview.adjustSize()
        option = QStyleOptionSlider()
        self.seek_slider.initStyleOption(option)
        handle_rect = self.seek_slider.style().subControlRect(
            QStyle.CC_Slider,
            option,
            QStyle.SC_SliderHandle,
            self.seek_slider,
        )
        x = self.seek_slider.x() + handle_rect.center().x() - self.seek_preview.width() // 2
        y = self.seek_slider.y() - self.seek_preview.height() - 10
        x = max(10, min(self.bottom_bar.width() - self.seek_preview.width() - 10, x))
        self.seek_preview.move(x, max(4, y))
        self.seek_preview.show()
        self.seek_preview.raise_()

    def _hide_seek_preview(self):
        self.seek_preview.hide()

    def _reposition_loading_panel(self):
        self.loading_panel.adjustSize()
        x = max(16, (self.width() - self.loading_panel.width()) // 2)
        y = max(16, (self.height() - self.loading_panel.height()) // 2)
        self.loading_panel.move(x, y)

    def _set_loading_state(self, visible: bool, title: str | None = None, subtitle: str | None = None):
        if title is not None:
            self._loading_base_text = title
        if subtitle is not None:
            self.loading_subtitle.setText(subtitle)
        self._loading_visible = visible
        if visible:
            self._loading_dots = 0
            self.loading_title.setText(self._loading_base_text)
            self._reposition_loading_panel()
            self.loading_panel.show()
            self.loading_panel.raise_()
            self._loading_anim_timer.start()
        else:
            self.loading_panel.hide()
            self._loading_anim_timer.stop()

    def _tick_loading_indicator(self):
        if not self._loading_visible:
            return
        self._loading_dots = (self._loading_dots + 1) % 4
        self.loading_title.setText(f"{self._loading_base_text}{'.' * self._loading_dots}")
        self._reposition_loading_panel()

    def _control_positions(self) -> tuple[QPoint, QPoint, QPoint, QPoint]:
        top_visible = QPoint(0, 0)
        top_hidden = QPoint(0, -self._top_slide_offset)
        bottom_visible = QPoint(0, max(0, self.height() - self._bottom_bar_height))
        bottom_hidden = QPoint(0, self.height() + self._bottom_slide_offset)
        return top_visible, top_hidden, bottom_visible, bottom_hidden

    def _layout_overlay_controls(self):
        self._refresh_control_metrics()
        self.top_bar.setFixedWidth(self.width())
        self.bottom_bar.setFixedWidth(self.width())

    def _refresh_control_metrics(self):
        self._top_bar_height = max(1, self.top_bar.sizeHint().height())
        self._bottom_bar_height = max(1, self.bottom_bar.sizeHint().height())
        self.top_bar.setFixedHeight(self._top_bar_height)
        self.bottom_bar.setFixedHeight(self._bottom_bar_height)

    def _apply_control_positions(self, visible: bool):
        self._layout_overlay_controls()
        top_visible, top_hidden, bottom_visible, bottom_hidden = self._control_positions()
        self.top_bar.move(top_visible if visible else top_hidden)
        self.bottom_bar.move(bottom_visible if visible else bottom_hidden)

    def _init_control_fade(self):
        self._refresh_control_metrics()

        self.top_bar_opacity = QGraphicsOpacityEffect(self.top_bar)
        self.top_bar.setGraphicsEffect(self.top_bar_opacity)
        self.top_bar_opacity.setOpacity(1.0)

        self.bottom_bar_opacity = QGraphicsOpacityEffect(self.bottom_bar)
        self.bottom_bar.setGraphicsEffect(self.bottom_bar_opacity)
        self.bottom_bar_opacity.setOpacity(1.0)

        self._controls_fade = QParallelAnimationGroup(self)
        self._top_fade = QPropertyAnimation(self.top_bar_opacity, b"opacity", self)
        self._bottom_fade = QPropertyAnimation(self.bottom_bar_opacity, b"opacity", self)
        self._top_pos = QPropertyAnimation(self.top_bar, b"pos", self)
        self._bottom_pos = QPropertyAnimation(self.bottom_bar, b"pos", self)
        for anim in (self._top_fade, self._bottom_fade, self._top_pos, self._bottom_pos):
            anim.setDuration(self._controls_anim_ms)
            self._controls_fade.addAnimation(anim)
        self._top_fade.setEasingCurve(QEasingCurve.OutCubic)
        self._bottom_fade.setEasingCurve(QEasingCurve.OutCubic)
        self._top_pos.setEasingCurve(QEasingCurve.OutCubic)
        self._bottom_pos.setEasingCurve(QEasingCurve.OutCubic)
        self._apply_control_positions(True)
        self.top_bar.raise_()
        self.bottom_bar.raise_()
        self._controls_fade.finished.connect(self._finish_controls_animation)

    def _fade_controls(self, visible: bool):
        self._controls_target_visible = visible
        self._controls_fade.stop()
        if not visible:
            self._hide_seek_preview()
        self._layout_overlay_controls()
        top_visible_pos, top_hidden_pos, bottom_visible_pos, bottom_hidden_pos = self._control_positions()
        start = self.top_bar_opacity.opacity()
        end = 1.0 if visible else 0.0
        top_start_pos = self.top_bar.pos()
        bottom_start_pos = self.bottom_bar.pos()
        top_end_pos = top_visible_pos if visible else top_hidden_pos
        bottom_end_pos = bottom_visible_pos if visible else bottom_hidden_pos
        if visible:
            self.top_bar.show()
            self.bottom_bar.show()
            self.top_bar.raise_()
            self.bottom_bar.raise_()
            if self.top_bar_opacity.opacity() == 0.0:
                top_start_pos = top_hidden_pos
                self.top_bar.move(top_start_pos)
            if self.bottom_bar_opacity.opacity() == 0.0:
                bottom_start_pos = bottom_hidden_pos
                self.bottom_bar.move(bottom_start_pos)
        for anim in (self._top_fade, self._bottom_fade):
            anim.setStartValue(start)
            anim.setEndValue(end)
        self._top_pos.setStartValue(top_start_pos)
        self._top_pos.setEndValue(top_end_pos)
        self._bottom_pos.setStartValue(bottom_start_pos)
        self._bottom_pos.setEndValue(bottom_end_pos)
        self._controls_fade.start()

    def _finish_controls_animation(self):
        if not self._controls_target_visible:
            self.top_bar.hide()
            self.bottom_bar.hide()
            self._apply_control_positions(False)
        else:
            self._apply_control_positions(True)

    def eventFilter(self, obj, ev):
        if obj is self.parent() and ev.type() == QEvent.Resize:
            self.setGeometry(self.parent().rect())
            self._update_responsive_controls_layout()
        elif obj is self.seek_slider:
            if ev.type() in (QEvent.Enter, QEvent.MouseMove, QEvent.HoverMove):
                self._show_controls()
                self._controls_timer.stop()
                if hasattr(ev, "position"):
                    self._show_seek_preview(self._seek_value_from_position(int(ev.position().x())))
            elif ev.type() == QEvent.Leave:
                self._hide_seek_preview()
                self._arm_controls_hide()
        elif obj in (self.top_bar, self.bottom_bar):
            if ev.type() in (QEvent.Enter, QEvent.MouseMove, QEvent.HoverMove):
                self._show_controls()
                self._controls_timer.stop()
            elif ev.type() == QEvent.Leave:
                self._arm_controls_hide()
        elif obj in (self, self.video):
            if ev.type() in (QEvent.Enter, QEvent.MouseMove, QEvent.HoverMove):
                self._show_controls()
                self._arm_controls_hide()
            elif ev.type() == QEvent.Leave and obj is self:
                self._hide_controls()
        return super().eventFilter(obj, ev)

    def _ensure_mpv(self):
        if self._mpv is not None:
            return self._mpv
        if not MPV_AVAILABLE:
            return None
        self._mpv = mpv.MPV(
            wid=int(self.video.winId()),
            log_handler=_mpv_log_handler,
            input_default_bindings=False,
            osc=False,
            hwdec="auto",
            cache="yes",
            demuxer_max_bytes="16MiB",
            demuxer_max_back_bytes="8MiB",
            network_timeout=15,
            user_agent="Mozilla/5.0",
            keep_open="yes",
        )
        return self._mpv

    def _dispose_mpv(self):
        if self._mpv is not None:
            try:
                self._mpv.terminate()
            except Exception:
                pass
            self._mpv = None

    def _get_mpv_prop(self, *names):
        if self._mpv is None:
            return None
        for name in names:
            attr_name = name.replace("-", "_")
            try:
                value = getattr(self._mpv, attr_name)
                if value not in (None, ""):
                    return value
            except Exception:
                pass
            for key in (name, attr_name):
                try:
                    value = self._mpv[key]
                    if value not in (None, ""):
                        return value
                except Exception:
                    pass
        return None

    def _get_mpv_number(self, *names) -> float:
        value = self._get_mpv_prop(*names)
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def show_and_play(
        self,
        url: str,
        title: str = "",
        is_live: bool = False,
        playlist: list[dict] | None = None,
        index: int = 0,
    ) -> bool:
        if not MPV_AVAILABLE:
            return False
        player = self._ensure_mpv()
        if player is None:
            return False
        self._playlist = playlist or []
        self._index = index
        self._reset_ui_state()
        self._play_current(url, title, is_live)
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._show_controls()
        self._arm_controls_hide()
        self._position_timer.start()
        return True

    def _play_current(self, url: str, title: str, is_live: bool):
        self._is_live = is_live
        self._duration = 0.0
        self._seeking = False
        self._waiting_for_start = True
        self.title_label.setText(title or "")
        self._update_play_icon(False)
        self.current_time_label.setText("" if is_live else "00:00")
        self.duration_label.setText("" if is_live else "00:00")
        self._set_seek_enabled(not is_live)
        self._set_playback_rate(1.0)
        self._update_responsive_controls_layout()
        self._set_loading_state(True, "Loading stream", "Preparing playback...")

        self._update_nav_buttons()
        _log.info("Playing %s%s: %s", "live " if is_live else "", title or "(untitled)", url)
        try:
            self._mpv.play(url)
            self._mpv["pause"] = False
            self._mpv["mute"] = False
            self._mpv["volume"] = self.volume_slider.value()
            self._mpv["speed"] = self._playback_rate
            self._sync_volume_ui()
        except Exception:
            _log.exception("mpv play failed for %s", url)

    def _reset_ui_state(self):
        self.title_label.setText("")
        self._is_live = False
        self._duration = 0.0
        self._seeking = False
        self._waiting_for_start = False
        self._update_play_icon(False)
        self._update_fullscreen_icon()
        self.current_time_label.setText("00:00")
        self.duration_label.setText("00:00")
        self._set_seek_enabled(False)
        self._playback_rate = 1.0
        blocker = QSignalBlocker(self.seek_slider)
        self.seek_slider.setValue(0)
        del blocker
        self._update_nav_buttons()
        self._sync_volume_ui()
        self._sync_rate_ui()
        self._hide_seek_preview()
        self._set_loading_state(False)
        self._update_responsive_controls_layout()

    def _play_at(self, idx: int):
        if not (0 <= idx < len(self._playlist)):
            return
        item = self._playlist[idx]
        self._index = idx
        self._play_current(item["url"], item.get("title", ""), item.get("is_live", False))

    def _set_seek_enabled(self, enabled: bool):
        self.seek_slider.setEnabled(enabled)
        if not enabled:
            blocker = QSignalBlocker(self.seek_slider)
            self.seek_slider.setValue(0)
            del blocker

    def _show_controls(self):
        self._controls_visible = True
        self._fade_controls(True)

    def _hide_controls(self):
        if not self.isVisible():
            return
        if self._seeking or self.top_bar.underMouse() or self.bottom_bar.underMouse() or self.seek_slider.underMouse():
            self._arm_controls_hide()
            return
        self._controls_visible = False
        self._fade_controls(False)

    def _arm_controls_hide(self):
        if self.isVisible():
            if self._seeking or self.top_bar.underMouse() or self.bottom_bar.underMouse() or self.seek_slider.underMouse():
                self._controls_timer.stop()
                return
            self._controls_timer.setInterval(self._controls_hide_interval())
            self._controls_timer.start()

    def _format_time(self, seconds: float) -> str:
        total = max(0, int(seconds))
        hours, rem = divmod(total, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _sync_playback_ui(self):
        if self._mpv is None or not self.isVisible():
            return

        duration = self._get_mpv_number("duration")
        time_pos = self._get_mpv_number("time-pos", "time_pos")
        paused_for_cache = bool(self._get_mpv_prop("paused-for-cache", "paused_for_cache"))
        core_idle = bool(self._get_mpv_prop("core-idle", "core_idle"))

        playback_ready = paused_for_cache or time_pos > 0 or duration > 0 or (self._is_live and not core_idle)
        if playback_ready:
            self._waiting_for_start = False

        if paused_for_cache:
            self._set_loading_state(True, "Buffering", "Waiting for more data...")
        elif self._waiting_for_start:
            self._set_loading_state(True, "Loading stream", "Preparing playback...")
        else:
            self._set_loading_state(False)

        if not self._is_live and duration > 0:
            self._duration = duration
            self.duration_label.setText(self._format_time(duration))
            self._set_seek_enabled(True)
        elif not self._is_live:
            self.duration_label.setText("--:--")
            self._set_seek_enabled(False)
        elif self._is_live:
            self.duration_label.setText("")
            self._set_seek_enabled(False)

        if self._is_live:
            self.current_time_label.setText("")
            return

        if self._seeking:
            return

        self.current_time_label.setText(self._format_time(time_pos))
        if self._duration > 0:
            slider_value = int((time_pos / self._duration) * self.SEEK_SCALE)
            slider_value = max(0, min(self.SEEK_SCALE, slider_value))
            blocker = QSignalBlocker(self.seek_slider)
            self.seek_slider.setValue(slider_value)
            del blocker

    def _on_seek_pressed(self):
        self._seeking = True
        self._show_controls()
        self._controls_timer.stop()
        self._show_seek_preview(self.seek_slider.value())

    def _on_seek_released(self):
        if self._mpv is not None and self._duration > 0 and not self._is_live:
            target = (self.seek_slider.value() / self.SEEK_SCALE) * self._duration
            try:
                self._mpv.command("seek", f"{target:.3f}", "absolute+exact")
            except Exception:
                pass
        self._seeking = False
        self._hide_seek_preview()
        self._sync_playback_ui()
        self._arm_controls_hide()

    def _on_seek_value_changed(self, value: int):
        if not self._seeking or self._duration <= 0 or self._is_live:
            return
        preview = (value / self.SEEK_SCALE) * self._duration
        self.current_time_label.setText(self._format_time(preview))
        self._show_seek_preview(value)

    def play_next(self):
        self._play_at(self._index + 1)

    def play_prev(self):
        self._play_at(self._index - 1)

    def toggle_fullscreen(self):
        win = self.window()
        if win.isFullScreen():
            win.showNormal()
        else:
            win.showFullScreen()
        self._apply_window_mode_state()
        self._update_fullscreen_icon()
        self._show_controls()
        self._arm_controls_hide()

    def toggle_mute(self):
        if self._mpv is None:
            return
        try:
            was_muted = bool(self._get_mpv_prop("mute"))
            self._mpv.cycle("mute")
            if was_muted and self.volume_slider.value() == 0:
                self.volume_slider.setValue(max(1, self._saved_volume))
            self._sync_volume_ui()
        except Exception:
            pass

    def _set_volume(self, value: int):
        self._saved_volume = value if value > 0 else self._saved_volume
        self.volume_value.setText(f"{value}%")
        if self._mpv is None:
            return
        try:
            self._mpv["volume"] = value
            self._mpv["mute"] = value == 0
            self._sync_volume_ui()
        except Exception:
            pass

    def _sync_volume_ui(self):
        if self._mpv is None:
            muted = self.volume_slider.value() == 0
        else:
            try:
                muted = bool(self._get_mpv_prop("mute"))
            except Exception:
                muted = self.volume_slider.value() == 0
        self._set_button_icon(self.mute_btn, "mute" if muted else "volume", "MUTE" if muted else "VOL")

    def stop_and_hide(self):
        self._controls_timer.stop()
        self._position_timer.stop()
        self._playlist = []
        self._index = 0
        if self._mpv is not None:
            try:
                self._mpv.command("stop")
            except Exception:
                pass
        if self.window().isFullScreen():
            self.window().showNormal()
        self._apply_window_mode_state()
        self._reset_ui_state()
        self._show_controls()
        self.hide()
        self._dispose_mpv()
        self.closed.emit()

    def _toggle_pause(self):
        if self._mpv is None:
            return
        try:
            self._mpv.cycle("pause")
            paused = bool(self._get_mpv_prop("pause"))
            self._update_play_icon(paused)
            if paused:
                self._set_loading_state(False)
        except Exception:
            pass

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._toggle_pause()
        super().mouseDoubleClickEvent(ev)

    def keyPressEvent(self, ev):
        key = ev.key()
        if key == Qt.Key_Escape:
            self.stop_and_hide()
        elif key == Qt.Key_Space:
            self._toggle_pause()
        elif key == Qt.Key_F:
            self.toggle_fullscreen()
        elif key == Qt.Key_N:
            self.play_next()
        elif key == Qt.Key_P:
            self.play_prev()
        elif key == Qt.Key_M:
            self.toggle_mute()
        elif key == Qt.Key_Up and self._mpv is not None:
            self.volume_slider.setValue(min(100, self.volume_slider.value() + 5))
        elif key == Qt.Key_Down and self._mpv is not None:
            self.volume_slider.setValue(max(0, self.volume_slider.value() - 5))
        elif key in (Qt.Key_Left, Qt.Key_Right) and self._mpv is not None and not self._is_live:
            delta = "10" if key == Qt.Key_Right else "-10"
            self._mpv.command("seek", delta, "relative")
        elif key == Qt.Key_BracketRight:
            self._cycle_playback_rate()
        elif key == Qt.Key_BracketLeft and not self._is_live:
            try:
                idx = self.SPEED_STEPS.index(self._playback_rate)
            except ValueError:
                idx = 1
            idx = (idx - 1) % len(self.SPEED_STEPS)
            self._set_playback_rate(self.SPEED_STEPS[idx])
        else:
            super().keyPressEvent(ev)
        self._show_controls()
        self._arm_controls_hide()

    def closeEvent(self, ev):
        self._position_timer.stop()
        self._dispose_mpv()
        super().closeEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._update_responsive_controls_layout()
        self._layout_overlay_controls()
        if self._controls_fade.state() != QAbstractAnimation.Running:
            self._apply_control_positions(self._controls_visible)
        self._reposition_loading_panel()
        if self.seek_preview.isVisible():
            self._show_seek_preview(self.seek_slider.value())


class ClickSeekSlider(QSlider):
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            option = QStyleOptionSlider()
            self.initStyleOption(option)
            handle_rect = self.style().subControlRect(
                QStyle.CC_Slider,
                option,
                QStyle.SC_SliderHandle,
                self,
            )
            if not handle_rect.contains(ev.position().toPoint()):
                if self.orientation() == Qt.Horizontal:
                    pos = int(ev.position().x())
                    span = self.width()
                else:
                    pos = int(ev.position().y())
                    span = self.height()
                value = QStyle.sliderValueFromPosition(
                    self.minimum(),
                    self.maximum(),
                    pos,
                    span,
                    option.upsideDown,
                )
                self.sliderPressed.emit()
                self.setValue(value)
                self.sliderMoved.emit(value)
                self.sliderReleased.emit()
                ev.accept()
                return
        super().mousePressEvent(ev)
