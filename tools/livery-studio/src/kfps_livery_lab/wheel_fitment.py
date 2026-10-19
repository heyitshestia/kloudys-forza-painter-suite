"""Nominal wheel dimensions and source-authored placeholder anchors.

Reference catalogues are explicit local research inputs, never bundled game data
or proof of installed-build/runtime fitment. No wheelbase sizing is used here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

from .part_fitment import validated_reference_bodies

CATALOG_FORMAT = "kfps-stock-fitment-reference-v1"
MAX_CATALOG_BYTES = 8 * 1024 * 1024
CORNERS = {"spindlelf": "front_left", "spindlerf": "front_right",
           "spindlelr": "rear_left", "spindlerr": "rear_right"}


def _number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid nominal wheel dimension.")
    return float(value)


def nominal_dimensions(size):
    if not isinstance(size, dict):
        raise ValueError("Wheel size must specify width, aspect and rim diameter.")
    width = _number(size.get("width_mm"), 50, 800) / 1000
    aspect = _number(size.get("aspect_percent"), 10, 150) / 100
    rim = _number(size.get("rim_diameter_in"), 5, 40) * 0.0254
    return {"tire_radius": rim / 2 + width * aspect,
            "tire_width": width, "rim_radius": rim / 2,
            "nominal_size": {key: size[key] for key in ("width_mm", "aspect_percent", "rim_diameter_in")}}


def _digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


def _reference_versions(catalog, row):
    versions = row.get("source_versions")
    if (not isinstance(versions, list) or not 1 <= len(versions) <= 8
            or any(type(v) is not int or not -(2**31) <= v < 2**31 for v in versions)
            or len(set(versions)) != len(versions)):
        raise ValueError("Invalid wheel reference version evidence.")
    provenance = catalog.get("provenance")
    references = provenance.get("references") if isinstance(provenance, dict) else None
    checks = row.get("reference_checks")
    if (not isinstance(references, list) or len(references) != len(versions)
            or not isinstance(checks, list) or len(checks) != len(versions)):
        raise ValueError("Wheel reference provenance is incomplete.")
    reference_versions, check_versions, selected_hashes = [], [], set()
    for reference in references:
        if (not isinstance(reference, dict) or type(reference.get("database_version")) is not int
                or not _digest(reference.get("sqlite_sha256"))):
            raise ValueError("Invalid wheel reference database provenance.")
        reference_versions.append(reference["database_version"])
    for check in checks:
        if (not isinstance(check, dict) or type(check.get("database_version")) is not int
                or check.get("available") is not True or not _digest(check.get("selected_rows_sha256"))):
            raise ValueError("Invalid wheel reference selected-row evidence.")
        check_versions.append(check["database_version"])
        selected_hashes.add(check["selected_rows_sha256"])
    if (set(reference_versions) != set(versions) or set(check_versions) != set(versions)
            or len(selected_hashes) != 1):
        raise ValueError("Wheel reference versions or selected rows disagree.")
    return list(versions)


def read_reference_record(root: Path, vehicle: dict, *, archive_sha256=None):
    """An explicit hash-pinned workspace pointer opts into local reference data."""
    pointer = root / "settings" / "wheel-fitment-reference.json"
    if not pointer.is_file():
        return None
    with pointer.open("rb") as handle:
        pointer_data = handle.read(8193)
    if len(pointer_data) > 8192:
        raise ValueError("Wheel reference configuration is too large.")
    config = json.loads(pointer_data.decode("utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Invalid wheel reference configuration.")
    relative = config.get("path")
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("Wheel reference must be a workspace-relative research catalogue.")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to((root / "runs").resolve()):
        raise ValueError("Wheel reference is outside the isolated research runs.")
    with path.open("rb") as handle:
        data = handle.read(MAX_CATALOG_BYTES + 1)
    digest = hashlib.sha256(data).hexdigest()
    if len(data) > MAX_CATALOG_BYTES or config.get("sha256") != digest:
        raise ValueError("Wheel reference size or fingerprint changed. Review its source before using it.")
    catalog = json.loads(data)
    if not isinstance(catalog, dict):
        raise ValueError("Invalid wheel reference catalogue.")
    rows = catalog.get("records")
    if catalog.get("format") != CATALOG_FORMAT or not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError("Unsupported wheel reference catalogue.")
    matches = [row for row in rows if isinstance(row, dict) and type(row.get("car_id")) is int
               and row["car_id"] == vehicle["car_id"]
               and isinstance(row.get("model_code"), str)
               and row["model_code"] == vehicle["model_code"]]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Ambiguous wheel reference for this car.")
    row = matches[0]
    if row.get("available") is False:
        return None
    if row.get("available") is not True:
        raise ValueError("Wheel reference availability must be explicit.")
    local_archive = row.get("local_archive", {})
    if not isinstance(local_archive, dict):
        raise ValueError("Invalid local archive identity evidence.")
    pinned_archive = local_archive.get("archive_sha256")
    if pinned_archive is not None and not _digest(pinned_archive):
        raise ValueError("Invalid local archive fingerprint.")
    if pinned_archive is not None and pinned_archive != archive_sha256:
        return None
    versions = _reference_versions(catalog, row)
    front = nominal_dimensions(row.get("front"))["nominal_size"]
    rear = nominal_dimensions(row.get("rear"))["nominal_size"]
    clean_bodies = validated_reference_bodies(row)
    return {"car_id": row["car_id"], "front": front, "rear": rear,
            "body_options": clean_bodies,
            "catalog_sha256": digest, "source_versions": list(versions),
            "same_build_verified": False}


def authored_wheel_anchors(document):
    """Use authored WheelStyle/spindle origins, not the wider wheel locators.

    Prefer the explicit authored instance transform. The legacy effective field
    remains accepted for compatible snapshots. Reflect X once; suspension is unknown.
    """
    anchors = {}
    for node in document.get("nodes", []):
        extras = node.get("extras", {})
        if extras.get("kfps_part_type") != "WheelStyle" or extras.get("kfps_stock_part") is not True:
            continue
        bone = extras.get("kfps_instance_bone_name")
        corner = CORNERS.get(bone.casefold()) if isinstance(bone, str) else None
        if not corner:
            continue
        matrix = extras.get("kfps_authored_instance_transform", extras.get("kfps_instance_transform"))
        if not isinstance(matrix, list) or len(matrix) != 16:
            return None
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in matrix):
            return None
        if any(abs(matrix[i]) > 1e-6 for i in (3, 7, 11)) or abs(matrix[15] - 1) > 1e-6:
            return None
        point = [-float(matrix[12]), float(matrix[13]), float(matrix[14])]
        if any(abs(v) > 10 for v in point):
            return None
        if corner in anchors and any(abs(a - b) > 1e-5 for a, b in zip(anchors[corner], point)):
            return None
        anchors[corner] = point
    if set(anchors) != set(CORNERS.values()):
        return None
    if len({tuple(point) for point in anchors.values()}) != 4:
        return None
    return anchors


def placeholder_assembly(assembly, document, record):
    result = copy.deepcopy(assembly or {})
    # Do not advertise the baseline wheelbase heuristic as an accurate size.
    for key in ("tire_radius", "tire_width", "rim_radius", "wheel_dimensions"):
        result.pop(key, None)
    evidence = {"format": "kfps-placeholder-fitment-v1", "status": "unavailable",
                "geometry": "simple-placeholder", "wheelbase_sizing_used": False,
                "same_build_verified": False, "runtime_fitment_verified": False,
                "size_basis": "nominal-unloaded-tire-size", "placement_basis": "reference-outer-track-with-authored-axle-height-and-length"}
    result["wheel_fitment"] = evidence
    if not record:
        evidence["reason"] = "No qualified nominal tire size is available. No guessed wheels are shown."
        return result
    dimensions = {axle: nominal_dimensions(record[axle]) for axle in ("front", "rear")}
    anchors = authored_wheel_anchors(document)
    if not anchors:
        evidence["reason"] = "Authored wheel anchors are missing or ambiguous. No guessed wheels are shown."
        return result
    # Authored spindle origins can be a wheel's outer plane (e.g. Supra), so they
    # are not universal tire centers. Constrain lateral extents to the explicit
    # stock body's outer track; keep source axle midpoint, height and length.
    stock = [body for body in validated_reference_bodies(record) if body["is_stock"]]
    if len(stock) != 1:
        evidence["reason"] = "A unique stock outer-track reference is unavailable. No guessed wheels are shown."
        return result
    body = stock[0].get("native_body", {})
    evidence["authored_anchors"] = copy.deepcopy(anchors)
    outer_tracks = {}
    for axle, field in (("front", "ModelFrontTrackOuter"), ("rear", "ModelRearTrackOuter")):
        try:
            track = _number(body.get(field), .5, 4)
        except ValueError:
            evidence["reason"] = "Stock outer-track dimensions are unavailable. No guessed wheels are shown."
            return result
        left, right = anchors[f"{axle}_left"], anchors[f"{axle}_right"]
        if left[0] <= right[0] or track <= dimensions[axle]["tire_width"]:
            evidence["reason"] = "Source wheel orientation or outer-track dimensions are inconsistent."
            return result
        midpoint = (left[0] + right[0]) / 2
        half_track = (track - dimensions[axle]["tire_width"]) / 2
        left[0], right[0] = midpoint + half_track, midpoint - half_track
        outer_tracks[axle] = track
    result["format"] = "kfps_fh6_local_vehicle_assembly_v1"
    result["wheel_centers"] = anchors
    result["wheel_dimensions"] = {corner: dimensions[corner.split("_")[0]] for corner in anchors}
    evidence.update(status="reference-sized", catalog_sha256=record["catalog_sha256"],
                    stock_outer_tracks=outer_tracks,
                    source_versions=record.get("source_versions", []),
                    reason="Reference stock sizes; installed-build and runtime suspension fitment are unverified.")
    return result
