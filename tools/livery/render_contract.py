from __future__ import annotations

import hashlib
import io
import json
import os
import struct
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .portable_mesh_converter import read_local_chassis_projection_meshes
from .projection_alignment import build_aligned_projection_bounds
from .vehicle_assets import VehicleAsset, read_vehicle_assembly_metadata
from .derived_cache import file_sha256
from .package import _render_livery_sections


GRUB_TAG = 0x47727562
TXCB_TAG = 0x54584342
TXCH_TAG = 0x54584348
UNSIGNED_BC4 = 3
ATLAS_SIZE = (2048, 1024)
RENDER_CONTRACT_FORMAT = "kfps_fh6_section_render_contract_v3"
RENDER_CONTRACT_REVISION = 11
MASK_PAGE_COUNT = 3
MASK_CHANNELS = 4
PAINT_ATLAS_WIDTH = 2048
PAINT_PADDING = 8

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
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


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


def _projection_axis(projection: dict[str, Any], key: str, scale_key: str) -> tuple[int, float]:
    value = str(projection.get(key) or "").strip().casefold()
    axis_name = value[-1:] if value else ""
    if axis_name not in AXIS_INDEX:
        raise LiveryRenderContractError(f"The livery projection axis {key} is invalid.")
    try:
        scale = float(projection.get(scale_key, 1.0))
    except (TypeError, ValueError) as exc:
        raise LiveryRenderContractError(f"The livery projection scale {scale_key} is invalid.") from exc
    if not np.isfinite(scale) or abs(scale) < 0.000001:
        raise LiveryRenderContractError(f"The livery projection scale {scale_key} is invalid.")
    sign = -1.0 if value.startswith("-") else 1.0
    return AXIS_INDEX[axis_name], sign * scale


