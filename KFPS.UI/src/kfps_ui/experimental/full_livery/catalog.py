from __future__ import annotations

import json
import os
import sqlite3
import shutil
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = 1


class FullLiveryCatalog:
    """Rebuildable durable index; never an authority for writes or ownership."""

    def __init__(self, path: str | Path, quarantine_root: str | Path | None = None):
        self.path = Path(path)
        self.quarantine_root = Path(quarantine_root) if quarantine_root else self.path.parent / "quarantine"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.quarantine_root.mkdir(parents=True, exist_ok=True)
        self._initialize_with_recovery()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except Exception:
            connection.close()
            raise

    def _initialize_with_recovery(self) -> None:
        try:
            with closing(self._connect()) as connection:
                result = connection.execute("PRAGMA quick_check").fetchone()
                if result and str(result[0]).casefold() != "ok":
                    raise sqlite3.DatabaseError(str(result[0]))
                self._migrate(connection)
                connection.commit()
        except sqlite3.DatabaseError:
            self._quarantine_corrupt_database()
            with closing(self._connect()) as connection:
                self._migrate(connection)
                connection.commit()

    def _quarantine_corrupt_database(self) -> None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        for suffix in ("", "-wal", "-shm"):
            source = Path(str(self.path) + suffix)
            if source.exists():
                target = self.quarantine_root / f"{self.path.name}.{stamp}{suffix}.corrupt"
                os.replace(source, target)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sources (
                path TEXT PRIMARY KEY,
                root TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                parser_revision INTEGER NOT NULL,
                seen_token TEXT NOT NULL,
                row_json TEXT NOT NULL,
                indexed_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS sources_root_seen ON sources(root, seen_token);
            CREATE TABLE IF NOT EXISTS packages (
                path TEXT PRIMARY KEY,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                compiler_revision INTEGER NOT NULL,
                seen_token TEXT NOT NULL,
                row_json TEXT NOT NULL,
                indexed_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS packages_seen ON packages(seen_token);
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                revision INTEGER NOT NULL,
                size INTEGER NOT NULL,
                last_access REAL NOT NULL,
                valid INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS cache_lru ON cache_entries(kind, last_access);
            """
        )
        current = connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if current and int(current[0]) > SCHEMA_VERSION:
            raise sqlite3.DatabaseError("The full-livery catalog was created by a newer KFPS build.")
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _canonical(path: str | Path) -> str:
        return str(Path(path).resolve())

    def cached_source(self, path: str | Path, *, size: int, mtime_ns: int, parser_revision: int) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT row_json FROM sources WHERE path = ? AND size = ? AND mtime_ns = ? AND parser_revision = ?",
                (self._canonical(path), int(size), int(mtime_ns), int(parser_revision)),
            ).fetchone()
        if not row:
            return None
        try:
            value = json.loads(row[0])
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def source_snapshot(self, roots: Iterable[str | Path]) -> dict[str, dict[str, Any]]:
        normalized = [self._canonical(root) for root in roots]
        if not normalized:
            return {}
        placeholders = ",".join("?" for _ in normalized)
        with closing(self._connect()) as connection:
            records = connection.execute(
                f"SELECT path, root, size, mtime_ns, content_hash, parser_revision, row_json "
                f"FROM sources WHERE root IN ({placeholders})",
                tuple(normalized),
            ).fetchall()
        snapshot: dict[str, dict[str, Any]] = {}
        for record in records:
            try:
                row = json.loads(record[6])
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            snapshot[str(record[0])] = {
                "root": str(record[1]),
                "size": int(record[2]),
                "mtime_ns": int(record[3]),
                "content_hash": str(record[4]),
                "parser_revision": int(record[5]),
                "row": row,
            }
        return snapshot

    def apply_source_scan(
        self,
        roots: Iterable[str | Path],
        seen_token: str,
        records: Iterable[dict[str, Any]],
    ) -> int:
        normalized_roots = [self._canonical(root) for root in roots]
        values = []
        indexed_at = time.time()
        for record in records:
            values.append((
                self._canonical(record["path"]),
                self._canonical(record["root"]),
                int(record["size"]),
                int(record["mtime_ns"]),
                str(record["content_hash"]),
                int(record["parser_revision"]),
                str(seen_token),
                json.dumps(record["row"], separators=(",", ":"), sort_keys=True),
                indexed_at,
            ))
        with self.transaction() as connection:
            if values:
                connection.executemany(
                    """
                    INSERT INTO sources(path, root, size, mtime_ns, content_hash, parser_revision, seen_token, row_json, indexed_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        root=excluded.root, size=excluded.size, mtime_ns=excluded.mtime_ns,
                        content_hash=excluded.content_hash, parser_revision=excluded.parser_revision,
                        seen_token=excluded.seen_token, row_json=excluded.row_json, indexed_at=excluded.indexed_at
                    """,
                    values,
                )
            if not normalized_roots:
                return 0
            placeholders = ",".join("?" for _ in normalized_roots)
            cursor = connection.execute(
                f"DELETE FROM sources WHERE root IN ({placeholders}) AND seen_token != ?",
                (*normalized_roots, str(seen_token)),
            )
            return int(cursor.rowcount)

    def upsert_source(
        self,
        path: str | Path,
        *,
        root: str | Path,
        size: int,
        mtime_ns: int,
        content_hash: str,
        parser_revision: int,
        seen_token: str,
        row: dict[str, Any],
    ) -> None:
        payload = json.dumps(row, separators=(",", ":"), sort_keys=True)
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO sources(path, root, size, mtime_ns, content_hash, parser_revision, seen_token, row_json, indexed_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    root=excluded.root, size=excluded.size, mtime_ns=excluded.mtime_ns,
                    content_hash=excluded.content_hash, parser_revision=excluded.parser_revision,
                    seen_token=excluded.seen_token, row_json=excluded.row_json, indexed_at=excluded.indexed_at
                """,
                (
                    self._canonical(path), self._canonical(root), int(size), int(mtime_ns),
                    str(content_hash), int(parser_revision), str(seen_token), payload, time.time(),
                ),
            )

    def mark_source_seen(self, path: str | Path, seen_token: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE sources SET seen_token = ? WHERE path = ?",
                (str(seen_token), self._canonical(path)),
            )

    def finish_source_scan(self, roots: Iterable[str | Path], seen_token: str) -> int:
        roots = [self._canonical(root) for root in roots]
        if not roots:
            return 0
        placeholders = ",".join("?" for _ in roots)
        with self.transaction() as connection:
            cursor = connection.execute(
                f"DELETE FROM sources WHERE root IN ({placeholders}) AND seen_token != ?",
                (*roots, str(seen_token)),
            )
            return int(cursor.rowcount)

    def source_rows(self, roots: Iterable[str | Path] | None = None) -> list[dict[str, Any]]:
        query = "SELECT row_json FROM sources"
        params: tuple[Any, ...] = ()
        if roots:
            normalized = [self._canonical(root) for root in roots]
            query += " WHERE root IN (" + ",".join("?" for _ in normalized) + ")"
            params = tuple(normalized)
        with closing(self._connect()) as connection:
            records = connection.execute(query, params).fetchall()
        rows = []
        for record in records:
            try:
                value = json.loads(record[0])
            except ValueError:
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows

    def cached_package(self, path: str | Path, *, size: int, mtime_ns: int, compiler_revision: int) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            record = connection.execute(
                "SELECT row_json FROM packages WHERE path = ? AND size = ? AND mtime_ns = ? AND compiler_revision = ?",
                (self._canonical(path), int(size), int(mtime_ns), int(compiler_revision)),
            ).fetchone()
        if not record:
            return None
        try:
            value = json.loads(record[0])
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def package_snapshot(self) -> dict[str, dict[str, Any]]:
        with closing(self._connect()) as connection:
            records = connection.execute(
                "SELECT path, size, mtime_ns, compiler_revision, row_json FROM packages"
            ).fetchall()
        snapshot: dict[str, dict[str, Any]] = {}
        for record in records:
            try:
                row = json.loads(record[4])
            except ValueError:
                continue
            if not isinstance(row, dict):
                continue
            snapshot[str(record[0])] = {
                "size": int(record[1]),
                "mtime_ns": int(record[2]),
                "compiler_revision": int(record[3]),
                "row": row,
            }
        return snapshot

    def apply_package_scan(
        self,
        seen_token: str,
        records: Iterable[dict[str, Any]],
    ) -> int:
        values = []
        indexed_at = time.time()
        for record in records:
            values.append((
                self._canonical(record["path"]),
                int(record["size"]),
                int(record["mtime_ns"]),
                int(record["compiler_revision"]),
                str(seen_token),
                json.dumps(record["row"], separators=(",", ":"), sort_keys=True),
                indexed_at,
            ))
        with self.transaction() as connection:
            if values:
                connection.executemany(
                    """
                    INSERT INTO packages(path, size, mtime_ns, compiler_revision, seen_token, row_json, indexed_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        size=excluded.size, mtime_ns=excluded.mtime_ns,
                        compiler_revision=excluded.compiler_revision, seen_token=excluded.seen_token,
                        row_json=excluded.row_json, indexed_at=excluded.indexed_at
                    """,
                    values,
                )
            cursor = connection.execute(
                "DELETE FROM packages WHERE seen_token != ?", (str(seen_token),)
            )
            return int(cursor.rowcount)

    def upsert_package(
        self,
        path: str | Path,
        *,
        size: int,
        mtime_ns: int,
        compiler_revision: int,
        seen_token: str,
        row: dict[str, Any],
    ) -> None:
        payload = json.dumps(row, separators=(",", ":"), sort_keys=True)
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO packages(path, size, mtime_ns, compiler_revision, seen_token, row_json, indexed_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size=excluded.size, mtime_ns=excluded.mtime_ns,
                    compiler_revision=excluded.compiler_revision, seen_token=excluded.seen_token,
                    row_json=excluded.row_json, indexed_at=excluded.indexed_at
                """,
                (
                    self._canonical(path), int(size), int(mtime_ns), int(compiler_revision),
                    str(seen_token), payload, time.time(),
                ),
            )

    def mark_package_seen(self, path: str | Path, seen_token: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE packages SET seen_token = ? WHERE path = ?",
                (str(seen_token), self._canonical(path)),
            )

    def finish_package_scan(self, seen_token: str) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM packages WHERE seen_token != ?", (str(seen_token),)
            )
            return int(cursor.rowcount)

    def package_rows(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            records = connection.execute("SELECT row_json FROM packages").fetchall()
        rows = []
        for record in records:
            try:
                value = json.loads(record[0])
            except ValueError:
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows

    def record_cache_entry(
        self,
        cache_key: str,
        *,
        kind: str,
        path: str | Path,
        source_fingerprint: str,
        revision: int,
    ) -> None:
        candidate = Path(path)
        size = (candidate.stat().st_size if candidate.is_file() else
                sum(item.stat().st_size for item in candidate.rglob("*") if item.is_file()))
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO cache_entries(cache_key, kind, path, source_fingerprint, revision, size, last_access, valid)
                VALUES(?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(cache_key) DO UPDATE SET
                    kind=excluded.kind, path=excluded.path,
                    source_fingerprint=excluded.source_fingerprint,
                    revision=excluded.revision, size=excluded.size,
                    last_access=excluded.last_access, valid=1
                """,
                (
                    str(cache_key), str(kind), self._canonical(path), str(source_fingerprint),
                    int(revision), int(size), time.time(),
                ),
            )

    def prune_derived_cache(self, root: Path, *, protected: Iterable[Path], max_bytes: int = 2 * 1024**3) -> dict:
        root = root.resolve()
        protected_paths = {path.resolve() for path in protected}
        with closing(self._connect()) as connection:
            access = {row[0]: float(row[1]) for row in connection.execute("SELECT path,last_access FROM cache_entries")}
        entries = []
        for name in ("meshes", "atlases", "previews"):
            parent = root / name
            if not parent.is_dir() or parent.is_symlink() or os.path.isjunction(parent):
                continue
            for item in parent.iterdir():
                if item.is_symlink() or os.path.isjunction(item) or item.name.endswith(".validated.json"):
                    continue
                path = item.resolve()
                if path.parent != parent or path in protected_paths:
                    # Protected entries still count towards the disk budget.
                    pinned = True
                else:
                    pinned = False
                files = list(path.rglob("*")) if path.is_dir() else [path, path.with_suffix(path.suffix + ".validated.json")]
                if any(file.is_symlink() or os.path.isjunction(file) for file in files):
                    continue
                size = sum(file.stat().st_size for file in files if file.is_file())
                touched = access.get(self._canonical(path), path.stat().st_mtime)
                entries.append((touched, path, size, pinned))
        total = sum(entry[2] for entry in entries)
        removed = 0
        for touched, path, size, pinned in sorted(entries):
            if total <= max_bytes:
                break
            if pinned or time.time() - touched < 60:
                continue
            try:
                # Only immediate children of these three disposable cache roots
                # are eligible; packages, state, saves and links are excluded.
                path.relative_to(root)
                if path.parent.name not in {"meshes", "atlases", "previews"} or path.parent.parent != root:
                    continue
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
                    path.with_suffix(path.suffix + ".validated.json").unlink(missing_ok=True)
                with self.transaction() as connection:
                    connection.execute("DELETE FROM cache_entries WHERE path=?", (self._canonical(path),))
                total -= size
                removed += size
            except OSError:
                continue
        return {"bytes": total, "removed_bytes": removed, "budget_bytes": max_bytes}

    def invalidate_cache(self) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM cache_entries")

    def stats(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            sources = int(connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0])
            packages = int(connection.execute("SELECT COUNT(*) FROM packages").fetchone()[0])
            cache_entries = int(connection.execute("SELECT COUNT(*) FROM cache_entries").fetchone()[0])
        return {"sources": sources, "packages": packages, "cache_entries": cache_entries}
