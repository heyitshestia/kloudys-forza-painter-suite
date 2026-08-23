from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import psutil
import secrets
import shutil
import struct
import string
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from .app_paths import AppPaths
from .json_service import JsonService
from .log_service import LogService
from .lifecycle import discard_queued_events
from .models import DictListModel
from .preview_service import PreviewService
from .qt_utils import safe_file_part


class CGroupLibraryService(QObject):
    changed = Signal()
    fm8CreatorPromptRequested = Signal()
    _resultReady = Signal(object)

    def __init__(
        self,
        paths: AppPaths,
        preview: PreviewService,
        jsons: JsonService,
        log: LogService,
        supporter=None,
        demo: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.paths = paths
        self.preview = preview
        self.jsons = jsons
        self.log = log
        self.supporter = supporter
        self.demo = demo
        self._closed = False
        self._cancel_event = threading.Event()
        self._future = None
        self._running = False
        self._status = "Ready"
        self._summary = "Scan Forza saves into the offline Library, or create a save-folder vinyl from the selected JSON."
        self._candidate_count = 0
        self._exported_count = 0
        self._skipped_count = 0
        self._last_output = ""
        self._active_game_key = "fh6"
        self._creator_prompt_summary = ""
        self._creator_prompt_model = DictListModel(["creator", "displayName", "detailText", "score", "recommended"])
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="cgroup-library")
        self._resultReady.connect(self._apply_result)

    @Property(bool, notify=changed)
    def running(self):
        return self._running

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Property(str, notify=changed)
    def summary(self):
        return self._summary

    @Property(int, notify=changed)
    def candidateCount(self):
        return self._candidate_count

    @Property(int, notify=changed)
    def exportedCount(self):
        return self._exported_count

    @Property(int, notify=changed)
    def skippedCount(self):
        return self._skipped_count

    @Property(str, notify=changed)
    def libraryFolder(self):
        return str(self._library_root(self._active_game_key))

    @Property(str, notify=changed)
    def lastOutput(self):
        return self._last_output

    @Property(str, notify=changed)
    def activeGame(self):
        return self._active_game_key

    @Property(QObject, constant=True)
    def creatorCandidateModel(self):
        return self._creator_prompt_model

    @Property(str, notify=changed)
    def creatorPromptSummary(self):
        return self._creator_prompt_summary

    @Slot()
    @Slot(str)
    def scanSaves(self, game: str = "fh6"):
        if self._closed or self._running:
            self.log.append("C_group library scan is already running.")
            return
        if self.supporter is not None and not bool(getattr(self.supporter, "unlocked", False)):
            self._status = "Supporter unlock required"
            self._summary = "Offline save-library scan and offline folder imports are available with a local supporter unlock."
            self.changed.emit()
            self.log.append("Forza save-library scan requires a local supporter unlock.")
            return
        game_key = self._game_key(game)
        self._active_game_key = game_key
        self._running = True
        game_label = self._game_label(game_key)
        self._status = f"Scanning {game_label}"
        self._summary = f"Scanning common {game_label} save folders for individual vinyl group files..."
        self.changed.emit()
        self.log.append(f"Scanning {game_label} save folders for individual vinyl group files...")
        if game_key == "fh5":
            self.log.append(
                "FH5 save-library scan: the first scan can take quite some time when you have many vinyls, "
                "because KFPS imports each group and renders thumbnails/previews. Later scans reuse cached previews."
            )
        elif game_key == "fh4":
            self.log.append(
                "FH4 offline scan reads user-created vinyl groups from the Microsoft Store/Xbox WGS save container. "
                "It does not edit the save or require FH4 to be running."
            )
        elif game_key == "fm8":
            self.log.append(
                "FM8 offline scan uses the separate local-save LayerGroups/data path. "
                "It reads saved files only; it does not touch the live editor or FH offline export flow."
            )

        self._cancel_event.clear()
        future = self._executor.submit(self._scan_work, game_key)
        self._future = future
        future.add_done_callback(self._emit_future_result)

    @Slot(str, result=bool)
    def confirmFm8Creator(self, creator: str) -> bool:
        creator = str(creator or "").strip()
        if not creator:
            self._status = "Profile not saved"
            self._summary = "Choose a valid FM8 creator profile before scanning the offline library."
            self.changed.emit()
            return False
        self._save_creator_profile(creator)
        self._creator_prompt_model.replace([])
        self._creator_prompt_summary = ""
        self._status = "FM8 profile saved"
        self._summary = "FM8 profile confirmed privately. Scanning your vinyl groups..."
        self.changed.emit()
        self.scanSaves("fm8")
        return True

    @Slot()
    def cancelFm8CreatorPrompt(self):
        self._creator_prompt_model.replace([])
        self._creator_prompt_summary = ""
        self._status = "FM8 profile needed"
        self._summary = "FM8 offline library scan waits until you choose the local creator profile once."
        self.changed.emit()

    @Slot(str)
    def installSelectedJsonToFH6(self, json_path: str):
        if self._running:
            self.log.append("C_group folder install is already running.")
            return
        if self.supporter is not None and not bool(getattr(self.supporter, "unlocked", False)):
            self._status = "Supporter unlock required"
            self._summary = "FH6 offline folder import is available with a local supporter unlock."
            self.changed.emit()
            self.log.append("FH6 save-folder import requires a local supporter unlock.")
            return
        source = Path(str(json_path or ""))
        if not source.is_file():
            self.log.append("Choose a JSON before installing into an FH6 save folder.", "error")
            return

        start = self._suggest_layer_group_dialog_root()
        folder = QFileDialog.getExistingDirectory(
            None,
            "Choose the existing FH6 LayerGroup folder to replace",
            str(start if start and start.exists() else self.paths.app_root),
        )
        if not folder:
            return
        self.installJsonToFH6LayerGroup(str(source), folder)

    @Slot(str)
    def createFH6LayerGroupFromSelectedJson(self, json_path: str):
        self.createLayerGroupFromSelectedJson(json_path, "FH6")

    @Slot(str, str)
    def createLayerGroupFromSelectedJson(self, json_path: str, game: str = "fh6"):
        if self._closed or self._running:
            self.log.append("C_group folder install is already running.")
            return
        if self.supporter is not None and not bool(getattr(self.supporter, "unlocked", False)):
            self._status = "Supporter unlock required"
            self._summary = "Offline folder import is available with a local supporter unlock."
            self.changed.emit()
            self.log.append("Save-folder import requires a local supporter unlock.")
            return
        source = Path(str(json_path or ""))
        if not source.is_file():
            self.log.append("Choose a JSON before creating a save-folder vinyl.", "error")
            return
        game_key = self._game_key(game)
        game_label = self._game_label(game_key)
        if game_key == "fh5":
            self._status = "FH5 offline import disabled"
            self._summary = "FH5 offline folder import is not wired yet. Use online import/export for FH5 testing."
            self.changed.emit()
            self.log.append("FH5 offline folder import is not wired yet.", "error")
            return
        self._running = True
        self._active_game_key = game_key
        self._status = "Offline import"
        if game_key == "fm8":
            self._summary = "Creating a separate FM8 LayerGroups/data folder from the selected JSON."
            self.log.append(
                "FM8 offline import writes a new local-save LayerGroups/data folder. "
                "Existing FM8 saves and the FH offline C_group writer are left untouched."
            )
        elif game_key == "fh4":
            self._summary = "Creating a new FH4 vinyl group in the local Xbox WGS save container."
            self.log.append(
                "FH4 offline import creates a separate WGS LayerGroup entry after backing up the complete local save slot. "
                "FH4 must be fully closed before the save is changed."
            )
        else:
            self._summary = f"Creating a new {game_label} vinyl group folder from the selected JSON."
        self.changed.emit()
        self.log.append(f"Offline import: creating a new {game_label} vinyl group in supported local save data...")
        self._cancel_event.clear()
        future = self._executor.submit(self._create_folder_install_work, Path(source), game_key)
        self._future = future
        future.add_done_callback(self._emit_future_result)

    @Slot(str, str)
    def installJsonToFH6LayerGroup(self, json_path: str, target_folder: str):
        if self._closed or self._running:
            self.log.append("C_group folder install is already running.")
            return
        if self.supporter is not None and not bool(getattr(self.supporter, "unlocked", False)):
            self._status = "Supporter unlock required"
            self._summary = "FH6 offline folder import is available with a local supporter unlock."
            self.changed.emit()
            self.log.append("FH6 save-folder import requires a local supporter unlock.")
            return
        self._running = True
        self._active_game_key = "fh6"
        self._status = "Installing FH6 folder"
        self._summary = "Backing up the selected FH6 LayerGroup folder, then writing a flat C_group."
        self.changed.emit()
        self.log.append("Installing selected JSON into an FH6 LayerGroup folder...")
        self._cancel_event.clear()
        future = self._executor.submit(self._install_work, Path(json_path), Path(target_folder))
        self._future = future
        future.add_done_callback(self._emit_future_result)

    def _emit_future_result(self, future):
        if not self._closed:
            self._resultReady.emit(self._future_result(future))

    def _future_result(self, future):
        try:
            return future.result()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @Slot(object)
    def _apply_result(self, result):
        if self._closed:
            return
        self._running = False
        ok = bool(result.get("ok"))
        self._candidate_count = int(result.get("candidates") or 0)
        self._exported_count = int(result.get("exported") or 0)
        self._skipped_count = int(result.get("skipped") or 0)
        outputs = [str(item) for item in result.get("outputs") or []]
        self._last_output = outputs[0] if outputs else ""

        if ok:
            self._status = "Complete"
            self._summary = result.get("message") or (
                f"Scanned {self._candidate_count} candidate(s), exported {self._exported_count}, "
                f"skipped {self._skipped_count}."
            )
            self.log.append(self._summary)
            if outputs:
                self.jsons.setSource(3)
                self.jsons.refresh()
                self.jsons.selectPath(outputs[0])
                self.jsons.refreshRecent()
        else:
            self._status = "Failed"
            self._summary = result.get("error") or "C_group library scan failed."
            self.log.append(self._summary, "error")
        self.changed.emit()

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._cancel_event.set()
        if self._future is not None:
            self._future.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)
        discard_queued_events(self)

    @staticmethod
    def _game_key(game: str | None) -> str:
        text = str(game or "fh6").strip().lower()
        if text in {"fm", "fm8", "forza motorsport", "forza motorsport 8", "motorsport"}:
            return "fm8"
        if text in {"fh4", "forza horizon 4"}:
            return "fh4"
        if text in {"fh5", "forza horizon 5"}:
            return "fh5"
        return "fh6"

    @staticmethod
    def _game_label(game_key: str) -> str:
        return {"fm8": "FM8", "fh4": "FH4", "fh5": "FH5", "fh6": "FH6"}.get(
            game_key, str(game_key).upper()
        )

    def _library_root(self, game_key: str | None = None) -> Path:
        return self.paths.library_root

    def _root_cache_file(self, game_key: str | None = None) -> Path:
        return self.paths.runtime_root / f"cgroup-library-roots-{self._game_key(game_key)}.json"

    @property
    def _creator_profile_file(self) -> Path:
        return self.paths.runtime_root / "fm8-local-profile.json"

    @classmethod
    def _normalize_creator_name(cls, value: str) -> str:
        return " ".join(str(value or "").replace("\x00", " ").split()).casefold()

    @classmethod
    def _creator_hash(cls, creator: str, salt: str) -> str:
        normalized = cls._normalize_creator_name(creator)
        payload = f"kfps-fm8-local-profile-v1:{salt}:{normalized}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _system_creator_names() -> set[str]:
        return {
            "",
            "forza",
            "forza baselivery",
            "turn 10",
            "turn10",
            "mclaren",
        }

    def _load_creator_profile(self) -> dict[str, str] | None:
        try:
            data = json.loads(self._creator_profile_file.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict) or data.get("format") != "kfps_fm8_local_profile_v1":
            return None
        salt = str(data.get("salt") or "")
        digest = str(data.get("creator_hash") or "")
        if len(salt) < 16 or len(digest) != 64:
            return None
        return {"salt": salt, "creator_hash": digest}

    def _save_creator_profile(self, creator: str) -> None:
        salt = secrets.token_hex(16)
        payload = {
            "format": "kfps_fm8_local_profile_v1",
            "created_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "salt": salt,
            "creator_hash": self._creator_hash(creator, salt),
        }
        self._creator_profile_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self._creator_profile_file.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temp, self._creator_profile_file)

    def _creator_matches_profile(self, creator: str, profile: dict[str, str] | None = None) -> bool:
        profile = profile or self._load_creator_profile()
        if not profile:
            return False
        salt = str(profile.get("salt") or "")
        digest = str(profile.get("creator_hash") or "")
        return bool(creator) and self._creator_hash(creator, salt) == digest

    def _fm8_profile_matches_verified_group(self, profile: dict[str, str] | None) -> bool:
        from tools.cgroup.fm8_ownership import assess_fm8_layer_group_files

        if not profile:
            return False
        for source_path in self._discover_save_artifacts(self._default_save_roots("fm8"), "fm8"):
            if not assess_fm8_layer_group_files(source_path).allowed:
                continue
            metadata = self._read_layer_group_metadata(source_path)
            if self._creator_matches_profile(str(metadata.get("creator") or ""), profile):
                return True
        return False

    def _prepare_fm8_creator_prompt(self) -> bool:
        rows = self._fm8_creator_candidate_rows()
        self._creator_prompt_model.replace(rows)
        if rows:
            self._status = "Choose FM8 profile"
            self._summary = "Confirm your local FM8 creator profile once before scanning the offline library."
            self._creator_prompt_summary = (
                "KFPS found multiple creators in the FM8 local cache. Pick your own profile so downloaded/community "
                "vinyls stay hidden from the offline library."
            )
        else:
            self._status = "FM8 profile not found"
            self._summary = "No FM8 creator profiles were found in local save files. Save one vinyl group in FM8, then scan again."
            self._creator_prompt_summary = self._summary
        self.changed.emit()
        self.fm8CreatorPromptRequested.emit()
        return True

    def _fm8_creator_candidate_rows(self) -> list[dict[str, Any]]:
        from tools.cgroup.fm8_ownership import assess_fm8_layer_group_files
        from tools.cgroup.forza_source_decoder import DecodeError, decode_forza_source

        roots = self._default_save_roots("fm8")
        system_names = self._system_creator_names()
        candidates: dict[str, dict[str, Any]] = {}

        def add_creator(creator: str, title: str, kind: str, mtime: float) -> None:
            creator = " ".join(str(creator or "").replace("\x00", " ").split())
            key = self._normalize_creator_name(creator)
            if not key or key in system_names:
                return
            item = candidates.setdefault(
                key,
                {
                    "creator": creator,
                    "layergroups": 0,
                    "liveries": 0,
                    "titles": [],
                    "newest": 0.0,
                },
            )
            if kind == "livery":
                item["liveries"] += 1
            else:
                item["layergroups"] += 1
            if title and len(item["titles"]) < 5:
                item["titles"].append(str(title))
            item["newest"] = max(float(item.get("newest") or 0.0), float(mtime or 0.0))

        for source_path in self._discover_save_artifacts(roots, "fm8"):
            if not assess_fm8_layer_group_files(source_path).allowed:
                continue
            metadata = self._read_layer_group_metadata(source_path)
            try:
                mtime = source_path.stat().st_mtime
            except OSError:
                mtime = 0.0
            add_creator(str(metadata.get("creator") or ""), str(metadata.get("title") or ""), "layergroup", mtime)

        seen_liveries: set[str] = set()
        for root in roots:
            for livery_path in self._targeted_fm8_liveries(root):
                try:
                    resolved = str(livery_path.resolve()).lower()
                except OSError:
                    continue
                if resolved in seen_liveries:
                    continue
                seen_liveries.add(resolved)
                try:
                    decode_forza_source(livery_path, allow_locked=False, game="fm8")
                except DecodeError:
                    continue
                metadata = self._read_layer_group_metadata(livery_path)
                try:
                    mtime = livery_path.stat().st_mtime
                except OSError:
                    mtime = 0.0
                add_creator(str(metadata.get("creator") or ""), str(metadata.get("title") or ""), "livery", mtime)

        now = time.time()
        rows: list[dict[str, Any]] = []
        for item in candidates.values():
            layergroups = int(item.get("layergroups") or 0)
            liveries = int(item.get("liveries") or 0)
            newest = float(item.get("newest") or 0.0)
            score = layergroups + liveries
            if layergroups and liveries:
                score += 8
            if newest and now - newest < 14 * 86400:
                score += 3
            elif newest and now - newest < 60 * 86400:
                score += 1
            detail = f"{layergroups} vinyl group(s), {liveries} design(s)"
            titles = [str(title) for title in item.get("titles") or [] if title]
            if titles:
                detail += " - " + ", ".join(titles[:3])
            rows.append(
                {
                    "creator": str(item.get("creator") or ""),
                    "displayName": str(item.get("creator") or ""),
                    "detailText": detail,
                    "score": score,
                    "recommended": False,
                }
            )
        rows.sort(key=lambda row: (int(row.get("score") or 0), str(row.get("displayName") or "")), reverse=True)
        if rows:
            rows[0]["recommended"] = True
            rows[0]["displayName"] = f"{rows[0]['displayName']}  ·  best guess"
        return rows[:18]

    def _scan_work(self, game_key: str = "fh6") -> dict[str, Any]:
        from tools.cgroup.fm8_ownership import assess_fm8_layer_group_files
        from tools.cgroup.find_forza_sources import describe_source
        from tools.cgroup.forza_source_decoder import DecodeError, decode_forza_source

        if self._cancel_event.is_set():
            raise concurrent.futures.CancelledError()
        game_key = self._game_key(game_key)
        game_label = self._game_label(game_key)
        roots = self._default_save_roots(game_key)
        if self.demo:
            return {
                "ok": True,
                "game": game_key,
                "roots": [str(root) for root in roots],
                "candidates": 0,
                "exported": 0,
                "skipped": 0,
                "outputs": [],
            }
        if not roots:
            return {
                "ok": True,
                "game": game_key,
                "roots": [],
                "candidates": 0,
                "exported": 0,
                "skipped": 0,
                "outputs": [],
                "message": f"No common {game_label} save folders were found on this machine.",
            }

        source_paths = self._discover_save_artifacts(roots, game_key)
        ignored_designs = self._count_ignored_designs(roots, game_key)
        if source_paths:
            self._save_cached_roots(self._roots_for_sources(source_paths), game_key)
        candidates = []
        for path in source_paths:
            if self._cancel_event.is_set():
                raise concurrent.futures.CancelledError()
            candidates.append(
                describe_source(path, expected_layers=None, inspect=True, inspect_locked=False, game=game_key)
            )
        candidates.sort(key=lambda item: (item.get("_sort_mtime") or 0.0, item.get("file") or ""), reverse=True)

        library_root = self._library_root(game_key)
        library_root.mkdir(parents=True, exist_ok=True)
        self._flatten_legacy_game_library_roots(library_root)
        exported: list[str] = []
        active_entry_names: set[str] = set()
        active_source_keys: set[str] = set()
        skipped = 0
        ignored_restricted_fm8 = 0
        fm8_grouped_sources = 0
        fm8_group_transforms = 0
        fm8_pre_group_records = 0

        for source in candidates:
            if self._cancel_event.is_set():
                raise concurrent.futures.CancelledError()
            source_path = Path(str(source.get("file") or ""))
            if not source_path.is_file():
                skipped += 1
                continue
            fm8_ownership = None
            if game_key == "fm8":
                fm8_ownership = assess_fm8_layer_group_files(source_path)
                if not fm8_ownership.allowed:
                    skipped += 1
                    ignored_restricted_fm8 += 1
                    continue
            decode = source.get("decode") or {}
            if not decode.get("ok"):
                skipped += 1
                continue
            fingerprint = str(source.get("fingerprint") or self._file_fingerprint(source_path))

            try:
                decoded = decode_forza_source(source_path, allow_locked=False, game=game_key)
            except DecodeError:
                skipped += 1
                continue

            layers = len(decoded.layers)
            if game_key == "fh5" and decoded.source_kind != "cgroup":
                skipped += 1
                continue
            if game_key == "fm8" and layers <= 0:
                skipped += 1
                continue
            if game_key == "fm8":
                report = decoded.report
                grouped = int(report.get("group_nodes") or 0)
                if grouped:
                    fm8_grouped_sources += 1
                fm8_group_transforms += int(report.get("non_identity_group_transforms") or 0)
                fm8_pre_group_records += int(report.get("fm8_pre_group_transform_records") or 0)
            metadata = self._read_layer_group_metadata(source_path)
            title = metadata.get("title") or source.get("folder_name") or source_path.parent.name or "Forza LayerGroup"
            metadata["layers"] = layers
            metadata["layer_count"] = layers
            metadata["shape_count"] = layers
            metadata["asset_type"] = "vinyl_group"
            metadata["target_game"] = game_key
            metadata["source_folder"] = source.get("folder_name") or source_path.parent.name
            if fm8_ownership is not None:
                metadata["ownership_verified"] = True
            display_stem = safe_file_part(str(title), "forza-layergroup")
            try:
                source_key_text = str(source_path.resolve())
            except OSError:
                source_key_text = str(source_path)
            active_source_keys.add(self._source_path_key(source_path))
            source_key = hashlib.sha1(source_key_text.encode("utf-8", errors="ignore")).hexdigest()[:8]
            entry_name = safe_file_part(f"{display_stem}-{layers}layers-{source_key}-{fingerprint}", "forza-layergroup")
            active_entry_names.add(entry_name)
            entry_root = library_root / entry_name
            output_json = entry_root / f"{entry_name}.json"
            report_path = entry_root / f"{entry_name}.report.json"
            manifest_path = entry_root / f"{entry_name}.manifest.json"

            payload = {
                "format": "kfps_forza_save_library_json_v1",
                "source_path": str(source_path),
                "source_kind": decoded.source_kind,
                "target_game": game_key,
                "metadata": metadata,
                "shapes": decoded.layers,
            }
            report_payload = decoded.report
            manifest_payload = {
                "format": "kfps_cgroup_library_manifest_v1",
                "created_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                "source_path": str(source_path),
                "source_kind": decoded.source_kind,
                "asset_type": "vinyl_group",
                "target_game": game_key,
                "source_modified_utc": source.get("modified_utc"),
                "source_fingerprint": fingerprint,
                "layers": layers,
                "layer_count": layers,
                "shape_count": layers,
                "title": metadata.get("title"),
                "description": metadata.get("description"),
                "creator": metadata.get("creator"),
                "display_name": metadata.get("display_name") or title,
                "source_folder": metadata.get("source_folder"),
                "warnings": decoded.report.get("warnings", [])
                + decoded.report.get("identity_warnings", []),
            }
            entry_root.mkdir(parents=True, exist_ok=True)
            self._write_text_if_changed(output_json, json.dumps(payload, indent=2))
            self._write_text_if_changed(report_path, json.dumps(report_payload, indent=2))
            self._write_text_if_changed(manifest_path, json.dumps(manifest_payload, indent=2))
            self._write_preview(output_json)
            exported.append(str(output_json.resolve()))

        self._prune_non_layergroup_library_entries(
            library_root,
            active_entry_names,
            active_source_keys,
            game_key,
        )

        fm8_message = ""
        if game_key == "fm8":
            fm8_message = (
                f"; FM8 local-save decoder recovered {fm8_group_transforms} placed group transform(s) "
                f"from {fm8_grouped_sources} grouped save(s), using {fm8_pre_group_records} pre-group transform record(s)"
            )

        return {
            "ok": True,
            "game": game_key,
            "roots": [str(root) for root in roots],
            "candidates": len(candidates),
            "exported": len(exported),
            "skipped": skipped,
            "ignored_designs": ignored_designs,
            "ignored_restricted_fm8": ignored_restricted_fm8,
            "fm8_grouped_sources": fm8_grouped_sources,
            "fm8_group_transforms": fm8_group_transforms,
            "fm8_pre_group_records": fm8_pre_group_records,
            "outputs": exported,
            "message": (
                f"{game_label} save scan complete: scanned {len(candidates)} candidate(s), "
                f"exported {len(exported)}, skipped {skipped}"
                + (f", protected {ignored_restricted_fm8} non-owned FM8 vinyl(s)" if ignored_restricted_fm8 else "")
                + (f", ignored {ignored_designs} design(s)" if ignored_designs else "")
                + fm8_message
                + "."
            ),
        }

    def _install_work(self, json_path: Path, target_folder: Path) -> dict[str, Any]:
        from tools.cgroup.cgroup_codec import build_flat_cgroup_from_json, read_flat_cgroup, write_cgroup_file
        from tools.cgroup.forza_source_decoder import DecodeError, decode_forza_source

        if self._cancel_event.is_set():
            raise concurrent.futures.CancelledError()
        json_path = json_path.resolve()
        target_folder = target_folder.resolve()
        self._validate_fh6_layer_group_target(target_folder)
        if not json_path.is_file():
            raise ValueError(f"JSON does not exist: {json_path}")

        existing_cgroup = target_folder / "C_group"
        try:
            decode_forza_source(existing_cgroup, allow_locked=False, game="fh6")
        except DecodeError as exc:
            raise ValueError(
                "Target folder does not decode as a normal editable FH6 LayerGroup. "
                "Use a disposable user-created group, not a locked/community design."
            ) from exc

        payload = build_flat_cgroup_from_json(json_path)
        backup_folder = self._backup_layer_group_folder(target_folder)
        temp_cgroup = target_folder / "C_group.kfps.tmp"
        try:
            written = write_cgroup_file(temp_cgroup, payload)
            parsed = read_flat_cgroup(written)
            os.replace(temp_cgroup, existing_cgroup)

            title = self._title_for_install_json(json_path)
            self._write_or_rename_header(target_folder / "header", title)
            thumb_written = self._write_save_thumb(json_path, target_folder / "thumb.webp")
        finally:
            try:
                if temp_cgroup.exists():
                    temp_cgroup.unlink()
            except OSError:
                pass

        layers = int(parsed.get("count") or 0)
        thumb_note = "thumbnail refreshed" if thumb_written else "thumbnail left unchanged"
        return {
            "ok": True,
            "game": "fh6",
            "candidates": 1,
            "exported": 1,
            "skipped": 0,
            "outputs": [],
            "message": (
                f"FH6 folder install complete: wrote {layers} layer(s) into {target_folder.name}; "
                f"backup saved to {backup_folder}; {thumb_note}. Reload FH6's vinyl library/editor to see it."
            ),
        }

    def _create_folder_install_work(self, json_path: Path, game_key: str = "fh6") -> dict[str, Any]:
        from tools.cgroup.cgroup_codec import build_flat_cgroup_from_json, read_flat_cgroup, write_cgroup_file

        if self._cancel_event.is_set():
            raise concurrent.futures.CancelledError()
        game_key = self._game_key(game_key)
        if game_key == "fm8":
            return self._create_fm8_layer_group_install_work(json_path)
        if game_key == "fh4":
            return self._create_fh4_layer_group_install_work(json_path)
        if game_key != "fh6":
            raise ValueError(f"{self._game_label(game_key)} offline folder import is not wired yet.")

        json_path = json_path.resolve()
        if not json_path.is_file():
            raise ValueError(f"JSON does not exist: {json_path}")

        source_group = self._latest_fh6_layer_group()
        if source_group is None:
            raise ValueError("No existing FH6 LayerGroup folder was found. Save one vinyl group in FH6 first.")
        containers = source_group.parent
        if containers.name != "ContainersRoot":
            raise ValueError(f"Latest LayerGroup is not inside ContainersRoot: {source_group}")

        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        base_name = f"LayerGroup_0000_{stamp}"
        target_folder = containers / base_name
        suffix = 2
        while target_folder.exists():
            target_folder = containers / f"{base_name}_{suffix}"
            suffix += 1

        temp_folder = containers / f".{target_folder.name}.kfps-tmp"
        if temp_folder.exists():
            shutil.rmtree(temp_folder)
        temp_folder.mkdir(parents=True)
        try:
            payload = build_flat_cgroup_from_json(json_path)
            cgroup_path = write_cgroup_file(temp_folder / "C_group", payload)
            parsed = read_flat_cgroup(cgroup_path)
            title = self._title_for_install_json(json_path)
            source_header = source_group / "header"
            if source_header.is_file():
                self._atomic_write_bytes(temp_folder / "header", self._rename_header(source_header.read_bytes(), title))
            else:
                self._atomic_write_bytes(temp_folder / "header", self._build_draft_header(title))
            thumb_written = self._write_save_thumb(json_path, temp_folder / "thumb.webp")
            if not thumb_written:
                source_thumb = source_group / "thumb.webp"
                if source_thumb.is_file():
                    shutil.copy2(source_thumb, temp_folder / "thumb.webp")
            os.replace(temp_folder, target_folder)
        finally:
            if temp_folder.exists():
                shutil.rmtree(temp_folder, ignore_errors=True)

        layers = int(parsed.get("count") or 0)
        return {
            "ok": True,
            "game": "fh6",
            "candidates": 1,
            "exported": 1,
            "skipped": 0,
            "outputs": [],
            "message": (
                f"Offline import complete: created FH6 LayerGroup folder {target_folder.name} with {layers} layer(s) "
                "and a transparent thumbnail. "
                "Reload FH6's vinyl library/editor, or restart FH6 if it does not appear."
            ),
        }

    def _create_fm8_layer_group_install_work(self, json_path: Path) -> dict[str, Any]:
        from tools.cgroup.cgroup_codec import build_flat_cgroup_from_json, parse_flat_payload
        from tools.cgroup.fm8_ownership import assess_fm8_layer_group_files
        from tools.cgroup.forza_source_decoder import DecodeError, decode_forza_source

        json_path = json_path.resolve()
        if not json_path.is_file():
            raise ValueError(f"JSON does not exist: {json_path}")

        layer_groups_root = self._fm8_layer_groups_root()
        if layer_groups_root is None:
            raise ValueError("No FM8 LayerGroups folder was found. Save one vinyl group in Forza Motorsport first.")
        layer_groups_root.mkdir(parents=True, exist_ok=True)
        source_group = self._latest_fm8_layer_group()

        folder_name = str(uuid.uuid4())
        target_folder = layer_groups_root / folder_name
        while target_folder.exists():
            folder_name = str(uuid.uuid4())
            target_folder = layer_groups_root / folder_name

        temp_folder = layer_groups_root / f".{target_folder.name}.kfps-tmp"
        if temp_folder.exists():
            shutil.rmtree(temp_folder)
        temp_folder.mkdir(parents=True)
        target_installed = False
        try:
            payload = build_flat_cgroup_from_json(json_path, target_game="fm8")
            self._atomic_write_bytes(temp_folder / "data", payload)
            parsed = parse_flat_payload(payload)

            title = self._title_for_install_json(json_path)
            source_header = source_group / "header" if source_group else None
            if source_header and source_header.is_file():
                self._atomic_write_bytes(temp_folder / "header", self._rename_header(source_header.read_bytes(), title))
            else:
                self._atomic_write_bytes(temp_folder / "header", self._build_draft_header(title))

            thumb_written = self._write_save_thumb(json_path, temp_folder / "thumbnail")
            if not thumb_written and source_group:
                source_thumb = source_group / "thumbnail"
                if source_thumb.is_file():
                    shutil.copy2(source_thumb, temp_folder / "thumbnail")

            os.replace(temp_folder, target_folder)
            target_installed = True
            ownership = assess_fm8_layer_group_files(target_folder / "data")
            if not ownership.allowed:
                raise ValueError("The newly created FM8 vinyl group failed its ownership safety check.")
            try:
                verified = decode_forza_source(target_folder / "data", allow_locked=False, game="fm8")
            except DecodeError as exc:
                raise ValueError("The newly created FM8 vinyl group could not be reopened safely.") from exc
            expected_layers = int(parsed.get("count") or 0)
            if len(verified.layers) != expected_layers:
                raise ValueError(
                    f"The newly created FM8 vinyl group reopened with {len(verified.layers)} layer(s), "
                    f"expected {expected_layers}."
                )
        except Exception:
            if target_installed and target_folder.exists():
                shutil.rmtree(target_folder, ignore_errors=True)
            raise
        finally:
            if temp_folder.exists():
                shutil.rmtree(temp_folder, ignore_errors=True)

        layers = int(parsed.get("count") or 0)
        return {
            "ok": True,
            "game": "fm8",
            "candidates": 1,
            "exported": 1,
            "skipped": 0,
            "outputs": [],
            "message": (
                f"FM8 offline import complete: created separate LayerGroups folder {target_folder.name} "
                f"with {layers} layer(s). Existing FM8 save folders were not modified. "
                "Reload Forza Motorsport's vinyl group library/editor, or restart the game if it does not appear."
            ),
        }

    def _create_fh4_layer_group_install_work(self, json_path: Path) -> dict[str, Any]:
        from tools.cgroup.cgroup_codec import build_flat_cgroup_from_json, parse_flat_payload, wrap_payload
        from tools.cgroup.forza_source_decoder import DecodeError, cgroup_to_layers, decode_forza_source
        from tools.cgroup.xbox_wgs import (
            WgsFormatError,
            create_wgs_layer_group,
            find_wgs_slots,
            read_wgs_layer_groups,
        )

        json_path = json_path.resolve()
        if not json_path.is_file():
            raise ValueError(f"JSON does not exist: {json_path}")
        if self._game_process_running("ForzaHorizon4.exe"):
            raise ValueError(
                "Close FH4 completely before offline import. KFPS will not write Xbox WGS save files while the game is running."
            )

        roots = self._default_save_roots("fh4")
        slots = find_wgs_slots(roots)
        if not slots:
            raise ValueError(
                "No FH4 Microsoft Store/Xbox WGS save was found. Start FH4 once, save one user-created vinyl group, "
                "close the game, and try again."
            )

        template = None
        template_error = ""
        for slot in slots:
            try:
                groups = read_wgs_layer_groups(slot)
            except (OSError, WgsFormatError) as exc:
                template_error = str(exc)
                continue
            for group in groups:
                cgroup_path = group.cgroup_path
                if not cgroup_path:
                    continue
                try:
                    decode_forza_source(cgroup_path, allow_locked=False, game="fh4")
                except DecodeError as exc:
                    template_error = str(exc)
                    continue
                template = group
                break
            if template is not None:
                break
        if template is None:
            detail = f" Last parser error: {template_error}" if template_error else ""
            raise ValueError(
                "No normal user-created FH4 vinyl group was found to provide the WGS container structure. "
                "Save one simple vinyl group in FH4, close the game, and scan again." + detail
            )

        payload = build_flat_cgroup_from_json(json_path, target_game="fh4")
        parsed = parse_flat_payload(payload)
        decoded_layers, decoded_report = cgroup_to_layers(payload, game="fh4")
        expected_layers = int(parsed.get("count") or 0)
        if len(decoded_layers) != expected_layers:
            raise ValueError(
                f"FH4 offline import preflight decoded {len(decoded_layers)} layer(s), expected {expected_layers}. "
                "No save files were changed."
            )
        if decoded_report.get("warnings"):
            raise ValueError(
                "FH4 offline import preflight reported an unsafe C_group warning. No save files were changed: "
                + "; ".join(str(item) for item in decoded_report.get("warnings") or [])
            )

        title = self._title_for_install_json(json_path)
        source_header = template.header_path
        if source_header and source_header.is_file():
            header_data = self._rename_header(source_header.read_bytes(), title)
        else:
            header_data = self._build_draft_header(title)
        thumbnail_data = self._render_save_thumb_bytes(json_path, "PNG")
        if not thumbnail_data:
            source_thumbnail = template.thumbnail_path
            if source_thumbnail and source_thumbnail.is_file():
                thumbnail_data = source_thumbnail.read_bytes()
        if not thumbnail_data or not thumbnail_data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("KFPS could not build a valid FH4 PNG thumbnail. No save files were changed.")

        result = create_wgs_layer_group(
            template.slot_path,
            template,
            cgroup_data=wrap_payload(payload),
            header_data=header_data,
            thumbnail_data=thumbnail_data,
            backup_root=self.paths.runtime_root / "fh4-offline-import-backups",
        )
        verified = decode_forza_source(result.cgroup_path, allow_locked=False, game="fh4")
        if len(verified.layers) != expected_layers:
            raise ValueError(
                f"FH4 WGS import reopened with {len(verified.layers)} layer(s), expected {expected_layers}. "
                f"Restore the safety backup at {result.backup_path}."
            )
        self._save_cached_roots([template.slot_path.parent], "fh4")
        return {
            "ok": True,
            "game": "fh4",
            "candidates": 1,
            "exported": 1,
            "skipped": 0,
            "outputs": [],
            "message": (
                f"FH4 offline import complete: created {result.container_name} with {expected_layers} layer(s). "
                f"The complete pre-import WGS slot is backed up at {result.backup_path}. "
                "Start FH4 and open My Vinyl Groups to verify it."
            ),
        }

    @staticmethod
    def _game_process_running(process_name: str) -> bool:
        wanted = str(process_name).casefold()
        for process in psutil.process_iter(["name"]):
            try:
                if str(process.info.get("name") or "").casefold() == wanted:
                    return True
            except (psutil.Error, OSError, KeyError, TypeError):
                continue
        return False

    @staticmethod
    def _validate_fh6_layer_group_target(target_folder: Path) -> None:
        if not target_folder.is_dir():
            raise ValueError("Choose an existing FH6 LayerGroup folder, not a file.")
        if not target_folder.name.startswith("LayerGroup_"):
            raise ValueError("Target folder must be an existing LayerGroup_* folder.")
        if target_folder.parent.name.lower() != "containersroot":
            raise ValueError("Target LayerGroup must be inside a ContainersRoot save folder.")
        if not (target_folder / "C_group").is_file():
            raise ValueError("Target LayerGroup folder does not contain C_group.")

    def _backup_layer_group_folder(self, target_folder: Path) -> Path:
        root = self.paths.runtime_root / "cgroup-folder-import-backups"
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = safe_file_part(f"{target_folder.name}-{stamp}", "LayerGroup-backup")
        backup = root / base
        suffix = 2
        while backup.exists():
            backup = root / f"{base}-{suffix}"
            suffix += 1
        shutil.copytree(target_folder, backup)
        return backup

    def _suggest_layer_group_dialog_root(self) -> Path:
        for root in self._default_save_roots("fh6"):
            if not root.exists():
                continue
            latest = self._latest_layer_group_parent(root)
            if latest:
                return latest
            return root
        return self.paths.app_root

    @classmethod
    def _latest_layer_group_parent(cls, root: Path) -> Path | None:
        latest: tuple[float, Path] | None = None
        for cgroup in cls._discover_save_artifacts([root])[:40]:
            folder = cgroup.parent
            try:
                mtime = cgroup.stat().st_mtime
            except OSError:
                continue
            if latest is None or mtime > latest[0]:
                latest = (mtime, folder.parent if folder.parent.name == "ContainersRoot" else folder)
        return latest[1] if latest else None

    def _latest_fh6_layer_group(self) -> Path | None:
        latest: tuple[float, Path] | None = None
        for root in self._default_save_roots("fh6"):
            for cgroup in self._discover_save_artifacts([root], "fh6")[:120]:
                folder = cgroup.parent
                if folder.name.startswith("LayerGroup_") and folder.parent.name == "ContainersRoot":
                    try:
                        mtime = cgroup.stat().st_mtime
                    except OSError:
                        continue
                    if latest is None or mtime > latest[0]:
                        latest = (mtime, folder)
        return latest[1] if latest else None

    def _latest_fm8_layer_group(self) -> Path | None:
        from tools.cgroup.fm8_ownership import assess_fm8_layer_group_files

        latest: tuple[float, Path] | None = None
        root = self._fm8_layer_groups_root()
        if root is None:
            return None
        for data_file in self._targeted_fm8_layer_groups(root):
            folder = data_file.parent
            if not assess_fm8_layer_group_files(data_file).allowed:
                continue
            try:
                mtime = data_file.stat().st_mtime
            except OSError:
                continue
            if latest is None or mtime > latest[0]:
                latest = (mtime, folder)
        return latest[1] if latest else None

    def _fm8_layer_groups_root(self) -> Path | None:
        for root in self._default_save_roots("fm8"):
            name = root.name.lower()
            if name == "layergroups" and root.is_dir():
                return root
            candidate = root / "LayerGroups"
            if candidate.is_dir():
                return candidate
        return None

    @classmethod
    def _title_for_install_json(cls, json_path: Path) -> str:
        title = ""
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                metadata = data.get("metadata")
                if isinstance(metadata, dict):
                    title = str(metadata.get("display_name") or metadata.get("title") or "").strip()
                title = title or str(data.get("name") or "").strip()
        except Exception:
            title = ""
        if not title:
            title = json_path.stem
        title = " ".join(title.replace("\x00", " ").split())
        return title[:64] or "KFPS Import"

    @classmethod
    def _write_or_rename_header(cls, header_path: Path, title: str) -> None:
        if header_path.is_file():
            try:
                original = header_path.read_bytes()
                data = cls._rename_header(original, title)
            except OSError:
                data = b""
            if data:
                cls._atomic_write_bytes(header_path, data)
                return
        cls._atomic_write_bytes(header_path, cls._build_draft_header(title))

    @staticmethod
    def _rename_header(header: bytes, title: str) -> bytes:
        if len(header) < 8:
            return header
        old_length = struct.unpack_from("<I", header, 4)[0]
        old_end = 8 + int(old_length) * 2
        if old_end > len(header):
            return header
        encoded = title.encode("utf-16le")
        output = bytearray(header[:4])
        output.extend(struct.pack("<I", len(title)))
        output.extend(encoded)
        output.extend(header[old_end:])
        if len(output) < len(header):
            output.extend(b"\x00" * (len(header) - len(output)))
        return bytes(output)

    @staticmethod
    def _build_draft_header(title: str) -> bytes:
        now = datetime.now()
        output = bytearray()
        output.extend(struct.pack("<I", 7))
        output.extend(struct.pack("<I", len(title)))
        output.extend(title.encode("utf-16le"))
        output.extend(struct.pack("<I", 0))
        output.extend(struct.pack("<HBB", now.year, now.month, 0))
        field_block = bytearray(16)
        field_block[12] = 2
        output.extend(field_block)
        output.extend(b"\x00" * 8)
        creator = "KFPS"
        output.extend(struct.pack("<I", len(creator)))
        output.extend(creator.encode("utf-16le"))
        output.extend(b"\x00" * 28)
        output.extend(b"\x01\x02")
        output.extend(b"\x00" * 7)
        output.extend(struct.pack("<I", 0))
        output.extend(uuid.uuid4().bytes)
        output.extend(struct.pack("<II", 0, 0))
        output.extend(b"\x00" * 16)
        return bytes(output)

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        temp = path.with_name(f"{path.name}.kfps.tmp")
        temp.write_bytes(data)
        os.replace(temp, path)

    def _write_save_thumb(self, json_path: Path, thumb_path: Path) -> bool:
        try:
            data = self._render_save_thumb_bytes(json_path, "WEBP")
            if not data:
                return False
            temp = thumb_path.with_name(f"{thumb_path.name}.kfps.tmp")
            thumb_path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_bytes(data)
            os.replace(temp, thumb_path)
            return True
        except Exception:
            try:
                temp = thumb_path.with_name(f"{thumb_path.name}.kfps.tmp")
                if temp.exists():
                    temp.unlink()
            except OSError:
                pass
            return False

    def _render_save_thumb_bytes(self, json_path: Path, image_format: str) -> bytes | None:
        from io import BytesIO

        image = self._save_thumb_source_image(json_path)
        if image is None:
            return None
        image = self._fit_save_thumb(image)
        output = BytesIO()
        format_key = str(image_format or "WEBP").strip().upper()
        if format_key == "PNG":
            image.save(output, "PNG", optimize=True)
        else:
            image.save(output, "WEBP", quality=92, method=6)
        return output.getvalue()

    def _save_thumb_source_image(self, json_path: Path):
        from io import BytesIO

        from PIL import Image
        from json_preview_renderer import render_json_preview

        # Generated thumbnails should use the same geometry renderer as the app
        # preview, but without the checker/background layer the app preview uses.
        max_size = 900 if self._json_looks_generated(json_path) else 512
        preview_data = render_json_preview(json_path, max_size=max_size, transparent_background=True)
        if not preview_data:
            return None
        with Image.open(BytesIO(preview_data)) as image:
            return image.convert("RGBA").copy()

    @staticmethod
    def _fit_save_thumb(image):
        from PIL import Image

        output_size = 256
        resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        image = image.convert("RGBA")
        image.thumbnail((output_size, output_size), resample)
        canvas = Image.new("RGBA", (output_size, output_size), (0, 0, 0, 0))
        x = (output_size - image.width) // 2
        y = (output_size - image.height) // 2
        canvas.alpha_composite(image, (x, y))
        return canvas

    def _json_looks_generated(self, json_path: Path) -> bool:
        try:
            resolved = json_path.resolve()
            generated_root = self.paths.generated_root.resolve()
            if resolved == generated_root or generated_root in resolved.parents:
                return True
        except Exception:
            pass

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            shapes = data.get("shapes") if isinstance(data, dict) else None
        except Exception:
            return False
        if not isinstance(shapes, list):
            return False

        generated_types = {1, 2, 8, 16}
        identity_keys = {
            "type_word",
            "typeWord",
            "shape_word",
            "shapeWord",
            "resource_family",
            "resourceFamily",
            "resource_index",
            "resourceIndex",
        }
        for shape in shapes[:80]:
            if not isinstance(shape, dict):
                continue
            if any(key in shape for key in identity_keys):
                continue
            try:
                shape_type = int(shape.get("type"))
            except Exception:
                continue
            if shape_type in generated_types:
                return True
        return False

    @classmethod
    def _discover_save_artifacts(cls, roots: list[Path], game_key: str = "fh6") -> list[Path]:
        game_key = cls._game_key(game_key)
        found: list[Path] = []
        seen: set[str] = set()

        def add(path: Path) -> None:
            if not path.is_file():
                return
            key = str(path.resolve()).lower()
            if key in seen:
                return
            seen.add(key)
            found.append(path)

        for root in roots:
            if game_key == "fm8":
                targeted = cls._targeted_fm8_layer_groups(root)
            elif game_key == "fh4":
                targeted = cls._targeted_fh4_wgs_layer_groups(root)
            else:
                targeted = cls._targeted_xbox_layer_groups(root)
            for path in targeted:
                add(path)

        for root in roots:
            if game_key != "fm8" and cls._is_xbox_game_save_root(root):
                continue
            complete_fh5_root = game_key == "fh5" and cls._is_fh5_save_root(root)
            for path in cls._bounded_source_walk(
                root,
                max_files=None if complete_fh5_root else 60_000,
                max_seconds=None if complete_fh5_root else 18.0,
                game_key=game_key,
            ):
                add(path)

        found.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0.0, reverse=True)
        return found

    @staticmethod
    def _is_xbox_game_save_root(root: Path) -> bool:
        text = str(root).replace("\\", "/").lower()
        return "/xboxgames/gamesave" in text or text.endswith("/xboxgames/gamesave") or text.endswith("/xboxgames/gamesave/pgs")

    @staticmethod
    def _targeted_xbox_layer_groups(root: Path) -> list[Path]:
        text = str(root).replace("\\", "/").lower().rstrip("/")
        if text.endswith("/xboxgames/gamesave"):
            pgs_roots = [root / "pgs"]
        elif text.endswith("/xboxgames/gamesave/pgs"):
            pgs_roots = [root]
        else:
            return []

        paths: list[Path] = []
        for pgs in pgs_roots:
            if not pgs.exists():
                continue
            try:
                users = [item for item in pgs.iterdir() if item.is_dir()]
            except OSError:
                continue
            for user_folder in users:
                try:
                    save_slots = [item for item in user_folder.iterdir() if item.is_dir()]
                except OSError:
                    continue
                for slot in save_slots:
                    containers = slot / "ContainersRoot"
                    if not containers.is_dir():
                        continue
                    try:
                        groups = [item for item in containers.iterdir() if item.is_dir() and item.name.startswith("LayerGroup_")]
                    except OSError:
                        continue
                    for group in groups:
                        paths.append(group / "C_group")
        return paths

    @staticmethod
    def _targeted_fh4_wgs_layer_groups(root: Path) -> list[Path]:
        from tools.cgroup.xbox_wgs import find_wgs_slots, read_wgs_layer_groups

        paths: list[Path] = []
        for slot in find_wgs_slots([root]):
            try:
                groups = read_wgs_layer_groups(slot)
            except (OSError, ValueError):
                continue
            for group in groups:
                if group.cgroup_path and group.cgroup_path.is_file():
                    paths.append(group.cgroup_path)
        return paths

    @staticmethod
    def _targeted_fm8_layer_groups(root: Path) -> list[Path]:
        candidates: list[Path] = []
        if not root.exists():
            return candidates
        if root.name.lower() == "layergroups":
            layer_groups_root = root
        elif root.name.lower() == "ugc":
            layer_groups_root = root / "LayerGroups"
        else:
            maybe = root / "Microsoft.ForzaMotorsport" / "UGC" / "LayerGroups"
            layer_groups_root = maybe if maybe.is_dir() else root / "LayerGroups"
        if not layer_groups_root.is_dir():
            return candidates
        try:
            folders = [item for item in layer_groups_root.iterdir() if item.is_dir()]
        except OSError:
            return candidates
        for folder in folders:
            data_file = folder / "data"
            if data_file.is_file():
                candidates.append(data_file)
        return candidates

    @staticmethod
    def _targeted_fm8_liveries(root: Path) -> list[Path]:
        candidates: list[Path] = []
        if not root.exists():
            return candidates
        if root.name.lower() == "liveries":
            liveries_root = root
        elif root.name.lower() == "ugc":
            liveries_root = root / "Liveries"
        else:
            maybe = root / "Microsoft.ForzaMotorsport" / "UGC" / "Liveries"
            liveries_root = maybe if maybe.is_dir() else root / "Liveries"
        if not liveries_root.is_dir():
            return candidates
        try:
            folders = [item for item in liveries_root.iterdir() if item.is_dir()]
        except OSError:
            return candidates
        for folder in folders:
            data_file = folder / "data"
            if data_file.is_file():
                candidates.append(data_file)
        return candidates

    @classmethod
    def _count_ignored_designs(cls, roots: list[Path], game_key: str) -> int:
        if cls._game_key(game_key) != "fm8":
            return 0
        seen: set[str] = set()
        for root in roots:
            for path in cls._targeted_fm8_liveries(root):
                try:
                    seen.add(str(path.resolve()).lower())
                except OSError:
                    continue
        return len(seen)

    @staticmethod
    def _is_fh5_layer_group_candidate(path: Path) -> bool:
        name = path.name.lower()
        if name == "c_group":
            return True
        if name.endswith(".c_group"):
            return True
        from tools.cgroup.forza_source_decoder import probe_forza_source_kind

        return probe_forza_source_kind(path) == "cgroup"

    @staticmethod
    def _bounded_source_walk(
        root: Path,
        max_files: int | None,
        max_seconds: float | None,
        game_key: str = "fh6",
    ) -> list[Path]:
        if not root.exists():
            return []
        skip_names = {
            ".git",
            ".hg",
            ".svn",
            ".venv",
            "__pycache__",
            "checkpoints",
            "generated",
            "imgs",
            "node_modules",
            "previews",
            "python",
            "reports",
            "runtime",
            "site-packages",
            "venv",
        }
        found: list[Path] = []
        scanned = 0
        deadline = time.monotonic() + max_seconds if max_seconds is not None else None
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = [name for name in dirnames if name.lower() not in skip_names]
            scanned += len(filenames)
            for filename in filenames:
                current = Path(dirpath)
                filename_lower = filename.lower()
                if game_key == "fm8":
                    is_candidate = filename_lower == "data" and current.parent.name.lower() == "layergroups"
                elif game_key in {"fh4", "fh5"}:
                    is_candidate = CGroupLibraryService._is_fh5_layer_group_candidate(current / filename)
                else:
                    is_candidate = filename_lower == "c_group" and current.name.startswith("LayerGroup_")
                if is_candidate:
                    found.append(current / filename)
            if (max_files is not None and scanned >= max_files) or (
                deadline is not None and time.monotonic() >= deadline
            ):
                break
        return found

    def _default_save_roots(self, game_key: str | None = None) -> list[Path]:
        game_key = self._game_key(game_key)
        roots: list[Path] = []
        cached_roots = self._load_cached_roots(game_key)
        if game_key == "fh5":
            roots.extend(root for root in cached_roots if self._is_fh5_save_root(root))
        elif game_key == "fh4":
            roots.extend(root for root in cached_roots if self._is_fh4_save_root(root))
        else:
            roots.extend(cached_roots)

        local_app_data = os.environ.get("LOCALAPPDATA")
        if game_key == "fh5":
            roots.extend(self._discover_fh5_save_roots())
        elif game_key == "fh4":
            roots.extend(self._discover_fh4_save_roots())
        elif game_key == "fm8" and local_app_data:
            fm8_ugc = Path(local_app_data) / "Microsoft.ForzaMotorsport" / "UGC"
            for candidate in (fm8_ugc / "LayerGroups", fm8_ugc):
                if candidate.exists():
                    roots.append(candidate)
            roots.extend(self._discover_xbox_game_save_roots())
        else:
            roots.extend(self._discover_xbox_game_save_roots())

        if local_app_data and game_key == "fh6":
            packages = Path(local_app_data) / "Packages"
            if packages.exists():
                for pattern in (
                    "*Forza*/SystemAppData/wgs",
                    "*Forza*/SystemAppData/Helium",
                    "*Microsoft*Forza*/SystemAppData/wgs",
                    "*Microsoft*Forza*/SystemAppData/Helium",
                ):
                    roots.extend(path for path in packages.glob(pattern) if path.exists())

        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            key = str(root.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(root)
        return unique

    @classmethod
    def _is_fh4_save_root(cls, root: Path) -> bool:
        text = str(root).replace("\\", "/").lower()
        return (
            "sunrisebasegame" in text
            or "forzahorizon4" in text
            or "/1293830/" in text
            or text.endswith("/1293830/remote")
        )

    @classmethod
    def _discover_fh4_save_roots(cls) -> list[Path]:
        roots: list[Path] = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            packages = Path(local_app_data) / "Packages"
            if packages.exists():
                try:
                    package_folders = [item for item in packages.iterdir() if item.is_dir()]
                except OSError:
                    package_folders = []
                for package in package_folders:
                    name = package.name.lower()
                    if "sunrisebasegame" not in name and "forzahorizon4" not in name:
                        continue
                    for marker in ("wgs", "Helium"):
                        candidate = package / "SystemAppData" / marker
                        if candidate.exists():
                            roots.append(candidate)
        roots.extend(cls._discover_steam_remote_roots("1293830"))
        return cls._unique_existing_paths(roots)

    @classmethod
    def _is_fh5_save_root(cls, root: Path) -> bool:
        text = str(root).replace("\\", "/").lower()
        return (
            "624f8b84b80" in text
            or "forzahorizon5" in text
            or "/1551360/" in text
            or text.endswith("/1551360/remote")
        )

    @classmethod
    def _discover_fh5_save_roots(cls) -> list[Path]:
        roots: list[Path] = []
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            packages = Path(local_app_data) / "Packages"
            if packages.exists():
                for package in packages.iterdir():
                    if not package.is_dir():
                        continue
                    name = package.name.lower()
                    if "624f8b84b80" not in name and "forzahorizon5" not in name:
                        continue
                    for marker in ("wgs", "Helium"):
                        candidate = package / "SystemAppData" / marker
                        if candidate.exists():
                            roots.append(candidate)
        roots.extend(cls._discover_fh5_steam_roots())
        return cls._unique_existing_paths(roots)

    @classmethod
    def _discover_fh5_steam_roots(cls) -> list[Path]:
        return cls._discover_steam_remote_roots("1551360")

    @classmethod
    def _discover_steam_remote_roots(cls, app_id: str) -> list[Path]:
        roots: list[Path] = []
        for steam_root in cls._steam_install_roots():
            userdata = steam_root / "userdata"
            if not userdata.is_dir():
                continue
            try:
                users = [item for item in userdata.iterdir() if item.is_dir()]
            except OSError:
                continue
            for user in users:
                remote = user / str(app_id) / "remote"
                if remote.exists():
                    roots.append(remote)
        return cls._unique_existing_paths(roots)

    @classmethod
    def _steam_install_roots(cls) -> list[Path]:
        candidates: list[Path] = []
        try:
            import winreg  # type: ignore

            registry_locations = (
                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Valve\Steam", "InstallPath"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
            )
            for hive, key_name, value_name in registry_locations:
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        value, _ = winreg.QueryValueEx(key, value_name)
                    if value:
                        candidates.append(Path(str(value)))
                except OSError:
                    continue
        except Exception:
            pass

        for env_name in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            value = os.environ.get(env_name)
            if value:
                candidates.append(Path(value) / "Steam")

        for drive in cls._windows_drive_roots():
            candidates.extend((drive / "Steam", drive / "SteamLibrary" / "Steam"))

        return cls._unique_existing_paths(candidates)

    @staticmethod
    def _unique_existing_paths(paths: list[Path]) -> list[Path]:
        unique: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            if not path.exists():
                continue
            try:
                key = str(path.resolve()).lower()
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    @classmethod
    def _discover_xbox_game_save_roots(cls) -> list[Path]:
        roots: list[Path] = []
        for drive in cls._windows_drive_roots():
            for xbox_root in cls._find_xboxgames_roots(drive):
                for candidate in (xbox_root / "GameSave", xbox_root / "GameSave" / "pgs"):
                    if candidate.exists():
                        roots.append(candidate)
        return roots

    @staticmethod
    def _windows_drive_roots() -> list[Path]:
        roots: list[Path] = []
        if os.name == "nt":
            for letter in string.ascii_uppercase:
                root = Path(f"{letter}:/")
                if root.exists():
                    roots.append(root)
        else:
            for candidate in (Path("C:/"), Path("/mnt/c"), Path("/mnt/d"), Path("/mnt/e")):
                if candidate.exists():
                    roots.append(candidate)
        return roots

    @staticmethod
    def _find_xboxgames_roots(drive: Path) -> list[Path]:
        found: list[Path] = []
        direct = drive / "XboxGames"
        if direct.is_dir():
            found.append(direct)

        queue: list[tuple[Path, int]] = [(drive, 0)]
        seen: set[str] = set()
        max_depth = 3
        deadline = time.monotonic() + 4.0
        while queue and time.monotonic() < deadline:
            current, depth = queue.pop(0)
            try:
                key = str(current.resolve()).lower()
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            if current.name.lower() == "xboxgames":
                found.append(current)
                continue
            if depth >= max_depth:
                continue
            try:
                children = [item for item in current.iterdir() if item.is_dir()]
            except OSError:
                continue
            for child in children:
                name = child.name.lower()
                if name in {"$recycle.bin", "program files", "program files (x86)", "programdata", "users", "windows"}:
                    continue
                if name == "xboxgames" or depth < 2:
                    queue.append((child, depth + 1))

        unique: list[Path] = []
        seen_paths: set[str] = set()
        for path in found:
            try:
                key = str(path.resolve()).lower()
            except OSError:
                continue
            if key in seen_paths:
                continue
            seen_paths.add(key)
            unique.append(path)
        return unique

    def _load_cached_roots(self, game_key: str | None = None) -> list[Path]:
        try:
            data = json.loads(self._root_cache_file(game_key).read_text(encoding="utf-8"))
        except Exception:
            return []
        roots: list[Path] = []
        for value in data.get("roots", []) if isinstance(data, dict) else []:
            try:
                path = Path(str(value))
            except Exception:
                continue
            if path.exists():
                roots.append(path)
        return roots

    def _save_cached_roots(self, roots: list[Path], game_key: str | None = None) -> None:
        unique: list[str] = []
        seen: set[str] = set()
        for root in roots:
            if not root.exists():
                continue
            try:
                key = str(root.resolve())
            except OSError:
                continue
            low = key.lower()
            if low in seen:
                continue
            seen.add(low)
            unique.append(key)
        if not unique:
            return
        try:
            cache_file = self._root_cache_file(game_key)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(
                    {
                        "format": "kfps_cgroup_library_roots_v2",
                        "game": self._game_key(game_key),
                        "updated_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
                        "roots": unique,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    @staticmethod
    def _roots_for_sources(source_paths: list[Path]) -> list[Path]:
        roots: list[Path] = []
        for source in source_paths:
            parts = source.parts
            lowered = [part.lower() for part in parts]
            if "pgs" in lowered:
                index = lowered.index("pgs")
                roots.append(Path(*parts[: index + 1]))
                continue
            if "ugc" in lowered and "layergroups" in lowered:
                index = lowered.index("ugc")
                roots.append(Path(*parts[: index + 2]))
                continue
            if "1551360" in lowered and "remote" in lowered:
                index = lowered.index("remote")
                roots.append(Path(*parts[: index + 1]))
                continue
            for marker in ("wgs", "helium"):
                if marker in lowered:
                    index = lowered.index(marker)
                    roots.append(Path(*parts[: index + 1]))
                    break
        return roots

    @staticmethod
    def _file_fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            return ""
        return digest.hexdigest()[:12]

    def _write_preview(self, json_path: Path) -> None:
        preview_path = json_path.with_suffix(".preview.png")
        try:
            if preview_path.is_file() and preview_path.stat().st_mtime_ns >= json_path.stat().st_mtime_ns:
                return
        except OSError:
            pass
        try:
            from json_preview_renderer import render_json_preview

            data = render_json_preview(json_path, max_size=900)
            if data:
                preview_path.write_bytes(data)
                return
        except Exception:
            pass
        self.preview.preview_for_json(json_path, "exported")

    @staticmethod
    def _write_text_if_changed(path: Path, text: str) -> None:
        text = text + "\n"
        try:
            if path.is_file() and path.read_text(encoding="utf-8") == text:
                return
        except Exception:
            pass
        path.write_text(text, encoding="utf-8")

    @classmethod
    def _read_layer_group_metadata(cls, source_path: Path) -> dict[str, Any]:
        header_path = cls._metadata_header_path(source_path)
        strings = cls._extract_header_strings(header_path)
        generic_titles = {"Forza", "Forza BaseLivery"}
        meaningful = [item for item in strings if item not in generic_titles]
        title = source_path.parent.name
        description = ""
        creator = ""
        title_from_fm8_header = False
        if source_path.name.lower() == "data":
            fm8_title = cls._extract_fm8_header_title(header_path)
            if fm8_title and fm8_title not in generic_titles:
                title = fm8_title
                title_from_fm8_header = True
        if title_from_fm8_header:
            remaining = [item for item in meaningful if item != title]
            if len(remaining) >= 2:
                description = remaining[0]
                creator = remaining[1]
            elif len(remaining) == 1:
                creator = remaining[0]
        elif strings and strings[0] not in generic_titles and meaningful:
            title = meaningful[0]
            if len(meaningful) >= 3:
                description = meaningful[1]
                creator = meaningful[2]
            elif len(meaningful) == 2:
                creator = meaningful[1]
        elif meaningful:
            creator = meaningful[-1]
        return {
            "title": title,
            "display_name": title,
            "description": description,
            "creator": creator,
            "asset_type": "vinyl_group",
            "header_strings": meaningful[:6],
        }

    @staticmethod
    def _metadata_header_path(source_path: Path) -> Path:
        direct = source_path.parent / "header"
        if direct.is_file():
            return direct
        try:
            from tools.cgroup.xbox_wgs import logical_wgs_sibling

            wgs_header = logical_wgs_sibling(source_path, "header")
            if wgs_header and wgs_header.is_file():
                return wgs_header
        except (OSError, ValueError):
            pass
        name = source_path.name
        lower = name.lower()
        for suffix in (".c_group", ".c_livery", ".data"):
            if lower.endswith(suffix):
                base = name[: -len(suffix)]
                sibling = source_path.with_name(base + ".header")
                if sibling.is_file():
                    return sibling
                break
        return direct

    @staticmethod
    def _extract_header_strings(header_path: Path) -> list[str]:
        if not header_path.is_file():
            return []
        try:
            data = header_path.read_bytes()
        except OSError:
            return []
        strings: list[str] = []
        seen: set[str] = set()
        for offset in range(4, max(4, len(data) - 8)):
            length = struct.unpack_from("<I", data, offset)[0]
            if not 3 <= length <= 96:
                continue
            start = offset + 4
            end = start + length * 2
            if end > len(data):
                continue
            try:
                value = data[start:end].decode("utf-16le")
            except UnicodeDecodeError:
                continue
            value = CGroupLibraryService._clean_header_string(value)
            if not value or value in seen:
                continue
            seen.add(value)
            strings.append(value)
        return strings

    @staticmethod
    def _extract_fm8_header_title(header_path: Path) -> str:
        if not header_path.is_file():
            return ""
        try:
            data = header_path.read_bytes()
        except OSError:
            return ""
        if len(data) < 8:
            return ""
        try:
            length = struct.unpack_from("<I", data, 4)[0]
        except struct.error:
            return ""
        if not 1 <= length <= 96:
            return ""
        start = 8
        end = start + length * 2
        if end > len(data):
            return ""
        try:
            return CGroupLibraryService._clean_header_string(data[start:end].decode("utf-16le"), minimum_length=1)
        except UnicodeDecodeError:
            return ""

    @staticmethod
    def _clean_header_string(value: str, minimum_length: int = 3) -> str:
        if any(not (char.isprintable() or char.isspace()) for char in value):
            return ""
        value = " ".join(value.replace("\x00", " ").split())
        if len(value) < minimum_length:
            return ""
        ascii_count = sum(1 for char in value if char.isascii() and (char.isalnum() or char in " _-.?!'#/&()+,:"))
        if ascii_count < max(1, min(3, minimum_length)):
            return ""
        if ascii_count / max(len(value), 1) < 0.65:
            return ""
        printable_count = sum(1 for char in value if char.isprintable())
        if printable_count / max(len(value), 1) < 0.85:
            return ""
        return value[:120]

    @staticmethod
    @staticmethod
    def _flatten_legacy_game_library_roots(library_root: Path) -> None:
        for game_folder in ("fh6", "fh5", "fh4", "fm8"):
            legacy_root = library_root / game_folder
            if not legacy_root.is_dir():
                continue
            try:
                entries = [item for item in legacy_root.iterdir() if item.is_dir()]
            except OSError:
                continue
            for entry in entries:
                target = library_root / entry.name
                if target.exists():
                    suffix = 2
                    while (library_root / f"{entry.name}-{suffix}").exists():
                        suffix += 1
                    target = library_root / f"{entry.name}-{suffix}"
                try:
                    shutil.move(str(entry), str(target))
                except OSError:
                    continue
            try:
                legacy_root.rmdir()
            except OSError:
                pass

    @staticmethod
    def _source_path_key(path: Path | str) -> str:
        try:
            return str(Path(path).resolve()).casefold()
        except OSError:
            return str(path).casefold()

    @staticmethod
    def _prune_non_layergroup_library_entries(
        library_root: Path,
        active_entry_names: set[str],
        active_source_keys: set[str],
        game_key: str | None = None,
    ) -> None:
        if not library_root.is_dir():
            return
        scan_game_key = CGroupLibraryService._game_key(game_key)
        for entry in library_root.iterdir():
            if not entry.is_dir():
                continue
            manifest_paths = sorted(entry.glob("*.manifest.json"))
            if not manifest_paths:
                continue
            try:
                manifest = json.loads(manifest_paths[0].read_text(encoding="utf-8"))
            except Exception:
                continue
            source_path = Path(str(manifest.get("source_path") or ""))
            source_folder = str(manifest.get("source_folder") or source_path.parent.name)
            source_kind = str(manifest.get("source_kind") or "").lower()
            target_game = CGroupLibraryService._game_key(str(manifest.get("target_game") or "fh6"))
            if target_game != scan_game_key:
                continue
            is_fh_layer_group = source_path.name.lower() == "c_group" and source_folder.startswith("LayerGroup_")
            is_fh5_layer_group = target_game == "fh5" and source_kind == "cgroup"
            is_fh4_layer_group = target_game == "fh4" and source_kind == "cgroup"
            is_fm8_layer_group = (
                target_game == "fm8"
                and source_path.name.lower() == "data"
                and source_path.parent.parent.name.lower() == "layergroups"
            )
            is_layer_group = is_fh_layer_group or is_fh5_layer_group or is_fh4_layer_group or is_fm8_layer_group
            source_was_rescanned = CGroupLibraryService._source_path_key(source_path) in active_source_keys
            superseded = source_was_rescanned and entry.name not in active_entry_names
            if not is_layer_group or superseded:
                try:
                    shutil.rmtree(entry)
                except OSError:
                    pass
