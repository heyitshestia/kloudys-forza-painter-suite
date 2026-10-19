"""Explicit reference-database body joins, isolated from placement and game saves.

Input must be the car-specific record selected by the hash-pinned reference
loader. Public reference rows do not verify the installed build. The reusable
join validator preserves raw dimension fields, but the compatibility graph
never returns or applies them. An authored wheel origin is not a universal center.
"""

from __future__ import annotations

import copy

MAX_OPTIONS = 4096
MAX_ID = 2**31 - 1
BODY_FIELDS = ("Id", "ModelFrontTrackOuter", "ModelRearTrackOuter",
               "ModelFrontStockRideHeight", "ModelRearStockRideHeight")
UPGRADE_FIELDS = ("Id", "Ordinal", "CarBodyID", "IsStock")


def _identifier(value, label):
    if type(value) is not int or not 0 < value <= MAX_ID:
        raise ValueError(f"Invalid body compatibility {label}: expected a positive int32.")
    return value


def _body_ids(document):
    if not isinstance(document, dict):
        raise ValueError("Body compatibility requires a GLB document.")
    scenes = document.get("scenes")
    scene = document.get("scene", 0)
    if (not isinstance(scenes, list) or type(scene) is not int
            or not 0 <= scene < len(scenes) or not isinstance(scenes[scene], dict)):
        raise ValueError("Invalid body compatibility GLB scene.")
    extras = scenes[scene].get("extras")
    options = extras.get("kfps_part_options") if isinstance(extras, dict) else None
    if not isinstance(options, list) or len(options) > MAX_OPTIONS:
        raise ValueError("Invalid or oversized GLB part-option catalogue.")
    result = set()
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("Invalid GLB part-option row.")
        if option.get("part_type") != "CarBody":
            continue
        ident = _identifier(option.get("id"), "GLB CarBody ID")
        if ident in result:
            raise ValueError("Ambiguous duplicate GLB CarBody option.")
        result.add(ident)
    return result


def validated_reference_bodies(record):
    """Return detached whitelisted rows after validating the entire native join.

    None, absent body_options or an empty list return []. Every present row must
    have strict int32 IDs joined to record.car_id, unique option/parent IDs, and
    an exact Boolean is_stock agreeing with native integer IsStock (0 or 1).
    Any bad row raises ValueError before a result is returned; nothing is skipped.

    This does not require a GLB, verify source hashes, select a stock body, or
    interpret dimensions. Known raw track/ride-height fields are copied unchanged
    (None when absent). Consumers must validate needed numeric values/ranges and
    retain their reference-only provenance. No dimension is applied to geometry.
    """
    if record is None:
        return []
    if not isinstance(record, dict):
        raise ValueError("Body compatibility requires a reference record.")
    car_id = _identifier(record.get("car_id"), "reference car ID")
    rows = record.get("body_options", [])
    if not isinstance(rows, list) or len(rows) > MAX_OPTIONS:
        raise ValueError("Invalid or oversized body reference rows.")

    parent_ids, option_ids, result = set(), set(), []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid body reference row.")
        upgrade, body = row.get("native_upgrade"), row.get("native_body")
        if not isinstance(upgrade, dict) or not isinstance(body, dict):
            raise ValueError("Body reference requires explicit native upgrade and body rows.")
        option_id = _identifier(row.get("option_id"), "reference option ID")
        parent_id = _identifier(row.get("parent_id"), "reference parent ID")
        native_option = _identifier(upgrade.get("Id"), "native upgrade ID")
        ordinal = _identifier(upgrade.get("Ordinal"), "native upgrade Ordinal")
        native_parent = _identifier(upgrade.get("CarBodyID"), "native upgrade CarBodyID")
        native_body = _identifier(body.get("Id"), "native body ID")
        if (ordinal != car_id or native_option != option_id
                or native_parent != parent_id or native_body != parent_id):
            raise ValueError("Body reference native join disagrees with the selected car or row IDs.")
        if parent_id in parent_ids or option_id in option_ids:
            raise ValueError("Ambiguous duplicate body parent or option in reference rows.")
        stock, native_stock = row.get("is_stock"), upgrade.get("IsStock")
        if (type(stock) is not bool or type(native_stock) is not int
                or native_stock not in (0, 1) or stock != bool(native_stock)):
            raise ValueError("Body reference stock flags are malformed or disagree.")
        parent_ids.add(parent_id)
        option_ids.add(option_id)
        result.append({"option_id": option_id, "parent_id": parent_id, "is_stock": stock,
                       "native_upgrade": {key: upgrade[key] for key in UPGRADE_FIELDS},
                       "native_body": {key: copy.deepcopy(body.get(key)) for key in BODY_FIELDS}})
    return sorted(result, key=lambda row: row["parent_id"])


def reference_body_compatibility(glb_document, reference_record):
    """Return a reference-only parent map, or None without an optional record.

    Missing body rows or no matching GLB bodies yield an empty parent_map.
    Malformed or ambiguous joins raise ValueError, including rows later excluded
    by GLB membership. Only native row joins establish relations; stock flags,
    numeric suffixes, dimensions and precomputed maps are never used to map IDs.

    The existing client must revalidate saved manual combinations once a known
    mapping is supplied; previously accepted incompatible combinations may then
    be rejected. This helper does not rewrite projects or ordinary KFPS files.
    """
    if reference_record is None:
        return None
    rows = validated_reference_bodies(reference_record)
    car_id = reference_record["car_id"]
    digest = reference_record.get("catalog_sha256")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in digest)):
        raise ValueError("Body compatibility requires the reference catalogue SHA256.")

    present = _body_ids(glb_document)
    return {
        "source": (f"Reference catalogue SHA256 {digest.lower()}; car {car_id}; "
                   "List_UpgradeCarBody.CarBodyID -> Data_CarBody.Id; "
                   "List_UpgradeCarBody.Id -> declared GLB CarBody option"),
        "reference_only": True,
        "same_build_verified": False,
        "parent_map": [{"parent_upgrade_id": row["parent_id"], "body_option_id": row["option_id"]}
                       for row in rows if row["option_id"] in present],
    }
