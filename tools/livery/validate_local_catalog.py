#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.cgroup.forza_source_decoder import (
    extract_livery_payload,
    inspect_clivery_privacy,
    unwrap_forza_container,
)
from tools.livery.package import create_local_livery_preview
from tools.livery.portable_mesh_converter import (
    convert_vehicle_model_to_glb,
    validate_local_chassis_glb,
)
from tools.livery.render_contract import build_local_livery_atlases
from tools.livery.vehicle_assets import load_or_build_vehicle_asset_index


FORMAT = "kfps_fh6_local_livery_catalog_validation_v1"
INSPECTION_MESH_CACHE_REVISION = 10


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _header_title(source: Path) -> str:
    header = source.parent / "header"
    if not header.is_file():
        return ""
    data = header.read_bytes()
    if len(data) < 8:
        return ""
    units = struct.unpack_from("<I", data, 4)[0]
    if units <= 0 or units > 4096 or 8 + units * 2 > len(data):
        return ""
    return data[8 : 8 + units * 2].decode("utf-16le", errors="replace").strip("\x00 \t\r\n")


def inventory_liveries(save_root: Path, vehicle_index: dict[int, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_hash: dict[str, dict[str, Any]] = {}
    counters = {"files": 0, "duplicates": 0, "invalid": 0, "empty": 0}
    for source in sorted(save_root.rglob("C_livery"), key=lambda path: str(path).casefold()):
        counters["files"] += 1
        try:
            raw = source.read_bytes()
            digest = _sha256(raw)
            if digest in by_hash:
                counters["duplicates"] += 1
                continue
            payload = unwrap_forza_container(source)
            if len(payload) < 0x1A or payload[:4] != b"vlrc":
                counters["invalid"] += 1
                continue
            state = struct.unpack_from("<I", payload, 0x08)[0]
            car_id = struct.unpack_from("<I", payload, 0x10)[0]
            privacy = inspect_clivery_privacy(payload)
            _, section_counts, _ = extract_livery_payload(payload)
            placement_count = sum(section_counts)
            if placement_count <= 0:
                counters["empty"] += 1
                continue
            asset = vehicle_index.get(car_id)
            by_hash[digest] = {
                "source_sha256": digest,
                "source_path": str(source.resolve()),
                "title": _header_title(source) or source.parent.name,
                "car_id": car_id,
                "model_code": asset.model_code if asset else "",
                "state": state,
                "source_owned": bool(privacy["source_owned"]),
                "contains_foreign_groups": bool(privacy["contains_foreign_groups"]),
                "exportable": bool(privacy["source_owned"] and not privacy["contains_foreign_groups"]),
                "placement_count": placement_count,
                "section_counts": list(section_counts),
                "modified_ns": source.stat().st_mtime_ns,
            }
        except Exception as exc:
            counters["invalid"] += 1
            by_hash[f"invalid-{counters['invalid']}"] = {
                "source_path": str(source.resolve()),
                "error": str(exc),
            }
    rows = sorted(
        by_hash.values(),
        key=lambda row: (
            int(row.get("car_id") or 0),
            str(row.get("title") or "").casefold(),
            str(row.get("source_sha256") or ""),
        ),
    )
    return rows, counters


def _car_record(asset: Any, output_root: Path) -> dict[str, Any]:
    target = output_root / "meshes" / (
        f"{asset.model_code}-{asset.archive_mtime_ns}.local-chassis-v{INSPECTION_MESH_CACHE_REVISION}.glb"
    )
    started = time.monotonic()
    diagnostics: dict[str, int] = {}
    try:
        if target.is_file():
            validation = validate_local_chassis_glb(target)
            source = "cache"
        else:
            convert_vehicle_model_to_glb(asset, target, diagnostics=diagnostics)
            validation = validate_local_chassis_glb(target)
            source = "converted"
        return {
            "car_id": asset.car_id,
            "model_code": asset.model_code,
            "status": "ok",
            "source": source,
            "mesh_path": str(target.resolve()),
            "mesh_size": target.stat().st_size,
            "seconds": round(time.monotonic() - started, 3),
            "peak_resident_bytes": diagnostics.get("peak_resident_bytes", 0),
            **validation,
        }
    except Exception as exc:
        target.unlink(missing_ok=True)
        return {
            "car_id": asset.car_id,
            "model_code": asset.model_code,
            "status": "error",
            "seconds": round(time.monotonic() - started, 3),
            "error": str(exc),
        }


def _preview_record(
    row: dict[str, Any],
    asset: Any,
    output_root: Path,
    vehicle_index_cache: Path,
) -> dict[str, Any]:
    digest = str(row["source_sha256"])
    package = output_root / "previews" / f"{digest[:24]}.kfpspreview"
    render_root = output_root / "renders" / digest[:24]
    started = time.monotonic()
    try:
        create_local_livery_preview(
            row["source_path"],
            package,
            game_folder=Path(asset.archive_path).parents[2],
            vehicle_index_cache=vehicle_index_cache,
            _allow_unowned_private_preview=not bool(row["source_owned"]),
        )
        contract = build_local_livery_atlases(package, asset, render_root)
        return {
            "status": "ok",
            "package_path": str(package.resolve()),
            "render_root": str(render_root.resolve()),
            "seconds": round(time.monotonic() - started, 3),
            "sections": [item["section"] for item in contract.get("sections") or []],
            "visible_pixels": {
                item["section"]: int(item.get("visible_pixels") or 0)
                for item in contract.get("sections") or []
            },
        }
    except Exception as exc:
        package.unlink(missing_ok=True)
        return {
            "status": "error",
            "seconds": round(time.monotonic() - started, 3),
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inventory and independently exercise every unique nonempty local FH6 livery."
    )
    parser.add_argument("--save-root", type=Path, default=Path(r"C:\XboxGames\GameSave"))
    parser.add_argument("--game-folder", type=Path, default=Path(r"C:\XboxGames\Forza Horizon 6\Content"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runtime/full-livery/validation/catalog-current"),
    )
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--skip-previews", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    vehicle_index_cache = output / "vehicle-index.json"
    vehicle_index = load_or_build_vehicle_asset_index(args.game_folder, vehicle_index_cache)
    liveries, counters = inventory_liveries(args.save_root.resolve(), vehicle_index)
    if args.limit > 0:
        liveries = liveries[: args.limit]
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "save_root": str(args.save_root.resolve()),
        "game_folder": str(args.game_folder.resolve()),
        "counters": counters,
        "liveries": liveries,
        "cars": [],
        "complete": False,
    }
    manifest_path = output / "manifest.json"
    _write_json(manifest_path, manifest)
    if args.inventory_only:
        manifest["complete"] = True
        _write_json(manifest_path, manifest)
        print(json.dumps({"manifest": str(manifest_path), "liveries": len(liveries)}, indent=2))
        return 0

    car_ids = sorted({int(row["car_id"]) for row in liveries if row.get("car_id")})
    for car_id in car_ids:
        asset = vehicle_index.get(car_id)
        record = (
            _car_record(asset, output)
            if asset is not None
            else {"car_id": car_id, "status": "error", "error": "No local FH6 vehicle archive."}
        )
        manifest["cars"].append(record)
        _write_json(manifest_path, manifest)

    if not args.skip_previews:
        for index, row in enumerate(liveries):
            asset = vehicle_index.get(int(row.get("car_id") or 0))
            row["preview"] = (
                _preview_record(row, asset, output, vehicle_index_cache)
                if asset is not None
                else {"status": "error", "error": "No local FH6 vehicle archive."}
            )
            manifest["liveries"][index] = row
            _write_json(manifest_path, manifest)

    manifest["complete"] = True
    manifest["completed_utc"] = datetime.now(timezone.utc).isoformat()
    _write_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "liveries": len(liveries),
                "cars": len(car_ids),
                "car_errors": sum(item.get("status") != "ok" for item in manifest["cars"]),
                "preview_errors": sum(
                    (item.get("preview") or {}).get("status") != "ok" for item in manifest["liveries"]
                )
                if not args.skip_previews
                else None,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
