from __future__ import annotations

import sys
import unittest
from pathlib import Path


UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))

from kfps_ui.window_geometry import (  # noqa: E402
    MINIMUM_HEIGHT,
    MINIMUM_WIDTH,
    ScreenRect,
    calculate_window_placement,
)


class WindowGeometryTests(unittest.TestCase):
    def test_qml_minimum_matches_python_placement_floor(self):
        metrics = (UI / "qml" / "Kfps" / "Theme" / "Metrics.qml").read_text(encoding="utf-8")
        self.assertIn(f"readonly property int minWidth: {MINIMUM_WIDTH}", metrics)
        self.assertIn(f"readonly property int minHeight: {MINIMUM_HEIGHT}", metrics)

    def test_fresh_window_fits_and_centers_on_primary_screen(self):
        placement = calculate_window_placement([ScreenRect(0, 0, 1920, 1040)])
        self.assertEqual((placement.width, placement.height), (1760, 957))
        self.assertEqual((placement.x, placement.y), (80, 41))
        self.assertFalse(placement.maximized)

    def test_fresh_window_respects_compact_logical_desktop(self):
        placement = calculate_window_placement([ScreenRect(0, 0, 1280, 680)])
        self.assertGreaterEqual(placement.width, MINIMUM_WIDTH)
        self.assertGreaterEqual(placement.height, MINIMUM_HEIGHT)
        self.assertLessEqual(placement.width, 1280)
        self.assertLessEqual(placement.height, 680)

    def test_saved_window_restores_to_its_monitor(self):
        screens = [ScreenRect(0, 0, 1920, 1040), ScreenRect(-1600, 0, 1600, 900)]
        saved = {"x": -1500, "y": 80, "width": 1200, "height": 700, "maximized": True}
        placement = calculate_window_placement(screens, saved)
        self.assertEqual((placement.x, placement.y), (-1500, 80))
        self.assertEqual((placement.width, placement.height), (1200, 700))
        self.assertTrue(placement.maximized)

    def test_missing_monitor_is_clamped_onto_primary(self):
        saved = {"x": 5000, "y": -3000, "width": 2500, "height": 1400}
        placement = calculate_window_placement([ScreenRect(100, 50, 1280, 720)], saved)
        self.assertEqual((placement.x, placement.y), (100, 50))
        self.assertEqual((placement.width, placement.height), (1280, 720))

    def test_explicit_audit_size_is_not_clamped_to_fake_offscreen_display(self):
        placement = calculate_window_placement(
            [ScreenRect(0, 0, 800, 800)],
            requested_width=2560,
            requested_height=1440,
        )
        self.assertEqual((placement.width, placement.height), (2560, 1440))


if __name__ == "__main__":
    unittest.main()
