import logging
import random
from datetime import datetime

_log = logging.getLogger(__name__)

from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import favorites
import history
import search
from widgets import EpisodeListSkeleton, Hero, HeroSkeleton, PosterCard, Row, RowSkeleton, VirtualPosterGrid
from workers import run_async


class _BasePage(QWidget):
    def __init__(self, xtream, kind: str, item_label: str):
        super().__init__()
        self.xtream = xtream
        self.kind = kind
        self.fallback = {"live": "TV", "vod": "MOV", "series": "SER"}[kind]
        self.card_size = (200, 110) if kind == "live" else (160, 230)
        self.row_card_height = self.card_size[1] + (32 if kind != "series" else 0)

        self.categories: list[dict] = []
        self.items: list[dict] = []
        self.query = ""
        self.expanded_category: tuple[str, list] | None = None
        self._lazy_queue: list[tuple[str, list]] = []
        self._lazy_index = 0
        self._lazy_chunk = 3
        self._lazy_token = 0
        self._render_token = 0
        self._lazy_grid_items: list[dict] = []
        self._lazy_grid_index = 0
        self._lazy_grid_chunk = 24
        self._lazy_grid_cols = 6
        self._lazy_grid = None
        self._active_virtual_grid = None
        self._vod_synopsis_cache: dict[str, str] = {}
        self._vod_synopsis_pending: set[str] = set()
        self._vod_synopsis_waiters: dict[str, list] = {}
        self._series_synopsis_cache: dict[str, str] = {}
        self._series_synopsis_pending: set[str] = set()
        self._series_synopsis_waiters: dict[str, list] = {}
        self._fav_cache: dict = {}
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._apply_responsive_layout)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 24)
        outer.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel({"live": "Live TV", "vod": "Movies", "series": "Series"}[kind], self)
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch()

        self.updated_label = QLabel("", self)
        self.updated_label.setStyleSheet("color: #71717a; font-size: 12px; padding-right: 8px;")
        top.addWidget(self.updated_label)

        self.refresh_btn = QPushButton("Refresh", self)
        self.refresh_btn.setObjectName("chip")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._force_refresh)
        top.addWidget(self.refresh_btn)

        self.search = QLineEdit(self)
        self.search.setObjectName("searchInput")
        self.search.setPlaceholderText(f"Search {item_label} & categories...")
        self.search.setMinimumWidth(220)
        self.search.setMaximumWidth(460)
        self.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search.textChanged.connect(self._on_search)
        top.addWidget(self.search, 1)
        outer.addLayout(top)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget(self.scroll)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(16)
        self.scroll.setWidget(self.content)
        self.scroll.verticalScrollBar().valueChanged.connect(self._maybe_render_more_content)
        outer.addWidget(self.scroll, 1)

        self._stretch_added = False
        self._apply_responsive_metrics()
        self._show_loading_state()

        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._render)

        self._load_data()

    def _items_action(self) -> str:
        return {
            "live": "get_live_streams",
            "vod": "get_vod_streams",
            "series": "get_series",
        }[self.kind]

    def _load_data(self, force: bool = False):
        if self.kind == "live":
            run_async(self.xtream.get_live_categories, on_done=self._set_categories, force=force)
            run_async(self.xtream.get_live_streams, on_done=self._set_items, force=force)
        elif self.kind == "vod":
            run_async(self.xtream.get_vod_categories, on_done=self._set_categories, force=force)
            run_async(self.xtream.get_vod_streams, on_done=self._set_items, force=force)
        else:
            run_async(self.xtream.get_series_categories, on_done=self._set_categories, force=force)
            run_async(self.xtream.get_series, on_done=self._set_items, force=force)
        self._update_timestamp_label()

    def _force_refresh(self):
        self.refresh_btn.setEnabled(False)
        self.categories = []
        self.items = []
        self.expanded_category = None
        self._show_loading_state()
        self._load_data(force=True)
        QTimer.singleShot(1500, lambda: self.refresh_btn.setEnabled(True))

    def _update_timestamp_label(self):
        ts = self.xtream.cache_timestamp(self._items_action())
        if ts:
            text = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            self.updated_label.setText(f"Last updated: {text}")
        else:
            self.updated_label.setText("")

    def _set_categories(self, data):
        self.categories = data or []
        self._maybe_render()

    def _set_items(self, data):
        self.items = data or []
        self._update_timestamp_label()
        self._maybe_render()

    def _maybe_render(self):
        if self.categories and self.items:
            self._render()

    def _on_search(self, text):
        self.query = text.strip().lower()
        self._search_timer.start(180)

    def _id_of(self, item) -> str:
        return str(item.get("series_id") if self.kind == "series" else item.get("stream_id"))

    def _name_of(self, item) -> str:
        return item.get("name", "")

    def _image_of(self, item) -> str:
        return item.get("cover") if self.kind == "series" else item.get("stream_icon")

    def _ext_of(self, item) -> str:
        if self.kind == "live":
            return getattr(self.xtream, "live_ext", "ts") or "ts"
        return item.get("container_extension") or "mp4"

    def _siblings(self, item) -> list[dict]:
        if self.expanded_category and not self.query:
            pool = self.expanded_category[1]
        elif self.query:
            pool = search.rank(self.query, self.items, self._name_of)
        else:
            cid = str(item.get("category_id"))
            pool = [i for i in self.items if str(i.get("category_id")) == cid]
        return pool or [item]

    def _record_history(self, item):
        try:
            history.record(
                self.xtream.server,
                self.xtream.username,
                self.kind,
                self._id_of(item),
                self._name_of(item),
                cover=self._image_of(item) or "",
                extra={"category_id": item.get("category_id"),
                       "container_extension": item.get("container_extension", "")},
            )
        except Exception:
            _log.exception("history.record failed for %s", self.kind)

    def _on_play(self, item, backend: str = "app"):
        if self.kind == "series":
            self.parent_window.open_series(item)
            return
        self._record_history(item)
        url = self.xtream.stream_url(self.kind, self._id_of(item), self._ext_of(item))
        title = self._name_of(item)
        is_live = self.kind == "live"
        if backend == "app":
            siblings = self._siblings(item)
            playlist = [
                {
                    "url": self.xtream.stream_url(self.kind, self._id_of(s), self._ext_of(s)),
                    "title": self._name_of(s),
                    "is_live": is_live,
                }
                for s in siblings
            ]
            try:
                index = next(i for i, s in enumerate(siblings) if self._id_of(s) == self._id_of(item))
            except StopIteration:
                index = 0
            resume_pos, on_position_save = self._resume_info(item, is_live)
            self.parent_window.play_in_app(
                url, title, is_live, playlist, index,
                resume_pos=resume_pos, on_position_save=on_position_save,
            )
        else:
            self.parent_window.play_in_vlc(url)

    def _resume_info(self, item, is_live: bool):
        if is_live:
            return 0.0, None
        item_id = self._id_of(item)
        entries = history.load(self.xtream.server, self.xtream.username)
        entry = next(
            (e for e in entries if str(e.get("id")) == item_id and e.get("kind") == self.kind),
            None,
        )
        resume_pos = 0.0
        if entry:
            pos = float(entry.get("position", 0.0))
            dur = float(entry.get("duration", 0.0))
            if pos > 30 and (dur <= 0 or pos < dur - 30):
                resume_pos = pos

        server = self.xtream.server
        username = self.xtream.username
        kind = self.kind
        name = self._name_of(item)
        cover = self._image_of(item) or ""
        extra = {
            "category_id": item.get("category_id"),
            "container_extension": item.get("container_extension", ""),
        }

        def on_position_save(pos, dur):
            history.record(server, username, kind, item_id, name,
                           cover=cover, extra=extra, position=pos, duration=dur)

        return resume_pos, on_position_save

    def _on_download(self, item):
        if self.kind != "vod":
            return
        url = self.xtream.stream_url(self.kind, self._id_of(item), self._ext_of(item))
        title = self._name_of(item)
        ext = self._ext_of(item)
        self.parent_window.download_movie(url, title, ext)

    def _on_favorite(self, item):
        favorites.toggle(
            self.xtream.server, self.xtream.username, self.kind,
            self._id_of(item), self._name_of(item), self._image_of(item) or "",
        )
        self._render()

    def _is_fav(self, item) -> bool:
        bucket = self._fav_cache.get(self.kind, {})
        return bool(bucket.get(str(self._id_of(item))))

    def _render_favorites_row(self):
        fav_items = favorites.get_favorites(
            self.xtream.server, self.xtream.username, self.kind, self.items, self._id_of
        )
        if not fav_items:
            return
        row = Row("★ Favorites", len(fav_items), expandable=False, card_height=self.row_card_height)
        for item in fav_items:
            card = self._build_card(item, parent=row)
            row.add_card(card)
        self.content_layout.addWidget(row)

    def _clear_layout(self):
        self._lazy_queue = []
        self._lazy_index = 0
        self._lazy_token = getattr(self, "_render_token", 0)
        self._lazy_grid_items = []
        self._lazy_grid_index = 0
        self._lazy_grid = None
        self._active_virtual_grid = None
        self._stretch_added = False
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _available_content_width(self) -> int:
        viewport = self.scroll.viewport().width() if self.scroll is not None else self.width()
        return max(320, viewport - 24)

    def _apply_responsive_metrics(self):
        width = self._available_content_width()
        previous = (self.card_size, self.row_card_height)
        if self.kind == "live":
            if width < 780:
                self.card_size = (168, 96)
            elif width < 1080:
                self.card_size = (184, 102)
            else:
                self.card_size = (200, 110)
        else:
            if width < 700:
                self.card_size = (132, 196)
            elif width < 980:
                self.card_size = (146, 210)
            elif width < 1260:
                self.card_size = (154, 220)
            else:
                self.card_size = (160, 230)
        self.row_card_height = self.card_size[1] + (32 if self.kind != "series" else 0)
        return previous != (self.card_size, self.row_card_height)

    def _apply_responsive_layout(self):
        if not self._apply_responsive_metrics():
            if self._active_virtual_grid is not None:
                self._active_virtual_grid.update_visible(
                    self.scroll.verticalScrollBar().value(),
                    self.scroll.viewport().height(),
                )
            return
        if self.categories and self.items:
            self._render()
        else:
            self._show_loading_state()

    def _show_loading_state(self):
        self._clear_layout()
        hero_skel = HeroSkeleton(parent=self.content)
        self.content_layout.addWidget(hero_skel)
        for _ in range(3):
            row_skel = RowSkeleton(self.card_size, show_actions=(self.kind != "series"), parent=self.content)
            self.content_layout.addWidget(row_skel)
        if not self._stretch_added:
            self.content_layout.addStretch()
            self._stretch_added = True

    def _make_empty_state(self, title: str, body: str) -> QWidget:
        box = QWidget(self.content)
        box.setObjectName("emptyState")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(8)
        title_label = QLabel(title, box)
        title_label.setObjectName("emptyStateTitle")
        body_label = QLabel(body, box)
        body_label.setObjectName("emptyStateBody")
        body_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(body_label)
        return box

    def _make_section_header(
        self,
        title: str,
        meta: str = "",
        *,
        back_text: str | None = None,
        on_back=None,
    ) -> QWidget:
        wrap = QWidget(self.content)
        wrap.setObjectName("sectionHeader")
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        if back_text:
            back_btn = QPushButton(back_text, wrap)
            back_btn.setObjectName("sectionBackBtn")
            back_btn.setCursor(Qt.PointingHandCursor)
            if on_back is not None:
                back_btn.clicked.connect(on_back)
            layout.addWidget(back_btn)

        text_wrap = QWidget(wrap)
        text_layout = QVBoxLayout(text_wrap)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title_label = QLabel(title, text_wrap)
        title_label.setObjectName("sectionTitle")
        text_layout.addWidget(title_label)
        if meta:
            meta_label = QLabel(meta, text_wrap)
            meta_label.setObjectName("sectionMeta")
            text_layout.addWidget(meta_label)
        layout.addWidget(text_wrap, 1)
        return wrap

    def _badge_of(self, item) -> str:
        return {"live": "LIVE", "vod": "MOVIE", "series": "SERIES"}[self.kind]

    def _meta_of(self, item) -> str:
        parts: list[str] = []
        year = str(item.get("year") or "").strip()

        if self.kind == "live":
            stream_type = str(item.get("stream_type") or "").replace("_", " ").strip()
            parts.append(stream_type.title() if stream_type else "Channel")
            if str(item.get("tv_archive") or "0") == "1":
                parts.append("Catch-up")
        elif self.kind == "vod":
            if year:
                parts.append(year)
            duration = str(item.get("duration") or "").strip()
            if duration:
                parts.append(duration)
            ext = str(item.get("container_extension") or "").upper().strip()
            if ext:
                parts.append(ext)
        else:
            if year:
                parts.append(year)
            genre = str(item.get("genre") or "").strip()
            if genre:
                first_genre = genre.split(",")[0].strip()
                if first_genre:
                    parts.append(first_genre)
            if not parts:
                parts.append("Series")

        return " | ".join(part for part in parts if part)

    def _hero_meta_of(self, item) -> str:
        meta = self._meta_of(item)
        if self.kind == "live":
            return meta or "Featured live channel"
        return meta or self._badge_of(item).title()

    def _hero_subtitle_of(self, item) -> str:
        if self.kind == "live":
            return item.get("plot") or "Live broadcast"
        if self.kind == "vod":
            return self._synopsis_of(item)
        return item.get("plot") or ""

    def _synopsis_of(self, item) -> str:
        if self.kind not in ("vod", "series"):
            return ""
        item_id = self._id_of(item)
        cache = self._vod_synopsis_cache if self.kind == "vod" else self._series_synopsis_cache
        if item_id in cache:
            return cache[item_id]
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        return str(
            item.get("plot")
            or info.get("plot")
            or item.get("description")
            or info.get("description")
            or ""
        ).strip()

    def _request_series_synopsis(self, item, callback):
        if self.kind != "series":
            callback("")
            return
        item_id = self._id_of(item)
        cached = self._synopsis_of(item)
        if cached:
            callback(cached)
            return
        self._series_synopsis_waiters.setdefault(item_id, []).append(callback)
        if item_id in self._series_synopsis_pending:
            return
        self._series_synopsis_pending.add(item_id)
        run_async(
            self.xtream.get_series_info,
            on_done=lambda data, sid=item_id: self._on_series_synopsis_loaded(sid, data),
            on_error=lambda _msg, sid=item_id: self._on_series_synopsis_loaded(sid, {}),
            series_id=item_id,
        )

    def _on_series_synopsis_loaded(self, item_id: str, data):
        self._series_synopsis_pending.discard(item_id)
        plot = ""
        if isinstance(data, dict):
            info = data.get("info") if isinstance(data.get("info"), dict) else {}
            plot = str(info.get("plot") or data.get("plot") or info.get("description") or "").strip()
        self._series_synopsis_cache[item_id] = plot
        for cb in self._series_synopsis_waiters.pop(item_id, []):
            try:
                cb(plot)
            except Exception:
                pass

    def _request_vod_synopsis(self, item, callback):
        if self.kind != "vod":
            callback("")
            return
        item_id = self._id_of(item)
        cached = self._synopsis_of(item)
        if cached:
            callback(cached)
            return
        self._vod_synopsis_waiters.setdefault(item_id, []).append(callback)
        if item_id in self._vod_synopsis_pending:
            return
        self._vod_synopsis_pending.add(item_id)
        run_async(
            self.xtream.get_vod_info,
            on_done=lambda data, sid=item_id: self._on_vod_synopsis_loaded(sid, data),
            on_error=lambda _msg, sid=item_id: self._on_vod_synopsis_loaded(sid, {}),
            vod_id=item_id,
        )

    def _on_vod_synopsis_loaded(self, item_id: str, data):
        self._vod_synopsis_pending.discard(item_id)
        plot = ""
        if isinstance(data, dict):
            info = data.get("info") if isinstance(data.get("info"), dict) else {}
            movie_data = data.get("movie_data") if isinstance(data.get("movie_data"), dict) else {}
            plot = str(
                info.get("plot")
                or movie_data.get("plot")
                or data.get("plot")
                or movie_data.get("description")
                or ""
            ).strip()
        self._vod_synopsis_cache[item_id] = plot
        for cb in self._vod_synopsis_waiters.pop(item_id, []):
            try:
                cb(plot)
            except Exception:
                pass

    def _build_card(self, item, parent: QWidget | None = None) -> PosterCard:
        card = PosterCard(
            "",
            "",
            self.fallback,
            self.card_size,
            show_actions=(self.kind != "series"),
            parent=parent,
        )
        if self.kind == "series":
            card.configure(
                self._image_of(item),
                self._name_of(item),
                self.fallback,
                subtitle=self._meta_of(item),
                badge=self._badge_of(item),
                synopsis=self._synopsis_of(item),
                synopsis_loader=lambda cb, it=item: self._request_series_synopsis(it, cb),
                on_click=lambda it=item: self._on_play(it),
                on_favorite=lambda it=item: self._on_favorite(it),
                is_favorite=self._is_fav(item),
            )
        else:
            card.configure(
                self._image_of(item),
                self._name_of(item),
                self.fallback,
                subtitle=self._meta_of(item),
                badge=self._badge_of(item),
                synopsis=self._synopsis_of(item),
                synopsis_loader=(lambda cb, it=item: self._request_vod_synopsis(it, cb)) if self.kind == "vod" else None,
                on_click=lambda it=item: self._on_play(it, "app"),
                on_play_app=lambda it=item: self._on_play(it, "app"),
                on_play_vlc=lambda it=item: self._on_play(it, "vlc"),
                on_download=(lambda it=item: self._on_download(it)) if self.kind == "vod" else None,
                on_favorite=lambda it=item: self._on_favorite(it),
                is_favorite=self._is_fav(item),
            )
        return card

    def _configure_virtual_card(self, card: PosterCard, item):
        if self.kind == "series":
            card.configure(
                self._image_of(item),
                self._name_of(item),
                self.fallback,
                subtitle=self._meta_of(item),
                badge=self._badge_of(item),
                synopsis=self._synopsis_of(item),
                synopsis_loader=lambda cb, it=item: self._request_series_synopsis(it, cb),
                on_click=lambda it=item: self._on_play(it),
                on_favorite=lambda it=item: self._on_favorite(it),
                is_favorite=self._is_fav(item),
            )
            return
        card.configure(
            self._image_of(item),
            self._name_of(item),
            self.fallback,
            subtitle=self._meta_of(item),
            badge=self._badge_of(item),
            synopsis=self._synopsis_of(item),
            synopsis_loader=(lambda cb, it=item: self._request_vod_synopsis(it, cb)) if self.kind == "vod" else None,
            on_click=lambda it=item: self._on_play(it, "app"),
            on_play_app=lambda it=item: self._on_play(it, "app"),
            on_play_vlc=lambda it=item: self._on_play(it, "vlc"),
            on_download=(lambda it=item: self._on_download(it)) if self.kind == "vod" else None,
            on_favorite=lambda it=item: self._on_favorite(it),
            is_favorite=self._is_fav(item),
        )

    def _render_grid(self, items_to_render: list):
        self._active_virtual_grid = VirtualPosterGrid(
            items_to_render,
            self.card_size,
            self.fallback,
            show_actions=(self.kind != "series"),
            configure_card=self._configure_virtual_card,
            columns=6,
            spacing=8,
            parent=self.content,
        )
        self.content_layout.addWidget(self._active_virtual_grid)
        if not self._stretch_added:
            self.content_layout.addStretch()
            self._stretch_added = True
        QTimer.singleShot(0, self._maybe_render_more_content)

    def _expand_category(self, name: str, items: list):
        self.expanded_category = (name, items)
        self._render()

    def _collapse_category(self):
        self.expanded_category = None
        self._render()

    def _render(self):
        self._render_token = getattr(self, "_render_token", 0) + 1
        self._fav_cache = favorites.load(self.xtream.server, self.xtream.username)
        self._clear_layout()

        if not self.items:
            self.content_layout.addWidget(
                self._make_empty_state("No items available", "This section does not have any entries yet.")
            )
            self.content_layout.addStretch()
            self._stretch_added = True
            return

        if self.expanded_category and not self.query:
            name, items = self.expanded_category
            self.content_layout.addWidget(
                self._make_section_header(
                    name,
                    f"{len(items)} titles in this category",
                    back_text="Back",
                    on_back=self._collapse_category,
                )
            )
            self._stretch_added = False
            self._lazy_token = self._render_token
            self._render_grid(items[:240])
            return

        if self.query:
            filtered = search.rank(self.query, self.items, self._name_of, limit=240)
            self.content_layout.addWidget(
                self._make_section_header(
                    "Search results",
                    f'"{self.query}" • {len(filtered)} matches',
                )
            )
            if not filtered:
                self.content_layout.addWidget(
                    self._make_empty_state(
                        "No matches found",
                        f'Nothing matched "{self.query}". Try a broader title or category.',
                    )
                )
            else:
                self._stretch_added = False
                self._lazy_token = self._render_token
                self._render_grid(filtered[:120])
            if not filtered and not self._stretch_added:
                self.content_layout.addStretch()
                self._stretch_added = True
            return

        self._render_favorites_row()

        with_image = [item for item in self.items if self._image_of(item)]
        if with_image:
            hero_item = random.choice(with_image[:50])
            hero = Hero(self.content)
            hero.set_layout_mode({
                "live": "live_featured",
                "vod": "vod_featured",
                "series": "series_featured",
            }[self.kind])
            hero.set_content(
                self._name_of(hero_item),
                self._hero_subtitle_of(hero_item),
                self._image_of(hero_item),
                badge=self._badge_of(hero_item),
                meta=self._hero_meta_of(hero_item),
            )
            hero.play_clicked.connect(lambda it=hero_item: self._on_play(it, "app"))
            self.content_layout.addWidget(hero)
            if self.kind == "vod" and not self._hero_subtitle_of(hero_item):
                self._request_vod_synopsis(
                    hero_item,
                    lambda text, h=hero: h.update_subtitle(text) if text else None,
                )

        grouped: dict[str, list] = {}
        for item in self.items:
            cid = str(item.get("category_id"))
            grouped.setdefault(cid, []).append(item)

        queue = []
        all_label = {"live": "All Channels", "vod": "All Movies", "series": "All Series"}[self.kind]
        queue.append((all_label, list(self.items)))
        for cat in self.categories:
            cid = str(cat.get("category_id"))
            items = grouped.get(cid, [])
            if items:
                queue.append((cat.get("category_name", "Unknown"), items))

        self._stretch_added = False
        self._lazy_queue = queue
        self._lazy_index = 0
        self._lazy_token = self._render_token
        self._append_lazy_rows()
        QTimer.singleShot(0, self._maybe_render_more_content)

    def _append_lazy_rows(self):
        if not self._lazy_queue or self._lazy_token != self._render_token:
            return
        end = min(self._lazy_index + self._lazy_chunk, len(self._lazy_queue))
        for idx in range(self._lazy_index, end):
            name, items = self._lazy_queue[idx]
            row = Row(name, count=len(items), card_height=self.row_card_height, parent=self.content)
            row.expand_clicked.connect(lambda n=name, its=items: self._expand_category(n, its))
            for item in items[:20]:
                row.add_card(self._build_card(item, parent=row))
            self.content_layout.addWidget(row)
        self._lazy_index = end
        if self._lazy_index >= len(self._lazy_queue) and not self._stretch_added:
            self.content_layout.addStretch()
            self._stretch_added = True

    def _maybe_render_more_content(self, *_args):
        if self._active_virtual_grid is not None:
            self._active_virtual_grid.update_visible(
                self.scroll.verticalScrollBar().value(),
                self.scroll.viewport().height(),
            )
        if self._lazy_token != self._render_token:
            return
        bar = self.scroll.verticalScrollBar()
        threshold = max(240, bar.pageStep() // 2)
        near_end = bar.maximum() == 0 or bar.value() >= bar.maximum() - threshold
        if not near_end:
            return

        if not self._lazy_queue or self._lazy_index >= len(self._lazy_queue):
            return

        if near_end:
            self._append_lazy_rows()
            if self._lazy_index < len(self._lazy_queue):
                QTimer.singleShot(0, self._maybe_render_more_content)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._resize_timer.start(90)


class LiveTVPage(_BasePage):
    def __init__(self, xtream):
        super().__init__(xtream, "live", "channels")


class MoviesPage(_BasePage):
    def __init__(self, xtream):
        super().__init__(xtream, "vod", "movies")


class SeriesPage(_BasePage):
    open_show = Signal(dict)

    def __init__(self, xtream):
        super().__init__(xtream, "series", "series")


class ContinueWatchingPage(QWidget):
    KIND_LABEL = {"live": "Live", "vod": "Movie", "series": "Series"}
    KIND_FALLBACK = {"live": "TV", "vod": "MOV", "series": "SER"}

    def __init__(self, xtream, parent_window):
        super().__init__()
        self.xtream = xtream
        self.parent_window = parent_window
        self._cards: list[PosterCard] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 24)
        outer.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Continue Watching", self)
        title.setObjectName("pageTitle")
        top.addWidget(title)
        top.addStretch()

        self.clear_btn = QPushButton("Clear all", self)
        self.clear_btn.setObjectName("chip")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self._clear_all)
        top.addWidget(self.clear_btn)
        outer.addLayout(top)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget(self.scroll)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(16)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

    def refresh(self):
        self._clear_layout()
        entries = history.load(self.xtream.server, self.xtream.username)
        if not entries:
            self.content_layout.addWidget(self._make_empty_state(
                "Nothing to continue",
                "Items you play will appear here so you can jump back in quickly.",
            ))
            self.content_layout.addStretch()
            return

        from collections import defaultdict
        grouped: dict[str, list[dict]] = defaultdict(list)
        for entry in entries:
            kind = entry.get("kind", "")
            if kind in self.KIND_LABEL:
                grouped[kind].append(entry)

        section_order = ("live", "vod", "series")
        any_section = False
        for kind in section_order:
            items = grouped.get(kind) or []
            if not items:
                continue
            any_section = True
            self._render_section(kind, items)

        if not any_section:
            self.content_layout.addWidget(self._make_empty_state(
                "Nothing to continue",
                "Items you play will appear here so you can jump back in quickly.",
            ))
        self.content_layout.addStretch()

    def _render_section(self, kind: str, items: list[dict]):
        label = QLabel(self.KIND_LABEL[kind], self.content)
        label.setObjectName("rowTitle")
        self.content_layout.addWidget(label)

        row_wrap = QScrollArea(self.content)
        row_wrap.setWidgetResizable(True)
        row_wrap.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        strip = QWidget(row_wrap)
        strip_layout = QHBoxLayout(strip)
        strip_layout.setContentsMargins(0, 0, 0, 0)
        strip_layout.setSpacing(10)

        size = (200, 110) if kind == "live" else (160, 230)
        fallback = self.KIND_FALLBACK[kind]
        for entry in items:
            card = PosterCard(
                entry.get("cover") or "",
                entry.get("name", ""),
                fallback,
                size,
                show_actions=True,
                parent=strip,
            )
            card.configure(
                entry.get("cover") or "",
                entry.get("name", ""),
                fallback=fallback,
            )
            card.clicked.connect(lambda e=entry: self._play(e, "app"))
            card.play_app.connect(lambda e=entry: self._play(e, "app"))
            card.play_vlc.connect(lambda e=entry: self._play(e, "vlc"))
            self._cards.append(card)
            strip_layout.addWidget(card)
        strip_layout.addStretch()

        row_wrap.setWidget(strip)
        row_wrap.setFixedHeight(size[1] + 48)
        self.content_layout.addWidget(row_wrap)

    def _play(self, entry: dict, backend: str):
        kind = entry.get("kind", "")
        if kind == "series":
            fake = {
                "series_id": entry.get("id"),
                "name": entry.get("name", ""),
                "cover": entry.get("cover", ""),
            }
            self.parent_window.open_series(fake)
            return
        if kind == "live":
            ext = getattr(self.xtream, "live_ext", "ts") or "ts"
        else:
            ext = entry.get("container_extension") or "mp4"
        url = self.xtream.stream_url(kind, entry.get("id"), ext)
        is_live = kind == "live"
        if backend == "app":
            resume_pos = 0.0
            on_position_save = None
            if not is_live:
                pos = float(entry.get("position", 0.0))
                dur = float(entry.get("duration", 0.0))
                if pos > 30 and (dur <= 0 or pos < dur - 30):
                    resume_pos = pos
                item_id = str(entry.get("id", ""))
                server = self.xtream.server
                username = self.xtream.username
                name = entry.get("name", "")
                cover = entry.get("cover", "") or ""
                extra = {"container_extension": entry.get("container_extension", "")}

                def on_position_save(p, d):
                    history.record(server, username, kind, item_id, name,
                                   cover=cover, extra=extra, position=p, duration=d)

            self.parent_window.play_in_app(
                url, entry.get("name", ""), is_live, None, 0,
                resume_pos=resume_pos, on_position_save=on_position_save,
            )
        else:
            self.parent_window.play_in_vlc(url)

    def _make_empty_state(self, title_text: str, body_text: str) -> QWidget:
        box = QWidget(self.content)
        box.setObjectName("emptyState")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(8)
        title = QLabel(title_text, box)
        title.setObjectName("emptyStateTitle")
        body = QLabel(body_text, box)
        body.setObjectName("emptyStateBody")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)
        return box

    def _clear_layout(self):
        self._cards = []
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _clear_all(self):
        history.clear(self.xtream.server, self.xtream.username)
        self.refresh()


