"""Native gallery adapter for the existing Community account and Worker service."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QObject, Property, QBuffer, QIODevice, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QFileDialog

from .community_client import CommunityApiError, build_query
from .community_gallery_images import GalleryImages
from .community_preview_service import inspect_file, data_url
from .community_preview_photos import read_photos
from .community_tags import SUGGESTED_TAGS, MAX_TAGS, prepare_tags
from .models import DictListModel


def png_thumbnail(raw, width=640, height=400):
    image = QImage.fromData(raw)
    if image.isNull():
        raise ValueError("The artwork preview could not be read.")
    target = QImage(width, height, QImage.Format_RGBA8888)
    target.fill(Qt.transparent)
    image = image.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    painter = QPainter(target)
    painter.drawImage((width - image.width()) // 2, (height - image.height()) // 2, image)
    painter.end()
    output = QBuffer()
    output.open(QIODevice.WriteOnly)
    target.save(output, "PNG")
    return bytes(output.data())


def utc_schedule(fields):
    if not fields.get("timed"):
        return {"starts_at": None, "ends_at": None}
    values = []
    for name in ("starts", "ends"):
        value = datetime.fromisoformat(str(fields.get(name, "")))
        if value.tzinfo is None:
            value = value.astimezone()
        values.append(value.astimezone(timezone.utc))
    if values[1] <= values[0] or values[1].timestamp() <= time.time():
        raise ValueError("Choose a start and a later end time, with the end in the future.")
    return dict(zip(("starts_at", "ends_at"), (v.isoformat(timespec="milliseconds").replace("+00:00", "Z") for v in values)))


class CommunityGalleryService(QObject):
    changed = Signal()
    clockChanged = Signal()
    published = Signal()
    searchReset = Signal(str)
    renderChanged = Signal()
    renderOpened = Signal()
    renderClosed = Signal()
    liveryDownloaded = Signal()
    _completed = Signal(int, object)

    def __init__(self, repo, community, settings, parent=None):
        super().__init__(parent)
        self.repo, self.community, self.settings = Path(repo), community, settings
        self.root = community.paths.runtime_root / "community" / "gallery"
        self.root.mkdir(parents=True, exist_ok=True)
        self.images = GalleryImages()
        self.images.events.requested.connect(self._request_image)
        self.artwork_model = DictListModel(["artwork"], self)
        self.creator_model = DictListModel(["artwork"], self)
        self._rows, self._creator_rows, self._records = [], [], {}
        self._image_sources, self._image_pending, self._image_ready = {}, set(), {}
        self._filters = dict(kind="All", game="All", category="All", classification="All", sort="Newest", search="", supporters=False, creator="")
        self._scope, self._selected, self._creator = "Featured", {}, {}
        self._creator_name, self._page, self._creator_page = "", 0, 0
        self._more, self._creator_more = False, False
        self._catalog_loading, self._creator_loading = False, False
        self._catalog_generation, self._creator_generation = 0, 0
        self._epoch, self._job_id, self._jobs, self._active = 0, 0, {}, 0
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="community-gallery")
        self._completed.connect(self._finish)
        self._closed, self._message, self._error = False, "", False
        self._pending, self._ignored = None, []
        self._render_session, self._render_id = None, ""
        self._render_generation = 0
        self._fingerprint = None
        self._total = 0
        community.gallery_managed = True
        community.changed.connect(self._account_changed)
        community.catalogInvalidated.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self._account_changed()

    @Property(bool, constant=True)
    def live(self): return True
    @Property(QObject, constant=True)
    def artworkModel(self): return self.artwork_model
    @Property(QObject, constant=True)
    def creatorModel(self): return self.creator_model
    @Property("QVariantList", notify=changed)
    def rows(self): return list(self._rows)
    @Property(int, notify=changed)
    def totalCount(self): return self._total
    @Property(bool, notify=changed)
    def hasMore(self): return self._more
    @Property(bool, notify=changed)
    def creatorHasMore(self): return self._creator_more
    @Property("QVariantMap", notify=changed)
    def selected(self): return dict(self._selected)
    @Property("QVariantMap", notify=changed)
    def filters(self): return dict(self._filters)
    @Property(str, notify=changed)
    def scope(self): return self._scope
    @Property(str, notify=changed)
    def username(self): return self.community.username
    @Property(bool, notify=changed)
    def authenticated(self): return self.community.authenticated and not self.community.usernameRequired
    @Property(bool, notify=changed)
    def supporter(self): return self.community.supporterAccess
    @Property(bool, constant=True)
    def moderator(self): return False
    @Property(str, notify=changed)
    def language(self): return str(self.settings.communityLanguage)
    @Property(str, notify=changed)
    def status(self): return self._message or self.community.errorMessage or self.community.statusMessage
    @Property(bool, notify=changed)
    def hasError(self): return self._error or bool(self.community.errorMessage)
    @Property(bool, notify=changed)
    def busy(self): return self._active > 0
    @Property("QVariantMap", notify=changed)
    def upload(self): return {k: v for k, v in (self._pending or {}).items() if k not in ("payload", "preview", "photos")}
    @Property("QVariantMap", notify=changed)
    def profile(self):
        user = self.community.sessionUser
        return {"bio": user.get("bio", ""), "website": user.get("website_url", "")}
    @Property("QVariantMap", notify=changed)
    def creatorProfile(self): return dict(self._creator)
    @Property("QStringList", notify=changed)
    def ignoredCreators(self): return list(self._ignored)
    @Property("QStringList", constant=True)
    def suggestedTags(self): return list(SUGGESTED_TAGS)
    @Property(int, constant=True)
    def maximumTags(self): return MAX_TAGS
    @Property(QObject, notify=renderChanged)
    def liveryViewer(self): return self._render_session.service if self._render_session else None
    @Property(str, notify=clockChanged)
    def clock(self): return datetime.now().astimezone().strftime("%d %b %Y, %H:%M:%S %Z")
    @Property(str, notify=changed)
    def defaultStart(self): return datetime.fromtimestamp(time.time() + 60).astimezone().isoformat(timespec="minutes")
    @Property(str, notify=changed)
    def defaultEnd(self): return datetime.fromtimestamp(time.time() + 3660).astimezone().isoformat(timespec="minutes")

    def _call(self, function, callback, *, quiet=False):
        if self._closed: return
        self._job_id += 1
        ident, epoch = self._job_id, self._epoch
        self._jobs[ident] = (epoch, callback, quiet)
        if not quiet:
            self._active += 1
            self._message, self._error = "", False
        future = self._executor.submit(function)
        def done(result):
            try: value = result.result()
            except Exception as exc: value = exc
            if not self._closed: self._completed.emit(ident, value)
        future.add_done_callback(done)
        self.changed.emit()

    @Slot(int, object)
    def _finish(self, ident, value):
        job = self._jobs.pop(ident, None)
        if job is None: return
        epoch, callback, quiet = job
        if not quiet: self._active = max(0, self._active - 1)
        if epoch != self._epoch or self._closed: return
        if isinstance(value, Exception):
            logging.warning("Community gallery operation failed: %s", value)
            if not quiet: self._message, self._error = str(value), True
            if isinstance(value, CommunityApiError) and value.status == 401:
                self.community.refreshAccount()
            callback(None)
        else:
            callback(value)
        self.changed.emit()

    def _account_changed(self):
        client = self.community.sessionClient()
        fingerprint = (client.token, self.community.username, self.supporter)
        if fingerprint != self._fingerprint:
            self._fingerprint = fingerprint
            self._epoch += 1
            self._catalog_loading = self._creator_loading = False
            self.closeRender()
            self.images.clear()
            self._image_sources.clear(); self._image_pending.clear(); self._image_ready.clear()
            self._records.clear(); self._rows.clear(); self._creator_rows.clear()
            self._selected, self._creator, self._pending = {}, {}, None
            self.artwork_model.replace([]); self.creator_model.replace([])
            if not self.authenticated and self._scope in ("Favorites", "Following", "My uploads"):
                self._scope = "Browse"
            self.refresh()
            if self.authenticated:
                self._call(lambda: client.json("profile/ignored", authenticated=True), self._set_ignored, quiet=True)
        self.changed.emit()

    def _set_ignored(self, value):
        if value is not None: self._ignored = [row["username"] for row in value.get("items", [])]

    @Slot(str)
    def setLanguage(self, value):
        self.settings.setCommunityLanguage(value)
        self.changed.emit()

    @Slot("QStringList", str, result="QVariantMap")
    def prepareTags(self, current, entered): return prepare_tags(current, entered)

    def _path(self, page, creator=""):
        scopes = {"Featured": "featured", "Browse": "browse", "Timed Releases": "timed", "Livery": "browse", "Supporters": "browse", "Favorites": "favorites", "Following": "following", "My uploads": "mine"}
        sorts = {"Newest": "new", "Top rated": "votes", "Most downloaded": "downloads", "Name": "name"}
        filters = self._filters
        values = dict(view="gallery", scope="browse" if creator else scopes[self._scope], sort="new" if creator else sorts[filters["sort"]],
                      page=page, limit=48, creator=creator or filters["creator"])
        if not creator:
            values.update(search=filters["search"], kind="livery" if self._scope == "Livery" else filters["kind"], game=filters["game"], category=filters["category"],
                          classification="" if filters["classification"] == "All" else filters["classification"],
                          supporters="1" if self._scope == "Supporters" or filters["supporters"] else "")
        return build_query("artworks", values)

    @Slot()
    def refresh(self):
        if self._closed: return
        self._catalog_generation += 1
        generation = self._catalog_generation
        self._catalog_loading = True
        client = self.community.sessionClient()
        path = self._path(1)
        self._call(lambda: client.json(path, authenticated=bool(client.token)),
                   lambda value: self._apply_page(value, generation, False, False))

    @Slot()
    def loadMore(self):
        if self._catalog_loading or not self._more: return
        self._catalog_loading = True
        client, generation = self.community.sessionClient(), self._catalog_generation
        path = self._path(self._page + 1)
        self._call(lambda: client.json(path, authenticated=bool(client.token)),
                   lambda value: self._apply_page(value, generation, True, False), quiet=True)

    def _apply_page(self, value, generation, append, creator):
        if generation != (self._creator_generation if creator else self._catalog_generation): return
        if creator: self._creator_loading = False
        else: self._catalog_loading = False
        if value is None: return
        rows = self._creator_rows if creator else self._rows
        model = self.creator_model if creator else self.artwork_model
        if not append: rows.clear()
        known = {row["id"] for row in rows}
        new = [self._row(item) for item in value.get("items", []) if item.get("id") not in known]
        rows.extend(new)
        if append: model.append_many([{"artwork": row} for row in new])
        else: model.replace([{"artwork": row} for row in rows])
        page, pages = int(value.get("page", 1)), int(value.get("page_count", 1))
        if creator:
            self._creator_page, self._creator_more = page, page < pages
            self._creator["artworkCount"] = int(value.get("total", len(rows)))
        else:
            self._page, self._more, self._total = page, page < pages, int(value.get("total", len(rows)))
            if not append:
                ident = self._selected.get("id")
                row = next((row for row in rows if row["id"] == ident), rows[0] if rows else {})
                self._selected = row
                if row: self.select(row["id"])

    def _image_url(self, record, kind, path, digest=""):
        key = f"{self._epoch}/{record['id']}/{kind}/{digest or record.get('current_revision', 1)}"
        self._image_sources[key] = (path, digest, record["id"], kind)
        return f"image://community-gallery/{key}?ready={self._image_ready.get(key, 0)}"

    def _row(self, record):
        ident = str(record["id"])
        self._records[ident] = dict(record)
        creator = record.get("creator", {})
        locked = bool(record.get("supporter_only")) and not self.supporter
        starts, ends = record.get("starts_at"), record.get("ends_at")
        row = dict(id=ident, title=record.get("title", ""), description=record.get("description", ""),
            creator=creator.get("username", ""), kind=record.get("kind", "vinyl"), car=record.get("car", ""),
            game=", ".join(record.get("games", [])), shapes=record.get("shape_count", 0), tags=record.get("tags", []),
            category=record.get("category", ""), classification=record.get("classification", "toolmade"),
            supporter=bool(record.get("supporter_only")), locked=locked, own=creator.get("username") == self.username,
            favorite=bool(record.get("favorited")), followed=bool(creator.get("followed")), score=record.get("vote_score", 0),
            vote=record.get("vote", 0), downloads=record.get("downloads", 0), license=record.get("license", ""),
            state="available" if record.get("status") == "published" else record.get("status", "pending"),
            downloadable=not locked, sample=False, warning=record.get("schema_warning", ""), starts=starts, ends=ends, window="", photoUrls=[])
        if starts and ends:
            values = [datetime.fromisoformat(v.replace("Z", "+00:00")) for v in (starts, ends)]
            row["window"] = " - ".join(v.astimezone().strftime("%d %b %Y, %H:%M %Z") for v in values)
            if values[0].timestamp() > time.time(): row["state"] = "upcoming"
            if values[1].timestamp() <= time.time(): row["state"] = "expired"
        row["previewUrl"] = self._image_url(record, "thumbnail", record.get("thumbnail_url", ""), record.get("thumbnail_sha256", ""))
        return row

    @Slot(str)
    def _request_image(self, key):
        if key not in self._image_sources or key in self._image_pending: return
        path, digest, ident, kind = self._image_sources[key]
        if not path: return
        self._image_pending.add(key)
        client = self.community.sessionClient()
        def fetch():
            raw, _ = client.binary(path, authenticated=bool(client.token), maximum=2 * 1024 * 1024)
            if digest and hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("The artwork image failed its integrity check.")
            image = QImage.fromData(raw)
            if image.isNull() or image.width() > 2048 or image.height() > 2048:
                raise ValueError("The artwork image is invalid.")
            return image.scaled(640, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation) if kind == "thumbnail" else image
        def ready(image):
            self._image_pending.discard(key)
            if image is None: return
            self.images.put(key, image)
            self._image_ready[key] = self._image_ready.get(key, 0) + 1
            self._update_views(ident)
        self._call(fetch, ready, quiet=True)

    def _update_views(self, ident):
        for rows, model in ((self._rows, self.artwork_model), (self._creator_rows, self.creator_model)):
            for index, row in enumerate(rows):
                if row["id"] == ident:
                    rows[index] = self._row(self._records[ident])
                    model.set_row_value(index, "artwork", rows[index])
        if self._selected.get("id") == ident:
            self._selected = self._row(self._records[ident])
            self._selected_media()

    def _selected_media(self):
        if not self._selected: return
        record = self._records[self._selected["id"]]
        if not self._selected["locked"]:
            self._selected["previewUrl"] = self._image_url(record, "preview", record["preview_url"], record.get("preview_sha256", ""))
            self._selected["photoUrls"] = [self._image_url(record, f"photo{index}", path)
                for index, path in enumerate(record.get("photo_urls", []))] if self.authenticated else []
            if self._selected["kind"] == "livery" and not (record.get("cover_is_first_photo") and self._selected["photoUrls"]):
                self._selected["photoUrls"].insert(0, self._selected["previewUrl"])

    @Slot(str)
    def select(self, ident):
        if ident not in self._records: return
        if ident != self._render_id: self.closeRender()
        self._selected = self._row(self._records[ident])
        self._selected_media()
        self.changed.emit()

    @Slot(str, str)
    def filter(self, key, value):
        if key == "scope":
            if value == "Livery": self._filters["kind"] = "livery"
            elif self._scope == "Livery": self._filters["kind"] = "All"
            if value == "Supporters": self._filters["supporters"] = True
            elif self._scope == "Supporters": self._filters["supporters"] = False
            self._scope = value
        elif key in self._filters:
            self._filters[key] = value
            if key == "kind" and self._scope == "Livery" and value != "livery": self._scope = "Browse"
        else: return
        self.refresh()

    @Slot(bool)
    def filterSupporters(self, value):
        self._filters["supporters"] = value
        if not value and self._scope == "Supporters": self._scope = "Browse"
        self.refresh()

    @Slot(str)
    def viewCreator(self, name):
        self._creator_name = name
        self._creator_generation += 1
        generation = self._creator_generation
        self._creator_rows.clear(); self.creator_model.replace([])
        self._creator, self._creator_more, self._creator_loading = {}, False, True
        client = self.community.sessionClient()
        path = self._path(1, name)
        def fetch():
            return (client.json(f"creators/{quote(name)}", authenticated=bool(client.token)),
                    client.json(path, authenticated=bool(client.token)))
        def done(value):
            if generation != self._creator_generation: return
            self._creator_loading = False
            if value is None: return
            profile, catalog = value
            creator = profile.get("creator", {})
            self._creator = dict(username=name, creator=name, bio=creator.get("bio", ""), website=creator.get("website_url", ""),
                followers=creator.get("followers", 0), followed=creator.get("followed", False),
                ignored=creator.get("ignored", False), own=name == self.username, artworkCount=catalog.get("total", 0))
            self._apply_page(catalog, generation, False, True)
        self._call(fetch, done)

    @Slot()
    def loadMoreCreator(self):
        if self._creator_loading or not self._creator_more: return
        self._creator_loading = True
        client, generation = self.community.sessionClient(), self._creator_generation
        path = self._path(self._creator_page + 1, self._creator_name)
        self._call(lambda: client.json(path, authenticated=bool(client.token)),
                   lambda value: self._apply_page(value, generation, True, True), quiet=True)

    @Slot(str, result=bool)
    def inspectCreatorArtwork(self, ident):
        if ident not in self._records: return False
        self.select(ident)
        return True

    @Slot(str)
    def browseCreator(self, ident=""):
        self._filters["creator"], self._scope = self._creator_name, "Browse"
        self.refresh()

    def _post(self, path, payload, callback):
        client = self.community.sessionClient()
        self._call(lambda: client.json(path, "POST", payload, authenticated=True), callback)

    @Slot(int)
    def vote(self, value):
        if not self._selected: return
        ident = self._selected["id"]
        vote = 0 if self._selected.get("vote") == value else value
        def done(result):
            if result is not None and ident in self._records:
                self._records[ident].update(result); self._update_views(ident)
        self._post(f"artworks/{quote(ident)}/vote", {"vote": vote}, done)

    @Slot(str)
    def toggle(self, kind):
        if not self._selected: return
        ident, name = self._selected["id"], self._selected["creator"]
        if kind == "favorites":
            def done(result):
                if result is not None:
                    self._records[ident].update(result); self._update_views(ident)
            self._post(f"artworks/{quote(ident)}/favorite", {"favorite": not self._selected["favorite"]}, done)
        elif kind == "follows": self._follow(name, not self._selected["followed"])
        elif kind == "ignored": self._ignore(name, True)

    def _follow(self, name, value):
        def done(result):
            if result is None: return
            for ident, record in list(self._records.items()):
                if record.get("creator", {}).get("username") == name:
                    record["creator"]["followed"] = value; self._update_views(ident)
            if self._creator_name == name: self._creator.update(followed=value, followers=result.get("followers", 0))
        self._post(f"creators/{quote(name)}/follow", {"follow": value}, done)

    @Slot()
    def followCreator(self): self._follow(self._creator_name, not self._creator.get("followed"))

    def _ignore(self, name, value):
        def done(result):
            if result is None: return
            self._ignored = sorted((set(self._ignored) | {name}) if value else (set(self._ignored) - {name}))
            self.refresh()
        self._post(f"creators/{quote(name)}/ignore", {"ignored": value}, done)

    @Slot(str)
    def unignore(self, name): self._ignore(name, False)

    @Slot(str, str)
    def saveProfile(self, bio, website): self.community.updateProfile(bio, website)

    @Slot(str)
    def report(self, reason):
        ident = self._selected.get("id", "")
        self._post(f"artworks/{quote(ident)}/report", {"reason": "other", "details": reason},
                   lambda result: self._notice("Report sent to staff.", "운영진에게 신고를 보냈습니다.") if result is not None else None)

    @Slot(str)
    def moderate(self, action):
        if action != "remove" or not self._selected.get("own"): return
        client, ident = self.community.sessionClient(), self._selected["id"]
        self._call(lambda: client.json(f"artworks/{quote(ident)}", "DELETE", authenticated=True),
                   lambda result: self.refresh() if result is not None else None)

    @Slot(str)
    def updateTags(self, text):
        if not self._selected.get('own'): return
        tags = prepare_tags([], text)
        if tags['error']:
            self._message, self._error = tags['error'], True
            self.changed.emit()
            return
        ident, client = self._selected['id'], self.community.sessionClient()
        def ready(result):
            if result is not None:
                self._records[ident] = result['artwork']; self._update_views(ident)
        self._call(lambda: client.json(f'artworks/{quote(ident)}', 'PATCH', {'tags': tags['tags']}, authenticated=True), ready)

    def _notice(self, english, korean): self._message = korean if self.language == "ko" else english

    def _tick(self):
        self.clockChanged.emit()
        now = time.time()
        changed = any(row.get("ends") and datetime.fromisoformat(row["ends"].replace("Z", "+00:00")).timestamp() <= now
                      or row.get("state") == "upcoming" and datetime.fromisoformat(row["starts"].replace("Z", "+00:00")).timestamp() <= now
                      for row in self._rows + self._creator_rows)
        if changed and not self._catalog_loading:
            self.closeRender(); self.images.clear(); self._image_ready.clear()
            self._selected = {}
            self._rows.clear(); self.artwork_model.replace([])
            self.refresh()
            if self._creator_name: self.viewCreator(self._creator_name)

    @Slot()
    def chooseFile(self):
        path, _ = QFileDialog.getOpenFileName(None, "Community artwork", str(self.community.paths.library_root), "Artwork (*.json *.kfpslivery)")
        if path: self.inspectPath(path)

    @Slot(str)
    def inspectPath(self, path):
        if self.busy: return
        self._pending = None
        def inspect():
            if Path(path).suffix.lower() == '.kfpslivery' and Path(path).stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Community livery packages must be 16 MiB or smaller.")
            return inspect_file(path, self.root)
        def ready(result):
            if result is None: return
            self._pending = dict(result, previewUrl=data_url(result["preview"]), photos=[], photoUrls=[])
            self._notice("File checked. Ready to upload.", "파일 확인이 끝났습니다. 업로드할 준비가 되었어요.")
        self._call(inspect, ready)

    @Slot()
    def choosePhotos(self):
        paths, _ = QFileDialog.getOpenFileNames(None, "Livery photos (up to 3)", str(self.repo), "Photos (*.png *.jpg *.jpeg *.webp)")
        if paths: self.inspectPhotos(paths)

    @Slot("QStringList")
    def inspectPhotos(self, paths):
        if self.busy or not self._pending or self._pending['kind'] != 'livery': return
        def prepare():
            photos = read_photos(paths)
            result = []
            for photo in photos:
                width = 1920
                while len(photo) > 2 * 1024 * 1024 and width >= 800:
                    width = int(width * .8)
                    photo = png_thumbnail(photo, width, int(width * .625))
                if len(photo) > 2 * 1024 * 1024:
                    raise ValueError("A photo could not be prepared within the upload limit.")
                image = QImage.fromData(photo)
                if image.width() < 64 or image.height() < 64:
                    photo = png_thumbnail(photo)
                result.append(photo)
            return result
        def ready(photos):
            if photos is not None and self._pending:
                self._pending.update(photos=photos, photoUrls=[data_url(photo) for photo in photos])
        self._call(prepare, ready)

    @Slot(int)
    def removePhoto(self, index):
        if self.busy or not self._pending: return
        photos = self._pending.get('photos', [])
        if 0 <= index < len(photos):
            photos.pop(index)
            self._pending['photoUrls'] = [data_url(photo) for photo in photos]
            self.changed.emit()

    @Slot("QVariantMap")
    def publish(self, fields):
        if self.busy or not self._pending: return
        pending, client = dict(self._pending), self.community.sessionClient()
        version = self.community._app_version
        def upload():
            tags = prepare_tags([], fields.get('tags', ''))
            if tags['error']: raise ValueError(tags['error'])
            licenses = {'KFPS Community Share': 'kfps-community-share-v1', 'CC0 1.0': 'cc0-1.0',
                        'CC BY 4.0': 'cc-by-4.0', 'CC BY-NC 4.0': 'cc-by-nc-4.0'}
            metadata = dict(title=fields.get('title', ''), description=fields.get('description', ''),
                category=fields.get('category', 'Original Artwork'), classification=fields.get('classification', 'handmade'),
                tags=tags['tags'], supporter_only=bool(fields.get('supporter')), confirm_rights=bool(fields.get('rights')),
                confirm_compatibility=bool(fields.get('compatibility')), client_version=version,
                license=licenses.get(fields.get('license'), fields.get('license', 'kfps-community-share-v1')), **utc_schedule(fields))
            if pending['kind'] == 'vinyl':
                cover = png_thumbnail(pending['preview'], 900, 700)
                metadata.update(design=json.loads(pending['payload']), preview_base64=base64.b64encode(cover).decode(),
                                thumbnail_base64=base64.b64encode(png_thumbnail(cover)).decode())
                revision_id = str(fields.get('revision_id', ''))
                if revision_id:
                    metadata['change_note'] = fields.get('change_note', '')
                    return client.json(f'artworks/{quote(revision_id)}/revisions', 'POST', metadata, authenticated=True)
                return client.json('artworks', 'POST', metadata, authenticated=True)
            if fields.get('revision_id'):
                raise ValueError('Choose a vinyl JSON for this revision.')
            photos = pending.get('photos', [])
            if len(photos) > 3: raise ValueError('Add no more than three livery photos.')
            if not pending['preview']:
                raise ValueError('This livery package has no preview. Export it again with its in-game thumbnail.')
            cover = png_thumbnail(pending['preview'], 900, 700)
            metadata['photo_count'] = len(photos)
            files = {'package': ('artwork.kfpslivery', pending['payload'], 'application/octet-stream'),
                     'preview': ('preview.png', cover, 'image/png'),
                     'thumbnail': ('thumbnail.png', png_thumbnail(cover), 'image/png')}
            files.update({f'photo{index}': (f'photo{index}.png', photo, 'image/png') for index, photo in enumerate(photos)})
            return client.multipart('liveries', metadata, files)
        def ready(result):
            if result is None: return
            self._pending = None
            self._scope = 'My uploads'
            self._filters.update(kind='All', game='All', category='All', classification='All', creator='', search='', supporters=False)
            self.searchReset.emit("")
            if result.get('original_details_retained'):
                self._notice('Your previous upload was restored with its original details and photos.', '이전 업로드를 원래의 설명과 사진으로 복구했습니다.')
            else:
                self._notice('Artwork uploaded.', '작품을 업로드했습니다.')
            self.published.emit()
            self.refresh()
        self._call(upload, ready)

    def _livery_payload(self, record, client):
        from tools.livery.package import validate_full_livery_package
        raw, _ = client.binary(record['download_url'], authenticated=True, maximum=16 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != record.get('content_sha256'):
            raise ValueError('The downloaded livery failed its integrity check.')
        with tempfile.TemporaryDirectory(dir=self.root) as temporary:
            path = Path(temporary) / 'artwork.kfpslivery'
            path.write_bytes(raw)
            validate_full_livery_package(path)
        return raw

    @Slot()
    def download(self):
        if self.busy or not self._selected or self._selected.get('locked'): return
        record = dict(self._records[self._selected['id']])
        client = self.community.sessionClient()
        def fetch():
            if record.get('kind', 'vinyl') == 'vinyl':
                return self.community.downloadGalleryVinyl(record, client)
            raw = self._livery_payload(record, client)
            from .experimental.full_livery.paths import FullLiveryPaths
            folder = FullLiveryPaths.for_app(self.community.paths).package_root
            target = folder / (str(record['id']) + '.kfpslivery')
            self.community._atomic_write(target, raw)
            return {'path': str(target.resolve()), 'title': record['title']}
        def done(result):
            if result is None: return
            self.community.acceptGalleryDownload(result)
            if record.get('kind') == 'livery': self.liveryDownloaded.emit()
            self._notice('Downloaded to your library.', '라이브러리에 다운로드했습니다.')
        self._call(fetch, done)

    @Slot()
    def openDownloads(self): self.community.openDownloadedFolder()

    @Slot()
    def openRender(self):
        if self.busy or not self._selected or self._selected.get('locked') or self._selected.get('kind') != 'livery': return
        record, client = dict(self._records[self._selected['id']]), self.community.sessionClient()
        ident = record['id']
        self.closeRender()
        generation = self._render_generation
        def ready(raw):
            if raw is None or generation != self._render_generation or self._selected.get('id') != ident: return
            from .community_preview_livery import PreviewLiverySession
            self._render_session = PreviewLiverySession(self.repo, self.root / 'render', raw)
            self._render_id = ident
            self.renderChanged.emit(); self.renderOpened.emit()
            self._render_session.start()
        self._call(lambda: self._livery_payload(record, client), ready)

    @Slot()
    def closeRender(self):
        self._render_generation += 1
        session, self._render_session = self._render_session, None
        self._render_id = ''
        if session:
            self.renderChanged.emit(); self.renderClosed.emit()
            session.close()

    def close(self):
        self._closed = True
        self.timer.stop()
        self.closeRender()
        self._executor.shutdown(wait=True, cancel_futures=True)
        self.images.clear()
