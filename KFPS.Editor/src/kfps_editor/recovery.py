"""Bounded local recovery checkpoints; portable project files are unchanged."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path


REFERENCE_KEY = "editor_recovery_reference"
REFERENCE_ID = re.compile(r"[a-f0-9]{64}")


def _reference_id(payload: dict) -> str | None:
    reference = payload.get(REFERENCE_KEY)
    if reference is None:
        return None
    if not isinstance(reference, dict) or not REFERENCE_ID.fullmatch(str(reference.get("sha256", ""))):
        raise ValueError("Invalid recovery reference identity.")
    if type(reference.get("size")) is not int or reference["size"] <= 0:
        raise ValueError("Invalid recovery reference size.")
    return reference["sha256"]


class RecoveryStore:
    def __init__(self, marker: Path, write_json, max_bytes: int):
        self.marker = marker
        self.previous = marker.with_name("autosave.previous.json")
        self.references = marker.parent / "recovery-references"
        self.watermark = marker.with_name("autosave.revision.json")
        self.write_json = write_json
        self.max_bytes = max_bytes
        self._verified = {}
        self._remove_abandoned_temporary_files()

    def _remove_abandoned_temporary_files(self) -> None:
        # Constructed once under the server's recovery lock, before any writes.
        # Only this store's exact temporary names belong to crash cleanup.
        checkpoint_names = "|".join(re.escape(path.name) for path in (self.marker, self.previous, self.watermark))
        checkpoint_temp = re.compile(rf"\.(?:{checkpoint_names})\.[0-9]+\.[0-9]+\.tmp")
        for directory, matches in (
            (self.marker.parent, lambda name: name == self.previous.with_suffix(".tmp").name or checkpoint_temp.fullmatch(name)),
            (self.references, lambda name: re.fullmatch(r"[a-f0-9]{64}\.tmp", name)),
        ):
            try:
                if directory.is_symlink() or directory.is_junction() or not directory.is_dir():
                    continue
                for path in directory.iterdir():
                    if matches(path.name) and not path.is_symlink() and not path.is_junction() and path.is_file():
                        try:
                            path.unlink()
                        except OSError:
                            pass
            except OSError:
                pass

    def reference_path(self, identity: str) -> Path:
        if not isinstance(identity, str) or not REFERENCE_ID.fullmatch(identity):
            raise ValueError("Invalid recovery reference identity.")
        path = self.references / f"{identity}.json"
        if self.references.is_symlink() or self.references.is_junction() or path.is_symlink():
            raise ValueError("Recovery references must be regular local files.")
        return path

    def put_reference(self, body: bytes, identity: str) -> None:
        if not 0 < len(body) <= self.max_bytes:
            raise ValueError("Invalid recovery reference size.")
        if hashlib.sha256(body).hexdigest() != identity:
            raise ValueError("Recovery reference checksum does not match.")
        payload = json.loads(body)
        if not isinstance(payload, dict) or set(payload) != {"data_url", "svg_text"}:
            raise ValueError("Invalid recovery reference data.")
        if any(value is not None and not isinstance(value, str) for value in payload.values()):
            raise ValueError("Invalid recovery reference data.")
        target = self.reference_path(identity)
        self.references.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.stat().st_size == len(body):
            if hashlib.sha256(target.read_bytes()).hexdigest() == identity:
                return
        temporary = target.with_suffix(".tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(body)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        self._verified[identity] = self._reference_stat(target)
        self.prune_references()

    @staticmethod
    def _reference_stat(path: Path) -> tuple:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns

    def validate_reference(self, identity: str, size: int) -> None:
        path = self.reference_path(identity)
        current = self._reference_stat(path)
        if current[0] != size or not 0 < size <= self.max_bytes:
            raise ValueError("Recovery reference size does not match.")
        if self._verified.get(identity) != current:
            self.reference_bytes(identity)

    def reference_bytes(self, identity: str) -> bytes:
        path = self.reference_path(identity)
        if path.stat().st_size > self.max_bytes:
            raise ValueError("Recovery reference exceeds its storage limit.")
        body = path.read_bytes()
        if hashlib.sha256(body).hexdigest() != identity:
            raise ValueError("Recovery reference checksum does not match.")
        self._verified[identity] = self._reference_stat(path)
        return body

    def _read(self, path: Path, materialize: bool) -> dict:
        # Older versions pretty-printed these files; allow that small expansion.
        if path.stat().st_size > self.max_bytes * 2:
            raise ValueError("Recovery checkpoint exceeds its storage limit.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("shapes"), list):
            raise ValueError("Recovery checkpoint has no shapes list.")
        revision = payload.get("recovery_revision", 0)
        if type(revision) is not int or not 0 <= revision <= 2**53 - 1:
            raise ValueError("Invalid recovery revision.")
        identity = _reference_id(payload)
        if identity:
            self.validate_reference(identity, payload[REFERENCE_KEY]["size"])
            if materialize:
                reference = self.reference_bytes(identity)
                overlay = payload.get("editor_source_overlay")
                if not isinstance(overlay, dict):
                    raise ValueError("Recovery reference metadata is missing.")
                payload["editor_source_overlay"] = {**overlay, **json.loads(reference)}
                del payload[REFERENCE_KEY]
        return payload

    def read(self, *, materialize=True) -> tuple[dict | None, bool, str]:
        errors = []
        cleared_revision = 0
        try:
            watermark = json.loads(self.watermark.read_text(encoding="utf-8"))
            if watermark.get("cleared") is True and type(watermark.get("recovery_revision")) is int:
                cleared_revision = watermark["recovery_revision"]
        except (OSError, ValueError, AttributeError):
            pass
        for path in (self.marker, self.previous):
            try:
                payload = self._read(path, materialize)
                if cleared_revision and payload.get("recovery_revision", 0) < cleared_revision:
                    payload = {"action": "clear", "shapes": [], "recovery_revision": cleared_revision}
                return payload, path == self.previous, "; ".join(errors)
            except FileNotFoundError:
                if path.exists():
                    errors.append("Recovery reference is missing.")
            except (OSError, ValueError, TypeError) as exc:
                errors.append(str(exc))
        if cleared_revision:
            return {"action": "clear", "shapes": [], "recovery_revision": cleared_revision}, False, "; ".join(errors)
        return None, False, "; ".join(errors)

    def revision(self) -> int:
        return self.head()["recovery_revision"]

    def head(self) -> dict:
        highest = cleared = 0
        for path in (self.marker, self.previous, self.watermark):
            try:
                if path.stat().st_size > self.max_bytes * 2:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
                value = data.get("recovery_revision", 0)
                if type(value) is int and 0 <= value <= 2**53 - 1:
                    highest = max(highest, value)
                    if data.get("action") == "clear" or data.get("cleared") is True:
                        cleared = max(cleared, value)
            except (OSError, ValueError, AttributeError):
                pass
        return {"recovery_revision": highest, "clearedRevision": cleared}

    def write(self, payload: dict) -> None:
        identity = _reference_id(payload)
        if identity:
            try:
                self.validate_reference(identity, payload[REFERENCE_KEY]["size"])
            except FileNotFoundError:
                raise ValueError("Recovery reference is missing; retry the checkpoint.")
            overlay = payload.get("editor_source_overlay")
            if not isinstance(overlay, dict) or any(overlay.get(key) is not None for key in ("data_url", "svg_text")):
                raise ValueError("Recovery reference metadata is missing.")
            portable = {key: value for key, value in payload.items() if key != REFERENCE_KEY}
            portable["editor_source_overlay"] = {**overlay, "data_url": None, "svg_text": None}
            empty_source = len(b'{"data_url":null,"svg_text":null}')
            portable_size = len(json.dumps(portable, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            if portable_size + payload[REFERENCE_KEY]["size"] - empty_source > self.max_bytes:
                raise ValueError("Recovery exceeds the project storage limit.")
        # Preserve the last valid checkpoint before the atomic replacement. The
        # caller holds the single recovery lock across reference and head changes.
        try:
            self._read(self.marker, False)
        except (OSError, ValueError, TypeError):
            pass
        else:
            temporary = self.previous.with_suffix(".tmp")
            try:
                shutil.copyfile(self.marker, temporary)
                with temporary.open("r+b") as stream:
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.previous)
            finally:
                temporary.unlink(missing_ok=True)
        self.write_json(self.marker, payload)
        self.acknowledge(payload)

    def acknowledge(self, payload: dict) -> None:
        revision = payload.get("recovery_revision", 0)
        if revision:
            self.write_json(self.watermark, {"recovery_revision": revision, "cleared": payload.get("action") == "clear"})
        self.prune_references()

    def prune_references(self) -> None:
        if not self.references.is_dir() or self.references.is_symlink() or self.references.is_junction():
            return
        retained = set()
        for checkpoint in (self.marker, self.previous):
            try:
                identity = _reference_id(json.loads(checkpoint.read_text(encoding="utf-8")))
                if identity:
                    retained.add(identity)
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        candidates = [path for path in self.references.iterdir()
                      if path.is_file() and not path.is_symlink()
                      and path.suffix == ".json" and REFERENCE_ID.fullmatch(path.stem)]
        # Two recently uploaded references may be waiting for their checkpoint.
        # If an older delayed writer lost its sidecar, it must upload it again.
        orphans = sorted((path for path in candidates if path.stem not in retained),
                         key=lambda path: path.stat().st_mtime_ns, reverse=True)
        for path in orphans[2:]:
            try:
                path.unlink()
                self._verified.pop(path.stem, None)
            except OSError:
                pass
