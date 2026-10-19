"""Bounded local extraction of explicitly referenced native material textures.

This does not assign PBR meanings, implement native shaders, or change mesh UVs.
The wire layout is documented by the MIT-licensed FTS reference in FTS-REFERENCE.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import zipfile

from PIL import Image

MAX_SOURCE = 64 * 1024 * 1024
MAX_PIXELS = 16 * 1024 * 1024
MAX_TOTAL_PIXELS = 128 * 1024 * 1024
MAX_REFERENCES = 512


def _unpack(data, fmt, offset):
    size = struct.calcsize('<' + fmt)
    if offset < 0 or offset + size > len(data):
        raise ValueError('Native texture field exceeds bounds')
    values = struct.unpack_from('<' + fmt, data, offset)
    return values[0] if len(values) == 1 else values


def _slice(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError('Native texture record exceeds bounds')
    return data[offset:offset + size]


def resolve_reference(reference, car_code):
    if not isinstance(reference, str) or not isinstance(car_code, str):
        raise ValueError('Texture reference must be text')
    path = reference.replace('\\', '/')
    parts = path.split('/')
    if len(path) > 1024 or len(parts) < 6 or parts[:3] != ['game:', 'media', 'cars']:
        # Native path namespaces are case insensitive, unlike arbitrary URLs.
        if len(path) > 1024 or len(parts) < 6 or [p.lower() for p in parts[:3]] != ['game:', 'media', 'cars']:
            raise ValueError('Unsupported native texture namespace')
    if any(not p or p in ('.', '..') or ':' in p or '\0' in p for p in parts[3:]):
        raise ValueError('Unsafe native texture path')
    if not path.lower().endswith('.swatchbin'):
        raise ValueError('Native reference is not a swatchbin')
    if parts[3].lower() == '_library' and parts[4].lower() == 'textures':
        return 'shared', '/'.join(parts[5:])
    if parts[3].lower() == car_code.lower() and parts[4].lower() == 'textures':
        return 'car', '/'.join(parts[4:])
    raise ValueError('Foreign car or unsupported native texture resource')


def decode_texture(data):
    if not isinstance(data, bytes) or len(data) > MAX_SOURCE:
        raise ValueError('Texture exceeds source limit')
    if _unpack(data, 'I', 0) != 0x47727562:
        raise ValueError('Not a native texture bundle')
    version = _unpack(data, 'BB', 4)
    if version not in ((1, 0), (1, 1)):
        raise ValueError('Unsupported texture bundle version')
    count, start = (_unpack(data, 'I', 16), 20) if version >= (1, 1) else (_unpack(data, 'H', 6), 16)
    if count < 1 or count > 128:
        raise ValueError('Invalid texture blob count')
    candidates = []
    for index in range(count):
        tag, major, minor, nmeta, moff, off, packed, size = _unpack(data, 'IBBHIIII', start + index * 24)
        if tag != 0x54584342:
            continue
        if (major, minor) != (0, 0) or nmeta > 32 or (size and packed != size):
            raise ValueError('Unsupported compressed native texture blob')
        payload = _slice(data, off, size or packed)
        headers = []
        for mid in range(nmeta):
            at = moff + mid * 8
            mtag, flags, relative = _unpack(data, 'IHH', at)
            if mtag == 0x54584348:
                headers.append(_slice(data, at + relative, flags >> 4))
        if len(headers) != 1:
            raise ValueError('Missing or ambiguous PC texture header')
        candidates.append((headers[0], payload))
    if len(candidates) != 1:
        raise ValueError('Missing or ambiguous texture content blob')
    header, payload = candidates[0]
    width, height, depth, slices, mips, flags, transcoding, color, target, domain, slice_offset, _ = _unpack(header, 'IIIHBBiiiiII', 24)
    if not (0 < width <= 8192 and 0 < height <= 8192 and width * height <= MAX_PIXELS):
        raise ValueError('Texture dimensions exceed limit')
    if depth != 1 or slices != 1 or not 1 <= mips <= 16 or flags & 3 or transcoding != 0:
        raise ValueError('Array/cube/premultiplied/transcoded texture is unsupported')
    if color not in (0, 1, 2, 3) or target not in (0, 1, 2, 3):
        raise ValueError('Unsupported native color profile')
    encoding, mip_offset, _ = _unpack(header, 'III', slice_offset)
    byte_count, byte_offset, _ = _unpack(header, 'III', mip_offset)
    encoded = _slice(payload, byte_offset, byte_count)
    block = {
        0: (8, 'RGBA', 1, 'DXT1', 'RGBA'), 1: (16, 'RGBA', 2, 'DXT3', 'RGBA'),
        2: (16, 'RGBA', 3, 'DXT5', 'RGBA'), 3: (8, 'L', 4, 'BC4', 'R'),
        5: (16, 'RGB', 5, 'BC5', 'RG'), 9: (16, 'RGBA', 7, 'BC7', 'RGBA'),
        22: (16, 'RGBA', 7, 'BC7', 'RGBA'),
    }
    raw = {13: ('RGBA', 4, 'RGBA'), 19: ('L', 1, 'R'), 20: ('L', 1, 'A'), 21: ('LA', 2, 'RG')}
    if encoding in block:
        block_bytes, mode, decoder, fmt, channels = block[encoding]
        expected = ((width + 3) // 4) * ((height + 3) // 4) * block_bytes
        if len(encoded) != expected:
            raise ValueError('Block-compressed mip size mismatch')
        try:
            image = Image.frombytes(mode, (width, height), encoded, 'bcn', (decoder, fmt))
        except (OSError, ValueError) as exc:
            raise ValueError('Native block decoding failed') from exc
    elif encoding in raw:
        mode, stride, channels = raw[encoding]
        if len(encoded) != width * height * stride:
            raise ValueError('Raw mip size mismatch')
        image = Image.frombytes(mode, (width, height), encoded)
    else:
        raise ValueError(f'Unsupported native texture encoding {encoding}')
    return image, dict(width=width, height=height, encoding=encoding, mip=0,
        declared_mips=mips, native_channels=channels, png_mode=image.mode,
        color_profile=color, target_color_profile=target, domain=domain,
        premultiplied_alpha=False, flags=flags, transcoding=transcoding,
        decoded_pixels_sha256=hashlib.sha256(image.tobytes()).hexdigest(),
        channel_note='BC5 B is decoder-derived; RG8 PNG L/A store native R/G. No shader channel meaning inferred.',
        color_conversion_applied=False, orientation_changed=False)


def _safe_output(output):
    output = Path(os.path.abspath(output))
    lab = Path(__file__).resolve().parents[2]
    output.relative_to(lab / 'runs')
    for p in [output, *output.parents]:
        if p.exists() and (p.is_symlink() or getattr(p.stat(follow_symlinks=False), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError('Output path contains a reparse point')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Texture output must be a new or empty run directory')
    return output


def _json_chunk(glb):
    with Path(glb).open('rb') as stream:
        magic, version, size, length, kind = _unpack(stream.read(20), 'IIIII', 0)
        if magic != 0x46546c67 or version != 2 or kind != 0x4e4f534a or length > 32 * 1024 * 1024 or length > size - 20:
            raise ValueError('Invalid or excessive GLB JSON')
        chunk = stream.read(length)
        if len(chunk) != length:
            raise ValueError('Truncated GLB JSON')
        return json.loads(chunk)


def prepare_material_textures(glb, car_archive, shared_archive, output):
    """Return manifest; inputs read only, all PNGs/manifest in a fresh run directory."""
    output = _safe_output(output)
    doc = _json_chunk(glb)
    refs = set()
    for mesh in doc.get('meshes', []):
        material = mesh.get('extras', {}).get('kfps_native_material') or {}
        for parameter in material.get('parameters', []):
            if parameter.get('type') == 'Texture2D' and isinstance(parameter.get('value'), dict):
                path = parameter['value'].get('path')
                if isinstance(path, str) and path:
                    refs.add(path)
        if len(refs) > MAX_REFERENCES:
            raise ValueError('Native material texture reference limit exceeded')
    output.mkdir(parents=True, exist_ok=True)
    entries, total_pixels, total_bytes = [], 0, 0
    with zipfile.ZipFile(car_archive) as car, zipfile.ZipFile(shared_archive) as shared:
        archives, maps = {'car': car, 'shared': shared}, {}
        for key, archive in archives.items():
            if len(archive.infolist()) > 100000:
                raise ValueError('Archive entry count exceeds limit')
            members = {}
            for entry in archive.infolist():
                normalized = entry.filename.lower()
                if normalized in members:
                    raise ValueError('Ambiguous case-insensitive archive member')
                members[normalized] = entry
            maps[key] = members
        for reference in sorted(refs):
            record = {'reference': reference, 'status': 'unsupported'}
            try:
                namespace, name = resolve_reference(reference, Path(car_archive).stem)
                info = maps[namespace].get(name.lower())
                if info is None:
                    raise ValueError('Exact native texture member not found')
                if info.file_size <= 0 or info.file_size > MAX_SOURCE or total_bytes + info.file_size > 256 * 1024 * 1024:
                    raise ValueError('Texture source byte budget exceeded')
                total_bytes += info.file_size
                with archives[namespace].open(info) as stream:
                    source = stream.read(MAX_SOURCE + 1)
                if len(source) != info.file_size or len(source) > MAX_SOURCE:
                    raise ValueError('Texture length changed or exceeded budget')
                image, meta = decode_texture(source)
                total_pixels += meta['width'] * meta['height']
                if total_pixels > MAX_TOTAL_PIXELS:
                    image.close()
                    raise ValueError('Aggregate decoded texture pixel budget exceeded')
                digest = hashlib.sha256(source).hexdigest()
                filename = digest + '.png'
                destination = output / filename
                try:
                    if not destination.exists():
                        with destination.open('xb') as stream:
                            image.save(stream, format='PNG')
                    with Image.open(destination) as reread:
                        if reread.mode != image.mode or reread.size != image.size or reread.tobytes() != image.tobytes():
                            raise ValueError('PNG pixel round trip failed')
                finally:
                    image.close()
                record.update(status='decoded', source_archive=namespace, source_entry=info.filename,
                    source_sha256=digest, source_bytes=len(source), image=filename,
                    image_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(), **meta)
            except (ValueError, OSError, KeyError, zipfile.BadZipFile, NotImplementedError) as exc:
                record['error'] = str(exc)
            entries.append(record)
    manifest = dict(format='kfps-native-material-textures-v1', textures=entries,
        decoded=sum(x['status'] == 'decoded' for x in entries), referenced=len(entries),
        source_bytes=total_bytes, decoded_pixels=total_pixels, shader_equivalence_verified=False,
        inherited_materials_resolved=False, material_overrides_applied=False,
        contract='Exact direct native Texture2D references only. Paths relative to this manifest. No PBR meaning, UV replacement, or game fidelity claim.')
    with (output / 'manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('glb', 'car-archive', 'shared-archive', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    report = prepare_material_textures(args.glb, args.car_archive, args.shared_archive, args.output)
    print(json.dumps({k: report[k] for k in ('decoded', 'referenced', 'source_bytes', 'decoded_pixels')}))
