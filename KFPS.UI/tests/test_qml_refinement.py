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

    def test_checkable_ghost_buttons_show_selected_state_in_every_theme(self):
        ghost = self.read("components/GhostButton.qml")
        self.assertIn("root.selected ||", ghost)
        self.assertIn("root.checkable && root.checked", ghost)
        self.assertIn("root.checkedState ? Theme.navActiveTop", ghost)
        self.assertIn("root.checkedState ? Theme.navActiveMiddle", ghost)
        self.assertIn("root.checkedState ? Theme.navActiveBottom", ghost)
        self.assertIn("root.checkedState ? Theme.primaryHot", ghost)

    def test_fields_center_content_vertically(self):
        text_field = self.read("components/KfpsTextField.qml")
        text_area = self.read("components/KfpsTextArea.qml")
        combo = self.read("components/KfpsComboBox.qml")
        self.assertIn("verticalAlignment: TextInput.AlignVCenter", text_field)
        self.assertIn("verticalAlignment: Text.AlignVCenter", combo)
        self.assertIn("Layout.minimumHeight", text_field)
        self.assertIn("Layout.minimumHeight", combo)
        self.assertIn("Theme.technicalTypographyEnabled", text_field)
        self.assertIn("Theme.technicalTypographyEnabled", text_area)
        self.assertIn("Font.DemiBold", text_field)
        self.assertIn("Font.DemiBold", text_area)

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

    def test_support_page_replaces_header_promo_and_hides_after_unlock(self):
        main = self.read("Main.qml")
        sidebar = self.read("shell/Sidebar.qml")
        support = self.read("pages/SupportPage.qml")
        controller = (UI / "src" / "kfps_ui" / "app_controller.py").read_text(encoding="utf-8")

        self.assertFalse((QML / "shell" / "SupporterPromoToast.qml").exists())
        self.assertNotIn("SupporterPromoToast", main)
        self.assertNotIn("supporterPromo", main)
        self.assertIn('support: "SupportPage"', main)
        self.assertIn('"support": "Support KFPS"', controller)
        self.assertIn('if (page === "support") return "heart"', self.read("shell/HeaderControls.qml"))
        self.assertIn('if (!supporterService.unlocked)', sidebar)
        self.assertIn('{ page: "liveries", label: "Liveries", icon: "monitor" }', sidebar)
        self.assertNotIn('supporterService.unlocked || demoMode', sidebar)
        self.assertIn('items.splice(6, 0, { page: "support", label: "Support", icon: "heart" })', sidebar)
        self.assertIn('supporterService.unlocked && appController.currentPage === "support"', main)
        self.assertIn('objectName: "SupportPage"', support)
        self.assertIn('Component.onCompleted:', support)
        self.assertIn('if (supporterService.unlocked)', support)
        self.assertIn('appController.navigate("create")', support)

    def test_support_page_uses_the_real_product_and_accurate_benefits(self):
        support = self.read("pages/SupportPage.qml")
        self.assertIn('"https://ko-fi.com/s/2d1507698d"', support)
        self.assertIn("ONE-TIME PURCHASE - NOT A SUBSCRIPTION", support)
        self.assertIn("There is no monthly fee and no recurring KFPS charge.", support)
        for phrase in (
            "Instant Offline Imports & Exports",
            "Export complete FH4, FH5, FH6, and FM8 vinyl libraries into KFPS in one action",
            "No game needs to be started.",
            "Supporter Community",
            "Four Extra Themes",
            "Windows 94",
            "FH4, FH5, FH6, and FM8 remain available without supporter access",
        ):
            self.assertIn(phrase, support)

    def test_legacy_dashboard_page_is_retired(self):
        self.assertFalse((QML / "pages" / "DashboardPage.qml").exists())
        main = self.read("Main.qml")
        self.assertIn('dashboard: "CreatePage"', main)
        self.assertIn('create: "CreatePage"', main)

    def test_native_scaling_has_no_manual_scene_multiplier(self):
        theme = self.read("Kfps/Theme/Theme.qml")
        main = self.read("Main.qml")
        settings = self.read("pages/SettingsPage.qml")
        self.assertIn("return Math.round(value)", theme)
        self.assertIn("return value", theme)
        self.assertNotIn("viewportScale", theme)
        self.assertNotIn("uiScale", theme)
        self.assertNotIn("viewportFitScale", main)
        self.assertNotIn("UI scale", settings)

    def test_outputs_header_exposes_append_only_imgs_backup(self):
        outputs = self.read("pages/JsonPage.qml")
        self.assertIn('text: backupService.running ? "Backing up..." : "Backup imgs"', outputs)
        self.assertIn("onClicked: backupService.backupImgs()", outputs)
        self.assertIn("Existing backups are never deleted.", outputs)

    def test_outputs_exposes_fh4_live_and_offline_transfer(self):
        outputs = self.read("pages/JsonPage.qml")
        self.assertIn('model: ["FH6", "FH5", "FH4", "FM8"]', outputs)
        self.assertIn('"Offline Import to FH4"', outputs)
        self.assertIn('game.currentText === "FH4" || game.currentText === "FH6"', outputs)
        self.assertIn("all four support offline save-library scanning", outputs)
        self.assertIn('"Online Import to " + game.currentText', outputs)

    def test_frameless_window_uses_native_resize_zones(self):
        main = self.read("Main.qml")
        frame = self.read("shell/WindowResizeFrame.qml")
        title_bar = self.read("shell/AppTitleBar.qml")
        self.assertIn("WindowResizeFrame", main)
        for edge in ("Qt.TopEdge", "Qt.BottomEdge", "Qt.LeftEdge", "Qt.RightEdge"):
            self.assertIn(edge, frame)
        self.assertIn("startSystemResize", frame)
        self.assertIn("startSystemMove", title_bar)

    def test_title_bar_close_icon_uses_theme_independent_geometry(self):
        title_bar = self.read("shell/AppTitleBar.qml")
        self.assertIn('model: ["min", "max", "close"]', title_bar)
        self.assertIn("model: [-45, 45]", title_bar)
        self.assertIn("width: Theme.px(14)", title_bar)
        self.assertIn("height: Theme.px(14)", title_bar)
        self.assertNotIn('text: "×"', title_bar)

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
            "components/KfpsLinkText.qml",
        ):
            self.assertIn("objectName:", self.read(relative), relative)

        for relative in (
            "components/HoverCard.qml",
            "components/QuickActionRow.qml",
            "components/RecentJsonRow.qml",
            "shell/AnnouncementTicker.qml",
            "shell/AppTitleBar.qml",
            "pages/HelpPage.qml",
            "pages/SupportPage.qml",
            "pages/JsonPage.qml",
            "pages/CommunityPage.qml",
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
            "components/KfpsLinkText.qml",
        ):
            content = self.read(relative)
            self.assertIn("toolTipText", content, relative)
            self.assertIn("KfpsToolTip {", content, relative)

        tooltip = self.read("components/KfpsToolTip.qml")
        self.assertIn("maximumTextWidth", tooltip)
        self.assertIn("wrapMode: Text.Wrap", tooltip)
        self.assertIn("color: Theme.surfaceRaised", tooltip)

    def test_link_text_uses_padding_for_a_readable_click_target(self):
        link = self.read("components/KfpsLinkText.qml")
        self.assertIn("topPadding: Theme.px(7)", link)
        self.assertIn("bottomPadding: Theme.px(7)", link)
        self.assertNotIn("implicitHeight:", link)

    def test_every_reusable_control_instance_has_specific_hover_help(self):
        control_pattern = re.compile(
            r"^\s*(PrimaryButton|GhostButton|NavButton|KfpsTextField|KfpsTextArea|"
            r"KfpsComboBox|KfpsCheckBox|KfpsSwitch|KfpsSlider|QuickActionRow|"
            r"RecentJsonRow|KfpsLinkText|WorkflowCard)\s*\{"
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
                "Click to select. Double-click for details. Use Shift or Ctrl for multiple items; right-click for actions.",
                "Select this FM8 creator profile for private offline-library filtering.",
            ),
            "shell/AnnouncementTicker.qml": ("Click to resume", "Click to pause"),
            "shell/AppTitleBar.qml": ("Minimize KFPS.", "Maximize the KFPS window.", "Close KFPS."),
            "pages/SupportPage.qml": (
                "Open the official KFPS supporter-key product page on Ko-fi.",
                "Open Settings to add, replace, repair, or release a supporter key.",
            ),
            "SourceDownloadBlocker.qml": ("property string toolTipText", "Open the official KFPS latest-release page"),
        }
        for relative, phrases in required.items():
            content = self.read(relative)
            for phrase in phrases:
                self.assertIn(phrase, content, f"{relative} is missing hover help: {phrase}")

    def test_help_is_written_for_a_first_time_user(self):
        payload = json.loads((UI / "help" / "topics.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(payload["version"], 2)
        self.assertEqual(9, len(payload["categories"]))
        self.assertEqual(26, len(payload["topics"]))

        topics = {topic["key"]: topic for topic in payload["topics"]}
        self.assertEqual(len(topics), len(payload["topics"]))
        for key in (
            "first-run", "fh6-template", "import-fh6", "json-browser",
            "community-browse", "community-publish", "full-livery-packages", "support-checklist",
        ):
            self.assertIn(key, topics)

        all_keys = set(topics)
        for topic in topics.values():
            self.assertTrue(topic.get("summary"), topic["key"])
            self.assertTrue(topic.get("steps"), topic["key"])
            self.assertTrue(topic.get("sections"), topic["key"])
            self.assertTrue(set(topic.get("related", [])) <= all_keys, topic["key"])

        template_help = json.dumps(topics["fh6-template"]).lower()
        for phrase in ("fh4", "vinyl group editor", "3000", "white circle", "save", "reopen", "ungroup", "exact count"):
            self.assertIn(phrase, template_help)

        export_help = json.dumps(topics["export-games"]).lower()
        self.assertNotIn("tokens truncated", export_help)
        self.assertIn("fh4 supports online live transfer, local save-library scanning, and offline import", export_help)

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

    def test_output_folder_and_live_transfer_actions_stay_pinned(self):
        outputs = self.read("pages/JsonPage.qml")
        scroll_end = outputs.index('"Online Import to " + game.currentText')
        self.assertIn("id: importSetupScroll", outputs[:scroll_end])
        self.assertIn('text: "Open Output Folder"', outputs[scroll_end:])
        self.assertIn("onClicked: desktop.openJsonFolders()", outputs[scroll_end:])
        self.assertIn('text: "Online Export from Game"', outputs[scroll_end:])
        self.assertIn("onClicked: transferService.exportJson", outputs[scroll_end:])

    def test_outputs_use_explorer_style_selection_and_confirmed_mixed_deletion(self):
        outputs = self.read("pages/JsonPage.qml")
        service = (UI / "src" / "kfps_ui" / "json_service.py").read_text(encoding="utf-8")
        self.assertNotIn("jsonService.selectionMode", outputs)
        self.assertNotIn("jsonService.setSelectionMode", outputs)
        self.assertIn("jsonService.selectExplorerEntry(", outputs)
        self.assertIn("required property bool selected", outputs)
        self.assertIn("readonly property bool selectedInExplorer: fileCard.selected", outputs)
        self.assertIn("Qt.ControlModifier", outputs)
        self.assertIn("Qt.ShiftModifier", outputs)
        self.assertIn("jsonService.selectAllExplorerEntries()", outputs)
        self.assertIn("id: deleteSelectedEntriesDialog", outputs)
        self.assertIn("onAccepted: jsonService.deleteSelectedEntries()", outputs)
        self.assertIn("jsonService.copySelection()", outputs)
        self.assertIn("jsonService.cutSelection()", outputs)
        self.assertNotIn("deleteOutputsResultDialog", outputs)
        self.assertNotIn("onDeletionFinished", outputs)
        self.assertIn("def deleteSelectedEntries(self):", service)
        self.assertIn("def _delete_output_entries(self, values):", service)
        self.assertIn("def _operation_selection(self):", service)

    def test_outputs_use_a_source_scoped_file_explorer_without_changing_community_browsing(self):
        outputs = self.read("pages/JsonPage.qml")
        community = self.read("pages/CommunityPage.qml")
        combo = self.read("components/KfpsComboBox.qml")
        service = (UI / "src" / "kfps_ui" / "json_service.py").read_text(encoding="utf-8")
        self.assertIn("model: jsonService.explorerModel", outputs)
        self.assertIn("model: jsonService.folderModel", outputs)
        self.assertIn('objectName: "OutputFolderJump"', outputs)
        self.assertIn("jsonService.goBack()", outputs)
        self.assertIn("jsonService.goForward()", outputs)
        self.assertIn("jsonService.goUp()", outputs)
        self.assertIn("id: outputContextMenu", outputs)
        self.assertIn("id: deleteSelectedEntriesDialog", outputs)
        self.assertIn("onAccepted: jsonService.deleteSelectedEntries()", outputs)
        self.assertIn('property bool outputContextIsSource: false', outputs)
        self.assertIn('root.outputContextIsSource = String(entryKind || "") === "source"', outputs)
        for action in ('? "Cut "', '? "Copy "', 'text: "Rename folder"', 'text: "Rename JSON"', '? "Delete "'):
            self.assertIn(action, outputs)
        self.assertIn('text: root.outputContextIsFolder ? "New folder inside" : "New folder"', outputs)
        self.assertIn('visible: root.outputContextIsFolder && !root.outputContextIsSource', outputs)
        self.assertIn('enabled: jsonService.currentFolder.length > 0', outputs)
        self.assertNotIn("setLibraryFolderVisible", outputs)
        self.assertNotIn("jsonService.sourceIndex === 3", outputs)
        self.assertNotIn("jsonService.sourceIndex === 3", community)
        self.assertIn('model: ["Generated finals", "Editor exports", "Game exports", "Library"]', community)
        self.assertIn("jsonService.pasteIntoFolder(destination)", outputs)
        self.assertIn('objectName: "OutputSort"', outputs)
        self.assertIn('jsonService.setSortMode(modes[currentIndex])', outputs)
        self.assertIn('id: outputMoveFolderMenu', outputs)
        self.assertIn('model: jsonService.moveFolderModel', outputs)
        self.assertIn('jsonService.moveSelectedJsonsToFolder(path)', outputs)
        self.assertIn('def moveSelectedJsonsToFolder(self, value):', service)
        self.assertIn("model: jsonService.fileModel", community)
        self.assertIn("def pasteIntoFolder(self, value):", service)
        self.assertIn("def renameEntry(self, value, requested_name):", service)
        self.assertIn("def deleteEntry(self, value):", service)
        self.assertIn('OUTPUT_FOLDER_MARKER = ".kfps-output-folder"', service)
        self.assertIn("self._is_accessible_managed_folder(path, source)", service)
        self.assertIn("required property int index", combo)
        self.assertIn("required property var model", combo)
        self.assertIn("delegateRoot.model[role]", combo)
        self.assertIn("return root.textAt(delegateRoot.index)", combo)

    def test_create_manual_overrides_are_prefilled_from_the_selected_preset(self):
        create = self.read("pages/CreatePage.qml")
        self.assertIn("function syncManualOverrideDefaults", create)
        self.assertIn("generationService.manualOverrideDefaults", create)
        self.assertIn("root.syncManualOverrideDefaults(true)", create)
        for label in ("Max resolution", "Random samples", "Mutated samples", "Seed"):
            self.assertIn(f'text: "{label}"', create)

    def test_create_and_settings_stack_into_scrollable_cards(self):
        create = self.read("pages/CreatePage.qml")
        settings = self.read("pages/SettingsPage.qml")
        self.assertIn("id: pageScroll", create)
        self.assertIn("height: root.threeColumns ? pageScroll.availableHeight : implicitHeight", create)
        self.assertIn("Layout.fillHeight: root.threeColumns", create)
        self.assertIn("id: pageScroll", settings)
        self.assertIn("height: root.wide ? pageScroll.availableHeight : implicitHeight", settings)
        self.assertIn("Layout.fillHeight: root.wide", settings)

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
        self.assertIn("Layout.preferredWidth: Math.max(Theme.px(68), implicitWidth)", update)
        self.assertIn("wrapMode: Text.NoWrap", update)
        self.assertIn("wrapMode: Text.WordWrap", update)
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
