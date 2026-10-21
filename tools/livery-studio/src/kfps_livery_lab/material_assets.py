"""Bounded PC swatchbin decoding and local-only material texture staging.

Container/PCTextureContentHeader layout: ForzaTechStudio 4f373c5, MIT;
see docs/NATIVE-MATERIALS.md for full provenance. BC decoding uses installed
Pillow, not a hand-written GPU codec. This does not assign shader UV channels.
"""
from __future__ import annotations

import hashlib
import io
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import tempfile
import threading
import zipfile

from PIL import Image, __version__ as PILLOW_VERSION
from .prepare import workspace_path

LAB_ROOT = Path(__file__).resolve().parents[2]
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 4096 * 4096
PIPELINE_VERSION = "pc-swatch-straight-v1"
_FORMATS = {0: ("BC1", 71, 8), 1: ("BC2", 74, 16), 2: ("BC3", 77, 16),
            3: ("BC4_UNORM", 80, 8), 5: ("BC5_UNORM", 83, 16),
            9: ("BC7", 98, 16), 22: ("BC7_HQ", 98, 16)}
_RAW = {13: ("RGBA8", 4), 19: ("R8", 1), 20: ("A8", 1), 21: ("RG8", 2)}


class MaterialAssetError(ValueError):
    """An unsupported or unsafe texture is a reported omission, never guessed."""


def _range(data: bytes, offset: int, size: int) -> memoryview:
    if offset < 0 or size < 0 or offset > len(data) - size:
        raise MaterialAssetError("Texture structure or payload is truncated.")
    return memoryview(data)[offset:offset + size]


def _unpack(fmt: str, data: bytes, offset: int):
    return struct.unpack(fmt, _range(data, offset, struct.calcsize(fmt)))


