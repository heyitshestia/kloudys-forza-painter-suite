from __future__ import annotations

import hashlib
import json
import os
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .vehicle_assets import VehicleAsset, read_vehicle_assembly_metadata


GRUB_TAG = 0x47727562
TXCB_TAG = 0x54584342
TXCH_TAG = 0x54584348
UNSIGNED_BC4 = 3
ATLAS_SIZE = (2048, 1024)
RENDER_CONTRACT_FORMAT = "kfps_fh6_section_render_contract_v3"
RENDER_CONTRACT_REVISION = 7
MASK_PAGE_COUNT = 3
MASK_CHANNELS = 4
PAINT_ATLAS_WIDTH = 2048
PAINT_PADDING = 2

SECTION_TO_SLOT = {
    "Front": "front",
    "Back": "back",
    "Top": "top",
    # The portable GLB conversion reflects the game's X axis. Direct side-mask
    # routing compensates for that basis change and preserves the in-game side.
    "Left": "left",
    "Right": "right",
    "Spoiler": "wing",
    "FrontWindshield": "glass_front",
    "BackWindshield": "glass_back",
    "TopWindow": "glass_top",
    "LeftWindow": "glass_left",
    "RightWindow": "glass_right",
}
SECTION_FILTER = {
    "Front": "front",
    "FrontWindshield": "front",
    "Back": "back",
    "BackWindshield": "back",
    "Top": "top",
    "TopWindow": "top",
    "Spoiler": "top",
    "Left": "left",
    "LeftWindow": "left",
    "Right": "right",
    "RightWindow": "right",
}
SECTION_FACING = {
    "Front": (0.0, 0.0, 1.0),
    "Back": (0.0, 0.0, -1.0),
    "Top": (0.0, 1.0, 0.0),
    "Left": (1.0, 0.0, 0.0),
    "Right": (-1.0, 0.0, 0.0),
    "Spoiler": (0.0, 1.0, 0.0),
    "FrontWindshield": (0.0, 0.0, 1.0),
    "BackWindshield": (0.0, 0.0, -1.0),
    "TopWindow": (0.0, 1.0, 0.0),
    "LeftWindow": (1.0, 0.0, 0.0),
    "RightWindow": (-1.0, 0.0, 0.0),
}
SECTION_SLOT_INDEX = {section: index for index, section in enumerate(SECTION_TO_SLOT)}
TRANSPOSED_SLOTS = {"wing", "glass_front", "glass_back"}
FLIP_X_SLOTS = {"wing", "right", "glass_front", "glass_right"}
FLIP_Y_SLOTS = {"right", "glass_back", "glass_right"}


class LiveryRenderContractError(RuntimeError):
    pass


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _parse_pc_texture_bundle(data: bytes) -> dict[str, int]:
    if len(data) < 0x8C or _u32(data, 0) != GRUB_TAG:
        raise LiveryRenderContractError("The livery mask is not a supported Grub texture bundle.")
    major, minor = data[4], data[5]
    if major > 1 or (major == 1 and minor >= 1):
        blob_count = _u32(data, 0x10)
        blob_headers = 0x14
    else:
        blob_count = _u16(data, 0x06)
        blob_headers = 0x10

    for blob_index in range(blob_count):
        blob = blob_headers + blob_index * 0x18
        if blob + 0x18 > len(data) or _u32(data, blob) != TXCB_TAG:
            continue
        metadata_count = _u16(data, blob + 0x06)
        metadata_offset = _u32(data, blob + 0x08)
        payload_offset = _u32(data, blob + 0x0C)
        compressed_size = _u32(data, blob + 0x10)
        uncompressed_size = _u32(data, blob + 0x14)
        for metadata_index in range(metadata_count):
            metadata = metadata_offset + metadata_index * 8
            if metadata + 8 > len(data) or _u32(data, metadata) != TXCH_TAG:
                continue
            flags = _u16(data, metadata + 4)
            metadata_size = flags >> 4
            header_offset = metadata + _u16(data, metadata + 6)
            header = data[header_offset : header_offset + metadata_size]
            if len(header) < 0x40:
                raise LiveryRenderContractError("The livery mask texture header is truncated.")
            width = _u32(header, 0x18)
            height = _u32(header, 0x1C)
            depth = _u32(header, 0x20)
            slices = _u16(header, 0x24) & 0x3FFF
            mips = header[0x26]
            slices_offset = _u32(header, 0x38)
            if slices != 1 or mips != 1 or depth != 1 or slices_offset == 0:
                raise LiveryRenderContractError(
                    f"Unsupported livery mask layout: {slices} slices, {mips} mips, depth {depth}."
                )
            encoding = _u32(header, slices_offset)
            mip_array_offset = _u32(header, slices_offset + 4)
            mip_size = _u32(header, mip_array_offset)
            mip_payload_offset = _u32(header, mip_array_offset + 4)
            payload_size = uncompressed_size or compressed_size
            start = payload_offset + mip_payload_offset
            if payload_offset + payload_size > len(data) or start + mip_size > len(data):
                raise LiveryRenderContractError("The livery mask texture payload is truncated.")
            return {
                "width": width,
                "height": height,
                "encoding": encoding,
                "payload_offset": start,
                "payload_size": mip_size,
            }
    raise LiveryRenderContractError("The livery mask bundle has no supported texture payload.")


