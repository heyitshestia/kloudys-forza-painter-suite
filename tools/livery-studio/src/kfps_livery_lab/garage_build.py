"""Bounded, display-only owned body configuration shared by both hosts."""
from __future__ import annotations

import re
import hashlib
import json

BODY_PARTS = ("CarBody", "ChassisStiffness", "FrontBumper", "Hood",
              "RearBumper", "RearWing", "SideSkirts")


def has_fixed_stock_body(document):
    options = document['scenes'][document.get('scene', 0)].get('extras', {}).get('kfps_part_options', [])
    if any(row.get('part_type') == 'CarBody' for row in options):
        return False
    return any(mesh.get('primitives') and mesh.get('extras', {}).get('kfps_part_type') == 'CarBody'
               and mesh['extras'].get('kfps_stock_part') is True
               and mesh['extras'].get('kfps_part_option_ids') == [] for mesh in document.get('meshes', []))


def effective_options(options, names):
    """Retain source graphics; qualify fixed stock and nonvisual chassis IDs."""
    result = list(options)
    if not isinstance(names, dict) or not names.get('source'):
        return result
    fixed = names.get('fixed_stock_options', [])
    if names.get('same_build_verified') is True and isinstance(fixed, list) and len(fixed) <= len(BODY_PARTS):
        families = [row.get('part_type') for row in fixed if isinstance(row, dict)]
        present = {row.get('part_type') for row in options if isinstance(row, dict)}
        for row in fixed:
            if (not isinstance(row, dict) or row.get('part_type') not in BODY_PARTS
                    or row['part_type'] in present or families.count(row['part_type']) != 1
                    or type(row.get('id')) is not int or not 0 < row['id'] < 2**31
                    or type(row.get('body_option_id')) is not int or not 0 < row['body_option_id'] < 2**31
                    or type(row.get('body_parent_id')) is not int or not 0 < row['body_parent_id'] < 2**31
                    or row.get('source_kind') != 'database-fixed-stock' or row.get('fixed_stock') is not True
                    or row.get('stock') is not True or row.get('supported') is not True
                    or row.get('empty') is not True or type(row.get('declared_instance_count')) is not int
                    or row['declared_instance_count'] != 0):
                continue
            parent = -1 if row['part_type'] in ('CarBody', 'RearWing') else row['body_parent_id']
            if (row.get('car_body_id') != parent or row.get('parent_upgrade_id') != parent
                    or (row['part_type'] == 'CarBody' and row['id'] != row['body_option_id'])):
                continue
            result.append(dict(row))
    rows = names.get('non_visual_options', [])
    if not isinstance(rows, list) or len(rows) > 128:
        return result
    counts = {}
    for row in rows:
        if isinstance(row, dict) and type(row.get('id')) is int:
            counts[row['id']] = counts.get(row['id'], 0) + 1
    existing = {row.get('id') for row in options if isinstance(row, dict) and row.get('part_type') == 'ChassisStiffness'}
    for row in rows:
        if (not isinstance(row, dict) or row.get('part_type') != 'ChassisStiffness'
                or type(row.get('id')) is not int or not 0 < row['id'] < 2**31
                or row['id'] in existing or counts.get(row['id']) != 1
                or row.get('source_kind') != 'database-nonvisual' or row.get('requires_graphics') is not False
                or row.get('supported') is not True or row.get('empty') is not True
                or row.get('declared_instance_count') != 0 or type(row.get('declared_instance_count')) is not int
                or type(row.get('car_body_id')) is not int or not 0 < row['car_body_id'] < 2**31
                or row.get('parent_upgrade_id') != row['car_body_id']):
            continue
        result.append(dict(row))
    return result


def validate_build(value):
    if (not isinstance(value, dict) or set(value) != {"version", "parts", "fingerprint"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["fingerprint"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", value["fingerprint"])
            or not isinstance(value["parts"], dict) or set(value["parts"]) != set(BODY_PARTS)):
        raise ValueError("The Garage body configuration is invalid. Refresh Garage and retry.")
    for part, ident in value["parts"].items():
        if ident is not None and (type(ident) is not int or not -1 <= ident <= 2**31 - 1):
            raise ValueError(f"Invalid Garage part ID: {part}.")
    canonical = json.dumps({'version': 1, 'parts': value['parts']}, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(canonical).hexdigest() != value['fingerprint']:
        raise ValueError('The Garage body snapshot has changed. Refresh Garage and try again.')
    return {"version": 1, "parts": dict(value["parts"]), "fingerprint": value["fingerprint"]}


def resolve_build(value, options, fitment=None):
    """Resolve only exact declared options. Never substitute a stock component."""
    build = validate_build(value)
    if not isinstance(options, list) or len(options) > 4096:
        raise ValueError("The car has no valid body option catalogue.")
    selection, chosen = {}, []
    for part in BODY_PARTS:
        rows = [row for row in options if isinstance(row, dict) and row.get("part_type") == part]
        ident = build["parts"][part]
        if not rows:
            if ident is None or ident <= 0:
                continue
            raise ValueError(f"The car model does not declare Garage component {part} (ID {ident}).")
        if ident is None:
            raise ValueError(f"Garage is missing {part}. Refresh Garage before opening this build.")
        matches = [row for row in rows if type(row.get("id")) is int and row["id"] == ident]
        if (len(matches) != 1 or matches[0].get("supported", matches[0].get("available")) is not True):
            raise ValueError(f"Unavailable Garage component: {part} (ID {ident}). No stock substitute was applied.")
        selection[part] = ident
        chosen.append(matches[0])
    parents = {}
    if isinstance(fitment, dict) and fitment.get("source"):
        for row in fitment.get("parent_map", []):
            parent, body = row.get("parent_upgrade_id"), row.get("body_option_id")
            if parent in parents and parents[parent] != body:
                raise ValueError("Ambiguous body compatibility catalogue.")
            parents[parent] = body
    for row in chosen:
        required = parents.get(row.get("car_body_id"))
        if row["part_type"] != "CarBody" and required is not None and required != selection.get("CarBody"):
            raise ValueError(f"Garage component {row['part_type']} is incompatible with the selected body.")
    return selection


def resolve_prepared_build(value, prepared, assets):
    """Validate the target body before a prepared car replaces a live document."""
    from tools.livery.portable_mesh_converter import _glb_payloads

    document, _ = _glb_payloads(assets["api/local-mesh"][0])
    options = document["scenes"][document.get("scene", 0)]["extras"]["kfps_part_options"]
    fidelity = prepared["manifest"]["inspection_runtime"].get("fidelity", {})
    return resolve_build(value, effective_options(options, fidelity.get("part_names")),
                         fidelity.get("body_compatibility"))