def _level_size(encoding: int, width: int, height: int) -> int:
    if encoding in _FORMATS:
        return ((width + 3) // 4) * ((height + 3) // 4) * _FORMATS[encoding][2]
    if encoding in _RAW:
        return width * height * _RAW[encoding][1]
    raise MaterialAssetError(f"Unsupported native texture encoding {encoding}.")


def parse_pc_swatchbin(data: bytes) -> tuple[dict, bytes]:
    """Parse the FTS PC layout, validate every mip, return mip zero only."""
    if not isinstance(data, bytes) or not 16 <= len(data) <= MAX_SOURCE_BYTES:
        raise MaterialAssetError("Texture source exceeds the 32 MiB bound or is empty.")
    if _unpack("<I", data, 0)[0] != 0x47727562:
        raise MaterialAssetError("Not a Grub swatchbin bundle.")
    version = tuple(data[4:6])
    if version not in ((0, 0), (1, 0), (1, 1)):
        raise MaterialAssetError(f"Unsupported bundle version {version}.")
    start, count = (20, _unpack("<I", data, 16)[0]) if version == (1, 1) else (16, _unpack("<H", data, 6)[0])
    if not 1 <= count <= 64:
        raise MaterialAssetError("Texture blob count exceeds its bound.")
    _range(data, start, count * 24)
    textures = []
    for index in range(count):
        blob = start + index * 24
        tag, major, minor, metadata_count, metadata_offset, payload_offset, compressed, uncompressed = _unpack("<IBBHIIII", data, blob)
        if tag != 0x54584342:
            continue
        if (major, minor) not in ((0, 0), (1, 0), (1, 1)):
            raise MaterialAssetError("Only verified PC TXCB layouts are supported; Xbox tiled data is not decoded.")
        if compressed and uncompressed and compressed != uncompressed:
            raise MaterialAssetError("Compressed TXCB blobs are not supported.")
        payload_size = uncompressed or compressed
        if not payload_size:
            raise MaterialAssetError("Texture payload is empty.")
        _range(data, payload_offset, payload_size)
        if not 1 <= metadata_count <= 64:
            raise MaterialAssetError("Texture metadata count exceeds its bound.")
        _range(data, metadata_offset, metadata_count * 8)
        for index in range(metadata_count):
            entry = metadata_offset + index * 8
            tag, flags, relative = _unpack("<IHH", data, entry)
            if tag == 0x54584348:
                if payload_offset < max(start + count * 24, metadata_offset + metadata_count * 8, entry + relative + (flags >> 4)):
                    raise MaterialAssetError("Texture payload overlaps its container metadata.")
                header = bytes(_range(data, entry + relative, flags >> 4))
                textures.append((header, payload_offset, payload_size))
    if len(textures) != 1:
        raise MaterialAssetError("Exactly one texture header is required.")
    header, payload_offset, payload_size = textures[0]
    _range(header, 0, 64)
    width, height, depth = _unpack("<III", header, 24)
    packed, mip_count, flags = _unpack("<HBB", header, 36)
    transcoding, encoded_profile, target_profile, domain = _unpack("<iiii", header, 40)
    if not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > MAX_PIXELS:
        raise MaterialAssetError("Texture dimensions exceed the 4096/16-megapixel bound.")
    if depth != 1 or (packed & 0x3FFF) != 1 or packed >> 14 != 0 or flags & 1:
        raise MaterialAssetError("Only single-slice linear PC 2D textures are supported.")
    if flags & 2:
        raise MaterialAssetError("Premultiplied textures require a verified separate alpha path.")
    if transcoding != 0:
        raise MaterialAssetError("Transcoded or RLE texture data is not supported.")
    if encoded_profile not in (0, 1) or target_profile != encoded_profile:
        raise MaterialAssetError("Texture color conversion/profile is not supported.")
    if domain not in (0, 1, 2) or not 1 <= mip_count <= 16:
        raise MaterialAssetError("Invalid texture domain or mip count.")
    slices_offset = _unpack("<I", header, 56)[0]
    if slices_offset < 64:
        raise MaterialAssetError("Invalid slice table offset.")
    encoding, mips_offset, _ = _unpack("<iII", header, slices_offset)
    if mips_offset < slices_offset + 12:
        raise MaterialAssetError("Invalid mip table offset.")
    _range(header, mips_offset, mip_count * 12)
    end = 0
    levels = []
    for level in range(mip_count):
        size, offset, _ = _unpack("<III", header, mips_offset + level * 12)
        expected = _level_size(encoding, max(1, width >> level), max(1, height >> level))
        if size != expected or offset < end or offset > payload_size - size:
            raise MaterialAssetError("Texture mip dimensions, size, ordering or payload bounds are invalid.")
        levels.append({"level": level, "offset": offset, "bytes": size})
        end = offset + size
    if mip_count > max(width, height).bit_length():
        raise MaterialAssetError("Texture has more mip levels than its dimensions allow.")
    top = levels[0]
    payload = bytes(_range(data, payload_offset + top["offset"], top["bytes"]))
    metadata = {
        "width": width, "height": height, "source_mips": mip_count, "selected_mip": 0,
        "encoding": encoding, "format": (_FORMATS.get(encoding) or _RAW[encoding])[0],
        "color_space": "linear-srgb" if target_profile == 0 else "srgb",
        "encoded_profile": encoded_profile, "target_profile": target_profile,
        "domain": ("repeat", "clamp", "mirror")[domain], "premultiplied_alpha": False,
        "native_header_flags": flags, "source_sha256": hashlib.sha256(data).hexdigest(),
        "uv_channel": None, "uv_mapping_verified": False, "game_equivalent": False,
    }
    return metadata, payload


def _dds(metadata: dict, payload: bytes) -> bytes:
    header = bytearray(148)
    header[:4] = b"DDS "
    struct.pack_into("<7I", header, 4, 124, 0x81007, metadata["height"], metadata["width"], len(payload), 0, 1)
    struct.pack_into("<3I", header, 76, 32, 4, 0x30315844)
    struct.pack_into("<I", header, 108, 0x1000)
    # Use UNORM for byte decoding; retain the native transfer function separately.
    struct.pack_into("<5I", header, 128, _FORMATS[metadata["encoding"]][1], 3, 0, 1, 0)
    return bytes(header) + payload


def decode_swatchbin(data: bytes) -> tuple[Image.Image, dict]:
    metadata, payload = parse_pc_swatchbin(data)
    size = metadata["width"], metadata["height"]
    encoding = metadata["encoding"]
    try:
        if encoding in _FORMATS:
            with Image.open(io.BytesIO(_dds(metadata, payload))) as decoded:
                if decoded.size != size:
                    raise MaterialAssetError("DDS decoder dimensions changed unexpectedly.")
                image = decoded.convert("RGBA")
        elif encoding == 13:
            image = Image.frombytes("RGBA", size, payload)
        elif encoding == 19:
            image = Image.frombytes("L", size, payload).convert("RGBA")
        elif encoding == 20:
            image = Image.new("RGBA", size, (255, 255, 255, 255))
            image.putalpha(Image.frombytes("L", size, payload))
        else:
            r = Image.frombytes("L", size, payload[0::2])
            g = Image.frombytes("L", size, payload[1::2])
            image = Image.merge("RGBA", (r, g, Image.new("L", size, 0), Image.new("L", size, 255)))
    except (OSError, ValueError, NotImplementedError) as exc:
        raise MaterialAssetError(f"Pillow cannot decode this supported texture: {exc}") from exc
    metadata.update({"decoder": f"Pillow {PILLOW_VERSION}", "pipeline": PIPELINE_VERSION,
                     "rgba_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                     "decoded_mode": "RGBA", "flip_y": False,
                     "alpha_range": list(image.getextrema()[3])})
    return image, metadata


def _member_name(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 1024 or re.search(r"[\x00-\x1f\x7f:%?#]", value):
        raise MaterialAssetError("Invalid archive texture member.")
    value = value.replace("\\", "/")
    if value.startswith("/") or any(part in ("", ".", "..") for part in value.split("/")):
        raise MaterialAssetError("Archive texture paths cannot escape their archive.")
    if PurePosixPath(value).suffix.lower() != ".swatchbin":
        raise MaterialAssetError("Only swatchbin members may be staged.")
    return value


def _archive_guard(path: Path) -> None:
    if not path.is_file() or not 22 <= path.stat().st_size <= 2 * 1024**3:
        raise MaterialAssetError("Archive size is unsupported.")
    # Bound the central directory before ZipFile allocates its entry objects.
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 65557))
        tail = stream.read(65557)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        raise MaterialAssetError("Archive has no supported end record.")
    _, disk, central_disk, disk_count, count, central_size, central_offset, comment = struct.unpack_from("<4s4H2IH", tail, offset)
    if disk or central_disk or disk_count != count or count > 50000 or central_size > 16 * 1024**2 or central_offset + central_size > path.stat().st_size or offset + 22 + comment != len(tail):
        raise MaterialAssetError("Multi-disk, ZIP64 or oversized archive directories are unsupported.")


