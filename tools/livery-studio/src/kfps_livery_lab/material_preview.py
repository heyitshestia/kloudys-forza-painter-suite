"""Prepare one evidence-qualified native texture profile without application I/O.

The JS binding adapter remains authoritative for render semantics. This module
preflights that same conservative profile before reading configured archives.
See docs/NATIVE-TEXTURE-BINDING.md; no game-parity claim is made.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zipfile
import zlib

from .material_assets import LAB_ROOT, MaterialAssetError, MaterialAssetStore, _archive_guard
from .prepare import workspace_path

PROFILE = "fts-brake-basecolor-preview-v1"
UV_PIPELINE = "fts-importer-v-flipped-then-native-scale-offset-v1"
NATIVE_UV_PIPELINE = "native-unflipped-then-native-scale-offset-v1"
DECLARATION_SHA256 = "c48809e086530ad194c00fd7c8c608fd5889e2c2f64eb1d02714fa89f2c2d6a5"
_TEMPLATE = "game:/media/cars/_library/materials/_fmnext/brake/brakerotor_ch1.materialbin"
_DECLARATION_MEMBER = "_fmnext/brake/brakerotor_ch1.materialbin"
_PARAMETER_TYPES = {
    "85E937A9": "Texture2D", "F9E8078D": "Texture2D", "8D9C56EF": "Texture2D",
    "CD6B029B": "Float", "4E282123": "Float", "9A83BC93": "Bool",
    "19A7D8F1": "Float", "4A3D8375": "Float",
}
_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", re.I)
_MAX_JSON = 32 * 1024**2
_MAX_DECLARATION = 1024**2
_PUBLIC_METADATA = (
    "pipeline", "source_sha256", "png_sha256", "decoded_mode", "flip_y",
    "premultiplied_alpha", "color_space", "domain", "width", "height", "alpha_range",
)


class MaterialPreviewError(ValueError):
    """Invalid preparation configuration or GLB; no source files are changed."""


def _integer(value, low=0, high=512 * 1024**2):
    return type(value) is int and low <= value <= high


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MaterialPreviewError("Duplicate GLB JSON key.")
        result[key] = value
    return result


def _invalid_constant(_):
    raise MaterialPreviewError("Non-finite GLB JSON number.")


def _read_glb(path):
    try:
        size = path.stat().st_size
        if not 28 <= size <= 512 * 1024**2:
            raise MaterialPreviewError("GLB file exceeds preparation bounds.")
        with path.open("rb") as stream:
            if struct.unpack("<4sII", stream.read(12)) != (b"glTF", 2, size):
                raise MaterialPreviewError("Invalid GLB header.")
            length, kind = struct.unpack("<I4s", stream.read(8))
            if kind != b"JSON" or not 4 <= length <= min(_MAX_JSON, size - 28) or length % 4:
                raise MaterialPreviewError("Invalid or excessive GLB JSON chunk.")
            data = stream.read(length)
            binary_length, binary_kind = struct.unpack("<I4s", stream.read(8))
            if binary_kind != b"BIN\0" or binary_length % 4 or length + binary_length + 28 != size:
                raise MaterialPreviewError("Invalid GLB binary chunk.")
        document = json.loads(data, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (OSError, struct.error, ValueError, RecursionError) as exc:
        raise MaterialPreviewError("Cannot read bounded GLB metadata.") from exc
    if not isinstance(document, dict) or not isinstance(document.get("asset"), dict) or document["asset"].get("version") != "2.0":
        raise MaterialPreviewError("Expected GLB 2.0 metadata.")
    for name, maximum in (("meshes", 20000), ("accessors", 200000), ("bufferViews", 200000)):
        if not isinstance(document.get(name), list) or len(document[name]) > maximum:
            raise MaterialPreviewError("Missing or excessive GLB metadata arrays.")
    buffers = document.get("buffers")
    if (not isinstance(buffers, list) or len(buffers) != 1 or not isinstance(buffers[0], dict)
            or "uri" in buffers[0] or not _integer(buffers[0].get("byteLength"))
            or not 0 <= binary_length - buffers[0]["byteLength"] <= 3):
        raise MaterialPreviewError("Expected one internal GLB buffer.")
    return document, {"json_sha256": hashlib.sha256(data).hexdigest(), "bytes": size}


def _accessor_count(document, index, kind, components):
    accessors, views = document["accessors"], document["bufferViews"]
    if not _integer(index, 0, len(accessors) - 1):
        return None
    accessor = accessors[index]
    if (not isinstance(accessor, dict) or accessor.get("componentType") != 5126
            or accessor.get("type") != kind or accessor.get("normalized") or "sparse" in accessor
            or not _integer(accessor.get("count"), 1, 4000000)
            or not _integer(accessor.get("bufferView"), 0, len(views) - 1)):
        return None
    view = views[accessor["bufferView"]]
    if not isinstance(view, dict) or type(view.get("buffer")) is not int or view["buffer"] != 0:
        return None
    start, length = view.get("byteOffset", 0), view.get("byteLength")
    offset, stride = accessor.get("byteOffset", 0), view.get("byteStride", components * 4)
    if (not _integer(start) or not _integer(length, 1) or not _integer(offset)
            or not _integer(stride, components * 4, 252) or stride % 4 or offset % 4 or start % 4
            or start + length > document["buffers"][0]["byteLength"]
            or offset + (accessor["count"] - 1) * stride + components * 4 > length):
        return None
    return accessor["count"]


def _has_uv0(document, mesh):
    primitives = mesh.get("primitives")
    if not isinstance(primitives, list) or not 1 <= len(primitives) <= 64:
        return False
    for primitive in primitives:
        attrs = primitive.get("attributes") if isinstance(primitive, dict) else None
        if not isinstance(attrs, dict):
            return False
        count = _accessor_count(document, attrs.get("POSITION"), "VEC3", 3)
        if count is None or _accessor_count(document, attrs.get("TEXCOORD_0"), "VEC2", 2) != count:
            return False
    return True


def _native_path(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 1024 or re.search(r"[\x00-\x1f\x7f%?#]", value):
        return None
    value = value.replace("\\", "/")
    if not value.lower().startswith("game:/media/") or ":" in value[6:]:
        return None
    parts = value.split("/")[1:]
    if any(part in ("", ".", "..") or part[-1:] in (".", " ") or _RESERVED.match(part)
           or re.search(r'[<>"|*?]', part) for part in parts):
        return None
    return value


def _parameter_hash(value):
    return re.sub("^0x", "", value, flags=re.I).upper() if isinstance(value, str) and re.fullmatch(r"(?:0x)?[0-9a-f]{8}", value, re.I) else None


def _candidate(document, mesh):
    """No archive I/O until material semantics and UV provenance pass."""
    extras = mesh.get("extras") if isinstance(mesh, dict) else None
    native = extras.get("kfps_native_material") if isinstance(extras, dict) else None
    if not isinstance(native, dict):
        return None, "no-native-material"
    refs = native.get("nested_resources", [])
    if not isinstance(refs, list):
        return None, "unsupported-material-template"
    refs = [ref for ref in [native.get("resource_path"), *refs] if ref is not None]
    if not 1 <= len(refs) <= 32 or any((_native_path(ref) or "").lower() != _TEMPLATE for ref in refs):
        return None, "unsupported-material-template"
    bucket = extras.get("kfps_native_render_bucket")
    if not isinstance(bucket, dict) or bucket.get("opaque") is not True or any(bucket.get(key) for key in ("transparent", "alpha_to_coverage", "decal")):
        return None, "unsupported-alpha-or-decal-state"
    overrides = extras.get("kfps_material_instance_overrides")
    if overrides is not None and overrides != []:
        return None, "unresolved-instance-overrides"
    parameters = native.get("parameters")
    if not isinstance(parameters, list) or len(parameters) > 512:
        return None, "invalid-native-material"
    seen = {}
    for parameter in parameters:
        if not isinstance(parameter, dict):
            return None, "invalid-parameter"
        name, kind, value = _parameter_hash(parameter.get("name_hash")), parameter.get("type"), parameter.get("value")
        if name not in _PARAMETER_TYPES or kind != _PARAMETER_TYPES[name] or parameter.get("parser_placeholder"):
            return None, "unsupported-or-invalid-parameter"
        if kind == "Bool" and value is not False:
            return None, "unsupported-damage-switch"
        if kind == "Float" and not _finite(value):
            return None, "invalid-scalar"
        if kind == "Texture2D":
            path = _native_path(value.get("path")) if isinstance(value, dict) else None
            if not path:
                return None, "invalid-native-texture-path"
            value = {"path": path, "path_hash": _parameter_hash(value.get("path_hash"))}
        if name in seen and seen[name] != value:
            return None, "ambiguous-parameter"
        seen[name] = value
    if "85E937A9" not in seen:
        return None, "missing-basecolor-texture"
    for key in ("19A7D8F1", "4A3D8375"):
        if key in seen and not 1e-6 <= abs(seen[key]) <= 1024:
            return None, "invalid-material-tiling"
    transforms = extras.get("kfps_native_texcoord_transforms")
    if (not isinstance(transforms, list) or not 1 <= len(transforms) <= 8
            or not isinstance(transforms[0], list) or len(transforms[0]) != 4
            or any(not _finite(value) or abs(value) >= 1e6 for value in transforms[0])
            or abs(transforms[0][1]) < 1e-8 or abs(transforms[0][3]) < 1e-8):
        return None, "invalid-source-uv-transform"
    if extras.get("kfps_native_uv_pipeline") not in (UV_PIPELINE, NATIVE_UV_PIPELINE):
        return None, "unverified-uv-pipeline"
    if not _has_uv0(document, mesh):
        return None, "missing-or-invalid-native-uv0"
    return seen["85E937A9"]["path"].lower(), None


def _archive_path(game_root, relative):
    path = (game_root / relative).resolve(strict=True)
    if not path.is_relative_to(game_root) or not path.is_file():
        raise MaterialPreviewError("Archive escaped the configured game root.")
    return path


def _texture_location(game_root, source_path):
    prefix = "game:/media/cars/"
    if not source_path.startswith(prefix) or not source_path.endswith(".swatchbin"):
        raise MaterialPreviewError("Unsupported texture archive mapping.")
    parts = source_path[len(prefix):].split("/")
    if len(parts) < 3 or parts[1] != "textures":
        raise MaterialPreviewError("Unsupported texture archive mapping.")
    model = parts[0]
    if model == "_library":
        return _archive_path(game_root, "media/cars/_library/Textures.zip"), "/".join(parts[2:])
    if not re.fullmatch(r"[a-z0-9_-]{1,100}", model) or _RESERVED.match(model):
        raise MaterialPreviewError("Unsupported car archive identifier.")
    return _archive_path(game_root, f"media/cars/{model}.zip"), "/".join(parts[1:])


def _read_declaration(game_root):
    archive = _archive_path(game_root, "media/cars/_library/Materials.zip")
    _archive_guard(archive)
    with zipfile.ZipFile(archive) as bundle:
        matches = [entry for entry in bundle.infolist()
                   if entry.filename.replace("\\", "/").lower() == _DECLARATION_MEMBER]
        if len(matches) != 1:
            raise MaterialPreviewError("Missing or ambiguous native declaration.")
        entry = matches[0]
        if (entry.flag_bits & 1 or not 1 <= entry.file_size <= _MAX_DECLARATION
                or entry.file_size > max(1, entry.compress_size) * 2048):
            raise MaterialPreviewError("Declaration exceeds supported bounds.")
        with bundle.open(entry) as stream:
            data = stream.read(_MAX_DECLARATION + 1)
        if len(data) != entry.file_size:
            raise MaterialPreviewError("Invalid native declaration size.")
    return hashlib.sha256(data).hexdigest()


def _public_metadata(staged):
    """Whitelist and type-check every browser-visible field, including cached data."""
    for key in ("cache_key", "source_sha256", "png_sha256"):
        if not isinstance(staged.get(key), str) or not re.fullmatch(r"[a-f0-9]{64}", staged[key]):
            raise MaterialPreviewError("Invalid staged texture identity.")
    if (staged.get("pipeline") != "pc-swatch-straight-v1" or staged.get("decoded_mode") != "RGBA"
            or staged.get("flip_y") is not False or staged.get("premultiplied_alpha") is not False
            or staged.get("color_space") not in ("srgb", "linear-srgb")
            or staged.get("domain") not in ("repeat", "clamp", "mirror")
            or not _integer(staged.get("width"), 1, 4096) or not _integer(staged.get("height"), 1, 4096)):
        raise MaterialPreviewError("Unqualified staged texture metadata.")
    alpha = staged.get("alpha_range")
    if (not isinstance(alpha, list) or len(alpha) != 2 or any(not _integer(value, 0, 255) for value in alpha)
            or alpha[0] > alpha[1]):
        raise MaterialPreviewError("Unverified staged texture alpha range.")
    metadata = {key: staged[key] for key in _PUBLIC_METADATA}
    metadata["alpha_range"] = list(alpha)
    return metadata


def prepare_material_preview(glb_path, *, game_root, prepared_root, max_assets=32):
    """Return a portable manifest; stage only qualified textures in prepared_root.

    Caller owns manifest persistence and routes. Source paths are native resource
    identities, never host filenames. png_path is relative to prepared_root.
    Invalid inputs raise MaterialPreviewError; unsupported assets are omissions.
    """
    if not _integer(max_assets, 1, 128):
        raise MaterialPreviewError("max_assets must be between 1 and 128.")
    try:
        glb = workspace_path(glb_path, lab_root=LAB_ROOT)
        game = Path(game_root).resolve(strict=True)
        prepared = workspace_path(prepared_root, lab_root=LAB_ROOT)
        cache = (prepared / "material-preview/textures").resolve()
        if (glb.suffix.lower() != ".glb" or not glb.is_file()
                or not game.is_dir() or game.is_relative_to(prepared) or prepared.is_relative_to(game)
                or not cache.is_relative_to(prepared) or cache == prepared
                or (prepared.exists() and not prepared.is_dir())):
            raise MaterialPreviewError("Preparation paths violate the isolated workspace boundary.")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise MaterialPreviewError("Invalid or redirected preparation paths.") from exc
    document, source = _read_glb(glb)
    manifest = {"schema": "kfps-native-texture-preview-v1", "profile": PROFILE,
                "game_equivalent": False, "source": source, "status": "omitted",
                "declarations": [], "assets": [], "bindings": [], "omissions": [],
                "summary": {"total_meshes": len(document["meshes"]), "staged_meshes": 0,
                            "omitted_meshes": 0, "ignored_meshes": 0, "distinct_assets": 0}}
    declaration = None
    store = None
    by_source = {}
    io_errors = (MaterialPreviewError, MaterialAssetError, OSError, zipfile.BadZipFile,
                 RuntimeError, NotImplementedError, zlib.error, EOFError)
    for index, mesh in enumerate(document["meshes"]):
        texture, reason = _candidate(document, mesh)
        if reason in ("no-native-material", "unsupported-material-template"):
            manifest["summary"]["ignored_meshes"] += 1
            continue
        if reason is None and declaration is None:
            declaration = {"resource_path": _TEMPLATE, "sha256": None, "status": "omitted"}
            try:
                declaration["sha256"] = _read_declaration(game)
                declaration["status"] = "verified" if declaration["sha256"] == DECLARATION_SHA256 else "mismatch"
            except io_errors:
                declaration["reason"] = "declaration-unavailable-or-unsafe"
            manifest["declarations"].append(declaration)
        if reason is None and declaration["status"] != "verified":
            reason = "unverified-material-declaration"
        if reason is None:
            if texture not in by_source:
                if len(by_source) >= max_assets:
                    reason = "asset-limit-reached"
                else:
                    by_source[texture] = None
                    try:
                        archive, member = _texture_location(game, texture)
                        if store is None:
                            store = MaterialAssetStore(cache, allowed_roots=[game], max_entries=max_assets,
                                                       max_bytes=128 * 1024**2)
                        staged = store.stage(archive, member)
                        metadata = _public_metadata(staged)
                        image = Path(staged["image_path"]).resolve(strict=True)
                        if (not image.is_relative_to(cache) or image.name != "image.png"
                                or image.parent.name != staged["cache_key"]):
                            raise MaterialPreviewError("Unexpected staged image path.")
                        asset = {"source_path": texture, "cache_key": staged["cache_key"],
                                 "png_path": image.relative_to(prepared).as_posix(), "metadata": metadata}
                        by_source[texture] = asset
                        manifest["assets"].append(asset)
                    except io_errors:
                        reason = "texture-unavailable-unsafe-or-unsupported"
            if reason is None:
                asset = by_source[texture]
                if asset is None:
                    reason = "texture-unavailable-unsafe-or-unsupported"
                else:
                    manifest["bindings"].append({"mesh_index": index, "source_path": texture,
                                                 "cache_key": asset["cache_key"], "declaration_resource": _TEMPLATE})
                    manifest["summary"]["staged_meshes"] += 1
        if reason is not None:
            manifest["omissions"].append({"mesh_index": index, "reason": reason})
            manifest["summary"]["omitted_meshes"] += 1
    manifest["summary"]["distinct_assets"] = len({asset["cache_key"] for asset in manifest["assets"]})
    if manifest["assets"]:
        manifest["status"] = "partial" if manifest["omissions"] else "ready"
    return manifest
