"""Opt-in read-only installed-catalogue qualification; local cache writes only."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/livery-studio/src'))
from kfps_livery_lab import catalogue_cache, part_names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(ROOT / 'runtime')
    output.mkdir(parents=True, exist_ok=True)
    source = args.game_root / 'media/stripped/gamedbRC.slt'
    original = source.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    report = {'source_sha256': before, 'calls': []}
    for _ in range(3):
        start = time.perf_counter()
        result = catalogue_cache.load_installed_catalogue(args.game_root)
        elapsed = time.perf_counter() - start
        assert result['database'] is not None, result
        assert result['provenance']['current'], result['warnings']
        report['calls'].append({'seconds': elapsed, 'status': result['status'],
            'database_bytes': len(result['database']), 'provenance': result['provenance'],
            'warnings': result['warnings']})
    # Reuse cannot start a new provider, including in the metadata resolver.
    with patch.object(catalogue_cache, '_run_provider', side_effect=AssertionError('Unexpected rebuild')):
        assert catalogue_cache.load_installed_catalogue(args.game_root)['status'] == 'cached'
        mesh = ROOT / 'tools/livery-studio/runs/garage-builds-20261102/studio-car/mesh/vehicle.glb'
        data = mesh.read_bytes()
        document = json.loads(data[20:20 + int.from_bytes(data[12:16], 'little')])
        options = document['scenes'][document.get('scene', 0)]['extras']['kfps_part_options']
        names = part_names.load_part_names(args.game_root,
            {'car_id': 344, 'model_code': 'nis_fairladyz_03'}, options,
            reference_config=output / 'no-reference.json')
        assert names['same_build_verified'] and not names['reference_only'], names['warnings']
        assert len(names['names']) == 26 and names['non_visual_options'], names
        report['names'] = {'source': names['source'], 'count': len(names['names']),
                          'warnings': names['warnings'], 'same_build_verified': True}
    db = sqlite3.connect(':memory:')
    try:
        db.deserialize(result['database'])
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA query_only=ON')
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        report['cars'] = db.execute('SELECT count(*) FROM Data_Car').fetchone()[0]
        index = json.loads((ROOT / 'tools/livery-studio/runs/garage-builds-20261102/vehicle-index.json').read_text())['vehicles']
        rows = dict(db.execute('SELECT Id,MediaName FROM Data_Car'))
        matches = [int(i) for i, row in index.items() if rows[int(i)].lower() == row['model_code'].lower()]
        assert len(matches) == len(index) == len(rows)
        report['case_insensitive_model_matches'] = len(matches)
    finally:
        db.close()
    # Test the actual local reader boundary with damaged, private in-memory copies.
    config = json.loads((ROOT / 'runtime/garage/catalogue-reader.json').read_text())
    report['damaged_source_rejections'] = []
    for label, position in [('header', 20), ('body', 40), ('trailer', 36 + 128 * 1024)]:
        changed = bytearray(original)
        changed[position] ^= 1
        process = subprocess.run([config['python'], '-I', '-B', config['script'], '--stdin'],
            input=bytes(changed), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert process.returncode != 0 and process.stdout == b'', label
        report['damaged_source_rejections'].append(label)
    assert before == hashlib.sha256(source.read_bytes()).hexdigest()
    report['source_unchanged'] = True
    report['passed'] = True
    (output / 'installed-catalogue.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
