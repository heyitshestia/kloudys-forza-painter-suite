from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np


UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path.insert(0, str(ROOT))

from tools.livery.portable_mesh_converter import LocalProjectionMesh
from tools.livery.projection_alignment import (
    build_aligned_projection_bounds,
    optimize_projection_alignment,
)


class LiveryProjectionAlignmentTests(unittest.TestCase):
    def test_mask_fit_accepts_a_clear_translation(self):
        source = np.zeros((96, 128), dtype=bool)
        target = np.zeros_like(source)
        source[16:80, 20:90] = True
        target[22:86, 27:97] = True

        alignment, report = optimize_projection_alignment(source, target)

        self.assertTrue(report["accepted"])
        self.assertGreater(report["cost_improvement"], 0.05)
        self.assertGreater(alignment.offset_x, 0.0)
        self.assertGreater(alignment.offset_y, 0.0)

    def test_mask_fit_keeps_locator_anchored_longitudinal_axis(self):
        source = np.zeros((96, 128), dtype=bool)
        target = np.zeros_like(source)
        source[16:80, 20:90] = True
        target[22:86, 27:97] = True

        alignment, report = optimize_projection_alignment(source, target, lock_x=True)

        self.assertTrue(report["accepted"])
        self.assertEqual(1.0, alignment.scale_x)
        self.assertEqual(0.0, alignment.offset_x)
        self.assertGreater(alignment.offset_y, 0.0)

    def test_projection_bounds_include_fit_diagnostics(self):
        mesh = LocalProjectionMesh(
            name="synthetic",
            role="paint",
            projection_sides=1,
            positions=np.asarray([
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [1.0, 1.0, 0.0],
                [0.0, 1.0, 0.0],
            ], dtype=np.float32),
            normals=np.asarray([[0.0, 0.0, 1.0]] * 4, dtype=np.float32),
            indices=np.asarray([0, 1, 2, 0, 2, 3], dtype=np.int64),
        )
        mask = np.zeros((1024, 2048), dtype=np.uint8)
        mask[51:973, 102:1946] = 255
        section = {
            "slot_index": 0,
            "projection_axis": [0, 1, 1.0, 1.0],
            "projection_mask_region": [0.0, 1.0, 0.0, 1.0],
            "facing": [0.0, 0.0, 1.0],
        }

        result = build_aligned_projection_bounds([mesh], [section], {0: mask}, {})[0]

        self.assertEqual(2, len(result["minimum"]))
        self.assertEqual(2, len(result["maximum"]))
        self.assertTrue(result["alignment"]["accepted"])
        self.assertEqual(2, result["alignment"]["rasterized_triangles"])


if __name__ == "__main__":
    unittest.main()
