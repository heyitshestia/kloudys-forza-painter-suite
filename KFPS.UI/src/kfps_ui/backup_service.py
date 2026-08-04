from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from .app_paths import AppPaths
from .log_service import LogService
from .settings_service import SettingsService


BACKUP_FORMAT = "kfps-imgs-snapshot-v1"
BACKUP_FOLDER_NAME = "KFPS imgs Backups"


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except (OSError, ValueError):
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_snapshot_manifest(snapshot: Path) -> dict:
    try:
        payload = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(payload, dict) or payload.get("format") != BACKUP_FORMAT:
        return {}
    files = payload.get("files")
    return payload if isinstance(files, dict) else {}


def _latest_complete_snapshot(snapshots: Path) -> tuple[Path | None, dict]:
    try:
        candidates = sorted(
            (path for path in snapshots.iterdir() if path.is_dir() and not path.name.startswith(".")),
            key=lambda path: path.name,
            reverse=True,
        )
    except OSError:
        return None, {}
    for candidate in candidates:
        manifest = _load_snapshot_manifest(candidate)
        if manifest:
            return candidate, manifest
    return None, {}


def create_imgs_snapshot(
    imgs_root: Path,
    destination: Path,
    *,
    now: datetime | None = None,
    progress=None,
) -> dict:
    created_at = now or datetime.now()
    source = Path(imgs_root).resolve()
    destination = Path(destination).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"KFPS imgs folder was not found: {source}")
    if not destination.is_dir():
        raise FileNotFoundError(f"Backup destination was not found: {destination}")
    if _path_is_within(destination, source):
        raise ValueError("Choose a backup destination outside the KFPS imgs folder.")

    backup_root = destination / BACKUP_FOLDER_NAME
    snapshots = backup_root / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    previous, previous_manifest = _latest_complete_snapshot(snapshots)
    previous_files = previous_manifest.get("files", {}) if previous_manifest else {}

    timestamp = created_at.strftime("%Y%m%d-%H%M%S-%f")
    final = snapshots / timestamp
    suffix = 2
    while final.exists() or final.with_name(f".{final.name}.building").exists():
        final = snapshots / f"{timestamp}-{suffix}"
        suffix += 1
    building = final.with_name(f".{final.name}.building")
    snapshot_imgs = building / "imgs"
    snapshot_imgs.mkdir(parents=True)

    files = {}
    checked = 0
    copied = 0
    reused = 0
    skipped = 0
    try:
        for current_root, directory_names, file_names in os.walk(source, followlinks=False):
            directory_names[:] = sorted(
                name for name in directory_names
                if not (Path(current_root) / name).is_symlink()
            )
            file_names.sort()
            current = Path(current_root)
            relative_folder = current.relative_to(source)
            (snapshot_imgs / relative_folder).mkdir(parents=True, exist_ok=True)

            for name in file_names:
                source_file = current / name
                if source_file.is_symlink() or not source_file.is_file():
                    skipped += 1
                    continue
                relative = source_file.relative_to(source)
                relative_key = relative.as_posix()
                target = snapshot_imgs / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                source_hash = _sha256(source_file)
                source_stat = source_file.stat()
                previous_meta = previous_files.get(relative_key, {})
                previous_file = previous / "imgs" / relative if previous else None
                can_reuse = (
                    previous_file is not None
                    and previous_file.is_file()
                    and isinstance(previous_meta, dict)
                    and previous_meta.get("sha256") == source_hash
                    and _sha256(previous_file) == source_hash
                )
                if can_reuse:
                    try:
                        os.link(previous_file, target)
                        reused += 1
                    except OSError:
                        shutil.copy2(source_file, target)
                        copied += 1
                else:
                    shutil.copy2(source_file, target)
                    copied += 1
                files[relative_key] = {
                    "sha256": source_hash,
                    "size": int(source_stat.st_size),
                    "mtimeNs": int(source_stat.st_mtime_ns),
                }
                checked += 1
                if callable(progress) and (checked == 1 or checked % 50 == 0):
                    progress(checked)

        manifest = {
            "format": BACKUP_FORMAT,
            "created": created_at.isoformat(timespec="seconds"),
            "source": str(source),
            "snapshot": final.name,
            "previousSnapshot": previous.name if previous else "",
            "fileCount": checked,
            "copiedFiles": copied,
            "reusedFiles": reused,
            "skippedLinks": skipped,
            "files": files,
        }
        (building / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        for attempt in range(6):
            try:
                building.rename(final)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    except Exception:
        shutil.rmtree(building, ignore_errors=True)
        raise

    return {
        "snapshot": str(final),
        "fileCount": checked,
        "copiedFiles": copied,
        "reusedFiles": reused,
        "skippedLinks": skipped,
    }


class BackupService(QObject):
    changed = Signal()
    _completed = Signal(object)
    _progressed = Signal(int)

    def __init__(
        self,
        paths: AppPaths,
        settings: SettingsService,
        log: LogService,
        parent=None,
    ):
        super().__init__(parent)
        self.paths = paths
        self.settings = settings
        self.log = log
        self._running = False
        self._status = "Choose a folder to create the first imgs backup."
        self._last_snapshot = ""
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="imgs-backup")
        self._completed.connect(self._apply_result)
        self._progressed.connect(self._apply_progress)

    @Property(bool, notify=changed)
    def running(self):
        return self._running

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def destination(self):
        return self.settings.backupFolder

    @Property(str, notify=changed)
    def lastSnapshot(self):
        return self._last_snapshot

    def _choose_destination(self) -> Path | None:
        remembered = Path(self.settings.backupFolder) if self.settings.backupFolder else None
        if remembered and remembered.is_dir():
            return remembered
        initial = remembered.parent if remembered and remembered.parent.is_dir() else self.paths.app_root.parent
        selected = QFileDialog.getExistingDirectory(
            None,
            "Choose where KFPS should keep imgs backups",
            str(initial),
            QFileDialog.Option.ShowDirsOnly,
        )
        if not selected:
            self._status = "Backup cancelled. No destination was changed."
            self.changed.emit()
            return None
        destination = Path(selected).resolve()
        if _path_is_within(destination, self.paths.app_root / "imgs"):
            self._status = "Choose a backup destination outside the KFPS imgs folder."
            self.changed.emit()
            return None
        self.settings.backupFolder = str(destination)
        return destination

    @Slot()
    def backupImgs(self):
        if self._running:
            return
        destination = self._choose_destination()
        if destination is None:
            return
        self._running = True
        self._status = "Backing up imgs..."
        self.changed.emit()
        future = self._executor.submit(
            create_imgs_snapshot,
            self.paths.app_root / "imgs",
            destination,
            progress=self._progressed.emit,
        )

        def finished(task):
            try:
                self._completed.emit({"ok": True, "result": task.result()})
            except Exception as exc:
                self._completed.emit({"ok": False, "error": str(exc)})

        future.add_done_callback(finished)

    @Slot(int)
    def _apply_progress(self, checked):
        if not self._running:
            return
        self._status = f"Backing up imgs... {int(checked)} files checked"
        self.changed.emit()

    @Slot(object)
    def _apply_result(self, payload):
        self._running = False
        if not payload.get("ok"):
            self._status = f"Backup failed: {payload.get('error') or 'unknown error'}"
            self.log.append(self._status, "error")
            self.changed.emit()
            return
        result = payload["result"]
        self._last_snapshot = str(result.get("snapshot") or "")
        count = int(result.get("fileCount") or 0)
        copied = int(result.get("copiedFiles") or 0)
        reused = int(result.get("reusedFiles") or 0)
        self._status = f"Backup complete: {count} files ({copied} copied, {reused} reused)."
        self.log.append(f"{self._status} Snapshot: {self._last_snapshot}")
        self.changed.emit()
