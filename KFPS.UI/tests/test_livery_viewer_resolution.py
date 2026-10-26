"""Real pixel and cache contracts for both read-only viewer resolution levels."""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/livery-studio/src')]
from tools.livery import render_contract as native
from kfps_livery_lab.readonly_prepare import square_mask_atlas


class ViewerResolutionPixelsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.layers = [{'type': 1048679, 'source_section': 'Top',
                        'data': [0, 0, .18, .18, 19, 0, 0], 'color': [255, 30, 150, 255]}]
        self.package = self.root / 'livery.kfpslivery'
        buffer = io.BytesIO()
        Image.new('RGBA', (2048, 1024), (20, 120, 240, 255)).save(buffer, format='PNG')
        with zipfile.ZipFile(self.package, 'w') as archive:
            archive.writestr('projection/rendered/Top.png', buffer.getvalue())
        self.prepared = {
            'manifest': {'inspection_runtime': {'render_contract': {'mask_size': [2048, 2048]}}},
            'editor_config': {'sections': [{'section': 'Top', 'slot_index': 0,
                'source_region': [984/2048, 984/2048, 1064/2048, 1064/2048],
                'atlasToLocal': [1, 0, 0, 0, 1, 0]}]}}

    def tearDown(self):
        self.temp.cleanup()

    def square(self, scale, provider=True):
        output = self.root / f'q{scale}-{provider}'
        result = square_mask_atlas(self.package, self.prepared, output,
            quality_scale=scale, layer_provider=(lambda: self.layers) if provider else None)
        return result, output

    def tile(self, contract, output):
        with Image.open(output / contract['files']['paint']) as image:
            bounds = [round(value * image.size[i % 2])
                      for i, value in enumerate(contract['sections'][0]['paint_region'])]
            return image.crop(bounds)

    def test_square_masks_rerender_vectors_and_double_actual_tile_dimensions(self):
        before = copy.deepcopy(self.prepared)
        standard, std_root = self.square(2)
        high, high_root = self.square(4)
        std_tile, high_tile = self.tile(standard, std_root), self.tile(high, high_root)
        self.assertEqual((160, 160), std_tile.size)
        self.assertEqual((320, 320), high_tile.size)
        self.assertEqual('native-vector-crops', high['quality_source'])
        self.assertEqual([2048, 2048], high['mask_size'])
        self.assertEqual(before, self.prepared)
        self.assertEqual(standard['sections'][0]['source_region'], high['sections'][0]['source_region'])
        self.assertGreater(np.count_nonzero(np.asarray(high_tile)[..., 3]), 100)
        # It must come from the pink vectors, not the blue saved PNG, and must
        # not be a resized copy of the Standard texture.
        self.assertGreater(np.asarray(high_tile)[..., 0].max(), 240)
        self.assertNotEqual(high_tile.tobytes(), std_tile.resize(high_tile.size).tobytes())
        reduced = high_tile.resize(std_tile.size, Image.Resampling.BOX)
        error = np.abs(np.asarray(reduced).astype(float) - np.asarray(std_tile).astype(float)).mean()
        self.assertLess(error, 4)

    def test_square_without_private_source_capability_keeps_saved_images(self):
        result, output = self.square(4, provider=False)
        self.assertEqual(1, result['quality_scale'])
        self.assertEqual((80, 80), self.tile(result, output).size)
        self.assertEqual((20, 120, 240, 255), self.tile(result, output).getpixel((20, 20)))

    def test_square_missing_referenced_art_retains_original_without_fake_upscale(self):
        with patch.object(native, '_vector_paint_affine', return_value=None):
            result, output = self.square(4)
        self.assertEqual('mixed-original-and-vector', result['quality_source'])
        self.assertEqual((80, 80), self.tile(result, output).size)
        self.assertTrue(result['quality_notes'])

    def test_square_cancellation_stops_before_writing_artifacts(self):
        event = threading.Event()
        event.set()
        output = self.root / 'cancelled'
        with self.assertRaises(InterruptedError):
            square_mask_atlas(self.package, self.prepared, output, quality_scale=4,
                              layer_provider=lambda: self.layers, cancel_event=event)
        self.assertFalse(output.exists())

    def test_rectangular_mask_cache_separates_levels_and_preserves_masks_and_uvs(self):
        mask = Image.new('L', (2048, 1024), 0)
        mask.paste(255, (984, 472, 1064, 552))
        projection = dict(left='-40', right='40', top='40', bottom='-40',
                          xAxis='x', yAxis='y', xScale='1', yScale='1')
        asset = SimpleNamespace(archive_size=1, archive_mtime_ns=1, model_code='TEST')
        output = self.root / 'rectangle'
        with patch.object(native, '_archive_masks', return_value={'top': (mask, projection, 'test')}), \
             patch.object(native, 'read_vehicle_assembly_metadata', return_value={}):
            def build(scale):
                return native.build_local_livery_atlases(self.package, asset, output,
                    quality_scale=scale, layer_provider=lambda: self.layers)
            standard = build(2)
            standard_tile = self.tile(standard, output)
            mask_hashes = [native.file_sha256(output / name) for name in standard['files']['masks']]
            self.assertTrue(build(2)['cache_hit'])
            high = build(4)
            self.assertFalse(high['cache_hit'])
            high_tile = self.tile(high, output)
            self.assertEqual((standard_tile.width*2, standard_tile.height*2), high_tile.size)
            self.assertEqual(mask_hashes, [native.file_sha256(output / name) for name in high['files']['masks']])
            self.assertEqual(standard['uv_contract'], high['uv_contract'])
            self.assertTrue(build(4)['cache_hit'])
            self.assertFalse(build(2)['cache_hit'])
            self.assertEqual(standard_tile.tobytes(), self.tile(standard, output).tobytes())

    def test_atlas_limits_reject_before_allocating(self):
        fake_image = SimpleNamespace(width=64, height=17000)
        for scale in (1, 2, 4):
            with self.subTest(scale=scale), patch.object(native.Image, 'new') as allocate:
                with self.assertRaises(native.LiveryRenderContractError):
                    native._pack_paint_tiles([{'section': 'Top', 'slot_index': 0, 'image': fake_image}],
                                             width=8192, quality_scale=scale)
                allocate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
