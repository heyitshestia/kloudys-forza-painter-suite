#!/usr/bin/env python3
"""Portable local FH6 modelbin-to-GLB conversion for the livery inspector."""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import psutil

from .vehicle_assets import VehicleAsset, inspection_carbin_entry, inspection_model_entries


class PortableMeshConverterError(RuntimeError):
    pass


class ChassisConversionCancelled(PortableMeshConverterError):
    pass


MAX_LOCAL_CHASSIS_BYTES = 256 * 1024 * 1024
MAX_CONVERTER_RESIDENT_BYTES = 2 * 1024 * 1024 * 1024
GLB_JSON_CHUNK = 0x4E4F534A
GLB_BINARY_CHUNK = 0x004E4942
ROLE_NAMES = {"paint", "glass", "hidden", "dark", "trim"}
ACCESSOR_COMPONENT_BYTES = {5121: 1, 5123: 2, 5125: 4, 5126: 4}
ACCESSOR_COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def bundled_converter_path() -> Path:
    return Path(__file__).resolve().parent / "chassis-converter" / "bin" / "win-x64" / "Kfps.ChassisConverter.exe"


def _glb_payloads(path: Path) -> tuple[dict, bytes]:
    if not path.is_file() or path.stat().st_size > MAX_LOCAL_CHASSIS_BYTES:
        raise PortableMeshConverterError("The converted chassis GLB has an unsupported size.")
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise PortableMeshConverterError("The local chassis converter did not create a valid GLB file.")
    if struct.unpack_from("<I", data, 4)[0] != 2:
        raise PortableMeshConverterError("The converted chassis is not a GLB 2.0 file.")
    declared_length = struct.unpack_from("<I", data, 8)[0]
    if declared_length != len(data):
        raise PortableMeshConverterError("The converted chassis GLB has an invalid length declaration.")
    cursor = 12
    document: dict | None = None
    binary: bytes | None = None
    while cursor + 8 <= len(data):
        length, chunk_type = struct.unpack_from("<II", data, cursor)
        cursor += 8
        if length % 4 or cursor + length > len(data):
            raise PortableMeshConverterError("The converted chassis GLB has an invalid chunk boundary.")
        payload = data[cursor : cursor + length]
        cursor += length
        if chunk_type == GLB_JSON_CHUNK:
            if document is not None:
                raise PortableMeshConverterError("The converted chassis GLB has duplicate JSON chunks.")
            try:
                parsed = json.loads(
                    payload.rstrip(b"\x00 \t\r\n"),
                    parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
                )
            except (UnicodeDecodeError, ValueError) as exc:
                raise PortableMeshConverterError("The converted chassis GLB document is invalid.") from exc
            if not isinstance(parsed, dict):
                raise PortableMeshConverterError("The converted chassis GLB document is invalid.")
            document = parsed
        elif chunk_type == GLB_BINARY_CHUNK:
            if binary is not None:
                raise PortableMeshConverterError("The converted chassis GLB has duplicate binary chunks.")
            binary = payload
    if cursor != len(data) or document is None or binary is None:
        raise PortableMeshConverterError("The converted chassis GLB is incomplete.")
    return document, binary


def _glb_document(path: Path) -> dict:
    return _glb_payloads(path)[0]


def _document_array(document: dict, key: str) -> list:
    value = document.get(key)
    if not isinstance(value, list):
        raise PortableMeshConverterError(f"The converted chassis has an invalid GLB {key} array.")
    return value


