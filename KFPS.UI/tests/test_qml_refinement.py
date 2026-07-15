from __future__ import annotations

import re
import unittest
from pathlib import Path

UI = Path(__file__).resolve().parents[1]
QML = UI / "qml"


class QmlRefinementTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (QML / relative).read_text(encoding="utf-8")

    def test_buttons_use_symmetric_center_slots_and_fit_text(self):
        for name in ("PrimaryButton.qml", "GhostButton.qml"):
            text = self.read(f"components/{name}")
            self.assertIn("reserveSideSlots", text)
            self.assertIn("anchors.horizontalCenter: parent.horizontalCenter", text)
            self.assertIn("fontSizeMode: Text.HorizontalFit", text)
            self.assertIn("minimumPixelSize", text)
            self.assertIn("Layout.minimumHeight", text)

    def test_fields_center_content_vertically(self):
        text_field = self.read("components/KfpsTextField.qml")
        combo = self.read("components/KfpsComboBox.qml")
        self.assertIn("verticalAlignment: TextInput.AlignVCenter", text_field)
        self.assertIn("verticalAlignment: Text.AlignVCenter", combo)
        self.assertIn("Layout.minimumHeight", text_field)
        self.assertIn("Layout.minimumHeight", combo)

    def test_responsive_breakpoints_use_logical_units(self):
        theme = self.read("Kfps/Theme/Theme.qml")
        main = self.read("Main.qml")
        create = self.read("pages/CreatePage.qml")
        self.assertIn("function logical", theme)
        self.assertIn("Theme.logical(width)", main)
        self.assertIn("Theme.logical(height)", main)
        self.assertIn("Theme.logical(width)", create)
        self.assertIn("Theme.logical(height)", create)

    def test_short_sidebar_keeps_current_route_visible(self):
        sidebar = self.read("shell/Sidebar.qml")
        self.assertIn("currentIndex: root.pageIndex(appController.currentPage)", sidebar)
        self.assertIn("positionViewAtIndex(currentIndex, ListView.Contain)", sidebar)

    def test_legacy_dashboard_page_is_retired(self):
        self.assertFalse((QML / "pages" / "DashboardPage.qml").exists())
        main = self.read("Main.qml")
        self.assertIn('dashboard: "CreatePage"', main)
        self.assertIn('create: "CreatePage"', main)

    def test_global_scaling_uses_one_continuous_viewport_factor(self):
        theme = self.read("Kfps/Theme/Theme.qml")
        main = self.read("Main.qml")
        self.assertIn("property real viewportScale", theme)
        self.assertIn("readonly property real effectiveScale", theme)
        self.assertIn("viewportScale * uiScale", theme)
        self.assertIn("readonly property real viewportFitScale", main)
        self.assertIn('property: "viewportScale"', main)
        self.assertIn("Math.min(width / Metrics.launchWidth", main)

    def test_interactables_have_no_artificial_white_top_strip(self):
        files = [
            "components/PrimaryButton.qml",
            "components/GhostButton.qml",
            "components/NavButton.qml",
            "components/KfpsTextField.qml",
            "components/KfpsComboBox.qml",
            "components/GlassPanel.qml",
        ]
        forbidden = ("#aaffffff", "#38ffffff", "#b7ffffff", "#26ffffff", "#2effffff", "#46ffffff")
        for relative in files:
            content = self.read(relative).lower()
            for token in forbidden:
                self.assertNotIn(token, content, f"{relative} still contains top-strip token {token}")

    def test_interactables_expose_runtime_audit_names(self):
        for relative in (
            "components/PrimaryButton.qml",
            "components/GhostButton.qml",
            "components/NavButton.qml",
            "components/KfpsTextField.qml",
            "components/KfpsTextArea.qml",
            "components/KfpsComboBox.qml",
            "components/KfpsCheckBox.qml",
            "components/KfpsSwitch.qml",
            "components/KfpsSlider.qml",
        ):
            self.assertIn("objectName:", self.read(relative), relative)

    def test_generate_default_options_do_not_depend_on_scroll_position(self):
        generate = self.read("pages/GeneratePage.qml")
        self.assertIn('text: "Automatic Detail Heatmap"', generate)
        self.assertIn('text: "Luma Prep"', generate)
        self.assertIn('text: "Edge Repair"', generate)
        self.assertIn('text: "2x Mode"', generate)
        self.assertIn("columns: 2", generate)

    def test_create_manual_overrides_are_prefilled_from_the_selected_preset(self):
        create = self.read("pages/CreatePage.qml")
        self.assertIn("function syncManualOverrideDefaults", create)
        self.assertIn("generationService.manualOverrideDefaults", create)
        self.assertIn("root.syncManualOverrideDefaults(true)", create)
        for label in ("Max resolution", "Random samples", "Mutated samples", "Seed"):
            self.assertIn(f'text: "{label}"', create)

    def test_generation_previews_reload_overwritten_milestones(self):
        for page in ("pages/CreatePage.qml", "pages/GeneratePage.qml"):
            text = self.read(page)
            self.assertIn("generationService.previewRevision", text)
            self.assertIn("kfpsPreview=", text)

    def test_positive_geometry_literals_are_scaled(self):
        offenders: list[str] = []
        geometry = re.compile(
            r"^\s*(?:width|height|implicitWidth|implicitHeight|leftPadding|rightPadding|"
            r"topPadding|bottomPadding|spacing|radius|font\.pixelSize|iconSize)\s*:\s*"
            r"([1-9][0-9]*(?:\.[0-9]+)?)\s*$"
        )
        for folder in (QML / "components", QML / "shell", QML / "pages"):
            for path in sorted(folder.glob("*.qml")):
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    if geometry.match(line):
                        offenders.append(f"{path.relative_to(QML)}:{number}: {line.strip()}")
        self.assertEqual([], offenders, "Unscaled positive geometry literals:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
