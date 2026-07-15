from __future__ import annotations

import json
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

    def test_sidebar_support_message_preserves_credits(self):
        sidebar = self.read("shell/Sidebar.qml")
        self.assertIn('"Consider supporting the project"', sidebar)
        self.assertIn('text: "Credits"', sidebar)
        self.assertIn("Theme.supporterSignatureText", sidebar)
        self.assertNotIn("Folders and maintenance are in Settings.", sidebar)

    def test_supporter_promo_rim_blinks_without_rotating(self):
        promo = self.read("shell/SupporterPromoToast.qml")
        self.assertIn("SequentialAnimation on blinkLevel", promo)
        self.assertIn("PauseAnimation { duration: 1800 }", promo)
        self.assertNotIn("property real spin", promo)
        self.assertNotIn("carnivalRim.spin", promo)

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

    def test_reusable_interactables_expose_hover_help(self):
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
            "components/HoverCard.qml",
            "components/QuickActionRow.qml",
            "components/RecentJsonRow.qml",
        ):
            content = self.read(relative)
            self.assertIn("toolTipText", content, relative)
            self.assertIn("KfpsToolTip {", content, relative)

        tooltip = self.read("components/KfpsToolTip.qml")
        self.assertIn("maximumTextWidth", tooltip)
        self.assertIn("wrapMode: Text.Wrap", tooltip)
        self.assertIn("color: Theme.surfaceRaised", tooltip)

    def test_every_reusable_control_instance_has_specific_hover_help(self):
        control_pattern = re.compile(
            r"^\s*(PrimaryButton|GhostButton|NavButton|KfpsTextField|KfpsTextArea|"
            r"KfpsComboBox|KfpsCheckBox|KfpsSwitch|KfpsSlider|QuickActionRow|"
            r"RecentJsonRow|WorkflowCard)\s*\{"
        )
        missing: list[str] = []
        for folder_name in ("pages", "shell"):
            for path in sorted((QML / folder_name).glob("*.qml")):
                lines = path.read_text(encoding="utf-8").splitlines()
                for index, first_line in enumerate(lines):
                    match = control_pattern.match(first_line)
                    if not match:
                        continue
                    depth = 0
                    has_tooltip = "toolTipText" in first_line
                    for line in lines[index:]:
                        if depth == 1 and re.match(r"^\s*toolTipText\s*:", line):
                            has_tooltip = True
                        depth += line.count("{") - line.count("}")
                        if depth <= 0:
                            break
                    if not has_tooltip:
                        missing.append(f"{path.relative_to(QML)}:{index + 1} {match.group(1)}")
        self.assertEqual([], missing, "Controls without specific hover help:\n" + "\n".join(missing))

    def test_custom_click_targets_explain_their_actions(self):
        required = {
            "pages/HelpPage.qml": ("text: categoryButton.summary", "text: topicButton.summary"),
            "pages/JsonPage.qml": (
                "Click to select this vinyl. Double-click to open its preview and file details.",
                "Select this FM8 creator profile for private offline-library filtering.",
            ),
            "shell/AnnouncementTicker.qml": ("Click to resume", "Click to pause"),
            "shell/AppTitleBar.qml": ("Minimize KFPS.", "Maximize the KFPS window.", "Close KFPS."),
            "shell/SupporterPromoToast.qml": ("Open the KFPS supporter page",),
            "SourceDownloadBlocker.qml": ("property string toolTipText", "Open the official KFPS latest-release page"),
        }
        for relative, phrases in required.items():
            content = self.read(relative)
            for phrase in phrases:
                self.assertIn(phrase, content, f"{relative} is missing hover help: {phrase}")

    def test_help_is_written_for_a_first_time_user(self):
        payload = json.loads((UI / "help" / "topics.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(payload["version"], 2)
        self.assertEqual(8, len(payload["categories"]))
        self.assertEqual(22, len(payload["topics"]))

        topics = {topic["key"]: topic for topic in payload["topics"]}
        self.assertEqual(len(topics), len(payload["topics"]))
        for key in ("first-run", "fh6-template", "import-fh6", "json-browser", "support-checklist"):
            self.assertIn(key, topics)

        all_keys = set(topics)
        for topic in topics.values():
            self.assertTrue(topic.get("summary"), topic["key"])
            self.assertTrue(topic.get("steps"), topic["key"])
            self.assertTrue(topic.get("sections"), topic["key"])
            self.assertTrue(set(topic.get("related", [])) <= all_keys, topic["key"])

        template_help = json.dumps(topics["fh6-template"]).lower()
        for phrase in ("vinyl group editor", "3000", "white circle", "save", "reopen", "ungroup", "exact count"):
            self.assertIn(phrase, template_help)

        first_run_help = json.dumps(topics["first-run"]).lower()
        self.assertIn("online means", first_run_help)
        self.assertIn("offline means", first_run_help)

    def test_unclear_action_labels_are_retired(self):
        page_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((QML / "pages").glob("*.qml"))
        )
        for old_label in (
            "Generate Final Vinyl",
            "Graceful Stop",
            "Force Stop",
            "Launch Empty Editor",
            "Online Import Selected JSON",
            "Online Export Current Group",
            "Browse JSON",
            "Copy support checklist",
            "Run updater from GitHub",
            "Import Unlock",
            "Open Ko-fi Unlock",
        ):
            self.assertNotIn(old_label, page_text)

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

    def test_header_pills_stay_on_create_reference_geometry(self):
        main = self.read("Main.qml")
        self.assertIn("id: createHeaderReference", main)
        self.assertIn("id: createReferenceSource", main)
        self.assertIn("id: createReferencePreview", main)
        self.assertIn("workspace.createHeaderSourceCenterX", main)
        self.assertIn("workspace.createHeaderPreviewCenterX", main)
        self.assertNotIn("x: workspace.pageHeaderAlignmentAvailable", main)

    def test_update_patch_notes_expand_for_wrapped_lines(self):
        update = self.read("pages/UpdatePage.qml")
        self.assertIn("patchNoteContent.implicitHeight", update)
        self.assertIn("visible: details.length > 0", update)
        self.assertNotIn("maximumLineCount: 2", update)

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