def _projection_mask_region(projection: dict[str, Any]) -> list[float]:
    try:
        left = float(projection["left"])
        right = float(projection["right"])
        top = float(projection["top"])
        bottom = float(projection["bottom"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveryRenderContractError("The livery projection rectangle is incomplete.") from exc
    values = [
        (left + ATLAS_SIZE[0] / 2.0) / ATLAS_SIZE[0],
        (right + ATLAS_SIZE[0] / 2.0) / ATLAS_SIZE[0],
        (ATLAS_SIZE[1] / 2.0 - top) / ATLAS_SIZE[1],
        (ATLAS_SIZE[1] / 2.0 - bottom) / ATLAS_SIZE[1],
    ]
    if any(not np.isfinite(value) for value in values):
        raise LiveryRenderContractError("The livery projection rectangle is invalid.")
    return values


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
    return Image.fromarray(rgba)


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
                Image.fromarray(mask),
                projection,
                hashlib.sha256(data).hexdigest(),
            )
        return result


def _save_png(image: Image.Image, path: Path) -> None:
    temporary = path.with_name(path.name + ".tmp")
    image.save(temporary, format="PNG", compress_level=3)
    os.replace(temporary, path)


def _pack_paint_tiles(
    tiles: list[dict[str, Any]],
    *, width: int = PAINT_ATLAS_WIDTH,
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
        if image.width + PAINT_PADDING * 2 > width:
            raise LiveryRenderContractError(
                f"The {item['section']} paint region is too wide for the local texture atlas."
            )
        if x + image.width + PAINT_PADDING > width:
            x = PAINT_PADDING
            y += row_height + PAINT_PADDING * 2
            row_height = 0
        placements[item["section"]] = (x, y, image.width, image.height)
        x += image.width + PAINT_PADDING * 2
        row_height = max(row_height, image.height)
        max_bottom = max(max_bottom, y + image.height + PAINT_PADDING)

    height = max(1, max_bottom)
    if height > 8192 or width * height > 24 * 1024 * 1024:
        raise LiveryRenderContractError(
            f"The local section paint atlas would be {width} x {height} pixels; use Standard preview quality."
        )
    atlas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for item in ordered:
        left, top, _, _ = placements[item["section"]]
        atlas.alpha_composite(item["image"], (left, top))
        image = item["image"]
        # Extruded edges protect bilinear/mipmap sampling from neighbouring tiles.
        for box, target, size in (
            ((0, 0, 1, image.height), (left - PAINT_PADDING, top), (PAINT_PADDING, image.height)),
            ((image.width - 1, 0, image.width, image.height), (left + image.width, top), (PAINT_PADDING, image.height)),
            ((0, 0, image.width, 1), (left, top - PAINT_PADDING), (image.width, PAINT_PADDING)),
            ((0, image.height - 1, image.width, image.height), (left, top + image.height), (image.width, PAINT_PADDING)),
        ):
            atlas.paste(image.crop(box).resize(size, Image.Resampling.NEAREST), target)
    return atlas, placements


def _vector_paint_tile(layers, section, slot, projection, bounds, scale, game_folder, cancel_event):
    left, top, right, bottom = bounds
    a, b, c, d, e, f = _atlas_to_local_affine(
        slot, *ATLAS_SIZE, float(projection.get("xorigin", 0)), float(projection.get("yorigin", 0))
    )
    corners = [(a*x+b*y+c, d*x+e*y+f) for x in (left, right) for y in (top, bottom)]
    min_x, max_x = min(p[0] for p in corners), max(p[0] for p in corners)
    min_y, max_y = min(p[1] for p in corners), max(p[1] for p in corners)
    size = (round((max_x-min_x)*scale), round((max_y-min_y)*scale))
    rendered, references_verified, _ = _render_livery_sections(
        layers, game_folder=game_folder, strict_assets=False, cancel_event=cancel_event,
        canvas_size=size, world_bounds=(min_x-1024, 512-max_y, max_x-1024, 512-min_y),
    )
    if not references_verified:
        return None
    data = rendered.get(section)
    if data is None:
        return Image.new("RGBA", ((right-left)*scale, (bottom-top)*scale))
    with Image.open(io.BytesIO(data)) as source:
        artwork = source.convert("RGBA")
    # The native section canvas clips artwork outside these coordinates.
    for box in (
        (0, 0, max(0, round(-min_x*scale)), size[1]),
        (min(size[0], round((2048-min_x)*scale)), 0, size[0], size[1]),
        (0, 0, size[0], max(0, round(-min_y*scale))),
        (0, min(size[1], round((1024-min_y)*scale)), size[0], size[1]),
    ):
        clipped = (max(0, box[0]), max(0, box[1]), min(size[0], box[2]), min(size[1], box[3]))
        if clipped[2] > clipped[0] and clipped[3] > clipped[1]:
            artwork.paste((0, 0, 0, 0), clipped)
    return artwork.transform(
        ((right-left)*scale, (bottom-top)*scale), Image.Transform.AFFINE,
        (a, b, (a*left+b*top+c-min_x)*scale, d, e, (d*left+e*top+f-min_y)*scale),
        resample=Image.Resampling.BILINEAR,
    )


def build_local_livery_atlases(
    package_path: Path | str,
    asset: VehicleAsset,
    output_dir: Path | str,
    *,
    mesh_path: Path | str | None = None,
    mesh_validation: dict | None = None,
    cancel_event=None,
    progress=None,
    quality_scale: int = 1,
    layer_provider=None,
    game_folder: str | Path | None = None,
) -> dict[str, Any]:
    package = Path(package_path).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    scale = 2 if quality_scale == 2 and layer_provider is not None else 1
    signature = {
        "contract_revision": RENDER_CONTRACT_REVISION,
        "package_sha256": file_sha256(package),
        "archive_size": asset.archive_size,
        "archive_mtime_ns": asset.archive_mtime_ns,
        "model_code": asset.model_code,
        "quality_scale": scale,
    }
    local_mesh = Path(mesh_path).resolve() if mesh_path else None
    if local_mesh is not None:
        mesh_stat = local_mesh.stat()
        signature.update({
            "mesh_size": mesh_stat.st_size,
            "mesh_mtime_ns": mesh_stat.st_mtime_ns,
        })
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
                and all(name and Path(name).name == name and (output / name).is_file()
                        and file_sha256(output / name) == (cached.get("file_sha256") or {}).get(name)
                        for name in cached_names)
            ):
                return {**cached, "root": str(output), "cache_hit": True}
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    masks = _archive_masks(asset)
    section_layers = {}
    quality_notes = []
    if scale > 1:
        for layer in layer_provider():
            section_layers.setdefault(str(layer.get("source_section") or ""), []).append(layer)
    assembly = read_vehicle_assembly_metadata(asset)
    projection_meshes = (
        read_local_chassis_projection_meshes(local_mesh)
        if local_mesh is not None and (mesh_validation is None or mesh_validation.get("projected_livery_meshes", 1) > 0)
        else []
    )
    mask_pages = [
        np.zeros((ATLAS_SIZE[1], ATLAS_SIZE[0], MASK_CHANNELS), dtype=np.uint8)
        for _ in range(MASK_PAGE_COUNT)
    ]
    paint_tiles: list[dict[str, Any]] = []
    pending_records: list[dict[str, Any]] = []
    alignment_masks: dict[int, np.ndarray] = {}
    with zipfile.ZipFile(package) as bundle:
        available = {name.casefold(): name for name in bundle.namelist()}
        for section, slot in SECTION_TO_SLOT.items():
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError("Livery texture preparation was cancelled.")
            member = available.get(f"projection/rendered/{section}.png".casefold())
            mask_record = masks.get(slot)
            if not member or mask_record is None:
                continue
            if progress is not None:
                progress(f"Preparing {section.lower()} livery texture")
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
            alignment_masks[slot_index] = mask_values
            source_bounds = _projection_pixel_bounds(projection)
            axis_x, axis_x_scale = _projection_axis(projection, "xAxis", "xScale")
            axis_y, axis_y_scale = _projection_axis(projection, "yAxis", "yScale")
            tile = None
            if scale > 1:
                tile = _vector_paint_tile(section_layers.get(section, []), section, slot, projection,
                                          source_bounds, scale, game_folder, cancel_event)
                if tile is None:
                    quality_notes.append(f"{section}: retained original resolution because referenced artwork is unavailable locally")
            if tile is None:
                with bundle.open(member) as source, Image.open(source) as artwork:
                    warped = _warped_uv_layer(artwork, slot, projection)
                    tile = warped.crop(source_bounds)
            kind = "glass" if slot.startswith("glass_") else "body"
            filter_name = SECTION_FILTER[section]
            native_tile = tile if scale == 1 else tile.resize(
                (source_bounds[2]-source_bounds[0], source_bounds[3]-source_bounds[1]), Image.Resampling.BOX)
            tile_alpha = np.asarray(native_tile.getchannel("A"), dtype=np.uint8)
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
                    "projection_axis": [axis_x, axis_y, axis_x_scale, axis_y_scale],
                    "projection_mask_region": _projection_mask_region(projection),
                    "visible_pixels": visible,
                }
            )

    if not paint_tiles:
        raise LiveryRenderContractError("The package and local car masks have no shared livery sections.")
    aligned_bounds = (
        build_aligned_projection_bounds(
            projection_meshes,
            pending_records,
            alignment_masks,
            assembly,
        )
        if projection_meshes
        else {}
    )
    atlas_width = max(PAINT_ATLAS_WIDTH * scale, max(item["image"].width + PAINT_PADDING * 2 for item in paint_tiles))
    paint_atlas, placements = _pack_paint_tiles(paint_tiles, width=atlas_width)
    paint_filename = "section-paint.png"
    _save_png(paint_atlas, output / paint_filename)
    mask_filenames: list[str] = []
    for page_index, page in enumerate(mask_pages):
        filename = f"section-masks-{page_index}.png"
        _save_png(Image.fromarray(page), output / filename)
        mask_filenames.append(filename)

    records: list[dict[str, Any]] = []
    for record in pending_records:
        aligned = aligned_bounds.get(int(record["slot_index"]))
        if aligned is not None:
            record["projection_minimum"] = aligned["minimum"]
            record["projection_maximum"] = aligned["maximum"]
            record["projection_alignment"] = aligned["alignment"]
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
            "world_projection_fallback": True,
        },
        "assembly": assembly,
        "projection_bounds_source": (
            "local-chassis-mask-alignment-v1"
            if projection_meshes
            else "direct-uv-only"
            if local_mesh is not None
            else "viewer-legacy-bounds"
        ),
        "paint_size": list(paint_atlas.size),
        "quality_scale": scale,
        "quality_source": ("mixed-original-and-vector" if quality_notes else
                           "native-vector-crops" if scale > 1 else "package-section-images"),
        "quality_notes": quality_notes,
        "mask_size": list(ATLAS_SIZE),
        "filters": [
            name
            for name in ("all", "top", "left", "right", "front", "back")
            if name == "all" or any(record["filter"] == name for record in records)
        ],
        "files": files,
        "file_sha256": {name: file_sha256(output / name) for name in [paint_filename, *mask_filenames]},
        "sections": records,
    }
    temporary = index_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, index_path)
    return {**index, "root": str(output), "cache_hit": False}
