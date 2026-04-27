import math
import time

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtCore import QRect
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from workers import load_image


class SkeletonBlock(QFrame):
    def __init__(self, width: int | None = None, height: int = 16, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("skeletonBlock")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if width is not None:
            self.setFixedWidth(width)
        self.setFixedHeight(height)


class PosterCardSkeleton(QFrame):
    def __init__(self, size: tuple[int, int] = (160, 230), show_actions: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("loadingCard")
        total_height = size[1] + (32 if show_actions else 0)
        image_height = max(58, size[1] - 52)
        self.setFixedSize(QSize(size[0], total_height))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        poster = SkeletonBlock(height=image_height, parent=self)
        poster.setObjectName("skeletonPoster")
        layout.addWidget(poster)

        body = QWidget(self)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(6)
        title = SkeletonBlock(width=int(size[0] * 0.78), height=14, parent=body)
        meta = SkeletonBlock(width=int(size[0] * 0.52), height=10, parent=body)
        body_layout.addWidget(title)
        body_layout.addWidget(meta)
        layout.addWidget(body)

        if show_actions:
            actions = QWidget(self)
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(10, 0, 10, 8)
            actions_layout.setSpacing(6)
            actions_layout.addWidget(SkeletonBlock(height=24, parent=actions), 1)
            actions_layout.addWidget(SkeletonBlock(height=24, parent=actions), 1)
            layout.addWidget(actions)


class RowSkeleton(QWidget):
    def __init__(self, card_size: tuple[int, int], show_actions: bool = True, count: int = 6, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 0)
        header.addWidget(SkeletonBlock(width=180, height=18, parent=self))
        header.addStretch()
        header.addWidget(SkeletonBlock(width=82, height=28, parent=self))
        layout.addLayout(header)

        cards = QHBoxLayout()
        cards.setContentsMargins(4, 0, 4, 4)
        cards.setSpacing(8)
        for _ in range(count):
            cards.addWidget(PosterCardSkeleton(card_size, show_actions, parent=self))
        cards.addStretch()
        layout.addLayout(cards)


class HeroSkeleton(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("heroSkeleton")
        self.setFixedHeight(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.addStretch()

        panel = QWidget(self)
        panel.setObjectName("heroPanel")
        panel.setMaximumWidth(620)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 22, 24, 22)
        panel_layout.setSpacing(12)
        panel_layout.addWidget(SkeletonBlock(width=88, height=24, parent=panel))
        panel_layout.addWidget(SkeletonBlock(width=360, height=18, parent=panel))
        panel_layout.addWidget(SkeletonBlock(width=460, height=52, parent=panel))
        panel_layout.addWidget(SkeletonBlock(width=520, height=14, parent=panel))
        panel_layout.addWidget(SkeletonBlock(width=410, height=14, parent=panel))
        panel_layout.addSpacing(4)
        panel_layout.addWidget(SkeletonBlock(width=168, height=46, parent=panel))
        layout.addWidget(panel, 0, Qt.AlignLeft | Qt.AlignBottom)


class EpisodeListSkeleton(QWidget):
    def __init__(self, count: int = 7, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for _ in range(count):
            row = QFrame(self)
            row.setObjectName("episodeRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 12, 14, 12)
            row_layout.setSpacing(8)
            row_layout.addWidget(SkeletonBlock(width=260, height=14, parent=row), 1)
            row_layout.addWidget(SkeletonBlock(width=76, height=28, parent=row))
            row_layout.addWidget(SkeletonBlock(width=60, height=28, parent=row))
            layout.addWidget(row)
        layout.addStretch()


class PosterCard(QFrame):
    clicked = Signal()
    play_app = Signal()
    play_vlc = Signal()
    download = Signal()

    def __init__(
        self,
        image_url: str,
        title: str,
        fallback: str = "?",
        size: tuple[int, int] = (160, 230),
        show_actions: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("card")
        self._show_actions = show_actions
        self._base_height = size[1]
        height = size[1] + (32 if show_actions else 0)
        self.setFixedSize(QSize(size[0], height))
        self.setCursor(Qt.PointingHandCursor)
        self._fallback = fallback
        self._img_w = size[0]
        self._img_h = max(58, size[1] - 52)
        self._click_handler = None
        self._play_app_handler = None
        self._play_vlc_handler = None
        self._download_handler = None
        self._fav_handler = None
        self._fav_enabled = False
        self._is_favorite = False
        self._synopsis_loader = None
        self._synopsis_requested = False
        self._synopsis_loading = False
        self._load_token = 0
        self._bound_item_index = None
        self._hover_delay_ms = 260
        self._last_scroll_at = 0.0
        self._connected_scrollbars: set[int] = set()

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._show_synopsis_if_ready)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_wrap = QWidget(self)
        self.image_wrap.setObjectName("cardArt")
        self.image_wrap.setFixedSize(self._img_w, self._img_h)
        art_layout = QGridLayout(self.image_wrap)
        art_layout.setContentsMargins(0, 0, 0, 0)

        self.image_label = QLabel(self.image_wrap)
        self.image_label.setObjectName("cardImage")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedSize(self._img_w, self._img_h)
        art_layout.addWidget(self.image_label, 0, 0)

        self.badge_label = QLabel("", self.image_wrap)
        self.badge_label.setObjectName("cardBadge")
        self.badge_label.setVisible(False)
        art_layout.addWidget(self.badge_label, 0, 0, Qt.AlignTop | Qt.AlignLeft)

        self.synopsis_overlay = QFrame(self.image_wrap)
        self.synopsis_overlay.setObjectName("cardSynopsisOverlay")
        self.synopsis_overlay.setVisible(False)
        self.synopsis_overlay.setFixedSize(self._img_w, self._img_h)
        synopsis_layout = QVBoxLayout(self.synopsis_overlay)
        synopsis_layout.setContentsMargins(12, 12, 12, 12)
        synopsis_layout.setSpacing(8)

        self.synopsis_title = QLabel("", self.synopsis_overlay)
        self.synopsis_title.setObjectName("cardSynopsisTitle")
        self.synopsis_title.setWordWrap(True)
        synopsis_layout.addWidget(self.synopsis_title)

        self.synopsis_scroll = QScrollArea(self.synopsis_overlay)
        self.synopsis_scroll.setObjectName("cardSynopsisScroll")
        self.synopsis_scroll.setWidgetResizable(True)
        self.synopsis_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.synopsis_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.synopsis_scroll.setFrameShape(QFrame.NoFrame)
        self.synopsis_scroll.viewport().setAutoFillBackground(False)

        synopsis_body = QWidget(self.synopsis_scroll)
        synopsis_body_layout = QVBoxLayout(synopsis_body)
        synopsis_body_layout.setContentsMargins(0, 0, 0, 0)
        synopsis_body_layout.setSpacing(0)

        self.synopsis_label = QLabel("", synopsis_body)
        self.synopsis_label.setObjectName("cardSynopsisText")
        self.synopsis_label.setWordWrap(True)
        self.synopsis_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        synopsis_body_layout.addWidget(self.synopsis_label)
        synopsis_body_layout.addStretch()
        self.synopsis_scroll.setWidget(synopsis_body)
        synopsis_layout.addWidget(self.synopsis_scroll, 1)
        art_layout.addWidget(self.synopsis_overlay, 0, 0)

        _fav_size = 28
        self.fav_btn = QPushButton("☆", self.image_wrap)
        self.fav_btn.setObjectName("favBtn")
        self.fav_btn.setFixedSize(_fav_size, _fav_size)
        self.fav_btn.setCursor(Qt.PointingHandCursor)
        self.fav_btn.setToolTip("Add to Favorites")
        self.fav_btn.clicked.connect(self._handle_favorite)
        self.fav_btn.move(self._img_w - _fav_size - 6, 6)
        self.fav_btn.hide()

        for obj in (
            self.image_wrap,
            self.image_label,
            self.badge_label,
            self.synopsis_overlay,
            self.synopsis_scroll.viewport(),
            self.synopsis_label,
            self.synopsis_title,
            self.fav_btn,
        ):
            obj.installEventFilter(self)
        layout.addWidget(self.image_wrap)

        body = QWidget(self)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 10, 10, 10)
        body_layout.setSpacing(2)

        self.title_label = QLabel(title, body)
        self.title_label.setObjectName("cardTitle")
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_label.setWordWrap(False)
        self.title_label.setFixedHeight(20)
        body_layout.addWidget(self.title_label)

        self.meta_label = QLabel("", body)
        self.meta_label.setObjectName("cardMeta")
        self.meta_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.meta_label.setWordWrap(False)
        self.meta_label.setFixedHeight(16)
        self.meta_label.setVisible(False)
        body_layout.addWidget(self.meta_label)
        layout.addWidget(body)

        self.actions_widget = QWidget(self)
        actions = QHBoxLayout(self.actions_widget)
        actions.setContentsMargins(10, 0, 10, 8)
        actions.setSpacing(6)

        self.app_btn = QPushButton("In App", self.actions_widget)
        self.app_btn.setObjectName("cardActionPrimary")
        self.app_btn.setCursor(Qt.PointingHandCursor)
        self.app_btn.setFixedHeight(24)
        self.app_btn.clicked.connect(self._handle_play_app)

        self.vlc_btn = QPushButton("In VLC", self.actions_widget)
        self.vlc_btn.setObjectName("cardActionSecondary")
        self.vlc_btn.setCursor(Qt.PointingHandCursor)
        self.vlc_btn.setFixedHeight(24)
        self.vlc_btn.clicked.connect(self._handle_play_vlc)

        self.download_btn = QPushButton("DL", self.actions_widget)
        self.download_btn.setObjectName("cardActionSecondary")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setFixedHeight(24)
        self.download_btn.setFixedWidth(30)
        self.download_btn.setToolTip("Download")
        self.download_btn.clicked.connect(self._handle_download)
        self.download_btn.setVisible(False)

        actions.addWidget(self.app_btn, 1)
        actions.addWidget(self.vlc_btn, 1)
        actions.addWidget(self.download_btn)
        layout.addWidget(self.actions_widget)
        self.actions_widget.setVisible(show_actions)

        self.configure(image_url, title, fallback)

    def configure(
        self,
        image_url: str,
        title: str,
        fallback: str | None = None,
        subtitle: str = "",
        badge: str = "",
        synopsis: str = "",
        synopsis_loader=None,
        on_click=None,
        on_play_app=None,
        on_play_vlc=None,
        on_download=None,
        on_favorite=None,
        is_favorite: bool = False,
    ):
        self._click_handler = on_click
        self._play_app_handler = on_play_app
        self._play_vlc_handler = on_play_vlc
        self._download_handler = on_download
        self._fav_handler = on_favorite
        self._fav_enabled = on_favorite is not None
        self._synopsis_loader = synopsis_loader
        self.download_btn.setVisible(on_download is not None and self._show_actions)
        if self._fav_enabled:
            self.set_favorite(is_favorite)
        self.fav_btn.hide()
        self._synopsis_requested = False
        self._synopsis_loading = False
        if fallback is not None:
            self._fallback = fallback

        self.title_label.setText(title or "Untitled")
        self.meta_label.setText(subtitle)
        self.meta_label.setVisible(bool(subtitle))
        self.badge_label.setText(badge)
        self.badge_label.setVisible(bool(badge))
        self.synopsis_title.setText(title or "")
        self.synopsis_label.setText((synopsis or "").strip())
        self._hover_timer.stop()
        self.synopsis_overlay.setVisible(False)
        self.synopsis_scroll.verticalScrollBar().setValue(0)
        self.setToolTip("")

        self._load_token += 1
        self.image_label.clear()
        self.image_label.setPixmap(QPixmap())
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setText(self._fallback)

        if image_url:
            token = self._load_token
            load_image(
                image_url,
                lambda pm, t=token: self._set_image(pm, t),
                (self._img_w, self._img_h),
            )

    def _set_image(self, pm: QPixmap, token: int | None = None):
        if token is not None and token != self._load_token:
            return
        if pm.isNull():
            return
        scaled = pm.scaled(
            self._img_w,
            self._img_h,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        x = max(0, (scaled.width() - self._img_w) // 2)
        y = max(0, (scaled.height() - self._img_h) // 2)
        cropped = scaled.copy(x, y, self._img_w, self._img_h)
        self.image_label.setText("")
        self.image_label.setPixmap(cropped)
        self.image_label.setAlignment(Qt.AlignCenter)

    def _handle_play_app(self):
        self.play_app.emit()
        if self._play_app_handler:
            self._play_app_handler()

    def _handle_play_vlc(self):
        self.play_vlc.emit()
        if self._play_vlc_handler:
            self._play_vlc_handler()

    def _handle_download(self):
        self.download.emit()
        if self._download_handler:
            self._download_handler()

    def _handle_favorite(self):
        if self._fav_handler:
            self._fav_handler()

    def set_favorite(self, state: bool):
        self._is_favorite = state
        self.fav_btn.setText("★" if state else "☆")
        self.fav_btn.setToolTip("Remove from Favorites" if state else "Add to Favorites")
        self.fav_btn.setProperty("active", state)
        self.fav_btn.style().unpolish(self.fav_btn)
        self.fav_btn.style().polish(self.fav_btn)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
            if self._click_handler:
                self._click_handler()
        super().mousePressEvent(ev)

    def _set_synopsis_visible(self, visible: bool):
        has_synopsis = bool(self.synopsis_label.text().strip())
        should_show = visible and (has_synopsis or self._synopsis_loading)
        self.synopsis_overlay.setVisible(should_show)
        if should_show:
            self.synopsis_overlay.raise_()
        else:
            self.synopsis_scroll.verticalScrollBar().setValue(0)

    def _bind_ancestor_scrollbars(self):
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                for bar in (
                    parent.verticalScrollBar(),
                    parent.horizontalScrollBar(),
                ):
                    if bar is None:
                        continue
                    bar_id = id(bar)
                    if bar_id in self._connected_scrollbars:
                        continue
                    bar.valueChanged.connect(self._on_ancestor_scrolled)
                    self._connected_scrollbars.add(bar_id)
            parent = parent.parentWidget()

    def _on_ancestor_scrolled(self, *_args):
        self._last_scroll_at = time.monotonic()
        self._hover_timer.stop()
        self._set_synopsis_visible(False)

    def _schedule_synopsis_show(self):
        self._bind_ancestor_scrollbars()
        self._hover_timer.start(self._hover_delay_ms)

    def _show_synopsis_if_ready(self):
        if not (self.underMouse() or self.image_wrap.underMouse() or self.synopsis_overlay.underMouse()):
            return
        elapsed_ms = (time.monotonic() - self._last_scroll_at) * 1000
        if elapsed_ms < self._hover_delay_ms:
            self._hover_timer.start(max(40, int(self._hover_delay_ms - elapsed_ms)))
            return
        self._ensure_synopsis()
        self._set_synopsis_visible(True)

    def _ensure_synopsis(self):
        has_synopsis = bool(self.synopsis_label.text().strip())
        if has_synopsis or self._synopsis_loader is None or self._synopsis_requested:
            return
        self._synopsis_requested = True
        self._synopsis_loading = True
        self.synopsis_label.setText("Loading description...")
        token = self._load_token
        self._synopsis_loader(lambda text, t=token: self._apply_synopsis(text, t))
        self._set_synopsis_visible(True)

    def _apply_synopsis(self, text: str, token: int):
        if token != self._load_token:
            return
        self._synopsis_loading = False
        cleaned = (text or "").strip()
        self.synopsis_label.setText(cleaned or "No description available.")
        self._set_synopsis_visible(self.underMouse() or self.image_wrap.underMouse() or self.synopsis_overlay.underMouse())

    def eventFilter(self, obj, ev):
        if obj is self.fav_btn:
            if ev.type() == QEvent.Leave:
                QTimer.singleShot(0, self._update_fav_btn_visibility)
            return super().eventFilter(obj, ev)
        if obj in (
            self.image_wrap,
            self.image_label,
            self.badge_label,
            self.synopsis_overlay,
            self.synopsis_scroll.viewport(),
            self.synopsis_label,
            self.synopsis_title,
        ):
            if ev.type() in (QEvent.Enter, QEvent.HoverEnter):
                self._schedule_synopsis_show()
                if self._fav_enabled:
                    self.fav_btn.raise_()
                    self.fav_btn.show()
            elif ev.type() in (QEvent.MouseMove, QEvent.HoverMove):
                if self.synopsis_overlay.isVisible():
                    self._set_synopsis_visible(True)
                elif self.underMouse():
                    self._schedule_synopsis_show()
            elif ev.type() == QEvent.Wheel:
                self._on_ancestor_scrolled()
            elif ev.type() == QEvent.Leave:
                self._hover_timer.stop()
                QTimer.singleShot(0, lambda: self._set_synopsis_visible(self.underMouse() or self.image_wrap.underMouse()))
                QTimer.singleShot(0, self._update_fav_btn_visibility)
        return super().eventFilter(obj, ev)

    def enterEvent(self, ev):
        self._schedule_synopsis_show()
        if self._fav_enabled:
            self.fav_btn.raise_()
            self.fav_btn.show()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover_timer.stop()
        self._set_synopsis_visible(False)
        self.synopsis_scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(0, self._update_fav_btn_visibility)
        super().leaveEvent(ev)

    def _update_fav_btn_visibility(self):
        if self._fav_enabled and (self.underMouse() or self.image_wrap.underMouse()):
            return
        self.fav_btn.hide()

    def showEvent(self, ev):
        self._last_scroll_at = time.monotonic()
        self._bind_ancestor_scrollbars()
        super().showEvent(ev)


class VirtualPosterGrid(QWidget):
    def __init__(
        self,
        items: list[dict],
        card_size: tuple[int, int],
        fallback: str,
        show_actions: bool,
        configure_card,
        columns: int = 6,
        spacing: int = 8,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.items = items
        self.card_size = card_size
        self.fallback = fallback
        self.show_actions = show_actions
        self.configure_card = configure_card
        self.columns = max(1, columns)
        self._base_columns = max(1, columns)
        self.spacing = spacing
        self.card_width = card_size[0]
        self.card_height = card_size[1] + (32 if show_actions else 0)
        self.cards: list[PosterCard] = []
        self._visible_count = 0
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._update_columns()
        self._update_height()

    def _column_capacity_for_width(self, width: int) -> int:
        if width <= 0:
            return self._base_columns
        return max(1, (width + self.spacing) // (self.card_width + self.spacing))

    def _update_columns(self) -> bool:
        new_columns = self._column_capacity_for_width(self.width())
        if new_columns == self.columns:
            return False
        self.columns = new_columns
        return True

    def _update_height(self):
        rows = max(1, math.ceil(len(self.items) / self.columns))
        total_height = rows * self.card_height + max(0, rows - 1) * self.spacing
        self.setMinimumHeight(total_height)
        self.setMaximumHeight(total_height)

    def _refresh_layout_for_resize(self):
        changed = self._update_columns()
        if changed:
            self._update_height()
        scroll_parent = self.parentWidget()
        while scroll_parent is not None and not isinstance(scroll_parent, QScrollArea):
            scroll_parent = scroll_parent.parentWidget()
        if isinstance(scroll_parent, QScrollArea):
            self.update_visible(
                scroll_parent.verticalScrollBar().value(),
                scroll_parent.viewport().height(),
            )
        elif changed:
            self.update()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._refresh_layout_for_resize()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._refresh_layout_for_resize()

    def _ensure_pool_count(self, needed: int):
        needed = max(0, min(len(self.items), needed))
        while len(self.cards) < needed:
            card = PosterCard(
                "",
                "",
                self.fallback,
                self.card_size,
                show_actions=self.show_actions,
                parent=self,
            )
            card.hide()
            self.cards.append(card)

    def update_visible(self, scroll_value: int, viewport_height: int):
        if not self.items:
            return

        row_span = self.card_height + self.spacing
        local_top = scroll_value - self.y()
        local_bottom = scroll_value + viewport_height - self.y()

        if local_bottom < 0 or local_top > self.height():
            for card in self.cards:
                card.setGeometry(-10000, -10000, self.card_width, self.card_height)
            return

        first_row = max(0, (max(0, local_top) // row_span) - 1)
        last_row = min(
            math.ceil(len(self.items) / self.columns) - 1,
            (max(0, local_bottom) // row_span) + 1,
        )
        first_index = first_row * self.columns
        last_index = min(len(self.items), (last_row + 1) * self.columns)
        needed_cards = max(0, last_index - first_index)
        self._ensure_pool_count(needed_cards)

        self.setUpdatesEnabled(False)
        for pool_index, item_index in enumerate(range(first_index, last_index)):
            card = self.cards[pool_index]
            if card._bound_item_index != item_index:
                self.configure_card(card, self.items[item_index])
                card._bound_item_index = item_index
            row = item_index // self.columns
            col = item_index % self.columns
            x = col * (self.card_width + self.spacing)
            y = row * (self.card_height + self.spacing)
            card.setGeometry(x, y, self.card_width, self.card_height)
            if not card.isVisible():
                card.show()

        for card in self.cards[last_index - first_index:]:
            card._bound_item_index = None
            card.setGeometry(-10000, -10000, self.card_width, self.card_height)
        self.setUpdatesEnabled(True)


class Row(QWidget):
    expand_clicked = Signal()

    def __init__(self, title: str, count: int = 0, expandable: bool = True, card_height: int = 220, parent: QWidget | None = None):
        super().__init__(parent)
        self._card_height = card_height
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        title_wrap = QWidget(self)
        title_wrap.setObjectName("rowHeaderBlock")
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        header = QLabel(title, title_wrap)
        header.setObjectName("rowTitle")
        title_layout.addWidget(header)

        self.count_label = QLabel(f"{count} titles" if count else "", title_wrap)
        self.count_label.setObjectName("rowMeta")
        self.count_label.setVisible(bool(count))
        title_layout.addWidget(self.count_label)

        header_row.addWidget(title_wrap)
        header_row.addStretch()
        if expandable:
            self.expand_btn = QPushButton("View all", self)
            self.expand_btn.setObjectName("rowActionBtn")
            self.expand_btn.setCursor(Qt.PointingHandCursor)
            self.expand_btn.clicked.connect(self.expand_clicked.emit)
            header_row.addWidget(self.expand_btn)
        layout.addLayout(header_row)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(self._card_height + 18)
        self.scroll.horizontalScrollBar().setSingleStep(120)
        self.scroll.horizontalScrollBar().setPageStep(420)

        container = QWidget(self.scroll)
        self.hbox = QHBoxLayout(container)
        self.hbox.setContentsMargins(4, 4, 4, 8)
        self.hbox.setSpacing(8)
        self.hbox.addStretch()
        self.scroll.setWidget(container)

        wrapper = QWidget(self)
        wrap_layout = QHBoxLayout(wrapper)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(8)

        self.left_btn = QPushButton("<", wrapper)
        self.left_btn.setObjectName("scrollBtn")
        self.left_btn.setFixedWidth(42)
        self.left_btn.setFixedHeight(80)
        self.left_btn.clicked.connect(lambda: self._scroll(-420))
        self.right_btn = QPushButton(">", wrapper)
        self.right_btn.setObjectName("scrollBtn")
        self.right_btn.setFixedWidth(42)
        self.right_btn.setFixedHeight(80)
        self.right_btn.clicked.connect(lambda: self._scroll(420))

        wrap_layout.addWidget(self.left_btn)
        wrap_layout.addWidget(self.scroll, 1)
        wrap_layout.addWidget(self.right_btn)
        layout.addWidget(wrapper)

        self._scroll_anim = QPropertyAnimation(self.scroll.horizontalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(180)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.scroll.horizontalScrollBar().valueChanged.connect(self._update_scroll_buttons)
        self.scroll.horizontalScrollBar().rangeChanged.connect(lambda *_: self._update_scroll_buttons())
        self.scroll.viewport().installEventFilter(self)
        self._update_scroll_buttons()
        QTimer.singleShot(0, self._update_scroll_buttons)

    def eventFilter(self, obj, ev):
        if obj is self.scroll.viewport() and ev.type() == QEvent.Wheel:
            delta = ev.angleDelta().x()
            if delta == 0 and ev.modifiers() & Qt.ShiftModifier:
                delta = ev.angleDelta().y()
            if delta != 0:
                self._scroll(-delta)
                ev.accept()
                return True
        return super().eventFilter(obj, ev)

    def _scroll(self, delta: int):
        bar = self.scroll.horizontalScrollBar()
        target = max(bar.minimum(), min(bar.maximum(), bar.value() + delta))
        if target == bar.value():
            return
        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(bar.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()

    def _update_scroll_buttons(self):
        bar = self.scroll.horizontalScrollBar()
        at_start = bar.value() <= bar.minimum()
        at_end = bar.value() >= bar.maximum()
        self.left_btn.setEnabled(not at_start)
        self.right_btn.setEnabled(not at_end)

    def add_card(self, card: PosterCard):
        self.hbox.insertWidget(self.hbox.count() - 1, card)
        QTimer.singleShot(0, self._update_scroll_buttons)


class Hero(QFrame):
    play_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("hero")
        self._min_hero_height = 320
        self._side_margin = 36
        self._top_margin = 32
        self._bottom_margin = 32
        self._panel_padding = 24
        self._layout_mode = "featured"
        self.setMinimumHeight(self._min_hero_height)
        self._pixmap: QPixmap | None = None
        self._load_token = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(self._side_margin, self._top_margin, self._side_margin, self._bottom_margin)
        layout.addStretch()

        self.panel = QWidget(self)
        self.panel.setObjectName("heroPanel")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(24, 22, 24, 22)
        panel_layout.setSpacing(10)

        self.badge_label = QLabel("", self.panel)
        self.badge_label.setObjectName("heroBadge")
        self.badge_label.setVisible(False)
        panel_layout.addWidget(self.badge_label, 0, Qt.AlignLeft)

        self.meta_label = QLabel("", self.panel)
        self.meta_label.setObjectName("heroMeta")
        self.meta_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.meta_label.setWordWrap(True)
        self.meta_label.setVisible(False)
        panel_layout.addWidget(self.meta_label)

        self.title_label = QLabel("", self.panel)
        self.title_label.setObjectName("heroTitle")
        self.title_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.title_label.setWordWrap(True)
        panel_layout.addWidget(self.title_label)

        self.sub_label = QLabel("", self.panel)
        self.sub_label.setObjectName("heroSubtitle")
        self.sub_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.sub_label.setWordWrap(True)
        panel_layout.addWidget(self.sub_label)
        panel_layout.addSpacing(6)

        self.play_btn = QPushButton("Play", self.panel)
        self.play_btn.setObjectName("playBtn")
        self.play_btn.setFixedWidth(168)
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.clicked.connect(self.play_clicked.emit)
        panel_layout.addWidget(self.play_btn, 0, Qt.AlignLeft)
        layout.addWidget(self.panel, 0, Qt.AlignLeft | Qt.AlignBottom)
        QTimer.singleShot(0, self._update_responsive_layout)

    def set_layout_mode(self, mode: str):
        self._layout_mode = mode
        self._update_responsive_layout()

    def _layout_profile(self, available_width: int) -> dict:
        if self._layout_mode == "detail":
            if available_width < 680:
                return {"ratio": 0.96, "min_width": 260, "max_width": available_width, "max_height_factor": 1.35}
            if available_width < 920:
                return {"ratio": 0.92, "min_width": 360, "max_width": available_width, "max_height_factor": 1.15}
            if available_width < 1280:
                return {"ratio": 0.82, "min_width": 460, "max_width": available_width, "max_height_factor": 1.00}
            return {"ratio": 0.72, "min_width": 560, "max_width": available_width, "max_height_factor": 0.86}

        if self._layout_mode == "series_featured":
            if available_width < 680:
                return {"ratio": 0.94, "min_width": 260, "max_width": available_width, "max_height_factor": 1.15}
            if available_width < 980:
                return {"ratio": 0.82, "min_width": 340, "max_width": available_width, "max_height_factor": 0.92}
            if available_width < 1320:
                return {"ratio": 0.70, "min_width": 420, "max_width": 920, "max_height_factor": 0.76}
            return {"ratio": 0.64, "min_width": 480, "max_width": 980, "max_height_factor": 0.68}

        if self._layout_mode == "vod_featured":
            if available_width < 680:
                return {"ratio": 0.94, "min_width": 260, "max_width": available_width, "max_height_factor": 1.05}
            if available_width < 980:
                return {"ratio": 0.78, "min_width": 320, "max_width": 720, "max_height_factor": 0.84}
            if available_width < 1320:
                return {"ratio": 0.64, "min_width": 380, "max_width": 820, "max_height_factor": 0.70}
            return {"ratio": 0.58, "min_width": 420, "max_width": 900, "max_height_factor": 0.62}

        if self._layout_mode == "live_featured":
            if available_width < 680:
                return {"ratio": 0.94, "min_width": 260, "max_width": available_width, "max_height_factor": 0.98}
            if available_width < 980:
                return {"ratio": 0.72, "min_width": 300, "max_width": 660, "max_height_factor": 0.76}
            if available_width < 1320:
                return {"ratio": 0.56, "min_width": 340, "max_width": 720, "max_height_factor": 0.62}
            return {"ratio": 0.50, "min_width": 360, "max_width": 760, "max_height_factor": 0.56}

        if available_width < 680:
            return {"ratio": 0.94, "min_width": 260, "max_width": available_width, "max_height_factor": 1.05}
        if available_width < 980:
            return {"ratio": 0.76, "min_width": 320, "max_width": 620, "max_height_factor": 0.82}
        if available_width < 1320:
            return {"ratio": 0.62, "min_width": 360, "max_width": 760, "max_height_factor": 0.68}
        return {"ratio": 0.56, "min_width": 380, "max_width": 840, "max_height_factor": 0.60}

    def _update_responsive_layout(self):
        available_width = max(1, self.width() - (self._side_margin * 2))
        profile = self._layout_profile(available_width)
        panel_width = max(
            min(available_width, profile["max_width"]),
            min(profile["min_width"], available_width),
        )
        panel_width = min(panel_width, max(profile["min_width"], int(available_width * profile["ratio"])))
        panel_width = max(280, min(available_width, panel_width))
        if panel_width > 0 and self.panel.width() != panel_width:
            self.panel.setFixedWidth(panel_width)

        text_width = max(220, panel_width - (self._panel_padding * 2))
        for label in (self.meta_label, self.title_label, self.sub_label):
            label.setFixedWidth(text_width)

        panel_layout = self.panel.layout()
        if panel_layout is not None:
            panel_layout.activate()
        self.panel.adjustSize()

        panel_height = self.panel.sizeHint().height()
        max_height = max(self._min_hero_height, int(max(self.width(), available_width) * profile["max_height_factor"]))
        target_height = max(self._min_hero_height, min(max_height, panel_height + self._top_margin + self._bottom_margin + 28))
        if self.minimumHeight() != target_height or self.maximumHeight() != target_height:
            self.setMinimumHeight(target_height)
            self.setMaximumHeight(target_height)

    _HERO_SUBTITLE_LIMIT = 280

    @staticmethod
    def _truncate_subtitle(text: str, limit: int) -> str:
        text = (text or "").strip()
        if len(text) <= limit:
            return text
        cut = text.rfind(" ", 0, limit)
        if cut < limit * 0.6:
            cut = limit
        return text[:cut].rstrip(" ,;:.-") + "…"

    def set_content(
        self,
        title: str,
        subtitle: str,
        image_url: str,
        badge: str = "",
        meta: str = "",
    ):
        self._load_token += 1
        self.title_label.setText(title)
        if self._layout_mode != "detail":
            subtitle = self._truncate_subtitle(subtitle or "", self._HERO_SUBTITLE_LIMIT)
        self.sub_label.setText(subtitle or "")
        self.badge_label.setText(badge)
        self.badge_label.setVisible(bool(badge))
        self.meta_label.setText(meta)
        self.meta_label.setVisible(bool(meta))
        self._pixmap = None
        self._update_responsive_layout()
        QTimer.singleShot(0, self._update_responsive_layout)
        self.update()
        if image_url:
            token = self._load_token
            load_image(image_url, lambda pm, t=token: self._set_image(pm, t), (1280, 720))

    def update_subtitle(self, subtitle: str):
        if self._layout_mode != "detail":
            subtitle = self._truncate_subtitle(subtitle or "", self._HERO_SUBTITLE_LIMIT)
        self.sub_label.setText(subtitle or "")
        self._update_responsive_layout()
        QTimer.singleShot(0, self._update_responsive_layout)

    def _set_image(self, pm: QPixmap, token: int | None = None):
        if token is not None and token != self._load_token:
            return
        if pm.isNull():
            return
        self._pixmap = pm
        self.update()

    def paintEvent(self, ev):
        painter = QPainter(self)
        rect = self.rect()
        if self._pixmap:
            scaled = self._pixmap.scaled(
                rect.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = (scaled.width() - rect.width()) // 2
            y = (scaled.height() - rect.height()) // 2
            painter.drawPixmap(rect, scaled, QRect(x, y, rect.width(), rect.height()))
        else:
            painter.fillRect(rect, QColor("#3f0a0f"))

        side_grad = QLinearGradient(0, 0, rect.width(), 0)
        side_grad.setColorAt(0.0, QColor(4, 4, 6, 240))
        side_grad.setColorAt(0.42, QColor(4, 4, 6, 165))
        side_grad.setColorAt(1.0, QColor(4, 4, 6, 30))
        painter.fillRect(rect, QBrush(side_grad))

        bottom_grad = QLinearGradient(0, rect.height(), 0, 0)
        bottom_grad.setColorAt(0.0, QColor(0, 0, 0, 240))
        bottom_grad.setColorAt(0.34, QColor(0, 0, 0, 130))
        bottom_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(bottom_grad))

        accent = QLinearGradient(0, 0, rect.width(), rect.height())
        accent.setColorAt(0.0, QColor(126, 8, 20, 70))
        accent.setColorAt(0.4, QColor(126, 8, 20, 12))
        accent.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, QBrush(accent))

        super().paintEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._update_responsive_layout()
