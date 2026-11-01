"""Owned-package artwork import. No save installation or browser filesystem API."""
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import zipfile

from .model import validate_shapes
from .save_codec import MAX_PAYLOAD, NAMES, unwrap_bounded

MAX_PACKAGE_BYTES = 256 * 1024 * 1024
MAX_LAYOUT_BYTES = 32 * 1024 * 1024
_READERS = threading.BoundedSemaphore(2)


def _text(value, maximum):
    return (isinstance(value, str) and 0 < len(value.strip()) <= maximum
            and not any(ord(char) < 32 for char in value))


def validate_layout(value, resolve_resource=None):
    """Validate the narrow section-layout contract without stripping metadata."""
    from tools.cgroup.forza_source_decoder import canonical_resource_for_word
    if (not isinstance(value, dict) or set(value) != {"format", "vehicle", "vinyls", "placements"}
            or value["format"] != "kfps-livery-layout-v1"):
        raise ValueError("The package artwork layout is invalid or unsupported.")
    vehicle = value["vehicle"]
    if (not isinstance(vehicle, dict) or set(vehicle) != {"car_id", "model_code"}
            or type(vehicle["car_id"]) is not int or not 0 < vehicle["car_id"] <= 0xffffffff
            or not _text(vehicle["model_code"], 160)):
        raise ValueError("The package has no exact car identity.")
    vinyls, placements = value["vinyls"], value["placements"]
    if (not isinstance(vinyls, list) or not isinstance(placements, list)
            or not 0 < len(vinyls) == len(placements) <= len(NAMES)):
        raise ValueError("The package contains no editable artwork or exceeds the section limit.")
    seen = set()
    count = 0
    resolver = resolve_resource or (lambda kind: canonical_resource_for_word(kind - 0x100000))
    for source, placement in zip(vinyls, placements):
        if not isinstance(placement, dict) or placement.get("section") not in NAMES:
            raise ValueError("The package contains an unsupported artwork section.")
        section = placement["section"]
        expected = {"id": "placement-" + section, "vinylId": "save-" + section, "section": section,
                    "x": 0, "y": 0, "scaleX": 1, "scaleY": 1, "rotation": 0, "opacity": 1, "visible": True}
        if (section in seen or placement != expected or type(placement["visible"]) is not bool
                or not isinstance(source, dict) or set(source) != {"id", "name", "shapes"}
                or source["id"] != expected["vinylId"] or not _text(source["name"], 160)):
            raise ValueError("The package artwork is not an exact section layout.")
        seen.add(section)
        # Native validation intentionally sanitizes its return value. Check the
        # geometry, but retain the decoder's original nested-group metadata.
        validate_shapes({"shapes": source["shapes"]}, resolver)
        for shape in source["shapes"]:
            groups = shape.get("editor_group_path", [])
            if (not isinstance(groups, list) or len(groups) > 64
                    or any(not isinstance(group, dict) or set(group) != {"id", "name"}
                           or not _text(group["id"], 160) or not _text(group["name"], 160) for group in groups)):
                raise ValueError("The package has unsupported nested group metadata.")
            if groups and (shape.get("editor_group_id") != groups[-1]["id"]
                           or shape.get("editor_group_name") != groups[-1]["name"]):
                raise ValueError("The package group metadata is inconsistent.")
        count += len(source["shapes"])
    if count > 25000:
        raise ValueError("The package exceeds the editable artwork limit.")
    body = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_LAYOUT_BYTES - 1024:
        raise ValueError("Package artwork exceeds the 32 MiB transfer limit.")
    return json.loads(body)


def _check_source(path):
    if path.suffix.lower() != ".kfpslivery":
        raise ValueError("Choose a Liveries package, not a game save.")
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise ValueError("Redirected package paths are not supported.")


def request_for_package(path, snapshot_root):
    """CPU/I/O work: caller must invoke this from its existing worker thread."""
    from .export_service import ExportService
    from tools.cgroup.forza_source_decoder import clivery_to_layers, layers_to_kfps_json_layers
    from tools.livery.package import validate_full_livery_package, FullLiveryPackageError
    path = Path(path).absolute()
    if not _READERS.acquire(blocking=False):
        raise ValueError("Another package is being opened. Retry when it finishes.")
    try:
        _check_source(path)
        with tempfile.TemporaryDirectory(prefix="package-", dir=snapshot_root) as temporary:
            snapshot = Path(temporary) / "source.kfpslivery"
            with path.open("rb") as source, snapshot.open("xb") as destination:
                _check_source(path)
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise ValueError("Choose a private regular package file.")
                if not 0 < before.st_size <= MAX_PACKAGE_BYTES:
                    raise ValueError("The package is empty or exceeds 256 MiB.")
                total = 0
                while block := source.read(min(1024 * 1024, MAX_PACKAGE_BYTES + 1 - total)):
                    total += len(block)
                    if total > MAX_PACKAGE_BYTES:
                        raise ValueError("The package exceeds 256 MiB.")
                    destination.write(block)
                after = os.fstat(source.fileno())
                _check_source(path)
                if (total != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)
                        or not os.path.samestat(before, path.stat())):
                    raise ValueError("The package changed while it was being opened. Retry.")
            # All subsequent validation and decoding sees this one private
            # snapshot, never a second read of the mutable catalogue source.
            # The general package validator uses the legacy unbounded source
            # decoder. Establish the nested compression bound before calling it.
            with zipfile.ZipFile(snapshot) as archive:
                unwrap_bounded(ExportService._member(archive, "source/fh6/C_livery", MAX_PAYLOAD))
            manifest = validate_full_livery_package(snapshot)
            vehicle = {key: manifest["vehicle"][key] for key in ("car_id", "model_code")}
            service = ExportService(snapshot, vehicle, NAMES)
            layout = service.template_layout()
            grouped, report = clivery_to_layers(service.template.payload, preserve_groups=True)
            if report["warnings"] or len(grouped) != service.count:
                raise ValueError("The package artwork did not decode completely with its groups.")
            for source, placement in zip(layout["vinyls"], layout["placements"]):
                shapes, warnings = layers_to_kfps_json_layers(
                    [item for item in grouped if item["section"] == placement["section"]], game="fh6")
                flat = [{key: item for key, item in shape.items() if not key.startswith("editor_group_")} for shape in shapes]
                if warnings or flat != source["shapes"]:
                    raise ValueError("The package groups cannot be imported without changing artwork.")
                source["shapes"] = shapes
            name = manifest.get("livery", {}).get("title")
            name = name.strip()[:120] if _text(name, 1000) else "Package artwork"
            return {"name": name, "layout": validate_layout(layout)}
    except FullLiveryPackageError:
        raise ValueError("Package integrity, ownership or completeness validation failed. Nothing was opened.") from None
    except (OSError, KeyError, TypeError, RecursionError, zipfile.BadZipFile):
        raise ValueError("The package is missing, unreadable or unsupported. Nothing was opened.") from None
    finally:
        _READERS.release()