class SeriesDetailPage(QWidget):
    back = Signal()

    def __init__(self, xtream, parent_window):
        super().__init__()
        self.xtream = xtream
        self.parent_window = parent_window
        self.show_data: dict | None = None
        self.seasons: dict = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 24)
        outer.setSpacing(10)

        back_btn = QPushButton("Back", self)
        back_btn.setObjectName("navBtn")
        back_btn.setFixedWidth(120)
        back_btn.clicked.connect(self.back.emit)
        outer.addWidget(back_btn)

        self.hero = Hero(self)
        self.hero._min_hero_height = 360
        self.hero.set_layout_mode("detail")
        outer.addWidget(self.hero)

        self.season_bar = QHBoxLayout()
        self.season_bar.setSpacing(6)
        outer.addLayout(self.season_bar)

        self.episodes_scroll = QScrollArea(self)
        self.episodes_scroll.setWidgetResizable(True)
        self.episodes_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.episodes_container = QWidget(self.episodes_scroll)
        self.episodes_layout = QVBoxLayout(self.episodes_container)
        self.episodes_layout.setSpacing(6)
        self.episodes_scroll.setWidget(self.episodes_container)
        outer.addWidget(self.episodes_scroll, 1)

    def load(self, show: dict):
        self.show_data = show
        meta_parts = []
        year = str(show.get("year") or "").strip()
        genre = str(show.get("genre") or "").strip()
        if year:
            meta_parts.append(year)
        if genre:
            meta_parts.append(genre.split(",")[0].strip())
        self.hero.set_content(
            show.get("name", ""),
            show.get("plot") or "",
            show.get("cover", ""),
            badge="SERIES",
            meta=" | ".join(part for part in meta_parts if part),
        )
        self.hero.play_btn.hide()
        self.hero._update_responsive_layout()
        self._clear(self.season_bar)
        self._clear(self.episodes_layout)
        self.episodes_layout.addWidget(EpisodeListSkeleton(parent=self.episodes_container))
        run_async(
            self.xtream.get_series_info,
            on_done=self._on_episodes,
            on_error=self._on_episodes_error,
            series_id=show.get("series_id"),
        )

    def _on_episodes_error(self, msg: str):
        self._clear(self.episodes_layout)
        err = QWidget(self.episodes_container)
        err.setObjectName("emptyState")
        err_layout = QVBoxLayout(err)
        err_layout.setContentsMargins(28, 28, 28, 28)
        err_layout.setSpacing(8)
        title = QLabel("Failed to load episodes", err)
        title.setObjectName("emptyStateTitle")
        body = QLabel(msg, err)
        body.setObjectName("emptyStateBody")
        body.setWordWrap(True)
        err_layout.addWidget(title)
        err_layout.addWidget(body)
        self.episodes_layout.addWidget(err)

    def _make_info_box(self, title_text: str, body_text: str) -> QWidget:
        box = QWidget(self.episodes_container)
        box.setObjectName("emptyState")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(8)
        title = QLabel(title_text, box)
        title.setObjectName("emptyStateTitle")
        body = QLabel(body_text, box)
        body.setObjectName("emptyStateBody")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)
        return box

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _on_episodes(self, data):
        episodes = data.get("episodes") if isinstance(data, dict) else None
        if isinstance(episodes, list):
            grouped: dict = {}
            for ep in episodes:
                season = str(ep.get("season", "1"))
                grouped.setdefault(season, []).append(ep)
            self.seasons = grouped
        elif isinstance(episodes, dict):
            self.seasons = episodes
        else:
            self.seasons = {}

        self._clear(self.season_bar)
        season_keys = sorted(
            self.seasons.keys(),
            key=lambda value: int(value) if str(value).isdigit() else 0,
        )
        if not season_keys:
            self._clear(self.episodes_layout)
            self.episodes_layout.addWidget(
                self._make_info_box("No episodes found", "This show does not have any listed episodes yet.")
            )
            self.episodes_layout.addStretch()
            return

        self._buttons = []
        for season in season_keys:
            btn = QPushButton(f"Season {season}", self)
            btn.setObjectName("chip")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, key=season: self._select_season(key))
            self.season_bar.addWidget(btn)
            self._buttons.append(btn)
        self.season_bar.addStretch()
        self._select_season(season_keys[0])

    def _select_season(self, key: str):
        for btn in self._buttons:
            btn.setChecked(btn.text() == f"Season {key}")
        self._clear(self.episodes_layout)
        episodes = self.seasons.get(key, [])
        self._current_episodes = episodes
        for ep in episodes:
            ep_id = str(ep.get("id"))
            num = ep.get("episode_num", "?")
            title = ep.get("title") or f"Episode {num}"
            ext = ep.get("container_extension") or "mp4"

            row_w = QWidget(self.episodes_container)
            row_w.setObjectName("episodeRow")
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(12, 8, 12, 8)
            row_h.setSpacing(8)

            label = QLabel(f"E{num}  -  {title}", row_w)
            label.setObjectName("episodeLabel")
            row_h.addWidget(label, 1)

            app_btn = QPushButton("Watch in App", row_w)
            app_btn.setObjectName("cardActionPrimary")
            app_btn.setFixedHeight(28)
            app_btn.setFixedWidth(112)
            app_btn.setCursor(Qt.PointingHandCursor)
            app_btn.clicked.connect(
                lambda _=False, sid=ep_id, e=ext, t=title: self._play(sid, e, t, "app")
            )
            row_h.addWidget(app_btn)

            vlc_btn = QPushButton("Watch in VLC", row_w)
            vlc_btn.setObjectName("cardActionSecondary")
            vlc_btn.setFixedHeight(28)
            vlc_btn.setFixedWidth(112)
            vlc_btn.setCursor(Qt.PointingHandCursor)
            vlc_btn.clicked.connect(
                lambda _=False, sid=ep_id, e=ext, t=title: self._play(sid, e, t, "vlc")
            )
            row_h.addWidget(vlc_btn)

            dl_btn = QPushButton("DL", row_w)
            dl_btn.setObjectName("cardActionSecondary")
            dl_btn.setFixedHeight(28)
            dl_btn.setFixedWidth(42)
            dl_btn.setCursor(Qt.PointingHandCursor)
            dl_btn.setToolTip("Download episode")
            dl_btn.clicked.connect(
                lambda _=False, sid=ep_id, e=ext, t=title: self._download_episode(sid, e, t)
            )
            row_h.addWidget(dl_btn)

            self.episodes_layout.addWidget(row_w)
        self.episodes_layout.addStretch()

    def _play(self, sid: str, ext: str, title: str, backend: str = "app"):
        url = self.xtream.stream_url("series", sid, ext)
        show = self.show_data or {}
        if show.get("series_id") is not None:
            try:
                history.record(
                    self.xtream.server,
                    self.xtream.username,
                    "series",
                    str(show.get("series_id")),
                    show.get("name", ""),
                    cover=show.get("cover", "") or "",
                    extra={"category_id": show.get("category_id")},
                )
            except Exception:
                _log.exception("history.record failed for series")
        if backend == "app":
            eps = getattr(self, "_current_episodes", []) or []
            playlist = [
                {
                    "url": self.xtream.stream_url(
                        "series", str(ep.get("id")),
                        ep.get("container_extension") or "mp4",
                    ),
                    "title": ep.get("title") or f"Episode {ep.get('episode_num', '?')}",
                    "is_live": False,
                }
                for ep in eps
            ]
            try:
                index = next(i for i, ep in enumerate(eps) if str(ep.get("id")) == sid)
            except StopIteration:
                index = 0

            entries = history.load(self.xtream.server, self.xtream.username)
            ep_entry = next((e for e in entries if str(e.get("id")) == sid and e.get("kind") == "series"), None)
            resume_pos = 0.0
            if ep_entry:
                pos = float(ep_entry.get("position", 0.0))
                dur = float(ep_entry.get("duration", 0.0))
                if pos > 30 and (dur <= 0 or pos < dur - 30):
                    resume_pos = pos

            server = self.xtream.server
            username = self.xtream.username
            show = self.show_data or {}
            ep_title = title

            def on_position_save(p, d):
                history.record(server, username, "series", sid, ep_title,
                               cover=show.get("cover", "") or "",
                               extra={"category_id": show.get("category_id")},
                               position=p, duration=d)

            self.parent_window.play_in_app(
                url, title, False, playlist, index,
                resume_pos=resume_pos, on_position_save=on_position_save,
            )
        else:
            self.parent_window.play_in_vlc(url)

    def _download_episode(self, sid: str, ext: str, title: str):
        show = self.show_data or {}
        show_name = show.get("name", "")
        full_title = f"{show_name} - {title}" if show_name else title
        url = self.xtream.stream_url("series", sid, ext)
        self.parent_window.download_movie(url, full_title, ext)
