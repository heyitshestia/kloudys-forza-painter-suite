"""Integrity receipts for disposable local renderer assets, never game saves."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable


def file_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def validated_derived_file(path: Path, validator: Callable, revision: int) -> dict:
    receipt = path.with_suffix(path.suffix + ".validated.json")
    signature = {"sha256": file_sha256(path), "revision": int(revision)}
    try:
        value = json.loads(receipt.read_text(encoding="utf-8"))
        if value.get("signature") == signature and isinstance(value.get("validation"), dict):
            return value["validation"]
    except (OSError, ValueError, AttributeError):
        pass
    result = validator(path)
    if file_sha256(path) != signature["sha256"]:
        raise OSError("The derived renderer file changed during validation.")
    temporary = receipt.with_name(f"{receipt.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps({"signature": signature, "validation": result}), encoding="utf-8")
        os.replace(temporary, receipt)
    finally:
        temporary.unlink(missing_ok=True)
    return result