def _decode_unsigned_bc4(payload: bytes, width: int, height: int) -> np.ndarray:
    if width % 4 or height % 4:
        raise LiveryRenderContractError("BC4 livery mask dimensions must be divisible by four.")
    block_width = width // 4
    block_height = height // 4
    expected = block_width * block_height * 8
    if len(payload) != expected:
        raise LiveryRenderContractError(
            f"BC4 livery mask payload is {len(payload)} bytes; expected {expected}."
        )
    blocks = np.frombuffer(payload, dtype=np.uint8).reshape(block_height, block_width, 8)
    endpoint_0 = blocks[..., 0].astype(np.uint16)
    endpoint_1 = blocks[..., 1].astype(np.uint16)
    palette = np.empty((block_height, block_width, 8), dtype=np.uint8)
    palette[..., 0] = endpoint_0
    palette[..., 1] = endpoint_1
    eight_value = endpoint_0 > endpoint_1
    for index in range(2, 8):
        seven_step = ((8 - index) * endpoint_0 + (index - 1) * endpoint_1) // 7
        if index <= 5:
            five_step = ((6 - index) * endpoint_0 + (index - 1) * endpoint_1) // 5
        elif index == 6:
            five_step = np.zeros_like(endpoint_0)
        else:
            five_step = np.full_like(endpoint_0, 255)
        palette[..., index] = np.where(eight_value, seven_step, five_step).astype(np.uint8)
    packed_indices = np.zeros((block_height, block_width), dtype=np.uint64)
    for byte_index in range(6):
        packed_indices |= blocks[..., 2 + byte_index].astype(np.uint64) << (8 * byte_index)
    image = np.empty((height, width), dtype=np.uint8)
    for pixel_index in range(16):
        selector = ((packed_indices >> (3 * pixel_index)) & 7).astype(np.intp)
        values = np.take_along_axis(palette, selector[..., None], axis=2)[..., 0]
        image[pixel_index // 4 :: 4, pixel_index % 4 :: 4] = values
    return image


def _atlas_to_local_affine(
    slot: str,
    width: int,
    height: int,
    x_origin: float,
    y_origin: float,
) -> tuple[float, float, float, float, float, float]:
    slot = slot.casefold()
    flip_x = -1.0 if slot in FLIP_X_SLOTS else 1.0
    flip_y = -1.0 if slot in FLIP_Y_SLOTS else 1.0
    center_x = width / 2.0
    center_y = height / 2.0
    if slot in TRANSPOSED_SLOTS:
        return (
            0.0,
            -flip_x,
            center_x + flip_x * (center_y - y_origin),
            -flip_y,
            0.0,
            center_y + flip_y * (center_x + x_origin),
        )
    return (
        flip_x,
        0.0,
        center_x - flip_x * (center_x + x_origin),
        0.0,
        flip_y,
        center_y - flip_y * (center_y - y_origin),
    )


def _warped_uv_layer(
    artwork: Image.Image,
    slot: str,
    projection: dict[str, Any],
) -> Image.Image:
    if artwork.size != ATLAS_SIZE:
        raise LiveryRenderContractError(
            f"{slot} artwork must be {ATLAS_SIZE[0]} x {ATLAS_SIZE[1]} pixels."
        )
    affine = _atlas_to_local_affine(
        slot,
        artwork.width,
        artwork.height,
        float(projection.get("xorigin", 0.0)),
        float(projection.get("yorigin", 0.0)),
    )
    return artwork.convert("RGBA").transform(
        ATLAS_SIZE,
        Image.Transform.AFFINE,
        affine,
        resample=Image.Resampling.BILINEAR,
        fillcolor=(0, 0, 0, 0),
    )


def _projection_pixel_bounds(projection: dict[str, Any]) -> tuple[int, int, int, int]:
    """Return the exact FH6 projection rectangle in atlas pixel coordinates."""

    try:
        canvas_left = min(float(projection["left"]), float(projection["right"]))
        canvas_right = max(float(projection["left"]), float(projection["right"]))
        canvas_top = max(float(projection["top"]), float(projection["bottom"]))
        canvas_bottom = min(float(projection["top"]), float(projection["bottom"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveryRenderContractError("The livery projection rectangle is incomplete.") from exc

    left = int(round(ATLAS_SIZE[0] / 2.0 + canvas_left))
    right = int(round(ATLAS_SIZE[0] / 2.0 + canvas_right))
    top = int(round(ATLAS_SIZE[1] / 2.0 - canvas_top))
    bottom = int(round(ATLAS_SIZE[1] / 2.0 - canvas_bottom))
    if not (0 <= left < right <= ATLAS_SIZE[0] and 0 <= top < bottom <= ATLAS_SIZE[1]):
        raise LiveryRenderContractError(
            f"The livery projection rectangle {(left, top, right, bottom)} is outside {ATLAS_SIZE}."
        )
    return left, top, right, bottom


def _masked_atlas_layer(
    artwork: Image.Image,
    mask: Image.Image,
    slot: str,
    projection: dict[str, Any],
) -> Image.Image:
    if artwork.size != mask.size or artwork.size != ATLAS_SIZE:
        raise LiveryRenderContractError(
            f"{slot} artwork and mask must both be {ATLAS_SIZE[0]} x {ATLAS_SIZE[1]} pixels."
        )
    warped = _warped_uv_layer(artwork, slot, projection)
    rgba = np.asarray(warped, dtype=np.uint8).copy()
    mask_values = np.asarray(mask.convert("L"), dtype=np.uint16)
    rgba[..., 3] = (
        (rgba[..., 3].astype(np.uint16) * mask_values + 127) // 255
    ).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def _archive_masks(asset: VehicleAsset) -> dict[str, tuple[Image.Image, dict[str, Any], str]]:
    with zipfile.ZipFile(asset.archive_path) as bundle:
        available = {name.casefold(): name for name in bundle.namelist()}
        xml_name = available.get("liverymasks/masks.xml")
        if not xml_name:
            raise LiveryRenderContractError(f"{asset.archive_name} has no LiveryMasks/Masks.xml.")
        projections = {
            element.tag.casefold(): dict(element.attrib)
            for element in ET.fromstring(bundle.read(xml_name))
            if element.attrib.get("valid", "false").casefold() == "true"
        }
        result: dict[str, tuple[Image.Image, dict[str, Any], str]] = {}
        for slot in sorted(set(SECTION_TO_SLOT.values())):
            name = available.get(f"liverymasks/{slot}.swatchbin")
            projection = projections.get(slot)
            if not name or projection is None:
                continue
            data = bundle.read(name)
            texture = _parse_pc_texture_bundle(data)
            if texture["encoding"] != UNSIGNED_BC4:
                raise LiveryRenderContractError(
                    f"{name} uses texture encoding {texture['encoding']}; unsigned BC4 was expected."
                )
            start = texture["payload_offset"]
            mask = _decode_unsigned_bc4(
                data[start : start + texture["payload_size"]],
                texture["width"],
                texture["height"],
            )
            result[slot] = (
                Image.fromarray(mask, mode="L"),
                projection,
                hashlib.sha256(data).hexdigest(),
            )
        return result


def _save_png(image: Image.Image, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    image.save(temporary, format="PNG", optimize=True)
    os.replace(temporary, path)


def _pack_paint_tiles(
    tiles: list[dict[str, Any]],
) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    """Pack cropped section paint into deterministic padded shelves."""

    ordered = sorted(
        tiles,
        key=lambda item: (
            -int(item["image"].height),
            -int(item["image"].width),
            int(item["slot_index"]),
        ),
    )
    placements: dict[str, tuple[int, int, int, int]] = {}
    x = PAINT_PADDING
    y = PAINT_PADDING
    row_height = 0
    max_bottom = PAINT_PADDING
    for item in ordered:
        image: Image.Image = item["image"]
        if image.width + PAINT_PADDING * 2 > PAINT_ATLAS_WIDTH:
            raise LiveryRenderContractError(
                f"The {item['section']} paint region is too wide for the local texture atlas."
            )
        if x + image.width + PAINT_PADDING > PAINT_ATLAS_WIDTH:
            x = PAINT_PADDING
            y += row_height + PAINT_PADDING * 2
            row_height = 0
        placements[item["section"]] = (x, y, image.width, image.height)
        x += image.width + PAINT_PADDING * 2
        row_height = max(row_height, image.height)
        max_bottom = max(max_bottom, y + image.height + PAINT_PADDING)

    height = max(1, max_bottom)
    if height > 8192:
        raise LiveryRenderContractError(
            f"The local section paint atlas would be {PAINT_ATLAS_WIDTH} x {height} pixels."
        )
    atlas = Image.new("RGBA", (PAINT_ATLAS_WIDTH, height), (0, 0, 0, 0))
    for item in ordered:
        left, top, _, _ = placements[item["section"]]
        atlas.alpha_composite(item["image"], (left, top))
    return atlas, placements


def build_local_livery_atlases(
    package_path: Path | str,
    asset: VehicleAsset,
    output_dir: Path | str,
) -> dict[str, Any]:
    package = Path(package_path).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    signature = {
        "contract_revision": RENDER_CONTRACT_REVISION,
        "package_sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
        "archive_size": asset.archive_size,
        "archive_mtime_ns": asset.archive_mtime_ns,
        "model_code": asset.model_code,
    }
    index_path = output / "index.json"
    if index_path.is_file():
        try:
            cached = json.loads(index_path.read_text(encoding="utf-8"))
            files = cached.get("files") or {}
            cached_names = [str(files.get("paint") or "")]
            cached_names.extend(str(name) for name in (files.get("masks") or []))
            if (
                cached.get("format") == RENDER_CONTRACT_FORMAT
                and cached.get("signature") == signature
                and len(cached_names) == MASK_PAGE_COUNT + 1
                and all(name and (output / name).is_file() for name in cached_names)
            ):
                return {**cached, "root": str(output)}
        except (OSError, ValueError, TypeError):
            pass

    masks = _archive_masks(asset)
    mask_pages = [
        np.zeros((ATLAS_SIZE[1], ATLAS_SIZE[0], MASK_CHANNELS), dtype=np.uint8)
        for _ in range(MASK_PAGE_COUNT)
    ]
    paint_tiles: list[dict[str, Any]] = []
    pending_records: list[dict[str, Any]] = []
    with zipfile.ZipFile(package) as bundle:
        available = {name.casefold(): name for name in bundle.namelist()}
        for section, slot in SECTION_TO_SLOT.items():
            member = available.get(f"projection/rendered/{section}.png".casefold())
            mask_record = masks.get(slot)
            if not member or mask_record is None:
                continue
            mask, projection, mask_hash = mask_record
            if mask.size != ATLAS_SIZE:
                raise LiveryRenderContractError(
                    f"{slot} mask is {mask.size}; expected {ATLAS_SIZE}."
                )
            slot_index = SECTION_SLOT_INDEX[section]
            mask_page = slot_index // MASK_CHANNELS
            mask_channel = slot_index % MASK_CHANNELS
            mask_values = np.asarray(mask.convert("L"), dtype=np.uint8)
            mask_pages[mask_page][..., mask_channel] = mask_values
            if mask.getbbox() is None:
                continue
            source_bounds = _projection_pixel_bounds(projection)
            with bundle.open(member) as source, Image.open(source) as artwork:
                warped = _warped_uv_layer(artwork, slot, projection)
                tile = warped.crop(source_bounds)
            kind = "glass" if slot.startswith("glass_") else "body"
            filter_name = SECTION_FILTER[section]
            tile_alpha = np.asarray(tile.getchannel("A"), dtype=np.uint8)
            mask_crop = mask_values[
                source_bounds[1] : source_bounds[3], source_bounds[0] : source_bounds[2]
            ]
            visible = int(np.count_nonzero((tile_alpha > 0) & (mask_crop > 0)))
            paint_tiles.append(
                {"section": section, "slot_index": slot_index, "image": tile}
            )
            pending_records.append(
                {
                    "section": section,
                    "slot": slot,
                    "slot_index": slot_index,
                    "kind": kind,
                    "filter": filter_name,
                    "facing": list(SECTION_FACING[section]),
                    "mask_page": mask_page,
                    "mask_channel": mask_channel,
                    "mask_sha256": mask_hash,
                    "source_bounds": list(source_bounds),
                    "visible_pixels": visible,
                }
            )

    if not paint_tiles:
        raise LiveryRenderContractError("The package and local car masks have no shared livery sections.")
    paint_atlas, placements = _pack_paint_tiles(paint_tiles)
    paint_filename = "section-paint.png"
    _save_png(paint_atlas, output / paint_filename)
    mask_filenames: list[str] = []
    for page_index, page in enumerate(mask_pages):
        filename = f"section-masks-{page_index}.png"
        _save_png(Image.fromarray(page), output / filename)
        mask_filenames.append(filename)

    records: list[dict[str, Any]] = []
    for record in pending_records:
        left, top, width, height = placements[record["section"]]
        source_left, source_top, source_right, source_bottom = record.pop("source_bounds")
        record["source_region"] = [
            source_left / ATLAS_SIZE[0],
            source_top / ATLAS_SIZE[1],
            source_right / ATLAS_SIZE[0],
            source_bottom / ATLAS_SIZE[1],
        ]
        record["paint_region"] = [
            left / paint_atlas.width,
            top / paint_atlas.height,
            (left + width) / paint_atlas.width,
            (top + height) / paint_atlas.height,
        ]
        records.append(record)
    records.sort(key=lambda item: int(item["slot_index"]))
    files = {"paint": paint_filename, "masks": mask_filenames}
    index = {
        "format": RENDER_CONTRACT_FORMAT,
        "signature": signature,
        "uv_contract": {
            "attribute": "TEXCOORD_3",
            "u_scale": 0.5,
            "flip_u": False,
            "flip_v": False,
            "world_projection_fallback": False,
        },
        "assembly": read_vehicle_assembly_metadata(asset),
        "paint_size": list(paint_atlas.size),
        "mask_size": list(ATLAS_SIZE),
        "filters": [
            name
            for name in ("all", "top", "left", "right", "front", "back")
            if name == "all" or any(record["filter"] == name for record in records)
        ],
        "files": files,
        "sections": records,
    }
    temporary = index_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, index_path)
    return {**index, "root": str(output)}
