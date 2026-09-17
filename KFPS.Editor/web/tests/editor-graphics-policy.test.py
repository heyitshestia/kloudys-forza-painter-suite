"""Launch-independent graphics policy; no user profile or window is opened."""
import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor import baseline, graphics


class GraphicsPolicyTests(unittest.TestCase):
    def test_external_and_internal_match(self):
        external = baseline.isolated_environment({"PATH": "keep"})
        internal = baseline.isolated_environment({"PATH": "keep", "QSG_RHI_BACKEND": "opengl"})
        for env in (external, internal):
            graphics.configure_environment(env)
        self.assertEqual(external, internal)
        self.assertEqual(external["QSG_RHI_BACKEND"], "opengl")

    def test_conflicting_parent_policies_are_removed(self):
        for backend in ("d3d11", "d3d12", "vulkan", "software", "opengl", ""):
            with self.subTest(backend=backend):
                env = {"QSG_RHI_BACKEND": backend, "qsg_render_loop": "basic",
                       "QT_QUICK_BACKEND": "software", "PATH": "keep"}
                graphics.configure_environment(env)
                self.assertEqual(env, {"QSG_RHI_BACKEND": "opengl", "PATH": "keep"})

    def test_policy_is_idempotent_and_keeps_test_debugging(self):
        env = {"QTWEBENGINE_REMOTE_DEBUGGING": "12345"}
        graphics.configure_environment(env)
        first = dict(env)
        graphics.configure_environment(env)
        self.assertEqual(first, env)

    def test_shared_launcher_keeps_reporting_policy_editor_normalizes_its_own(self):
        env = baseline.isolated_environment({"QSG_RHI_BACKEND": "d3d11"})
        self.assertEqual(env, baseline.isolated_environment(env))
        self.assertEqual(env["QSG_RHI_BACKEND"], "d3d11")
        graphics.configure_environment(env)
        self.assertEqual(env["QSG_RHI_BACKEND"], "opengl")

    def test_qt_policy_is_explicit(self):
        from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
        evidence = graphics.configure_qt()
        self.assertEqual(QQuickWindow.graphicsApi(), QSGRendererInterface.GraphicsApi.OpenGL)
        self.assertEqual(evidence, {"policy": "editor-opengl-v1", "requested_backend": "opengl",
                                    "qt_graphics_api": "OpenGL"})

    def test_startup_configures_graphics_before_app_and_host(self):
        tree = ast.parse((ROOT / "KFPS.Editor/src/kfps_editor/cli.py").read_text())
        calls = {node.func.id: node.lineno for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertLess(calls["configure_environment"], calls["verify"])
        self.assertLess(calls["verify"], calls["configure_qt"])
        self.assertLess(calls["configure_qt"], calls["QApplication"])
        self.assertLess(calls["QApplication"], calls["EditorDesktop"])


if __name__ == "__main__":
    unittest.main()
