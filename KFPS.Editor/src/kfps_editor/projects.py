"""Atomic project writes with bounded, artwork-free outcome receipts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading


class ProjectSaveError(ValueError):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def read_bounded_document(path: Path, max_bytes: int) -> bytes:
    with path.open("rb") as stream:
        if os.fstat(stream.fileno()).st_size > max_bytes:
            raise ProjectSaveError("File exceeds the editor input limit. Choose a smaller file.", "input_too_large")
        body = stream.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise ProjectSaveError("File exceeds the editor input limit. Choose a smaller file.", "input_too_large")
    return body


class ProjectStore:
    RECEIPT_ID = re.compile(r"[a-f0-9-]{32,36}")
    HASH = re.compile(r"[a-f0-9]{64}")

    def __init__(self, root: Path, write_json, max_bytes: int, *, receipts: Path | None = None):
        self.root = root
        self.receipts = receipts or root.parent / "save-receipts"
        self.write_json = write_json
        self.max_bytes = max_bytes
        self.lock = threading.RLock()

    def _target(self, target_id):
        if not isinstance(target_id, str) or not target_id or "\x00" in target_id:
            raise ValueError("Invalid project ID.")
        target = (self.root / target_id).resolve()
        if not target.is_relative_to(self.root.resolve()) or target.suffix.lower() != ".json":
            raise ValueError("Project path is outside the project folder.")
        return target

    def fingerprint(self, target):
        with target.open("rb") as stream:
            if os.fstat(stream.fileno()).st_size > self.max_bytes:
                raise ValueError("Project exceeds the save limit.")
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def read(self, target_id):
        with self.lock:
            target = self._target(target_id)
            body = read_bounded_document(target, self.max_bytes)
            return {"id": target_id, "name": target.name, "payload": json.loads(body),
                    "receipt": {"target_id": target_id, "fingerprint": hashlib.sha256(body).hexdigest(),
                                "bytes": len(body), "write_stage": "read"}}

    def verify(self, target_id, fingerprint):
        if not isinstance(fingerprint, str) or not self.HASH.fullmatch(fingerprint):
            return False
        with self.lock:
            try:
                return self.fingerprint(self._target(target_id)) == fingerprint
            except (OSError, ValueError):
                return False

    def _receipt_path(self, request_id):
        if not isinstance(request_id, str) or not self.RECEIPT_ID.fullmatch(request_id):
            raise ValueError("Invalid save request ID.")
        if self.receipts.is_symlink() or self.receipts.is_junction():
            raise ValueError("Save receipts must be stored locally.")
        path = self.receipts / f"{request_id}.json"
        if path.is_symlink():
            raise ValueError("Save receipt must be a regular file.")
        return path

    def outcome(self, request_id):
        with self.lock:
            path = self._receipt_path(request_id)
            try:
                if path.stat().st_size > 4096:
                    raise ValueError("Invalid save receipt size.")
                receipt = json.loads(path.read_text(encoding="utf-8"))
                if receipt.get("request_id") != request_id:
                    raise ValueError("Save receipt identity does not match.")
                current = self.verify(receipt["target_id"], receipt["fingerprint"])
                if receipt["write_stage"] == "committed" or current:
                    return {"ok": True, "status": "committed", "current": current,
                            "receipt": {**receipt, "write_stage": "committed"}}
            except FileNotFoundError:
                pass
            except (OSError, ValueError, KeyError, TypeError):
                pass
            return {"ok": False, "status": "unknown"}

    def _prune(self):
        candidates = [path for path in self.receipts.glob("*.json")
                      if self.RECEIPT_ID.fullmatch(path.stem) and path.is_file() and not path.is_symlink()]
        for path in sorted(candidates, key=lambda item: item.stat().st_mtime_ns, reverse=True)[128:]:
            try:
                path.unlink()
            except OSError:
                pass

    def save(self, target_id, payload, *, request_id=None, expected=None, legacy_overwrite=False):
        # Legacy callers retain their existing behavior. The current editor always
        # supplies a request ID and must prove ownership before replacing a file.
        current_protocol = request_id is not None
        request_id = request_id or secrets.token_hex(16)
        receipt_path = self._receipt_path(request_id)
        if expected is not None and (not isinstance(expected, str) or not self.HASH.fullmatch(expected)):
            raise ValueError("Invalid expected project fingerprint.")
        with self.lock:
            target = self._target(target_id)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.{request_id}.tmp")
            try:
                hasher = hashlib.sha256()
                size = 0
                with temporary.open("xb") as stream:
                    for part in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(",", ":")).iterencode(payload):
                        body = part.encode("utf-8")
                        size += len(body)
                        if size > self.max_bytes:
                            raise ProjectSaveError("Project exceeds the save limit.", "project_too_large")
                        stream.write(body)
                        hasher.update(body)
                    stream.flush()
                    os.fsync(stream.fileno())
                fingerprint = hasher.hexdigest()
                if receipt_path.exists():
                    previous = self.outcome(request_id)
                    receipt = previous.get("receipt", {})
                    if receipt.get("target_id") == target_id and receipt.get("fingerprint") == fingerprint:
                        return previous
                    raise ProjectSaveError("This save request has already been used. Save again with a new request.", "save_request_used")
                if target.exists():
                    if expected is None and (current_protocol or not legacy_overwrite):
                        raise ProjectSaveError("That project already exists. Open it before saving, or use a different name.", "project_exists")
                    if expected is not None and self.fingerprint(target) != expected:
                        raise ProjectSaveError("The project changed on disk. Save As with a different name to keep both versions.", "project_conflict")
                elif expected is not None:
                    raise ProjectSaveError("The original project is missing. Save As with a new name.", "project_conflict")
                receipt = {"request_id": request_id, "target_id": target_id, "fingerprint": fingerprint,
                           "bytes": size, "write_stage": "prepared"}
                self.write_json(receipt_path, receipt)
                self._prune()
                os.replace(temporary, target)
                receipt["write_stage"] = "committed"
                # The prepared receipt and target hash can establish success even
                # if the completion journal or HTTP acknowledgment is interrupted.
                self.write_json(receipt_path, receipt)
                self._prune()
                return {"ok": True, "status": "committed", "current": True, "receipt": receipt}
            finally:
                temporary.unlink(missing_ok=True)
