from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import logging
import sqlite3
import time
import tempfile
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, Property, QBuffer, QIODevice, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QDesktopServices, QImage
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QFileDialog

from .community_preview_store import ACCOUNTS, PreviewError, PreviewStore
from .community_tags import SUGGESTED_TAGS, MAX_TAGS, prepare_tags
from .models import DictListModel
from .community_preview_images import PreviewImages


def image_bytes(raw):
    image = QImage.fromData(raw)
    if image.isNull():
        raise PreviewError("The preview image could not be read.")
    image = image.scaled(900, 700, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    output = QBuffer()
    output.open(QIODevice.WriteOnly)
    image.save(output, "PNG")
    return bytes(output.data())


def data_url(raw):
    return "data:image/png;base64," + base64.b64encode(raw).decode() if raw else ""


def inspect_file(path, root):
    source = Path(path).resolve(strict=True)
    if source.suffix.lower() not in (".json", ".kfpslivery"):
        raise PreviewError("Choose a vinyl JSON or a .kfpslivery package.")
    maximum = (24 if source.suffix.lower() == ".json" else 256) * 1024 * 1024
    with source.open("rb") as handle:
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise PreviewError("The selected file exceeds the upload size limit.")
    staging = Path(root).resolve() / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    # Validate an immutable local copy; the user's file and all production state stay untouched.
    with tempfile.TemporaryDirectory(dir=staging) as temporary:
        snapshot = Path(temporary) / ("upload" + source.suffix.lower())
        snapshot.write_bytes(raw)
        result = _inspect_snapshot(snapshot, Path(temporary))
        if result["title"] == "upload": result["title"] = source.stem
        return result


def _inspect_snapshot(source, root):
    from .community_validation import inspect_upload
    if source.suffix.lower() == ".json":
        result = inspect_upload(source, root)
        payload = json.dumps(result.payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return {"kind": "vinyl", "title": result.display_name, "shapes": result.shape_count,
                "game": ", ".join(result.detected_games) or "Unverified", "car": "",
                "warning": result.schema_warning, "payload": payload,
                "preview": image_bytes(result.preview_bytes), "extension": ".json"}
    if source.suffix.lower() == ".kfpslivery":
        from tools.livery.package import validate_full_livery_package
        if source.stat().st_size > 256 * 1024 * 1024:
            raise PreviewError("The livery package exceeds 256 MB.")
        manifest = validate_full_livery_package(source)
        with zipfile.ZipFile(source) as bundle:
            names = bundle.namelist()
            thumb = next((n for n in names if n == "source/fh6/bigThumb.webp"), "")
            thumb = thumb or next((n for n in names if n.startswith("preview/") and n.endswith((".png", ".webp"))), "")
            preview = image_bytes(bundle.read(thumb)) if thumb else b""
        return {"kind": "livery", "title": manifest.get("livery", {}).get("title") or source.stem,
                "shapes": manifest.get("livery", {}).get("decoded_layer_count", 0),
                "game": str(manifest.get("source", {}).get("game", "FH6")).upper(),
                "car": str(manifest.get("vehicle", {}).get("model_code") or manifest.get("livery", {}).get("target_car_id", "")),
                "warning": "", "payload": source.read_bytes(), "preview": preview, "extension": ".kfpslivery"}
    raise PreviewError("Choose a vinyl JSON or a .kfpslivery package.")


def seed_catalog(store, repo):
    if store.setting("seeded"):
        return
    now = time.time()
    assets = repo / "KFPS.UI" / "assets"
    samples = [
        ("Mini Kloudy", assets / "mini-kloudy.png", "vinyl", "Characters", "cute, character"),
        ("KFPS emblem", assets / "kfps-logo.png", "vinyl", "Logos", "logo, kfps"),
        ("Coffee break", assets / "mini-kloudy-splash" / "coffee.png", "vinyl", "Characters", "cute, coffee"),
        ("KFPS full-car showcase", repo / "docs/screenshots/showcase/livery-preview.png", "livery", "Motorsport", "itasha, kfps"),
        ("After hours", assets / "mini-kloudy-splash" / "exhausted.png", "vinyl", "Characters", "cute, character"),
        ("Supporter sample", assets / "mini-kloudy-splash" / "shark-plush.png", "vinyl", "Characters", "cute, character"),
    ]
    for index, (title, path, kind, category, tags) in enumerate(samples):
        if not path.is_file():
            continue
        store.add({"title": title, "description": "Local visual sample. This image is not a downloadable vinyl or livery file.",
                   "creator": "Kloudy" if index < 2 else "StudioSample", "kind": kind,
                   "category": category, "tags": tags.split(", "), "game": "FH6", "shapes": 0,
                   "classification": "handmade", "supporter": index == 5, "featured": True,
                   "license": "Preview only", "car": "KFPS showcase" if kind == "livery" else "",
                   "sample": True, "order": index, "warning": ""}, None, image_bytes(path.read_bytes()), "Moderator", seed=True)
    from .community_validation import inspect_upload
    fixture_root = store.root / "fixtures"
    fixture_root.mkdir(exist_ok=True)
    for index, (title, color) in enumerate([
        ("Track stripes", [242, 80, 145, 255]), ("Signal bars", [35, 192, 218, 255]),
        ("Sunset checker", [250, 193, 63, 255]), ("Timed release", [88, 212, 158, 255]),
        ("Upcoming release", [232, 110, 83, 255]), ("Supporter stripes", [206, 155, 240, 255]),
    ]):
        shapes = []
        for stripe in range(6):
            shapes.append({"type": 16, "color": color if stripe % 2 == 0 else [245, 245, 245, 255],
                           "data": [200 + stripe * 115, 450, 38, 280 - stripe * 22, 325]})
        source = fixture_root / f"sample-{index}.json"
        source.write_text(json.dumps({"shapes": shapes}), encoding="utf-8")
        inspected = inspect_upload(source, store.root)
        store.add({"title": title, "description": "Six editable shapes. A synthetic file for local upload and download checks.",
                   "creator": "Kloudy" if index >= 3 else "TestCreator", "kind": "vinyl", "category": "Patterns",
                   "tags": ["racing", "stripes"], "game": "FH6", "shapes": 6, "classification": "handmade",
                   "supporter": index == 5, "featured": index < 3, "license": "CC0 1.0", "car": "", "sample": False, "order": 10 + index, "warning": ""},
                  source.read_bytes(), image_bytes(inspected.preview_bytes), "Moderator", seed=True,
                  starts=now - 60 if index == 3 else now + 3600 if index == 4 else None,
                  ends=now + 3600 if index == 3 else now + 7200 if index == 4 else None)
    store.save_setting("seeded", "1")


class CommunityPreviewService(QObject):
    changed = Signal()
    clockChanged = Signal()
    uploadFinished = Signal(object)
    published = Signal()
    photosFinished = Signal(object)
    renderChanged = Signal()
    renderOpened = Signal()
    renderClosed = Signal()

    def __init__(self, repo, state_root):
        super().__init__()
        self.repo = Path(repo)
        self.store = PreviewStore(Path(state_root))
        self.mode = "Creator"
        self.creator_value = ""
        self.creator_filter = ""
        self.language_value = self.store.setting("language", "en")
        self.scope_value = "Featured"
        self.query = ""
        self.kind_value = "All"
        self.game_value = "All"
        self.category_value = "All"
        self.classification_value = "All"
        self.sort_value = "Newest"
        self.supporters_only = False
        self.rows_value = []
        self.artwork_model = DictListModel(["artwork"], self)
        self.creator_model = DictListModel(["artwork"], self)
        self.creator_cursor = None
        self.creator_profile_value = {}
        self.image_generation = 0
        self.images = PreviewImages(self.store.root / "catalog.sqlite3")
        self.selected_id = ""
        self.selected_value = {}
        self.message = ""
        self.error = False
        self.pending = None
        self._render_session = None
        self._render_id = ""
        self.working = False
        self.offset = 0
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="community-preview")
        self.uploadFinished.connect(self._finish_upload)
        self.photosFinished.connect(self._finish_photos)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()
        self.refresh()

    def now(self):
        return time.time() + self.offset

    @Property("QVariantList", notify=changed)
    def rows(self): return self.rows_value
    @Property("QVariantMap", notify=changed)
    def filters(self):
        return {"kind": self.kind_value, "game": self.game_value, "category": self.category_value,
                "classification": self.classification_value, "sort": self.sort_value, "search": self.query,
                "supporters": self.supporters_only, "creator": self.creator_filter}
    @Property(QObject, constant=True)
    def artworkModel(self): return self.artwork_model
    @Property(QObject, constant=True)
    def creatorModel(self): return self.creator_model
    @Property(bool, notify=changed)
    def creatorHasMore(self): return self.creator_cursor is not None
    @Property("QVariantMap", notify=changed)
    def selected(self): return self.selected_value
    @Property(str, notify=changed)
    def account(self): return self.mode
    @Property(str, notify=changed)
    def username(self): return ACCOUNTS[self.mode][0]
    @Property(bool, notify=changed)
    def authenticated(self): return bool(self.username)
    @Property(bool, notify=changed)
    def moderator(self): return ACCOUNTS[self.mode][2]
    @Property(bool, notify=changed)
    def supporter(self): return ACCOUNTS[self.mode][1]
    @Property(str, notify=changed)
    def language(self): return self.language_value
    @Property(str, notify=changed)
    def scope(self): return self.scope_value
    @Property(str, notify=changed)
    def status(self): return self.message
    @Property(bool, notify=changed)
    def hasError(self): return self.error
    @Property(bool, notify=changed)
    def busy(self): return self.working
    @Property("QVariantMap", notify=changed)
    def upload(self):
        return {k: v for k, v in (self.pending or {}).items() if k not in ("payload", "preview", "photos")}
    @Property(QObject, notify=renderChanged)
    def liveryViewer(self):
        return self._render_session.service if self._render_session else None
    @Property("QVariantMap", notify=changed)
    def profile(self): return self.store.profile(self.mode)
    @Property("QVariantMap", notify=changed)
    def creatorProfile(self):
        return self.creator_profile_value
    @Property("QStringList", notify=changed)
    def ignoredCreators(self): return self.store.ignored_creators(self.mode)
    @Property("QStringList", constant=True)
    def suggestedTags(self): return list(SUGGESTED_TAGS)
    @Property(int, constant=True)
    def maximumTags(self): return MAX_TAGS
    @Property(str, notify=clockChanged)
    def clock(self): return datetime.fromtimestamp(self.now()).astimezone().strftime("%d %b %Y, %H:%M:%S %Z")
    @Property(str, notify=changed)
    def defaultStart(self): return datetime.fromtimestamp(self.now() + 60).astimezone().isoformat(timespec="minutes")
    @Property(str, notify=changed)
    def defaultEnd(self): return datetime.fromtimestamp(self.now() + 3660).astimezone().isoformat(timespec="minutes")

    @Slot("QStringList", str, result="QVariantMap")
    def prepareTags(self, current, entered): return prepare_tags(current, entered)

    def _run(self, action):
        try:
            self.message = ""
            action()
            self.error = False
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.message, self.error = str(exc), True
            logging.warning("Local preview action rejected: %s", exc)
        self.refresh()

    @Slot()
    def refresh(self):
        self.images.set_access(self.username, self.offset, self.image_generation)
        all_rows = self.store.catalog(self.mode, self.now())
        self._next_boundary = self.store.next_boundary(self.now())
        rows = []
        for row in all_rows:
            if self.creator_filter and row["creator"] != self.creator_filter: continue
            if self.scope_value not in ("My uploads", "Moderation") and row["state"] != "available": continue
            if self.scope_value == "My uploads" and not row["own"]: continue
            if self.scope_value == "Moderation" and not self.moderator: continue
            if self.scope_value == "Featured" and not row.get("featured"): continue
            if self.scope_value == "Favorites" and not row["favorite"]: continue
            if self.scope_value == "Following" and not row["followed"]: continue
            if self.scope_value == "Timed Releases" and row["ends"] is None: continue
            if row["ignored"] and self.scope_value not in ("My uploads", "Moderation"): continue
            if self.kind_value != "All" and row["kind"] != self.kind_value: continue
            if self.game_value != "All" and row["game"] != self.game_value: continue
            if self.category_value != "All" and row["category"] != self.category_value: continue
            if self.classification_value != "All" and row["classification"] != self.classification_value: continue
            if self.supporters_only and not row.get("supporter"): continue
            haystack = " ".join([row["title"], row["creator"], row["description"], *row["tags"]]).casefold()
            if any(word not in haystack for word in self.query.casefold().split()): continue
            row["previewUrl"] = data_url(self.store.preview(row["id"], self.mode, self.now()))
            row["window"] = ""
            if row.get("ends"):
                row["window"] = " - ".join(datetime.fromtimestamp(row[k]).astimezone().strftime("%d %b, %H:%M %Z") for k in ("starts", "ends"))
            rows.append(row)
        rows.sort(key=lambda r: r.get("order", 100) if self.scope_value == "Featured" else
                  (-r["score"], -r["created"]) if self.sort_value == "Top rated" else
                  (-r["downloads"], -r["created"]) if self.sort_value == "Most downloaded" else
                  r["title"].casefold() if self.sort_value == "Name" else -r["created"])
        if [r["id"] for r in rows] == [r["id"] for r in self.rows_value]:
            for index, row in enumerate(rows):
                self.artwork_model.set_row_value(index, "artwork", row)
        else:
            self.artwork_model.replace([{"artwork": row} for row in rows])
        self.rows_value = rows
        if self.selected_id not in {r["id"] for r in rows}:
            self.selected_id = rows[0]["id"] if rows else ""
        self.selected_value = next((r for r in rows if r["id"] == self.selected_id), {})
        self._selection_media()
        if self.creator_value:
            profile = self.store.creator_profile(self.creator_value, self.mode, self.now())
            count_changed = profile["artworkCount"] != self.creator_profile_value.get("artworkCount")
            self.creator_profile_value = profile
            if count_changed:
                self.creator_model.replace([])
                self.creator_cursor = None
                self._append_creator_page()
        self.changed.emit()

    def _selection_media(self):
        if self.selected_value:
            self.selected_value["photoUrls"] = [data_url(raw) for raw in self.store.photos(self.selected_id, self.mode, self.now())]
        if self._render_session and (self.selected_id != self._render_id or self.selected_value.get("state") != "available" or self.selected_value.get("locked")):
            self.closeRender()

    def _tick(self):
        self.clockChanged.emit()
        if self.now() >= self._next_boundary:
            self.refresh()
            if self.creator_value: self.viewCreator(self.creator_value)

    @Slot(str)
    def setAccount(self, mode):
        if mode not in ACCOUNTS: return
        if mode != self.mode: self.closeRender()
        self.mode = mode
        self.image_generation += 1
        if self.scope_value == "Moderation" and not self.moderator: self.scope_value = "Browse"
        self.message = ""
        self.refresh()
        if self.creator_value: self.viewCreator(self.creator_value)

    @Slot(str)
    def setLanguage(self, language):
        self.language_value = language if language in ("en", "ko") else "en"
        self.store.save_setting("language", self.language_value)
        self.changed.emit()

    @Slot(str, str)
    def filter(self, key, value):
        attributes = {"scope": "scope_value", "search": "query", "kind": "kind_value", "game": "game_value",
                      "category": "category_value", "classification": "classification_value", "sort": "sort_value",
                      "creator": "creator_filter"}
        if key in attributes:
            setattr(self, attributes[key], value)
            self.refresh()

    @Slot(bool)
    def filterSupporters(self, value):
        self.supporters_only = value
        self.refresh()

    @Slot(str)
    def select(self, ident):
        self.selected_id = ident
        self.selected_value = next((r for r in self.rows_value if r["id"] == ident), {})
        self._selection_media()
        self.changed.emit()

    @Slot()
    def openRender(self):
        def action():
            from .community_preview_livery import PreviewLiverySession
            payload = self.store.render_payload(self.selected_id, self.mode, self.now())
            self.closeRender()
            self._render_session = PreviewLiverySession(self.repo, self.store.root / "render", payload)
            self._render_id = self.selected_id
            self.renderChanged.emit()
            self.renderOpened.emit()
            self._render_session.start()
        self._run(action)

    @Slot()
    def closeRender(self):
        session, self._render_session = self._render_session, None
        self._render_id = ""
        if session:
            self.renderChanged.emit()
            self.renderClosed.emit()
            session.close()

    @Slot(int)
    def vote(self, value):
        self._run(lambda: self.store.vote(self.selected_id, 0 if self.selected_value.get("vote") == value else value, self.mode, self.now()))

    @Slot(str)
    def toggle(self, kind):
        value = self.selected_id if kind == "favorites" else self.selected_value.get("creator", "")
        self._run(lambda: self.store.toggle(kind, value, self.mode))

    @Slot(str)
    def unignore(self, creator): self._run(lambda: self.store.toggle("ignored", creator, self.mode))

    @Slot()
    def download(self):
        def action():
            path = self.store.download(self.selected_id, self.mode, self.now())
            self.message = "Downloaded to the local test library: " + str(path.name)
        self._run(action)

    @Slot()
    def openDownloads(self): QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root / "downloads")))

    @Slot(str)
    def moderate(self, action): self._run(lambda: self.store.moderate(self.selected_id, action, self.mode, self.now()))

    @Slot(str)
    def report(self, reason):
        self._run(lambda: self.store.report(self.selected_id, reason, self.mode, self.now()))
        if not self.error:
            self.message = "Report saved to the local moderation queue."
            self.changed.emit()

    @Slot(result="QVariantList")
    def reports(self):
        return self.store.report_details(self.selected_id, self.mode) if self.moderator and self.selected_id else []

    @Slot(str, str)
    def saveProfile(self, bio, website): self._run(lambda: self.store.save_profile(self.mode, bio, website))

    @Slot(str)
    def viewCreator(self, creator):
        self.creator_value = creator
        self.creator_profile_value = self.store.creator_profile(creator, self.mode, self.now())
        self.creator_model.replace([])
        self.creator_cursor = None
        self._append_creator_page()
        self.changed.emit()

    def _append_creator_page(self):
        page = self.store.creator_page(self.creator_value, self.mode, now=self.now(), after=self.creator_cursor)
        self.creator_cursor = page["next"]
        self.creator_model.append_many([{"artwork": dict(row, previewUrl=
            f"image://community-preview/{self.image_generation}/{row['id']}")} for row in page["items"]])

    @Slot()
    def loadMoreCreator(self):
        if self.creator_value and self.creator_cursor is not None:
            self._append_creator_page()
            self.changed.emit()

    @Slot(str, result=bool)
    def inspectCreatorArtwork(self, ident):
        rows = [r for r in self.store.catalog(self.mode, self.now(), ident=ident)
                if r["id"] == ident and r["creator"] == self.creator_value and r["state"] == "available" and not r["ignored"]]
        if not rows: return False
        self.selected_id = ident
        self.selected_value = dict(rows[0], previewUrl=data_url(self.store.preview(ident, self.mode, self.now())))
        self._selection_media()
        self.changed.emit()
        return True

    @Slot()
    def followCreator(self):
        if self.creator_value and self.creator_value != self.username:
            self._run(lambda: self.store.toggle("follows", self.creator_value, self.mode))

    @Slot(str)
    def browseCreator(self, ident=""):
        self.creator_filter = self.creator_value
        self.scope_value = "Browse"
        self.query = ""
        self.kind_value = self.game_value = self.category_value = self.classification_value = "All"
        self.supporters_only = False
        if ident:
            self.selected_id = ident
        self.refresh()

    @Slot(int)
    def advanceClock(self, seconds):
        self.offset += seconds
        self.clockChanged.emit()
        self.refresh()
        if self.creator_value: self.viewCreator(self.creator_value)

    @Slot()
    def chooseFile(self):
        path, _ = QFileDialog.getOpenFileName(None, "Local Community upload", str(self.repo), "Artwork (*.json *.kfpslivery)")
        if path: self.inspectPath(path)

    @Slot(str)
    def inspectPath(self, path):
        if self.working: return
        self.working, self.pending, self.message = True, None, ""
        self.changed.emit()
        future = self._executor.submit(inspect_file, path, self.store.root)
        def done(f):
            try: result = f.result()
            except Exception as exc: result = exc
            if not self._closed: self.uploadFinished.emit(result)
        future.add_done_callback(done)

    @Slot(object)
    def _finish_upload(self, result):
        self.working = False
        if isinstance(result, Exception):
            self.error, self.message = True, str(result)
        else:
            self.pending = result
            self.pending["previewUrl"] = data_url(result["preview"])
            self.pending["photos"] = []
            self.pending["photoUrls"] = []
            self.error, self.message = False, "File checked. Ready for the local catalog."
        self.changed.emit()

    @Slot()
    def choosePhotos(self):
        paths, _ = QFileDialog.getOpenFileNames(None, "Livery photos (up to 3)", str(self.repo), "Photos (*.png *.jpg *.jpeg *.webp)")
        if paths: self.inspectPhotos(paths)

    @Slot("QStringList")
    def inspectPhotos(self, paths):
        if self.working or not self.pending or self.pending["kind"] != "livery": return
        from .community_preview_photos import read_photos
        self.working, self.error, self.message = True, False, ""
        self.changed.emit()
        future = self._executor.submit(read_photos, list(paths))
        def done(f):
            try: result = f.result()
            except Exception as exc: result = exc
            if not self._closed: self.photosFinished.emit(result)
        future.add_done_callback(done)

    @Slot(object)
    def _finish_photos(self, result):
        self.working = False
        if isinstance(result, Exception):
            self.error, self.message = True, str(result)
        elif self.pending:
            self.pending["photos"] = result
            self.pending["photoUrls"] = [data_url(raw) for raw in result]
            self.error, self.message = False, ""
        self.changed.emit()

    @Slot(int)
    def removePhoto(self, index):
        if self.working or not self.pending: return
        photos = self.pending.get("photos", [])
        if 0 <= index < len(photos):
            photos.pop(index)
            self.pending["photoUrls"] = [data_url(raw) for raw in photos]
            self.changed.emit()

    @Slot("QVariantMap")
    def publish(self, fields):
        def action():
            if not self.pending: raise PreviewError("Choose a file first.")
            if self.working: raise PreviewError("Wait for file checking to finish.")
            photos = self.pending.get("photos", [])
            if self.pending["kind"] == "livery" and not 1 <= len(photos) <= 3:
                raise PreviewError("Add one to three photos of your livery before publishing.")
            if not fields.get("rights"): raise PreviewError("Confirm that you have permission to share this artwork.")
            if self.pending.get("warning") and not fields.get("compatibility"):
                raise PreviewError("Acknowledge the compatibility warning.")
            tags = prepare_tags([], fields.get("tags", ""))
            if tags["error"]: raise PreviewError(tags["error"])
            starts = ends = None
            if fields.get("timed"):
                try:
                    start = datetime.fromisoformat(fields["starts"])
                    end = datetime.fromisoformat(fields["ends"])
                    if start.tzinfo is None or end.tzinfo is None: raise ValueError()
                    starts, ends = start.timestamp(), end.timestamp()
                except (KeyError, ValueError):
                    raise PreviewError("Use date/time with a timezone, for example 2026-09-19T13:00+02:00.")
            meta = {k: v for k, v in self.pending.items() if k not in ("payload", "preview", "previewUrl", "extension", "photos", "photoUrls")}
            meta.update(title=fields.get("title", "").strip(), description=fields.get("description", "").strip(),
                        category=fields.get("category", "Original Artwork"), classification=fields.get("classification", "handmade"),
                        supporter=bool(fields.get("supporter")), license=fields.get("license", "KFPS Community Share"),
                        tags=tags["tags"], featured=False, sample=False)
            cover = image_bytes(photos[0]) if photos else self.pending["preview"]
            self.selected_id = self.store.add(meta, self.pending["payload"], cover, self.mode,
                                               starts=starts, ends=ends, now=self.now(), photos=photos)
            self.scope_value = "My uploads"
            self.creator_filter = ""
            self.query = ""
            self.kind_value = self.game_value = self.category_value = self.classification_value = "All"
            self.supporters_only = False
            self.pending = None
            self.message = "Published to the local test catalog."
            self.published.emit()
        self._run(action)

    def close(self):
        self._closed = True
        self.closeRender()
        self.timer.stop()
        self._executor.shutdown(wait=True, cancel_futures=True)
        self.store.close()
