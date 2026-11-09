"""Read-only, declaration-bound FH6 part labels and body-parent relationships.

Reads the installed 0x0800 STR layout and localization token. Game strings
and databases remain local inputs, not bundled application content.

An on-demand local cache of installed media/stripped/gamedbRC.slt takes precedence.
Otherwise settings/part-names-reference.json explicitly opts into a local
SQLite reference: {"format":"kfps-part-names-reference-v1", "sqlite_path":
"...", "sha256":"...", "database_version":661353983, "language":"EN"}.
Relative SQLite paths are relative to the config file, never the process cwd.
reference_config may instead be a dict with an absolute sqlite_path.

Reference databases are NOT installed-build verification. PartsStringID is not a display-name
join; names use ManufacturerID and UpgradeTypes/Upgrades at the stored Level.
Missing level names remain partial, and IsStock does not imply Level == 0.

Chassis-only virtual empty options require Data_UpgradePart.Id=41,
PartName=ChassisStiffness, CategoryName=CarBody, the exact list table, and
HasRequiresGraphics=1. Each missing model ID must have RequiresGraphics=0
and an unambiguous car/body join. No ID arithmetic or stock substitution is
used. Reference Fairlady level-2 IDs 344001/344101 meet these conditions;
their installed Manifest.xml omits them while declaring level-1 empty and
level-3 cage options. Exclusive meshes use exact model membership, not
upgrade-level proximity.

Only explicit calls perform I/O. The installed catalogue is cached separately;
there is no persistent process, polling, network access or game-file write.
Returned data contain no filesystem paths or timestamps and are JSON-safe.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
import zipfile

from .file_io import io_path
from .part_fitment import reference_body_compatibility
from .catalogue_cache import WARNING_CODES as CATALOGUE_WARNING_CODES, load_installed_catalogue

FORMAT = "kfps-part-names-v1"
REFERENCE_FORMAT = "kfps-part-names-reference-v1"
STUDIO_ROOT = Path(__file__).parents[2]
CATALOGUE_CACHE_ROOT = STUDIO_ROOT.parents[1] / 'runtime/garage/catalogue'
CATALOGUE_READER_CONFIG = None
MAX_OPTIONS = 4096
MAX_DATABASE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_STRING_BYTES = 1024 * 1024
MAX_ROWS = 16384
SQLITE_MAGIC = b"SQLite format 3\0"
PART_TABLES = {
    "CarBody": "List_UpgradeCarBody",
    "ChassisStiffness": "List_UpgradeCarBodyChassisStiffness",
    "FrontBumper": "List_UpgradeCarBodyFrontBumper",
    "Hood": "List_UpgradeCarBodyHood",
    "RearBumper": "List_UpgradeCarBodyRearBumper",
    "RearWing": "List_UpgradeRearWing",
    "SideSkirts": "List_UpgradeCarBodySideSkirt",
}
STRING_TABLES = ("List_PartManufacturer", "UpgradeTypes", "Upgrades")


class _InvalidData(ValueError):
    pass


def _cancel(event):
    if event is not None and event.is_set():
        raise InterruptedError('Part name lookup cancelled.')


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _read(path, limit):
    with io_path(path).open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise _InvalidData("source-size-invalid")
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if (len(data) > limit or len(data) != before.st_size
            or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
        raise _InvalidData("source-changed-during-read")
    return data


def _identifier(value):
    return type(value) is int and 0 < value < 2**31


def _integer(value):
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value):
        return int(value)
    return None


def _hash32(value):
    result = 0xffffffff
    for byte in value.encode("ascii"):
        result ^= byte
        result = ((result << 7) | (result >> 25)) & 0xffffffff
    return result


def _parse_strings(data, expected_name):
    """Return full 64-bit localization IDs, validating both STR sections."""
    if len(data) < 136 or len(data) > MAX_STRING_BYTES:
        raise _InvalidData("string-table-size-invalid")
    if struct.unpack_from("<H", data)[0] != 0x0800:
        raise _InvalidData("string-table-version-unsupported")
    name = data[2:128].split(b"\0", 1)[0].decode("ascii")
    count = struct.unpack_from("<h", data, 130)[0]
    if name != expected_name or not 1 <= count <= 2 or len(data) < 132 + count * 4:
        raise _InvalidData("string-table-header-invalid")
    offsets = struct.unpack_from("<" + "i" * count, data, 132)
    if list(offsets) != sorted(set(offsets)) or offsets[0] < 132 + count * 4:
        raise _InvalidData("string-table-offset-invalid")
    values = {}
    for section, offset in enumerate(offsets):
        end = offsets[section + 1] if section + 1 < count else len(data)
        if offset < 0 or offset + 12 > end or end > len(data):
            raise _InvalidData("string-table-offset-invalid")
        block_size, string_size, entries = struct.unpack_from("<iii", data, offset)
        start = offset + 12 + entries * 8
        if (block_size < 0 or block_size > end - offset or not 0 <= entries <= MAX_ROWS
                or string_size < 0 or start > end or string_size > end - start):
            raise _InvalidData("string-table-block-invalid")
        seen = set()
        for index in range(entries):
            key, relative = struct.unpack_from("<Ii", data, offset + 12 + index * 8)
            if key in seen or not 0 <= relative < string_size:
                raise _InvalidData("string-table-symbol-invalid")
            seen.add(key)
            stop = data.find(b"\0", start + relative, start + string_size)
            if stop < 0 or stop - start - relative > 16384:
                raise _InvalidData("string-table-text-invalid")
            text = data[start + relative:stop].decode("utf-8")
            if section == 0:
                values[(_hash32(name) << 32) | key] = text
    return values


def _localization(archive, warnings):
    result = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        members = bundle.infolist()
        if len(members) > 4096:
            raise _InvalidData("string-archive-too-many-members")
        for table in STRING_TABLES:
            matches = [item for item in members if item.filename == table + ".str"]
            if not matches:
                warnings.append("missing-string-table:" + table)
                continue
            if (len(matches) != 1 or matches[0].file_size > MAX_STRING_BYTES
                    or matches[0].flag_bits & 1):
                raise _InvalidData("string-archive-member-invalid")
            with bundle.open(matches[0]) as stream:
                data = stream.read(MAX_STRING_BYTES + 1)
            result.update(_parse_strings(data, table))
    return result


def _localized(token, strings):
    if not isinstance(token, str) or not token:
        return None
    if not token.startswith("_&"):
        return token if len(token) <= 16384 else None
    if not re.fullmatch(r"_&[0-9]{1,20}", token):
        return None
    number = int(token[2:])
    return (strings.get(number) or None) if number < 2**64 else None


def _reference_config(value, provenance):
    base = None
    if isinstance(value, dict):
        config = value
        raw = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    else:
        path = Path(value) if value is not None else STUDIO_ROOT / "settings/part-names-reference.json"
        if not io_path(path).exists():
            return {}, None
        raw = _read(path, 16384)
        base = path.absolute().parent
        config = json.loads(raw.decode("utf-8-sig"))
    provenance["reference_config_sha256"] = _digest(raw)
    if not isinstance(config, dict) or config.get("format") != REFERENCE_FORMAT:
        raise _InvalidData("reference-config-invalid")
    language = config.get("language", "EN")
    if not isinstance(language, str) or not re.fullmatch(r"[A-Z]{2,3}", language):
        raise _InvalidData("reference-language-invalid")
    path, digest = config.get("sqlite_path"), config.get("sha256")
    if (not isinstance(path, str) or not path or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", digest)):
        raise _InvalidData("reference-config-invalid")
    path = Path(path)
    if not path.is_absolute():
        if base is None:
            raise _InvalidData("reference-path-must-be-absolute")
        path = base / path
    version = config.get("database_version")
    if version is not None and (type(version) is not int or not -(2**31) <= version < 2**31):
        raise _InvalidData("reference-version-invalid")
    return config, path


def _rows(db, table, where="", values=()):
    schema = db.execute("SELECT type,sql FROM sqlite_schema WHERE name=?", (table,)).fetchall()
    if (len(schema) != 1 or schema[0][0] != "table" or not isinstance(schema[0][1], str)
            or schema[0][1].lstrip().upper().startswith("CREATE VIRTUAL")):
        raise _InvalidData("metadata-table-unavailable:" + table)
    # Table and clause spellings are module constants; all input values are bound.
    rows = db.execute('SELECT * FROM "' + table + '"' + where + " LIMIT ?",
                      (*values, MAX_ROWS + 1)).fetchall()
    if len(rows) > MAX_ROWS:
        raise _InvalidData("metadata-row-limit")
    return [{key.lower(): row[key] for key in row.keys()} for row in rows]


def _unique(rows, key):
    result = {}
    for row in rows:
        ident = row.get(key)
        if not _identifier(ident) or ident in result:
            raise _InvalidData("metadata-identity-ambiguous")
        result[ident] = row
    return result


def _body_rows(db, car_id):
    upgrades = _unique(_rows(db, "List_UpgradeCarBody", " WHERE Ordinal=?", (car_id,)), "id")
    parents = {}
    for upgrade in upgrades.values():
        parent = upgrade.get("carbodyid")
        if (not _identifier(parent) or parent in parents or upgrade.get("ordinal") != car_id
                or type(upgrade.get("isstock")) is not int or upgrade["isstock"] not in (0, 1)):
            raise _InvalidData("body-parent-ambiguous")
        body = _rows(db, "Data_CarBody", " WHERE Id=?", (parent,))
        if len(body) != 1:
            raise _InvalidData("body-parent-unavailable")
        parents[parent] = upgrade
    return upgrades, parents


def _binding(option, row, car_id, bodies, parents, declared_bodies, *, require_declared_body=False):
    family = option["part_type"]
    parent = option.get("parent_upgrade_id", option.get("car_body_id"))
    if ("parent_upgrade_id" in option and "car_body_id" in option
            and option["parent_upgrade_id"] != option["car_body_id"]):
        return "declaration-parent-conflict"
    if "level" in option and (type(option["level"]) is not int or option["level"] != row.get("level")):
        return "declaration-level-conflict"
    if "stock" in option and (type(option["stock"]) is not bool
            or type(row.get("isstock")) is not int or option["stock"] != bool(row["isstock"])):
        return "declaration-stock-conflict"
    if family in ("CarBody", "RearWing"):
        if row.get("ordinal") != car_id:
            return "car-mismatch"
        if family == "CarBody":
            root_parent = parent is None or (type(parent) is int and parent == -1)
            if not root_parent and (not _identifier(parent) or parent != row.get("carbodyid")):
                return "declaration-parent-conflict"
    else:
        if not _identifier(parent) or parent != row.get("carbodyid"):
            return "declaration-parent-conflict"
        body = parents.get(parent)
        if body is None or body["id"] not in bodies:
            return "body-parent-unavailable"
        # Names need the exact native car/body join; geometry also needs its GLB body.
        if require_declared_body and body["id"] not in declared_bodies:
            return "declared-body-unavailable"
        if ("parent_is_stock" in option and (type(option["parent_is_stock"]) is not bool
                or option["parent_is_stock"] != bool(body["isstock"]))):
            return "declaration-parent-stock-conflict"
    return None


def _non_visual_options(db, options, car_id, bodies, parents, declared_bodies, reference_only):
    """Qualify only absent chassis IDs; missing graphics flags never imply empty."""
    family = "ChassisStiffness"
    table = PART_TABLES[family]
    declared = {option["id"] for option in options if option["part_type"] == family}
    if not declared or not declared_bodies:
        return []
    capabilities = _rows(db, "Data_UpgradePart",
        " WHERE PartName=? OR Id=? OR TableName=?", (family, 41, table))
    if (len(capabilities) != 1 or capabilities[0].get("id") != 41
            or capabilities[0].get("partname") != family
            or capabilities[0].get("tablename") != table
            or capabilities[0].get("categoryname") != "CarBody"
            or type(capabilities[0].get("hasrequiresgraphics")) is not int
            or capabilities[0]["hasrequiresgraphics"] != 1):
        raise _InvalidData("non-visual-chassis-capability-unavailable")
    parent_ids = sorted(parent for parent, body in parents.items() if body["id"] in declared_bodies)
    rows = _rows(db, table, " WHERE CarBodyID IN (" + ",".join("?" for _ in parent_ids) + ")",
                 tuple(parent_ids))
    candidates = []
    for row in rows:
        if row.get("id") in declared:
            continue
        if type(row.get("requiresgraphics")) is not int or row["requiresgraphics"] != 0:
            continue
        ident, parent = row.get("id"), row.get("carbodyid")
        if (not _identifier(ident) or not _identifier(parent)
                or type(row.get("level")) is not int or not 0 <= row["level"] <= 255
                or type(row.get("isstock")) is not int or row["isstock"] not in (0, 1)
                or ("ordinal" in row and row["ordinal"] != car_id)):
            raise _InvalidData("non-visual-chassis-row-invalid")
        # Recheck globally: a duplicate ID in another body is still ambiguous.
        if len(_rows(db, table, " WHERE Id=?", (ident,))) != 1:
            raise _InvalidData("non-visual-chassis-identity-ambiguous")
        body = parents[parent]
        option = {"part_type": family, "part_type_value": 41, "id": ident,
                  "level": row["level"], "stock": bool(row["isstock"]), "baseline": False,
                  "car_body_id": parent, "parent_upgrade_id": parent,
                  "parent_is_stock": bool(body["isstock"]), "fitment_verified": False,
                  "supported": True, "empty": True, "declared_instance_count": 0,
                  "requires_graphics": False, "source_kind": "database-nonvisual",
                  "reference_only": reference_only, "issues": []}
        if _binding(option, row, car_id, bodies, parents, declared_bodies, require_declared_body=True):
            raise _InvalidData("non-visual-chassis-parent-conflict")
        candidates.append(option)
    if len(options) + len(candidates) > MAX_OPTIONS:
        raise _InvalidData("non-visual-chassis-option-limit")
    return sorted(candidates, key=lambda option: option["id"])


def _fixed_stock_options(db, options, car_id, bodies, fixed_body, current):
    # A non-upgradable model body has its stock geometry already built in.
    # Require one exact current body join; absence alone never proves stock.
    if (not fixed_body or not current or len(bodies) != 1
            or any(row['part_type'] == 'CarBody' for row in options)):
        return []
    body = next(iter(bodies.values()))
    if type(body.get('isstock')) is not int or body['isstock'] != 1:
        return []
    declared = {row['part_type'] for row in options}
    result = []
    for family, table in PART_TABLES.items():
        if family in declared:
            continue
        rows = ([body] if family == 'CarBody' else _rows(db, table,
            ' WHERE Ordinal=?' if family == 'RearWing' else ' WHERE CarBodyID=?',
            (car_id if family == 'RearWing' else body['carbodyid'],)))
        if len(rows) != 1:
            continue
        row = rows[0]
        if (not _identifier(row.get('id')) or type(row.get('isstock')) is not int or row['isstock'] != 1
                or type(row.get('level')) is not int or not 0 <= row['level'] <= 255
                or len(_rows(db, table, ' WHERE Id=?', (row['id'],))) != 1
                or ('ordinal' in row and row['ordinal'] != car_id)):
            continue
        parent = -1 if family in ('CarBody', 'RearWing') else body['carbodyid']
        result.append({'part_type': family, 'id': row['id'], 'level': row['level'],
            'stock': True, 'baseline': True, 'car_body_id': parent, 'parent_upgrade_id': parent,
            'parent_is_stock': True, 'supported': True, 'empty': True, 'declared_instance_count': 0,
            'source_kind': 'database-fixed-stock', 'fixed_stock': True,
            'body_option_id': body['id'], 'body_parent_id': body['carbodyid'], 'issues': []})
    return result


def _resolve(db, vehicle, options, strings, result, cancel_event=None, *, fixed_body=False):
    _cancel(cancel_event)
    car_id = vehicle["car_id"]
    cars = _rows(db, "Data_Car", " WHERE Id=?", (car_id,))
    if len(cars) != 1:
        raise _InvalidData("car-identity-mismatch")
    media_name, model_code = cars[0].get("medianame"), vehicle["model_code"]
    if (not _identifier(cars[0].get("id")) or cars[0]["id"] != car_id
            or any(not isinstance(code, str)
                   or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", code)
                   for code in (media_name, model_code))
            or media_name.lower() != model_code.lower()):
        raise _InvalidData("car-identity-mismatch")
    bodies, parents = _body_rows(db, car_id)
    fixed = _fixed_stock_options(db, options, car_id, bodies, fixed_body, result['same_build_verified'])
    result['fixed_stock_options'] = fixed
    options = options + fixed
    manufacturers = _unique(_rows(db, "List_PartManufacturer"), "id")
    types = _rows(db, "UpgradeTypes")
    products = _rows(db, "Upgrades")
    declared_bodies = set()
    for option in options:
        _cancel(cancel_event)
        if option["part_type"] == "CarBody" and not option.get("_name_issue"):
            row = bodies.get(option["id"])
            if row is not None and not _binding(option, row, car_id, bodies, parents, set()):
                declared_bodies.add(option["id"])
    try:
        virtual = _non_visual_options(db, options, car_id, bodies, parents, declared_bodies,
                                      result["reference_only"])
    except (_InvalidData, sqlite3.Error):
        # Non-visual qualification is optional even when ordinary labels work.
        virtual = []
        result["warnings"].append("non-visual-chassis-data-unavailable-or-conflicting")
    result["non_visual_options"] = virtual
    valid_bodies = []
    virtual_ids = {option["id"] for option in virtual}
    for option in sorted(options + virtual, key=lambda o: (o["part_type"], o["id"])):
        _cancel(cancel_event)
        family, ident = option["part_type"], option["id"]
        output = {"part_type": family, "id": ident, "manufacturer": None, "product": None,
                  "category": None, "status": "unresolved", "issues": []}
        result["names"].append(output)
        if family == "ChassisStiffness" and ident in virtual_ids:
            output.update(source_kind="database-nonvisual", requires_graphics=False,
                          reference_only=result["reference_only"])
        if option.get("_name_issue"):
            output["issues"].append(option["_name_issue"])
            continue
        if family not in PART_TABLES:
            output["issues"].append("unsupported-part-family")
            continue
        try:
            rows = _rows(db, PART_TABLES[family], " WHERE Id=?", (ident,))
        except _InvalidData as error:
            output["issues"].append(str(error))
            continue
        if len(rows) != 1:
            output["issues"].append("part-row-unavailable-or-ambiguous")
            continue
        row = rows[0]
        issue = _binding(option, row, car_id, bodies, parents, declared_bodies)
        if issue:
            output["issues"].append(issue)
            continue
        manufacturer_id = row.get("manufacturerid")
        if (type(row.get("level")) is not int or not 0 <= row["level"] <= 255
                or type(row.get("isstock")) is not int or row["isstock"] not in (0, 1)
                or type(manufacturer_id) is not int or not 0 <= manufacturer_id < 2**31):
            output["issues"].append("part-row-invalid")
            continue
        if family == "CarBody":
            valid_bodies.append(row)
        output.update(level=row["level"], is_stock=bool(row["isstock"]),
                      manufacturer_id=manufacturer_id, data_car_body_id=row.get("carbodyid"))
        manufacturer = manufacturers.get(manufacturer_id, {})
        output["manufacturer"] = _localized(manufacturer.get("partmanufacturer"), strings)
        candidates = [t for t in types if t.get("partname") == family and t.get("isexception") == 0]
        if len(candidates) == 1:
            category = candidates[0]
            output["category"] = _localized(category.get("name"), strings)
            matches = [p for p in products if _integer(p.get("typeid")) == category.get("id")
                       and p.get("level") == row["level"] and p.get("isexception") == 0]
            if len(matches) == 1:
                output["product"] = _localized(matches[0].get("name"), strings)
        for field in ("manufacturer", "product", "category"):
            if output[field] is None and not (field == "manufacturer" and manufacturer_id == 0):
                output["issues"].append(field + "-unavailable")
        if not output["issues"]:
            output["status"] = "resolved"
        elif any(output[field] for field in ("manufacturer", "product", "category")):
            output["status"] = "partial"
    record = {"car_id": car_id, "catalog_sha256": result["provenance"]["database_sha256"],
              "body_options": [{"option_id": row["id"], "parent_id": row["carbodyid"],
                  "is_stock": bool(row["isstock"]),
                  "native_upgrade": {"Id": row["id"], "Ordinal": car_id,
                                     "CarBodyID": row["carbodyid"], "IsStock": row["isstock"]},
                  "native_body": {"Id": row["carbodyid"]}} for row in valid_bodies]}
    document = {"scenes": [{"extras": {"kfps_part_options": [option for option in options
                if option["part_type"] == "CarBody" and option["id"] in declared_bodies]}}]}
    compatibility = reference_body_compatibility(document, record)
    compatibility.update(source=result["source"], reference_only=result["reference_only"],
                         same_build_verified=result['same_build_verified'])
    result["body_compatibility"] = compatibility


def _declarations(options, warnings):
    if not isinstance(options, list) or len(options) > MAX_OPTIONS:
        warnings.append("invalid-or-oversized-option-catalogue")
        return []
    unique = {}
    for option in options:
        if (not isinstance(option, dict) or not isinstance(option.get("part_type"), str)
                or not 0 < len(option["part_type"]) <= 128 or type(option.get("id")) is not int
                or not -(2**31) <= option["id"] < 2**31):
            if "invalid-option-declaration" not in warnings:
                warnings.append("invalid-option-declaration")
            continue
        key = (option["part_type"], option["id"])
        if key in unique:
            unique[key]["_name_issue"] = "duplicate-option-id"
        else:
            # Never annotate or repair the renderer's original catalogue.
            unique[key] = dict(option)
            unique[key].pop("_name_issue", None)
            if not _identifier(option["id"]):
                unique[key]["_name_issue"] = "invalid-option-id"
    return list(unique.values())


def load_part_names(game_root, vehicle, options, *, reference_config=None,
                    cache_root=None, reader_config=None, cancel_event=None, fixed_body=False):
    """Label GLB options plus explicitly qualified non-visual chassis options.

    vehicle requires exact car_id/model_code. options is the unmodified GLB
    kfps_part_options list, not a saved-ID map. Optional file/schema failures
    return empty names with warnings. Bad/duplicate declarations remain unnamed;
    optional naming must not turn converter diagnostics into a viewing failure.
    A missing manufacturer 0 is explicit no-brand data, not an invented OEM.
    body_compatibility has the part_fitment contract; no selection is performed.
    Fixed stock options require unconditional model body evidence, an exact sole
    stock body join and current installed metadata. No saved ID is inferred.
    non_visual_options contains detached GLB-shaped empty options, never ID
    aliases. Consumers must preserve their reference-only provenance and check
    for conflicting mesh memberships before merging into a scene catalogue.
    """
    result = {"format": FORMAT, "source": "Part names unavailable", "reference_only": True,
              "same_build_verified": False, "names": [], "body_compatibility": None,
              "non_visual_options": [], "fixed_stock_options": [], "provenance": {}, "warnings": []}
    _cancel(cancel_event)
    if (not isinstance(vehicle, dict) or not _identifier(vehicle.get("car_id"))
            or not isinstance(vehicle.get("model_code"), str) or not vehicle["model_code"]):
        result["warnings"].append("exact-car-identity-unavailable")
        return result
    options = _declarations(options, result["warnings"])
    if (not options and not fixed_body) or game_root is None:
        return result
    db = None
    try:
        config, language = {}, "EN"
        root = Path(game_root)
        media = root if root.name.lower() == "media" else root / "media"
        cached = load_installed_catalogue(root,
            cache_root=CATALOGUE_CACHE_ROOT if cache_root is None else cache_root,
            reader_config=CATALOGUE_READER_CONFIG if reader_config is None else reader_config,
            cancel_event=cancel_event)
        installed = isinstance(cached.get('database'), bytes)
        stale = installed and cached.get('provenance', {}).get('current') is not True
        names_only = stale or (not installed and io_path(media / 'stripped/gamedbRC.slt').exists())
        if installed:
            database = cached['database']
            result['provenance'].update({key: cached['provenance'][key] for key in
                ('source_sha256', 'database_sha256', 'database_version', 'current')
                if key in cached['provenance']})
            result['reference_only'] = stale
            result['same_build_verified'] = not stale
            if stale:
                result['warnings'].append('installed-catalogue-stale')
        else:
            if names_only:
                result['warnings'].append('installed-catalogue-unavailable')
                result['warnings'].extend(code for code in cached.get('warnings', [])
                                          if code in CATALOGUE_WARNING_CODES)
            config, reference_path = _reference_config(reference_config, result["provenance"])
            language = config.get("language", "EN")
            if reference_path is None:
                result['warnings'].append('installed-catalogue-unavailable')
                result['warnings'].extend(code for code in cached.get('warnings', [])
                                          if code in CATALOGUE_WARNING_CODES)
                _cancel(cancel_event)
                return result
            database = _read(reference_path, MAX_DATABASE_BYTES)
        database_sha256 = _digest(database)
        if not installed and database_sha256 != config["sha256"].lower():
            raise _InvalidData("reference-fingerprint-mismatch")
        if len(database) > MAX_DATABASE_BYTES or not database.startswith(SQLITE_MAGIC):
            raise _InvalidData("database-format-unsupported")
        result["provenance"]["database_sha256"] = database_sha256
        archive = _read(media / ("stripped/StringTables/" + language + ".zip"), MAX_ARCHIVE_BYTES)
        result["provenance"].update(language=language, strings_sha256=_digest(archive))
        strings = _localization(archive, result["warnings"])
        _cancel(cancel_event)
        if not strings:
            return result
        db = sqlite3.connect(":memory:")
        db.deserialize(database)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("PRAGMA query_only=ON")
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, MAX_STRING_BYTES)
        db.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
        ticks = 0

        def bounded_query():
            nonlocal ticks
            ticks += 1
            return ticks > 20000 or (cancel_event is not None and cancel_event.is_set())

        db.set_progress_handler(bounded_query, 1000)
        version = _rows(db, "VersionInfo")
        if len(version) != 1 or type(version[0].get("database_version")) is not int:
            raise _InvalidData("database-version-invalid")
        version = version[0]["database_version"]
        if not installed and config.get("database_version", version) != version:
            raise _InvalidData("reference-version-mismatch")
        result["provenance"]["database_version"] = version
        kind = ('Previous installed' if stale else 'Installed cached') if installed else 'Hash-pinned reference'
        result["source"] = f"{kind} database (version {version}) with {language} game strings"
        _resolve(db, vehicle, options, strings, result, cancel_event, fixed_body=fixed_body)
        if names_only:
            # Cache loss must not turn a failed installed source into geometry approval.
            result['non_visual_options'] = []
            result['fixed_stock_options'] = []
            result['body_compatibility'] = None
    except InterruptedError:
        raise
    except (OSError, ValueError, TypeError, sqlite3.Error, zipfile.BadZipFile,
            NotImplementedError, RuntimeError, struct.error, UnicodeError) as error:
        _cancel(cancel_event)
        result["names"] = []
        result["non_visual_options"] = []
        result['fixed_stock_options'] = []
        result["body_compatibility"] = None
        result["warnings"].append(str(error) if isinstance(error, _InvalidData)
                                  else "optional-part-name-data-unavailable-or-invalid")
    finally:
        if db is not None:
            db.close()
    _cancel(cancel_event)
    return result