class MaterialAssetStore:
    """Thread-serialized content cache; never deletes existing files to make room."""

    def __init__(self, cache_root: Path, *, allowed_roots: list[Path], max_entries: int = 128, max_bytes: int = 256 * 1024**2):
        try:
            self.root = workspace_path(cache_root, lab_root=LAB_ROOT)
        except ValueError as exc:
            raise MaterialAssetError("Material cache must be a named directory under the authorized workspace.") from exc
        if not allowed_roots or len(allowed_roots) > 8:
            raise MaterialAssetError("Supply one to eight explicit read-only roots.")
        self.allowed_roots = tuple(Path(path).resolve(strict=True) for path in allowed_roots)
        if any(not path.is_dir() for path in self.allowed_roots):
            raise MaterialAssetError("Read-only roots must be directories.")
        if type(max_entries) is not int or not 1 <= max_entries <= 512 or type(max_bytes) is not int or not 1024 <= max_bytes <= 512 * 1024**2:
            raise MaterialAssetError("Invalid material cache bound.")
        self.max_entries, self.max_bytes = max_entries, max_bytes
        self.lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)

    def stage(self, archive: Path, member: str) -> dict:
        try:
            with self.lock:
                return self._stage(archive, member)
        except MaterialAssetError:
            raise
        except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise MaterialAssetError(f"Cannot stage native material texture: {exc}") from exc

    def _stage(self, archive: Path, member: str) -> dict:
        archive = Path(archive).resolve(strict=True)
        if not any(archive.is_relative_to(root) for root in self.allowed_roots):
            raise MaterialAssetError("Texture archive is outside the explicit read-only roots.")
        member = _member_name(member)
        _archive_guard(archive)
        with zipfile.ZipFile(archive) as bundle:
            if len(bundle.infolist()) > 50000:
                raise MaterialAssetError("Archive entry count exceeds its bound.")
            matches = [entry for entry in bundle.infolist() if entry.filename.replace("\\", "/").casefold() == member.casefold()]
            if len(matches) != 1:
                raise MaterialAssetError("Texture member is missing or ambiguous.")
            entry = matches[0]
            _member_name(entry.filename)
            if entry.flag_bits & 1 or not 1 <= entry.file_size <= MAX_SOURCE_BYTES or entry.file_size > max(1, entry.compress_size) * 2048:
                raise MaterialAssetError("Encrypted, oversized or excessive-ratio texture members are unsupported.")
            with bundle.open(entry) as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
            if len(data) != entry.file_size:
                raise MaterialAssetError("Texture member size does not match its archive record.")
        source_hash = hashlib.sha256(data).hexdigest()
        key = hashlib.sha256(f"{PIPELINE_VERSION}:{PILLOW_VERSION}:{source_hash}".encode("ascii")).hexdigest()
        with self.lock:
            if self.root.resolve() != self.root:
                raise MaterialAssetError("Material cache directory changed its resolved destination.")
            target = self.root / key
            if target.exists():
                return self._read(target, source_hash)
            entries = list(itertools.islice(self.root.iterdir(), self.max_entries + 1))
            if len(entries) >= self.max_entries:
                raise MaterialAssetError("Material texture cache entry limit reached.")
            occupied = 0
            for directory in entries:
                if not directory.is_dir() or directory.is_symlink() or directory.resolve().parent != self.root:
                    raise MaterialAssetError("Unexpected file or redirected directory in material cache.")
                children = list(itertools.islice(directory.iterdir(), 3))
                if {item.name for item in children} != {"image.png", "metadata.json"}:
                    raise MaterialAssetError("Unexpected files in material cache entry.")
                for item in children:
                    if not item.is_file() or item.is_symlink() or item.resolve().parent != directory:
                        raise MaterialAssetError("Unexpected redirected file in material cache.")
                    occupied += item.stat().st_size
            image, metadata = decode_swatchbin(data)
            try:
                encoded = io.BytesIO()
                image.save(encoded, format="PNG", compress_level=3)
                png = encoded.getvalue()
            finally:
                image.close()
            metadata["png_sha256"] = hashlib.sha256(png).hexdigest()
            metadata["png_bytes"] = len(png)
            description = json.dumps(metadata, sort_keys=True, indent=2).encode("utf-8")
            if occupied + len(png) + len(description) > self.max_bytes:
                raise MaterialAssetError("Material texture cache byte limit reached.")
            with tempfile.TemporaryDirectory(prefix=".stage-", dir=self.root) as temporary:
                temp = Path(temporary)
                (temp / "image.png").write_bytes(png)
                (temp / "metadata.json").write_bytes(description)
                # Reopen and verify before exposing an atomically renamed cache entry.
                self._read(temp, source_hash)
                os.rename(temp, target)
            return self._read(target, source_hash)

    def _read(self, target: Path, source_hash: str) -> dict:
        if target.resolve().parent != self.root or target.is_symlink():
            raise MaterialAssetError("Redirected material cache entry.")
        meta_path, image_path = target / "metadata.json", target / "image.png"
        for file in (meta_path, image_path):
            if not file.is_file() or file.is_symlink() or file.resolve().parent != target:
                raise MaterialAssetError("Missing or redirected material cache file.")
        if meta_path.stat().st_size > 16384 or image_path.stat().st_size > 80 * 1024**2:
            raise MaterialAssetError("Cached material exceeds its file-size bound.")
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            if metadata.get("pipeline") != PIPELINE_VERSION or metadata.get("source_sha256") != source_hash:
                raise MaterialAssetError("Material cache provenance mismatch.")
            png = image_path.read_bytes()
            if metadata.get("png_sha256") != hashlib.sha256(png).hexdigest():
                raise MaterialAssetError("Material cache image hash mismatch.")
            with Image.open(io.BytesIO(png)) as image:
                width, height = image.size
                if image.format != "PNG" or image.mode != "RGBA" or not 1 <= width <= 4096 or not 1 <= height <= 4096 or width * height > MAX_PIXELS:
                    raise MaterialAssetError("Invalid cached material image.")
                if image.size != (metadata.get("width"), metadata.get("height")) or hashlib.sha256(image.tobytes()).hexdigest() != metadata.get("rgba_sha256"):
                    raise MaterialAssetError("Material cache pixels do not match their record.")
                # Recompute for old entries too; this is evidence, not a stored alpha claim.
                metadata["alpha_range"] = list(image.getextrema()[3])
        except (OSError, json.JSONDecodeError, TypeError, AttributeError) as exc:
            raise MaterialAssetError(f"Invalid material cache entry: {exc}") from exc
        return {**metadata, "cache_key": target.name, "image_path": str(image_path)}
