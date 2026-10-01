"""Launch-independent graphics policy; no user profile or window is opened."""
import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "KFPS.Editor/src"))
from kfps_editor import baseline, graphics
from kfps_editor.graphics_probe import Adapter, adapter_identity, present_adapters

FAULTY = Adapter(*graphics.KNOWN_FAULTY)


class GraphicsSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "runtime/qml-shell-settings.json"
        self.path.parent.mkdir()

    def save(self, value):
        self.path.write_text(json.dumps({"editorGraphics": value, "theme": "keep"}))

    def select(self, adapters=(FAULTY,)):
        return graphics.select_policy(self.root, probe=lambda: adapters)

    def test_exact_auto_match_and_no_preferences_written(self):
        selected = self.select()
        self.assertEqual((selected.mode, selected.backend, selected.reason),
                         ("auto", "d3d11", "known-driver-workaround"))
        self.assertFalse(self.path.exists())

    def test_unknown_updated_driver_and_other_boards_stay_unchanged(self):
        for adapter in (Adapter(0x10DE, 0x2684, 1, FAULTY.driver),
                        Adapter(0x8086, 0x1234, 1, FAULTY.driver),
                        Adapter(FAULTY.vendor, FAULTY.device, 1, FAULTY.driver),
                        Adapter(FAULTY.vendor, 0x1234, FAULTY.subsystem, FAULTY.driver),
                        Adapter(FAULTY.vendor, FAULTY.device, FAULTY.subsystem, "32.0.31041.1005"),
                        Adapter(FAULTY.vendor, FAULTY.device, FAULTY.subsystem, "26.8.1"),
                        Adapter(FAULTY.vendor, FAULTY.device, FAULTY.subsystem, "")):
            with self.subTest(adapter=adapter):
                self.assertEqual(self.select((adapter,)).backend, "opengl")

    def test_ambiguous_unknown_and_no_adapters_preserve_default(self):
        for adapters in ((), (FAULTY, FAULTY), (FAULTY, Adapter(None, None, None, ""))):
            with self.subTest(adapters=adapters):
                self.assertEqual(self.select(adapters).backend, "opengl")

    def test_detection_is_fresh_not_cached(self):
        updated = Adapter(FAULTY.vendor, FAULTY.device, FAULTY.subsystem, "32.0.31041.1005")
        self.save("auto")
        with patch("kfps_editor.graphics_probe.present_adapters", side_effect=[(FAULTY,), (updated,), (FAULTY,)]) as probe:
            self.assertEqual([graphics.select_policy(self.root).backend for _ in range(3)],
                             ["d3d11", "opengl", "d3d11"])
            self.assertEqual(probe.call_count, 3)
        self.assertEqual(json.loads(self.path.read_text())["editorGraphics"], "auto")

    def test_manual_selections_bypass_probe_and_preserve_other_settings(self):
        for mode in ("opengl", "d3d11"):
            self.save(mode)
            original = self.path.read_bytes()
            with patch("kfps_editor.graphics_probe.present_adapters", side_effect=AssertionError("Must not probe")):
                selected = graphics.select_policy(self.root)
            self.assertEqual(selected.backend, mode)
            self.assertEqual(selected.reason, "user-choice")
            self.assertEqual(self.path.read_bytes(), original)

    def test_bad_settings_use_auto_without_repair_writes(self):
        for payload in (b"{", b"[]", b'{"editorGraphics": []}', b'{"editorGraphics": "vulkan"}',
                        b"x" * (1024 * 1024 + 1), b"\xff\xfe"):
            self.path.write_bytes(payload)
            self.assertEqual(self.select().backend, "d3d11")
            self.assertEqual(self.path.read_bytes(), payload)

    def test_settings_read_and_probe_failures_do_not_block_startup(self):
        with patch.object(Path, "open", side_effect=PermissionError()):
            self.assertEqual(self.select().settings_status, "unreadable")
        for error in (OSError("unavailable"), ValueError("bad data")):
            with patch("kfps_editor.graphics_probe.present_adapters", side_effect=error):
                self.assertEqual(graphics.select_policy(self.root).backend, "opengl")

    def test_hardware_id_uses_numeric_pci_identity_not_display_name(self):
        self.assertEqual(adapter_identity([r"PCI\VEN_1002&DEV_744C&SUBSYS_53051849&REV_C8"], FAULTY.driver), FAULTY)
        self.assertEqual(adapter_identity([r"pci\ven_1002&dev_744c&subsys_53051849"], FAULTY.driver), FAULTY)
        for ids in (["AMD Radeon RX 7900 XTX"], [r"PCI\VEN_1002&DEV_744C"], ["ROOT\\DISPLAY"]):
            self.assertIsNone(adapter_identity(ids, FAULTY.driver).vendor)

    def test_real_device_probe_returns_structured_nonidentifying_fields(self):
        for adapter in present_adapters():
            self.assertIsInstance(adapter, Adapter)
            self.assertIsInstance(adapter.driver, str)


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
        self.assertEqual(evidence["policy"], graphics.POLICY)
        self.assertEqual(evidence["requested_backend"], "opengl")
        self.assertEqual(evidence["qt_graphics_api"], "OpenGL")

    def test_both_backends_use_matching_environment_and_qt_api(self):
        for backend, api in (("opengl", "OpenGL"), ("d3d11", "Direct3D11")):
            selection = graphics.Selection(backend=backend)
            env = {"QSG_RHI_BACKEND": "software", "QT_QUICK_BACKEND": "software"}
            graphics.configure_environment(env, selection)
            self.assertEqual(env, {"QSG_RHI_BACKEND": backend})
            self.assertEqual(graphics.configure_qt(selection)["qt_graphics_api"], api)

    def test_startup_configures_graphics_before_app_and_host(self):
        tree = ast.parse((ROOT / "KFPS.Editor/src/kfps_editor/cli.py").read_text())
        calls = {node.func.id: node.lineno for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertLess(calls["select_policy"], calls["configure_environment"])
        self.assertLess(calls["configure_environment"], calls["verify"])
        self.assertLess(calls["verify"], calls["configure_qt"])
        self.assertLess(calls["configure_qt"], calls["QApplication"])
        self.assertLess(calls["QApplication"], calls["EditorDesktop"])


if __name__ == "__main__":
    unittest.main()
