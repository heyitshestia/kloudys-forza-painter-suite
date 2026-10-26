"""Prepare full liveries for Community without changing their source artwork."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile

from tools.livery.package import validate_full_livery_package

# Match tools/community_worker/src/livery_upload.ts. These are unpacked limits,
# except MAX_PACKAGE_BYTES, which applies to the ZIP sent over the network.
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
LAYERS = "livery/layers.json"


def _size_error(name: str, size: int, limit: int) -> ValueError:
    return ValueError(
        f"Community upload: {name} is {size / 1024**2:.2f} MiB after unpacking "
        f"(limit {limit / 1024**2:g} MiB). The .kfpslivery file size is compressed."
    )


def prepare_livery_upload(source: Path) -> tuple[dict, bytes]:
    """Validate before repacking; keep already-compatible packages byte-identical."""
    if source.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError("Community livery packages must be 16 MiB or smaller.")
    manifest = validate_full_livery_package(source)
    with zipfile.ZipFile(source) as bundle:
        infos = bundle.infolist()
        replacements = {}
        layer_info = bundle.getinfo(LAYERS)
        if (layer_info.file_size > MAX_MEMBER_BYTES
                or sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES):
            # The exporter writes indented JSON. Remove formatting only, after
            # native-source and manifest validation, without dropping any fields.
            layers = json.loads(bundle.read(layer_info))
            compact = json.dumps(layers, ensure_ascii=True, allow_nan=False,
                                 sort_keys=True, separators=(",", ":")).encode("utf-8")
            if len(compact) > MAX_MEMBER_BYTES:
                raise _size_error(LAYERS, len(compact), MAX_MEMBER_BYTES)
            if len(compact) < layer_info.file_size:
                replacements[LAYERS] = compact
                for record in manifest["files"]:
                    if record["path"] == LAYERS:
                        record.update(size=len(compact), sha256=hashlib.sha256(compact).hexdigest())
                replacements["manifest.json"] = json.dumps(
                    manifest, ensure_ascii=True, allow_nan=False, sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")

        total = 0
        for info in infos:
            size = len(replacements[info.filename]) if info.filename in replacements else info.file_size
            limit = MAX_MANIFEST_BYTES if info.filename == "manifest.json" else MAX_MEMBER_BYTES
            if size > limit:
                raise _size_error(info.filename, size, limit)
            total += size
        if total > MAX_EXPANDED_BYTES:
            raise _size_error("the complete package", total, MAX_EXPANDED_BYTES)
        if not replacements:
            return manifest, source.read_bytes()

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as prepared:
            prepared.comment = bundle.comment
            for info in infos:
                data = replacements.get(info.filename)
                if data is None:
                    data = bundle.read(info)
                prepared.writestr(copy.copy(info), data, compress_type=zipfile.ZIP_DEFLATED,
                                  compresslevel=6)
        payload = output.getvalue()
        if len(payload) > MAX_PACKAGE_BYTES:
            raise ValueError("The prepared Community livery package exceeds 16 MiB.")
        return manifest, payload
