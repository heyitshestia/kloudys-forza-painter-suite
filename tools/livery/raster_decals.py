from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path


class RasterDecalError(RuntimeError):
    pass


def resolve_fh6_decals_archive(game_folder: Path | str) -> Path:
    root = Path(game_folder).expanduser()
    candidates = [
        root,
        root / "media" / "livery" / "Decals.zip",
        root / "Content" / "media" / "livery" / "Decals.zip",
    ]
    for candidate in candidates:
        if candidate.is_file() and candidate.name.casefold() == "decals.zip":
            return candidate.resolve()
    raise RasterDecalError(
        f"FH6 built-in decal textures were not found below {root}. "
        "Choose the game folder or its Content folder."
    )


def _read_texture_surface(data: bytes) -> tuple[int, int, int, bytes]:
    if len(data) < 20 or data[:4] != b"burG":
        raise RasterDecalError("The built-in decal texture is not a supported bundle.")
    major, minor = data[4], data[5]
    position = 6
    if (major, minor) >= (1, 1):
        position += 10
        if position + 4 > len(data):
            raise RasterDecalError("The built-in decal texture header is truncated.")
        blob_count = struct.unpack_from("<I", data, position)[0]
        position += 4
    else:
        if position + 10 > len(data):
            raise RasterDecalError("The built-in decal texture header is truncated.")
        blob_count = struct.unpack_from("<H", data, position)[0]
        position += 10

    if blob_count <= 0 or blob_count > 1024:
        raise RasterDecalError("The built-in decal texture has an invalid blob table.")
    for index in range(blob_count):
        header = position + index * 0x18
        if header + 0x18 > len(data):
            break
        if data[header : header + 4] != b"BCXT":
            continue
        metadata_count = struct.unpack_from("<H", data, header + 6)[0]
        metadata_offset, pixel_offset, compressed_size, uncompressed_size = struct.unpack_from(
            "<IIII", data, header + 8
        )
        texture_header = None
        for metadata_index in range(metadata_count):
            record = metadata_offset + metadata_index * 8
            if record + 8 > len(data):
                break
            if data[record : record + 4] == b"HCXT":
                texture_header = record + struct.unpack_from("<H", data, record + 6)[0]
                break
        if texture_header is None or texture_header + 64 > len(data):
            raise RasterDecalError("The built-in decal texture has no usable content header.")

        width, height = struct.unpack_from("<II", data, texture_header + 0x18)
        packed = struct.unpack_from("<H", data, texture_header + 0x24)[0]
        transcoding = struct.unpack_from("<i", data, texture_header + 0x28)[0]
        slices_offset = struct.unpack_from("<I", data, texture_header + 0x38)[0]
        if packed >> 14:
            raise RasterDecalError("The built-in decal texture uses an unsupported tiled layout.")
        if not (0 < width <= 8192 and 0 < height <= 8192) or slices_offset == 0:
            raise RasterDecalError("The built-in decal texture has invalid dimensions.")
        slice_position = texture_header + slices_offset
        if slice_position + 4 > len(data):
            raise RasterDecalError("The built-in decal texture slice table is truncated.")
        slice_encoding = struct.unpack_from("<I", data, slice_position)[0]
        encoding = transcoding - 2 if transcoding > 1 else slice_encoding
        pixel_size = uncompressed_size or compressed_size
        if pixel_size <= 0 or pixel_offset + pixel_size > len(data):
            raise RasterDecalError("The built-in decal texture pixel data is truncated.")
        return width, height, encoding, data[pixel_offset : pixel_offset + pixel_size]
    raise RasterDecalError("The built-in decal texture has no supported image blob.")


def _bc7_dds(width: int, height: int, pixels: bytes) -> bytes:
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000
    pixel_format = struct.pack("<II4sIIIII", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
    header = (
        struct.pack("<IIIIIII", 124, flags, height, width, len(pixels), 0, 1)
        + bytes(44)
        + pixel_format
        + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    )
    # DXGI_FORMAT_BC7_UNORM, D3D10_RESOURCE_DIMENSION_TEXTURE2D, one array slice.
    return b"DDS " + header + struct.pack("<IIIII", 98, 3, 0, 1, 0) + pixels


def decode_fh6_decal_swatch(data: bytes):
    from PIL import Image

    width, height, encoding, pixels = _read_texture_surface(data)
    if encoding not in (9, 22):
        raise RasterDecalError(f"Built-in decal texture encoding {encoding} is not supported.")
    try:
        with Image.open(io.BytesIO(_bc7_dds(width, height, pixels))) as decoded:
            return decoded.convert("RGBA")
    except (OSError, ValueError) as exc:
        raise RasterDecalError("The built-in decal texture could not be decoded.") from exc


class FH6RasterDecalResolver:
    def __init__(self, game_folder: Path | str):
        self.archive = resolve_fh6_decals_archive(game_folder)
        self._cache: dict[int, object | None] = {}
        try:
            with zipfile.ZipFile(self.archive) as bundle:
                self._members = {name.casefold(): name for name in bundle.namelist()}
        except (OSError, zipfile.BadZipFile) as exc:
            raise RasterDecalError("The FH6 built-in decal archive is unreadable.") from exc

    def __call__(self, raster_id: int):
        raster_id = int(raster_id)
        if raster_id in self._cache:
            return self._cache[raster_id]
        candidates = [
            f"textures/decal{raster_id}.swatchbin",
            f"textures/decal{raster_id:03d}.swatchbin",
        ]
        member = next((self._members[name] for name in candidates if name in self._members), "")
        try:
            if not member:
                raise KeyError(raster_id)
            with zipfile.ZipFile(self.archive) as bundle:
                data = bundle.read(member)
            image = decode_fh6_decal_swatch(data)
        except (KeyError, OSError, zipfile.BadZipFile, RasterDecalError):
            image = None
        self._cache[raster_id] = image
        return image
