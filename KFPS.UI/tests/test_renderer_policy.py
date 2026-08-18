from __future__ import annotations

import unittest
from pathlib import Path
import sys


UI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI_ROOT / "src"))

from kfps_ui.renderer_policy import RendererPolicy, select_renderer_policy


class RendererPolicyTests(unittest.TestCase):
    def test_default_remains_the_tested_opengl_path(self):
        policy = select_renderer_policy({})
        self.assertEqual(policy, RendererPolicy("opengl", "KFPS default"))
        self.assertTrue(policy.persistent_scene_graph)

    def test_explicit_kfps_choice_wins_over_qt_environment(self):
        policy = select_renderer_policy(
            {"KFPS_QML_GRAPHICS": "d3d11", "QSG_RHI_BACKEND": "opengl"}
        )
        self.assertEqual(policy.name, "d3d11")
        self.assertEqual(policy.source, "KFPS_QML_GRAPHICS")

    def test_existing_qt_backend_is_respected(self):
        policy = select_renderer_policy({"QSG_RHI_BACKEND": "d3d11"})
        self.assertEqual(policy.name, "d3d11")
        self.assertEqual(policy.source, "QSG_RHI_BACKEND")

    def test_software_backend_disables_scene_graph_persistence(self):
        policy = select_renderer_policy({"QT_QUICK_BACKEND": "software"})
        self.assertEqual(policy.name, "software")
        self.assertFalse(policy.persistent_scene_graph)

    def test_unknown_backend_falls_back_with_a_diagnostic(self):
        policy = select_renderer_policy({"KFPS_QML_GRAPHICS": "mystery"})
        self.assertEqual(policy.name, "opengl")
        self.assertIn("Unsupported renderer", policy.warning)


if __name__ == "__main__":
    unittest.main()
