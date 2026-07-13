from __future__ import annotations

import re
import unittest
from pathlib import Path


UI_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = UI_ROOT / "src" / "kfps_ui"
QML_ROOT = UI_ROOT / "qml"


class ActivationIsolationTests(unittest.TestCase):
    def test_only_supporter_boundary_imports_activation_internals(self):
        allowed = {
            "activation_client.py",
            "activation_config.py",
            "activation_crypto.py",
            "activation_storage.py",
            "supporter_service.py",
        }
        import_pattern = re.compile(r"(?:from\s+\.activation_|import\s+.*activation_)")
        offenders = []
        for path in PYTHON_ROOT.rglob("*.py"):
            if path.name in allowed:
                continue
            if import_pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(UI_ROOT)))
        self.assertEqual(offenders, [], f"Activation internals escaped the supporter boundary: {offenders}")

    def test_activation_qml_references_stay_in_narrow_shell_and_settings_views(self):
        allowed = {
            Path("Main.qml"),
            Path("pages/SettingsPage.qml"),
            Path("shell/SupporterActivationNotice.qml"),
            Path("shell/SupporterPromoToast.qml"),
        }
        markers = ("activationState", "startActivation", "repairActivation", "deactivateDevice", "SupporterActivationNotice")
        offenders = []
        for path in QML_ROOT.rglob("*.qml"):
            relative = path.relative_to(QML_ROOT)
            if relative in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            if any(marker in text for marker in markers):
                offenders.append(str(relative))
        self.assertEqual(offenders, [], f"Activation UI escaped the intended shell/settings boundary: {offenders}")


if __name__ == "__main__":
    unittest.main()
