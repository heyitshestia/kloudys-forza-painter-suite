"""Blank authoring atlases retaining supported native mask sizes and pixels."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

SOURCE_SIZE = (2048, 1024)
SUPPORTED_MASK_SIZES = {(2048, 1024), (1024, 1024)}


def projection_bounds(projection, size):
    values = [float(projection[key]) for key in ("left", "right", "top", "bottom")]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Non-finite native projection rectangle.")
    left, right, top, bottom = values
    bounds = (round(size[0] / 2 + min(left, right)), round(size[1] / 2 - max(top, bottom)),
              round(size[0] / 2 + max(left, right)), round(size[1] / 2 - min(top, bottom)))
    if not (0 <= bounds[0] < bounds[2] <= size[0] and 0 <= bounds[1] < bounds[3] <= size[1]):
        raise ValueError("Native projection rectangle is outside its mask.")
    return bounds


def authoring_affine(slot, size, projection):
    from tools.livery.render_contract import _atlas_to_local_affine

    # The editor's source canvas remains 2048x1024. Only mask-space dimensions
    # vary. Convert its virtual atlas coordinates to native mask pixels first.
    a, b, c, d, e, f = _atlas_to_local_affine(
        slot, *size, float(projection.get("xorigin", 0)), float(projection.get("yorigin", 0)))
    sx, sy = size[0] / SOURCE_SIZE[0], size[1] / SOURCE_SIZE[1]
    result = [a * sx, b * sy, c + (SOURCE_SIZE[0] - size[0]) / 2,
              d * sx, e * sy, f + (SOURCE_SIZE[1] - size[1]) / 2]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("Non-finite native section transform.")
    return result


def build_authoring_atlases(package, asset, output_dir, *, mesh_path, mesh_validation):
    from tools.livery import render_contract as native
    from tools.livery import vehicle_assets
    from .prepare import atomic_json, file_hash

    masks = native._archive_masks(asset)
    sizes = {image.size for image, _, _ in masks.values()}
    if len(sizes) != 1 or not sizes.issubset(SUPPORTED_MASK_SIZES):
        raise ValueError("This car uses unsupported or mixed native mask dimensions. No masks were stretched.")
    size = sizes.pop()
    if size == SOURCE_SIZE:
        return native.build_local_livery_atlases(package, asset, output_dir,
                                                mesh_path=mesh_path, mesh_validation=mesh_validation)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    signature = {"adapter_revision": 1, "adapter_sha256": file_hash(Path(__file__)),
                 "contract_sha256": file_hash(Path(native.__file__)),
                 "assembly_helper_sha256": file_hash(Path(vehicle_assets.__file__)),
                 "archive_size": asset.archive_size, "archive_mtime_ns": asset.archive_mtime_ns,
                 "package_sha256": file_hash(Path(package)), "mesh_sha256": file_hash(Path(mesh_path)),
                 "masks": {slot: row[2] for slot, row in sorted(masks.items())},
                 "projection": {slot: row[1] for slot, row in sorted(masks.items())}}
    index_path = output / "index.json"
    if index_path.is_file():
        try:
            cached = json.loads(index_path.read_text(encoding="utf-8"))
            names = [cached["files"]["paint"], *cached["files"]["masks"]]
            if (cached.get("signature") == signature and len(names) == 4
                    and all(Path(name).name == name and file_hash(output / name) == cached["file_sha256"][name] for name in names)):
                return {**cached, "root": str(output), "cache_hit": True}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    pages = [np.zeros((size[1], size[0], 4), dtype=np.uint8) for _ in range(3)]
    tiles, records = [], []
    for section, slot in native.SECTION_TO_SLOT.items():
        if slot not in masks:
            continue
        image, projection, source_hash = masks[slot]
        index = native.SECTION_SLOT_INDEX[section]
        pages[index // 4][..., index % 4] = np.asarray(image.convert("L"), dtype=np.uint8)
        if image.getbbox() is None:
            continue
        left, top, right, bottom = projection_bounds(projection, size)
        tiles.append({"section": section, "slot_index": index,
                      "image": Image.new("RGBA", (right - left, bottom - top))})
        records.append({"section": section, "slot": slot, "slot_index": index,
                        "kind": "glass" if slot.startswith("glass_") else "body",
                        "filter": native.SECTION_FILTER[section], "facing": list(native.SECTION_FACING[section]),
                        "mask_page": index // 4, "mask_channel": index % 4, "mask_sha256": source_hash,
                        "source_region": [left / size[0], top / size[1], right / size[0], bottom / size[1]],
                        "visible_pixels": 0, "atlasToLocal": authoring_affine(slot, size, projection)})
    if not tiles:
        raise ValueError("This car has no nonempty native livery sections.")
    atlas, placements = native._pack_paint_tiles(tiles)
    native._save_png(atlas, output / "section-paint.png")
    for index, page in enumerate(pages):
        native._save_png(Image.fromarray(page), output / f"section-masks-{index}.png")
    for row in records:
        left, top, width, height = placements[row["section"]]
        row["paint_region"] = [left / atlas.width, top / atlas.height,
                               (left + width) / atlas.width, (top + height) / atlas.height]
    files = {"paint": "section-paint.png", "masks": [f"section-masks-{index}.png" for index in range(3)]}
    result = {"format": native.RENDER_CONTRACT_FORMAT, "signature": signature,
              "uv_contract": {"attribute": "TEXCOORD_3", "u_scale": 1024 / size[0], "v_scale": 1024 / size[1],
                              "flip_u": False, "flip_v": False, "world_projection_fallback": False},
              "assembly": native.read_vehicle_assembly_metadata(asset), "projection_bounds_source": "direct-uv-only",
              "paint_size": list(atlas.size), "mask_size": list(size), "quality_scale": 1,
              "quality_source": "native-mask-size-blank-authoring", "quality_notes": [],
              "filters": [name for name in ("all", "top", "left", "right", "front", "back")
                          if name == "all" or any(row["filter"] == name for row in records)],
              "files": files, "file_sha256": {name: file_hash(output / name) for name in [files["paint"], *files["masks"]]},
              "sections": records}
    atomic_json(index_path, result)
    return {**result, "root": str(output), "cache_hit": False}