def _array_index(value: object, rows: list, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value >= len(rows):
        raise PortableMeshConverterError(f"The converted chassis has an invalid GLB {label} index.")
    return value


def _validate_accessor(document: dict, binary: bytes, index: object) -> dict:
    accessors = _document_array(document, "accessors")
    views = _document_array(document, "bufferViews")
    try:
        accessor_index = _array_index(index, accessors, "accessor")
        accessor = accessors[accessor_index]
        if not isinstance(accessor, dict):
            raise TypeError("accessor is not an object")
        view_index = _array_index(accessor["bufferView"], views, "bufferView")
        view = views[view_index]
        if not isinstance(view, dict):
            raise TypeError("bufferView is not an object")
        component_size = ACCESSOR_COMPONENT_BYTES[int(accessor["componentType"])]
        component_count = ACCESSOR_COMPONENTS[str(accessor["type"])]
        count = int(accessor["count"])
        view_offset = int(view.get("byteOffset") or 0)
        view_length = int(view["byteLength"])
        accessor_offset = int(accessor.get("byteOffset") or 0)
        stride = int(view.get("byteStride") or (component_size * component_count))
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise PortableMeshConverterError("The converted chassis has an invalid GLB accessor.") from exc
    required = accessor_offset + ((count - 1) * stride if count else 0) + component_size * component_count
    if (
        int(view.get("buffer") or 0) != 0
        or count <= 0
        or view_offset < 0
        or view_length <= 0
        or accessor_offset < 0
        or stride < component_size * component_count
        or required > view_length
        or view_offset + view_length > len(binary)
    ):
        raise PortableMeshConverterError("The converted chassis GLB accessor is outside its binary buffer.")
    for key in ("min", "max"):
        values = accessor.get(key)
        if values is not None and (
            not isinstance(values, list)
            or len(values) != component_count
            or any(not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in values)
        ):
            raise PortableMeshConverterError("The converted chassis GLB accessor bounds are invalid.")
    return accessor


def _actual_index_max(document: dict, binary: bytes, accessor_index: object) -> int:
    accessors = _document_array(document, "accessors")
    views = _document_array(document, "bufferViews")
    index = _array_index(accessor_index, accessors, "accessor")
    accessor = accessors[index]
    view = views[_array_index(accessor["bufferView"], views, "bufferView")]
    component_type = int(accessor["componentType"])
    count = int(accessor["count"])
    component_size = ACCESSOR_COMPONENT_BYTES[component_type]
    stride = int(view.get("byteStride") or component_size)
    start = int(view.get("byteOffset") or 0) + int(accessor.get("byteOffset") or 0)
    format_code = "H" if component_type == 5123 else "I"
    if stride == component_size:
        end = start + count * component_size
        return max(value[0] for value in struct.iter_unpack(f"<{format_code}", binary[start:end]))
    unpack = struct.Struct(f"<{format_code}").unpack_from
    return max(unpack(binary, start + offset * stride)[0] for offset in range(count))


def validate_local_chassis_glb(path: Path | str) -> dict[str, int]:
    glb_path = Path(path)
    document, binary = _glb_payloads(glb_path)
    if str((document.get("asset") or {}).get("version") or "") != "2.0":
        raise PortableMeshConverterError("The converted chassis GLB document is not version 2.0.")
    try:
        buffers = _document_array(document, "buffers")
        declared_binary_length = int(buffers[0]["byteLength"])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise PortableMeshConverterError("The converted chassis GLB binary declaration is invalid.") from exc
    if len(buffers) != 1 or not isinstance(buffers[0], dict) or not 0 <= declared_binary_length <= len(binary):
        raise PortableMeshConverterError("The converted chassis GLB binary declaration is invalid.")
    nodes = _document_array(document, "nodes")
    meshes = _document_array(document, "meshes")
    scenes = _document_array(document, "scenes")
    part_options: list[dict] = []
    option_keys: set[tuple[str, int]] = set()
    if scenes:
        scene = scenes[_array_index(document.get("scene", 0), scenes, "scene")]
        if not isinstance(scene, dict):
            raise PortableMeshConverterError("The converted chassis has an invalid GLB scene record.")
        raw_options = (scene.get("extras") or {}).get("kfps_part_options") or []
        if not isinstance(raw_options, list) or any(not isinstance(item, dict) for item in raw_options):
            raise PortableMeshConverterError("The converted chassis has invalid part-option metadata.")
        for option in raw_options:
            try:
                part_name = str(option["part_type"]).strip()
                part_type = int(option["part_type_value"])
                option_id = int(option["id"])
                level = int(option["level"])
            except (KeyError, TypeError, ValueError) as exc:
                raise PortableMeshConverterError("The converted chassis has invalid part-option metadata.") from exc
            key = (part_name, option_id)
            if not part_name or part_type < 0 or level < 0 or key in option_keys:
                raise PortableMeshConverterError("The converted chassis has invalid part-option metadata.")
            option_keys.add(key)
            part_options.append(option)
    roles: dict[int, str] = {}
    allowed_sides: dict[int, object] = {}
    projection_sides: dict[int, object] = {}
    for node in nodes:
        if not isinstance(node, dict) or "mesh" not in node:
            continue
        extras = node.get("extras") or {}
        role = str(extras.get("kfps_role") or "")
        mesh_index = _array_index(node["mesh"], meshes, "mesh")
        roles[mesh_index] = role
        if "kfps_allowed_sides" in extras:
            allowed_sides[mesh_index] = extras["kfps_allowed_sides"]
        if "kfps_projection_sides" in extras:
            projection_sides[mesh_index] = extras["kfps_projection_sides"]
    paint = 0
    glass = 0
    direct_uv3 = 0
    projected = 0
    triangles = 0
    for index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            raise PortableMeshConverterError("The converted chassis has an invalid mesh record.")
        extras = mesh.get("extras") or {}
        role = str(extras.get("kfps_role") or roles.get(index) or "")
        if role not in ROLE_NAMES:
            raise PortableMeshConverterError("The converted chassis has an invalid material role.")
        raw_allowed = extras.get("kfps_allowed_sides", allowed_sides.get(index))
        raw_projection = extras.get("kfps_projection_sides", projection_sides.get(index))
        raw_option_ids = extras.get("kfps_part_option_ids") or []
        part_type = str(extras.get("kfps_part_type") or "").strip()
        if not isinstance(raw_option_ids, list) or any(
            isinstance(value, bool) or not isinstance(value, int) for value in raw_option_ids
        ):
            raise PortableMeshConverterError("The converted chassis has invalid mesh part-option metadata.")
        if raw_option_ids and (
            not part_type or any((part_type, option_id) not in option_keys for option_id in raw_option_ids)
        ):
            raise PortableMeshConverterError("The converted chassis references an unknown car-part option.")
        declared_allowed: int | None = None
        if raw_allowed is not None:
            if isinstance(raw_allowed, bool) or not isinstance(raw_allowed, (int, float)):
                raise PortableMeshConverterError("The converted chassis has an invalid livery-side declaration.")
            if isinstance(raw_allowed, float) and (not math.isfinite(raw_allowed) or not raw_allowed.is_integer()):
                raise PortableMeshConverterError("The converted chassis has an invalid livery-side declaration.")
            declared_allowed = int(raw_allowed)
            if declared_allowed < 0 or declared_allowed > 0x7FF:
                raise PortableMeshConverterError("The converted chassis has an invalid livery-side declaration.")
        declared_projection: int | None = None
        if raw_projection is not None:
            if isinstance(raw_projection, bool) or not isinstance(raw_projection, (int, float)):
                raise PortableMeshConverterError("The converted chassis has an invalid projection-side declaration.")
            if isinstance(raw_projection, float) and (
                not math.isfinite(raw_projection) or not raw_projection.is_integer()
            ):
                raise PortableMeshConverterError("The converted chassis has an invalid projection-side declaration.")
            declared_projection = int(raw_projection)
            if declared_projection < 0 or declared_projection > 0x7FF:
                raise PortableMeshConverterError("The converted chassis has an invalid projection-side declaration.")
        primitives = mesh.get("primitives") or []
        if not primitives:
            raise PortableMeshConverterError("The converted chassis contains a mesh with no geometry.")
        has_uv3 = False
        for primitive in primitives:
            if not isinstance(primitive, dict) or int(primitive.get("mode", 4)) != 4:
                raise PortableMeshConverterError("The converted chassis contains unsupported mesh geometry.")
            attributes = primitive.get("attributes") or {}
            if "POSITION" not in attributes or "NORMAL" not in attributes or primitive.get("indices") is None:
                raise PortableMeshConverterError("The converted chassis contains a mesh with no indexed geometry.")
            position = _validate_accessor(document, binary, attributes["POSITION"])
            normal = _validate_accessor(document, binary, attributes["NORMAL"])
            indices = _validate_accessor(document, binary, primitive["indices"])
            if (
                position.get("type") != "VEC3"
                or int(position.get("componentType") or 0) != 5126
                or normal.get("type") != "VEC3"
                or int(normal.get("componentType") or 0) != 5126
                or int(normal.get("count") or 0) != int(position.get("count") or 0)
                or indices.get("type") != "SCALAR"
                or int(indices.get("componentType") or 0) not in {5123, 5125}
                or int(indices.get("count") or 0) % 3
            ):
                raise PortableMeshConverterError("The converted chassis geometry contract is invalid.")
            declared_maximum = indices.get("max")
            index_max = declared_maximum[0] if isinstance(declared_maximum, list) and declared_maximum else -1
            actual_max = _actual_index_max(document, binary, primitive["indices"])
            if (
                not isinstance(index_max, (int, float))
                or isinstance(index_max, bool)
                or int(index_max) != actual_max
                or actual_max >= int(position["count"])
            ):
                raise PortableMeshConverterError("The converted chassis contains an out-of-range index.")
            triangles += int(indices["count"]) // 3
            if "TEXCOORD_3" in attributes:
                uv3 = _validate_accessor(document, binary, attributes["TEXCOORD_3"])
                if (
                    uv3.get("type") != "VEC2"
                    or int(uv3.get("componentType") or 0) != 5126
                    or int(uv3.get("count") or 0) != int(position.get("count") or 0)
                ):
                    raise PortableMeshConverterError("The converted chassis livery UV contract is invalid.")
                has_uv3 = True
        valid_mask = 0x3F if role == "paint" else 0x7C0 if role == "glass" else 0
        if declared_allowed is not None:
            if declared_allowed & ~valid_mask or (
                role in {"paint", "glass"} and declared_allowed == 0
            ):
                raise PortableMeshConverterError("The converted chassis has an invalid livery-side declaration.")
        if declared_projection is not None and declared_projection & ~valid_mask:
            raise PortableMeshConverterError("The converted chassis has an invalid projection-side declaration.")
        if role in {"paint", "glass"} and not has_uv3 and not declared_projection:
            raise PortableMeshConverterError(
                "The converted chassis has no exact UV3 or safe world-projection path."
            )
        if role == "paint":
            paint += 1
            direct_uv3 += int(has_uv3)
            projected += int(not has_uv3)
        elif role == "glass":
            glass += 1
            direct_uv3 += int(has_uv3)
            projected += int(not has_uv3)
    if not meshes or paint == 0:
        raise PortableMeshConverterError(
            "The converted chassis did not preserve livery-bearing paint geometry."
        )
    return {
        "mesh_count": len(meshes),
        "paint_meshes": paint,
        "glass_meshes": glass,
        "triangle_count": triangles,
        "direct_uv3_meshes": direct_uv3,
        "projected_livery_meshes": projected,
        "part_option_count": len(part_options),
    }


def _stop_process(process: subprocess.Popen) -> None:
    descendants: list[psutil.Process] = []
    try:
        descendants = psutil.Process(process.pid).children(recursive=True)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        pass
    for child in reversed(descendants):
        try:
            child.terminate()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    if process.poll() is None:
        process.terminate()
    _, alive = psutil.wait_procs(descendants, timeout=2.0)
    for child in alive:
        try:
            child.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            pass
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()


def _process_tree_resident_bytes(process_id: int) -> int:
    try:
        root = psutil.Process(process_id)
        processes = [root, *root.children(recursive=True)]
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return 0
    total = 0
    for process in processes:
        try:
            total += int(process.memory_info().rss)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return total


def _remove_converter_temporary_files(output_path: Path, process_id: int) -> None:
    prefix = f"{output_path.name}.{process_id}.tmp"
    for candidate in output_path.parent.glob(prefix + "*"):
        try:
            candidate.unlink()
        except OSError:
            pass


def convert_vehicle_model_to_glb(
    asset: VehicleAsset,
    output: Path | str,
    *,
    converter_path: Path | str | None = None,
    timeout_seconds: float = 300.0,
    cancel_event: threading.Event | None = None,
    max_process_bytes: int = MAX_CONVERTER_RESIDENT_BYTES,
    diagnostics: dict[str, int] | None = None,
) -> Path:
    converter = Path(converter_path) if converter_path else bundled_converter_path()
    if not converter.is_file():
        raise PortableMeshConverterError(
            "The bundled KFPS chassis converter is missing. Repair or update the KFPS installation."
        )
    if cancel_event and cancel_event.is_set():
        raise ChassisConversionCancelled("Local chassis preparation was superseded.")
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    entries = inspection_model_entries(asset)
    carbin_entry = inspection_carbin_entry(asset)

    with tempfile.TemporaryDirectory(prefix="kfps-chassis-request-") as temporary:
        request_path = Path(temporary) / "request.json"
        request_path.write_text(
            json.dumps(
                {
                    "archive": str(Path(asset.archive_path).resolve()),
                    "output": str(output_path),
                    "carbin_entry": carbin_entry,
                    "entries": entries,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        process = subprocess.Popen(
            [str(converter), "--request", str(request_path)],
            cwd=converter.parent,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        deadline = time.monotonic() + timeout_seconds
        peak_resident_bytes = 0
        try:
            while process.poll() is None:
                if cancel_event and cancel_event.is_set():
                    _stop_process(process)
                    raise ChassisConversionCancelled("Local chassis preparation was superseded.")
                resident_bytes = _process_tree_resident_bytes(process.pid)
                peak_resident_bytes = max(peak_resident_bytes, resident_bytes)
                if max_process_bytes > 0 and resident_bytes > max_process_bytes:
                    _stop_process(process)
                    raise PortableMeshConverterError(
                        "This car's local chassis exceeded KFPS's safe conversion memory limit and was stopped."
                    )
                if time.monotonic() >= deadline:
                    _stop_process(process)
                    raise PortableMeshConverterError("Local chassis conversion timed out.")
                time.sleep(0.1)
            stdout, stderr = process.communicate()
        finally:
            if process.poll() is None:
                _stop_process(process)
            if diagnostics is not None:
                diagnostics["peak_resident_bytes"] = peak_resident_bytes
            if process.returncode:
                _remove_converter_temporary_files(output_path, process.pid)
        if process.returncode != 0:
            detail = (stderr or stdout or "unknown converter error").strip().splitlines()[-1]
            raise PortableMeshConverterError(f"Local chassis conversion failed: {detail}")
        try:
            report = json.loads(stdout)
        except (TypeError, ValueError) as exc:
            output_path.unlink(missing_ok=True)
            raise PortableMeshConverterError("The local chassis converter returned an invalid report.") from exc
        unresolved = int(report.get("unresolved_instance_count") or 0)
        if unresolved:
            output_path.unlink(missing_ok=True)
            raise PortableMeshConverterError(
                f"The local chassis converter could not resolve {unresolved} car model instance(s)."
            )
    validate_local_chassis_glb(output_path)
    return output_path
