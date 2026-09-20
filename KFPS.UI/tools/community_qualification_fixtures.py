"""Build non-personal, reproducible Community qualification artwork."""
import json
import struct
import sys
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / 'KFPS.UI/src')]


def build(root):
    from PIL import Image, ImageDraw
    from tools.livery.package import create_full_livery_package, validate_full_livery_package
    root.mkdir(parents=True, exist_ok=True)
    for variant in range(4):
        shapes = []
        for i in range(3000):
            shapes.append(dict(type=(1, 2, 16)[i % 3],
                color=[(i * 17 + variant * 53) % 255, (i * 31) % 255, 170, 128 if i % 5 == 0 else 255],
                data=[(i % 60 - 30) * 12, (i // 60 - 25) * 12, 8 + variant, 9, i % 180]))
        (root / f'vinyl-{variant}.json').write_text(json.dumps({'shapes': shapes}), encoding='utf-8')
    for i, extension in enumerate(('png', 'jpg', 'webp')):
        image = Image.new('RGB', (1920, 1080), (24 + i * 40, 32, 48))
        draw = ImageDraw.Draw(image)
        for x in range(0, 1920, 120):
            draw.rectangle((x, 160, x + 60, 840), fill=((x // 8 + i * 57) % 255, 160, 190))
        draw.text((60, 60), f'KFPS SYNTHETIC QA - PHOTO {i+1} - NOT REAL ARTWORK', fill='white', font_size=42)
        image.save(root / f'photo-{i}.{extension}')
    payload = bytearray(0x40)
    payload[:4] = b'vlrc'
    struct.pack_into('<I', payload, 4, 1)
    struct.pack_into('<I', payload, 0x10, 1478)
    sections, counts = [], []
    for section in range(11):
        count = 400 if section < 3 else 0
        counts.append(count)
        shapes = bytearray()
        for i in range(count):
            shape = bytearray(32)
            shape[:2] = b'\x00\x02'
            struct.pack_into('<H', shape, 2, 101 + i % 2)
            struct.pack_into('<fffff', shape, 4, i % 90, (i % 20 - 10) * 15, (i // 20 - 10) * 15, .15, .15)
            shape[28:32] = bytes(((i * 17) % 255, 150, 220, 255))
            shapes.extend(shape)
        sections.append(bytes(shapes) + bytes(18 if count else 23))
    payload.extend(b'gyvl' + bytes(0x11) + b''.join(sections) + b'yrvl')
    payload.extend(struct.pack('<11I', *counts))
    packed = zlib.compress(payload)
    source = root / 'synthetic-native'
    source.mkdir(exist_ok=True)
    (source / 'C_livery').write_bytes(struct.pack('<II', len(packed), len(payload)) + packed)
    manifest = create_full_livery_package(source / 'C_livery', root / 'synthetic-audi.kfpslivery',
        game_folder=Path('C:/XboxGames/Forza Horizon 6/Content'),
        vehicle_index_cache=root / 'vehicle-index.json', model_code_override='AUD_2_SportQuattro_86',
        title_override='KFPS SYNTHETIC QA 1200 shapes')
    validate_full_livery_package(root / 'synthetic-audi.kfpslivery')
    (root / 'fixture-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({'vinyl_shapes': 3000, 'livery_counts': counts, 'package_bytes': (root / 'synthetic-audi.kfpslivery').stat().st_size}))


if __name__ == '__main__':
    build(Path(sys.argv[1]))
