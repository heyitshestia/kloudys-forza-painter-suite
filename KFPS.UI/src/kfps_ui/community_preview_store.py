"""Local-only Community prototype. No network, credentials, or production imports."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path


ACCOUNTS = {
    "Visitor": ("", False, False),
    "Member": ("Alex", False, False),
    "Supporter": ("Jisoo", True, False),
    "Creator": ("Kloudy", True, False),
    "Moderator": ("Kloudy", True, True),
}


class PreviewError(ValueError):
    pass


class PreviewStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "catalog.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS artwork (
                id TEXT PRIMARY KEY, metadata TEXT NOT NULL, payload BLOB,
                preview BLOB, digest TEXT NOT NULL, created REAL NOT NULL,
                starts REAL, ends REAL, state TEXT NOT NULL DEFAULT 'published'
            );
            CREATE TABLE IF NOT EXISTS votes (
                artwork TEXT REFERENCES artwork(id), account TEXT, value INTEGER CHECK(value IN (-1,1)),
                PRIMARY KEY(artwork,account)
            );
            CREATE TABLE IF NOT EXISTS favorites (
                artwork TEXT REFERENCES artwork(id), account TEXT, PRIMARY KEY(artwork,account)
            );
            CREATE TABLE IF NOT EXISTS follows (account TEXT, creator TEXT, PRIMARY KEY(account,creator));
            CREATE TABLE IF NOT EXISTS ignored (account TEXT, creator TEXT, PRIMARY KEY(account,creator));
            CREATE TABLE IF NOT EXISTS profiles (account TEXT PRIMARY KEY, bio TEXT, website TEXT);
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, artwork TEXT REFERENCES artwork(id), account TEXT,
                reason TEXT NOT NULL, created REAL NOT NULL, resolved INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (created REAL, action TEXT, artwork TEXT, account TEXT);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS downloads (artwork TEXT, account TEXT, day INTEGER,
                PRIMARY KEY(artwork,account,day));
            CREATE TABLE IF NOT EXISTS photos (
                artwork TEXT REFERENCES artwork(id), position INTEGER, image BLOB NOT NULL,
                PRIMARY KEY(artwork,position)
            );
            CREATE INDEX IF NOT EXISTS creator_gallery_order
                ON artwork(json_extract(metadata,'$.creator'),state,created DESC,id DESC);
        """)

    def close(self):
        self.db.close()

    def setting(self, key, default=""):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def save_setting(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(value)))

    def _identity(self, mode, *, required=True, moderator=False):
        if mode not in ACCOUNTS:
            raise PreviewError("Invalid test account.")
        user, supporter, admin = ACCOUNTS[mode]
        if required and not user:
            raise PreviewError("Sign in to continue.")
        if moderator and not admin:
            raise PreviewError("Moderator access required.")
        return user, supporter, admin

    def _event(self, action, artwork, account, now):
        self.db.execute("INSERT INTO events VALUES (?,?,?,?)", (now, action, artwork, account))

    def expire(self, now=None):
        now = time.time() if now is None else now
        with self.db:
            rows = self.db.execute(
                "SELECT id FROM artwork WHERE ends IS NOT NULL AND ends<=? AND state!='expired'", (now,)
            ).fetchall()
            for row in rows:
                self.db.execute("UPDATE artwork SET state='expired',payload=NULL,preview=NULL WHERE id=?", (row[0],))
                self.db.execute("DELETE FROM photos WHERE artwork=?", (row[0],))
                self._event("expired-and-purged", row[0], "scheduler", now)
        return len(rows)

    def next_boundary(self, now):
        row = self.db.execute("""
            SELECT MIN(value) FROM (
                SELECT starts AS value FROM artwork WHERE state='published' AND starts>?
                UNION ALL SELECT ends FROM artwork WHERE state!='expired' AND ends>?
            )
        """, (now, now)).fetchone()
        return row[0] if row[0] is not None else float("inf")

    def _row(self, artwork, mode, now, *, downloadable=False):
        self.expire(now)
        row = self.db.execute("SELECT * FROM artwork WHERE id=?", (artwork,)).fetchone()
        if not row:
            raise PreviewError("Artwork not found.")
        user, supporter, admin = self._identity(mode, required=downloadable)
        meta = json.loads(row["metadata"])
        if row["state"] != "published" or (row["starts"] is not None and now < row["starts"]):
            raise PreviewError("This artwork is not available.")
        if meta.get("supporter") and not supporter:
            raise PreviewError("A verified supporter key is required.")
        if downloadable and row["payload"] is None:
            raise PreviewError("This sample is preview-only. Upload a real file to test downloading.")
        return row, meta, user

    def add(self, metadata, payload, preview, mode, *, starts=None, ends=None, now=None, seed=False, photos=()):
        now = time.time() if now is None else now
        user, supporter, _ = self._identity(mode)
        if not str(metadata.get("title", "")).strip() or len(metadata["title"]) > 100:
            raise PreviewError("Enter a title of 1 to 100 characters.")
        if len(metadata.get("description", "")) > 4000:
            raise PreviewError("Keep the description under 4000 characters.")
        if metadata.get("kind") not in ("vinyl", "livery"):
            raise PreviewError("Unsupported artwork type.")
        if len(photos) > 3 or (photos and metadata["kind"] != "livery"):
            raise PreviewError("Liveries support up to three photos.")
        if any(not isinstance(photo, bytes) or not photo or len(photo) > 24 * 1024 * 1024 for photo in photos):
            raise PreviewError("Invalid livery photo.")
        if metadata.get("supporter") and not supporter:
            raise PreviewError("A verified supporter key is required.")
        if (starts is None) != (ends is None) or (starts is not None and ends <= starts):
            raise PreviewError("Choose an end time after the start time.")
        if ends is not None and ends <= now and not seed:
            raise PreviewError("The release window has already ended.")
        digest = hashlib.sha256(payload or uuid.uuid4().bytes).hexdigest()
        if payload and not seed and self.db.execute(
            "SELECT 1 FROM artwork WHERE digest=? AND state='published'", (digest,)
        ).fetchone():
            raise PreviewError("This file is already in the test catalog.")
        ident = uuid.uuid4().hex
        metadata = {"description": "", "tags": [], "category": "Original Artwork", "game": "Unverified",
                    "classification": "handmade", "supporter": False, "featured": False, "sample": False,
                    "car": "", "shapes": 0, "license": "KFPS Community Share", "warning": "", **metadata,
                    "creator": metadata.get("creator", user) if seed else user}
        with self.db:
            self.db.execute("INSERT INTO artwork VALUES (?,?,?,?,?,?,?,?,?)", (
                ident, json.dumps(metadata, ensure_ascii=False), payload, preview, digest, now,
                starts, ends, "published",
            ))
            self.db.executemany("INSERT INTO photos VALUES (?,?,?)", ((ident, i, photo) for i, photo in enumerate(photos)))
            self._event("uploaded", ident, user, now)
        return ident

    def catalog(self, mode, now=None, *, ident=None):
        now = time.time() if now is None else now
        self.expire(now)
        user, supporter, admin = self._identity(mode, required=False)
        votes = {r[0]: r[1] for r in self.db.execute("SELECT artwork,value FROM votes WHERE account=?", (user,))}
        scores = {r[0]: r[1] for r in self.db.execute("SELECT artwork,SUM(value) FROM votes GROUP BY artwork")}
        favorites = {r[0] for r in self.db.execute("SELECT artwork FROM favorites WHERE account=?", (user,))}
        follows = {r[0] for r in self.db.execute("SELECT creator FROM follows WHERE account=?", (user,))}
        ignored = {r[0] for r in self.db.execute("SELECT creator FROM ignored WHERE account=?", (user,))}
        downloads = {r[0]: r[1] for r in self.db.execute("SELECT artwork,COUNT(*) FROM downloads GROUP BY artwork")}
        reports = {r[0]: r[1] for r in self.db.execute("SELECT artwork,COUNT(*) FROM reports WHERE resolved=0 GROUP BY artwork")}
        result = []
        query = "SELECT id,metadata,created,starts,ends,state,payload IS NOT NULL AS downloadable FROM artwork"
        for row in self.db.execute(query + (" WHERE id=?" if ident else ""), (ident,) if ident else ()):
            item = dict(json.loads(row["metadata"]), id=row["id"], created=row["created"], starts=row["starts"], ends=row["ends"])
            item["state"] = row["state"] if row["state"] != "published" else (
                "scheduled" if row["starts"] is not None and now < row["starts"] else "available")
            own = item["creator"] == user
            if item["state"] != "available" and not (own or admin):
                continue
            item.update(score=scores.get(row["id"], 0), vote=votes.get(row["id"], 0),
                        favorite=row["id"] in favorites, followed=item["creator"] in follows,
                        ignored=item["creator"] in ignored, downloads=downloads.get(row["id"], 0),
                        reports=reports.get(row["id"], 0) if admin else 0, own=own,
                        locked=bool(item.get("supporter") and not supporter),
                        downloadable=bool(row["downloadable"]), admin=admin)
            result.append(item)
        return result

    def preview(self, ident, mode, now=None):
        now = time.time() if now is None else now
        user, _, admin = self._identity(mode, required=False)
        row = self.db.execute("SELECT preview,metadata,state,starts,ends FROM artwork WHERE id=?", (ident,)).fetchone()
        if not row or row["state"] in ("removed", "expired") or (row["ends"] is not None and row["ends"] <= now):
            return b""
        if row["starts"] is not None and now < row["starts"] and not (admin or json.loads(row["metadata"])["creator"] == user):
            return b""
        return bytes(row["preview"] or b"")

    def ignored_creators(self, mode):
        user, _, _ = self._identity(mode, required=False)
        return [r[0] for r in self.db.execute("SELECT creator FROM ignored WHERE account=? ORDER BY creator", (user,))]

    def photos(self, ident, mode, now=None):
        if not self.preview(ident, mode, now):
            return []
        return [bytes(r[0]) for r in self.db.execute("SELECT image FROM photos WHERE artwork=? ORDER BY position", (ident,))]

    def render_payload(self, ident, mode, now=None):
        row, meta, _ = self._row(ident, mode, time.time() if now is None else now, downloadable=True)
        if meta["kind"] != "livery":
            raise PreviewError("Choose a full livery for 3D preview.")
        raw = bytes(row["payload"])
        if hashlib.sha256(raw).hexdigest() != row["digest"]:
            raise PreviewError("The stored file failed its integrity check.")
        return raw

    def vote(self, ident, value, mode, now=None):
        now = time.time() if now is None else now
        user, _, _ = self._identity(mode)
        self._row(ident, mode, now)
        if value not in (-1, 0, 1):
            raise PreviewError("Invalid vote.")
        with self.db:
            self.db.execute("DELETE FROM votes WHERE artwork=? AND account=?", (ident, user))
            if value:
                self.db.execute("INSERT INTO votes VALUES (?,?,?)", (ident, user, value))

    def toggle(self, table, value, mode):
        user, _, _ = self._identity(mode)
        if table not in ("favorites", "follows", "ignored"):
            raise PreviewError("Unsupported action.")
        column = "artwork" if table == "favorites" else "creator"
        with self.db:
            old = self.db.execute(f"SELECT 1 FROM {table} WHERE {column}=? AND account=?", (value, user)).fetchone()
            if old:
                self.db.execute(f"DELETE FROM {table} WHERE {column}=? AND account=?", (value, user))
            else:
                self.db.execute(f"INSERT INTO {table} ({column},account) VALUES (?,?)", (value, user))

    def download(self, ident, mode, now=None):
        now = time.time() if now is None else now
        row, meta, user = self._row(ident, mode, now, downloadable=True)
        raw = bytes(row["payload"])
        if hashlib.sha256(raw).hexdigest() != row["digest"]:
            raise PreviewError("The stored file failed its integrity check.")
        directory = self.root / "downloads" / ident
        directory.mkdir(parents=True, exist_ok=True)
        extension = ".kfpslivery" if meta["kind"] == "livery" else ".json"
        target = directory / ("artwork" + extension)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(raw)
        temporary.replace(target)
        if target.read_bytes() != raw:
            raise PreviewError("The downloaded copy failed verification.")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO downloads VALUES (?,?,?)", (ident, user, int(now // 86400)))
            self._event("downloaded", ident, user, now)
        return target

    def report(self, ident, reason, mode, now=None):
        now = time.time() if now is None else now
        _, _, user = self._row(ident, mode, now)
        self._identity(mode)
        if not reason.strip() or len(reason) > 2000:
            raise PreviewError("Add a report reason of 1 to 2000 characters.")
        with self.db:
            self.db.execute("INSERT INTO reports VALUES (?,?,?,?,?,0)", (uuid.uuid4().hex, ident, user, reason.strip(), now))

    def moderate(self, ident, action, mode, now=None):
        now = time.time() if now is None else now
        user, _, admin = self._identity(mode)
        row = self.db.execute("SELECT metadata,state FROM artwork WHERE id=?", (ident,)).fetchone()
        if not row:
            raise PreviewError("Artwork not found.")
        meta = json.loads(row[0])
        if not admin and not (action == "remove" and meta["creator"] == user):
            raise PreviewError("Moderator access required.")
        if action not in ("remove", "restore", "feature", "resolve"):
            raise PreviewError("Unsupported action.")
        if action == "restore" and row[1] == "expired":
            raise PreviewError("Expired files have been deleted and cannot be restored.")
        with self.db:
            if action in ("remove", "restore"):
                self.db.execute("UPDATE artwork SET state=? WHERE id=?", ("removed" if action == "remove" else "published", ident))
            elif action == "feature":
                meta["featured"] = not meta.get("featured", False)
                self.db.execute("UPDATE artwork SET metadata=? WHERE id=?", (json.dumps(meta), ident))
            else:
                self.db.execute("UPDATE reports SET resolved=1 WHERE artwork=?", (ident,))
            self._event(action, ident, user, now)

    def report_details(self, ident, mode):
        self._identity(mode, moderator=True)
        return [dict(r) for r in self.db.execute(
            "SELECT account,reason,resolved FROM reports WHERE artwork=? ORDER BY created DESC", (ident,)
        )]

    def profile(self, mode):
        user, _, _ = self._identity(mode, required=False)
        row = self.db.execute("SELECT bio,website FROM profiles WHERE account=?", (user,)).fetchone()
        return dict(row) if row else {"bio": "", "website": ""}

    def creator_profile(self, creator, mode, now=None):
        user, _, _ = self._identity(mode, required=False)
        row = self.db.execute("SELECT bio,website FROM profiles WHERE account=?", (creator,)).fetchone()
        works = self.creator_page(creator, mode, now=now)
        followed = self.db.execute("SELECT 1 FROM follows WHERE account=? AND creator=?", (user, creator)).fetchone()
        count = self.db.execute("SELECT COUNT(*) FROM follows WHERE creator=?", (creator,)).fetchone()[0]
        return {"creator": creator, "bio": row["bio"] if row else "", "website": row["website"] if row else "",
                "followers": count, "followed": bool(followed), "own": creator == user,
                "artworks": works["items"], "artworkCount": works["total"]}

    def creator_page(self, creator, mode, *, now=None, after=None, limit=48):
        now = time.time() if now is None else now
        user, supporter, _ = self._identity(mode, required=False)
        limit = max(1, min(int(limit), 48))
        if self.db.execute("SELECT 1 FROM ignored WHERE account=? AND creator=?", (user, creator)).fetchone():
            return {"items": [], "next": None, "total": 0}
        where = """json_extract(metadata,'$.creator')=? AND state='published'
            AND (starts IS NULL OR starts<=?) AND (ends IS NULL OR ends>?)"""
        args = [creator, now, now]
        total = self.db.execute("SELECT COUNT(*) FROM artwork WHERE " + where, args).fetchone()[0]
        if after:
            where += " AND (created<? OR (created=? AND id<?))"
            args.extend([after[0], after[0], after[1]])
        rows = self.db.execute("SELECT id,metadata,created FROM artwork WHERE " + where
                               + " ORDER BY created DESC,id DESC LIMIT ?", [*args, limit+1]).fetchall()
        items = []
        for row in rows[:limit]:
            meta = json.loads(row["metadata"])
            items.append({k: meta.get(k, "") for k in ("title", "kind", "game", "car", "shapes", "creator")}
                         | {"id": row["id"], "locked": bool(meta.get("supporter") and not supporter)})
        cursor = (rows[limit-1]["created"], rows[limit-1]["id"]) if len(rows) > limit else None
        return {"items": items, "next": cursor, "total": total}

    def save_profile(self, mode, bio, website):
        user, _, _ = self._identity(mode)
        if len(bio) > 1000 or len(website) > 300 or (website and not website.startswith("https://")):
            raise PreviewError("Use a short bio and an HTTPS website address.")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO profiles VALUES (?,?,?)", (user, bio, website))
