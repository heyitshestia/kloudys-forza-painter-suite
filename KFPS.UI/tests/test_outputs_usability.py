"""Outputs navigation and safe action contracts, without game or desktop writes."""
from pathlib import Path
import json
import os
import tempfile
import textwrap
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from kfps_ui.app_paths import AppPaths
from kfps_ui.json_service import JsonService
from kfps_ui.editor_service import EditorService
from kfps_ui.desktop_service import DesktopService
from kfps_ui.community_service import CommunityService
from kfps_ui.workspace_tools import WorkspaceTools


UI = Path(__file__).resolve().parents[1]


class OutputsUsabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="outputs-usability-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.paths = AppPaths(root, UI, UI / "qml", UI / "assets", root / "runtime", root / "python/python.exe")
        self.roots = [self.paths.generated_root, self.paths.editor_json_root,
                      self.paths.exported_root, self.paths.library_root]
        for folder in self.roots:
            folder.mkdir(parents=True, exist_ok=True)
            self.write_json(folder / "Alpha.json")
            self.write_json(folder / "Beta.json")
            child = folder / "Review"
            child.mkdir()
            (child / ".kfps-output-folder").write_text(json.dumps({"displayName": "Review"}))
            self.write_json(child / "Child.json")
        preview = Mock(existing_preview_for_json=Mock(return_value=""))
        for name in ("_call_later", "_request_source_scan", "_ensure_logo", "_schedule_index_cache_save", "_save_index_cache_async"):
            stub = patch.object(JsonService, name)
            stub.start()
            self.addCleanup(stub.stop)
        self.service = JsonService(self.paths, preview, Mock(), Mock())
        self.addCleanup(self.service.close)
        self.reindex()
        self.service._load_source()

    @staticmethod
    def write_json(path):
        path.write_text(json.dumps({"shapes": [{"type": 1048677, "data": [0, 0, 1, 1, 0], "color": [255, 80, 60, 255]}]}))

    def reindex(self):
        for index, root in enumerate(self.roots):
            self.service._source_index_cache[index] = self.service._build_source_index(index, root, self.service._source_cache_key(index))

    def select(self, name):
        index = next(i for i, row in enumerate(self.service.explorerModel.rows) if row["name"] == name)
        self.service.selectExplorerEntry(index, False, False)

    def test_each_category_and_folder_keeps_its_own_state(self):
        service = self.service
        service.setSearchQuery("Alpha")
        service.setSortMode("name-asc")
        self.select("Alpha.json")
        service.setExplorerScroll(service.navigationKey, 125)
        service.openExplorerFolder(str(self.roots[0] / "Review"))
        self.assertEqual(service.searchQuery, "")
        self.assertEqual(service.sortMode, "date-desc")
        service.setSearchQuery("Child")
        service.setSortMode("shapes-desc")
        self.select("Child.json")
        service.setExplorerScroll(service.navigationKey, 64)
        service.setSource(1)
        self.assertEqual(service.searchQuery, "")
        self.assertEqual(service.sortMode, "date-desc")
        service.setSource(0)
        self.assertEqual(Path(service.currentFolder), self.roots[0] / "Review")
        self.assertEqual((service.searchQuery, service.sortMode, service.explorerScrollY), ("Child", "shapes-desc", 64))
        self.assertEqual(Path(service.selectedPath).name, "Child.json")
        self.assertEqual(service.explorerSelectionCount, 1)
        service.goUp()
        self.assertEqual((service.searchQuery, service.sortMode, service.explorerScrollY), ("Alpha", "name-asc", 125))
        self.assertEqual(Path(service.selectedPath).name, "Alpha.json")

    def test_refresh_retains_selection_and_reconciles_removed_files(self):
        service = self.service
        self.select("Alpha.json")
        service.setExplorerScroll(service.navigationKey, 90)
        service.refresh()
        self.assertEqual(service.explorerSelectionCount, 1)
        self.assertEqual(service.explorerScrollY, 90)
        (self.roots[0] / "Alpha.json").unlink()
        self.reindex()
        service.refresh()
        self.assertEqual(service.explorerSelectionCount, 0)
        self.assertEqual(service.selectedPath, "")

    def test_missing_folder_restores_safe_category_state(self):
        service = self.service
        service.setSearchQuery("Beta")
        service.openExplorerFolder(str(self.roots[0] / "Review"))
        service.setSearchQuery("Child")
        service.setSource(1)
        (self.roots[0] / "Review/.kfps-output-folder").unlink()
        service.setSource(0)
        self.assertEqual(Path(service.currentFolder), self.roots[0])
        self.assertEqual(service.searchQuery, "Beta")
        self.assertFalse(service.canGoUp)
        service.openExplorerFolder(str(self.paths.runtime_root))
        self.assertEqual(Path(service.currentFolder), self.roots[0])

    def test_scroll_updates_are_bounded_and_stale_keys_rejected(self):
        service = self.service
        key = service.navigationKey
        service.setSource(1)
        service.setExplorerScroll(key, 900)
        self.assertEqual(service.explorerScrollY, 0)
        for value in (float("nan"), float("inf"), -1):
            service.setExplorerScroll(service.navigationKey, value)
            self.assertEqual(service.explorerScrollY, 0)
        service.setExplorerScroll(service.navigationKey, 10**20)
        self.assertLessEqual(service.explorerScrollY, 10_000_000)

    def test_stale_and_inactive_scan_results_do_not_navigate(self):
        service = self.service
        service.setSearchQuery("Alpha")
        self.select("Alpha.json")
        service._source_scan_generation[0] = 4
        service._source_scan_generation[3] = 2
        service._apply_source_index_result(0, 3, service._empty_source_index(0), "")
        service._apply_source_index_result(3, 2, service._source_index_cache[3], "")
        self.assertEqual(service.sourceIndex, 0)
        self.assertEqual(service.searchQuery, "Alpha")
        self.assertEqual(Path(service.selectedPath).name, "Alpha.json")

    def test_deleting_active_folder_restores_parent_filter_and_sort(self):
        service = self.service
        service.setSearchQuery("Beta")
        service.setSortMode("shapes-desc")
        child = self.roots[0] / "Review"
        service.openExplorerFolder(str(child))
        service.setSearchQuery("Child")
        self.assertTrue(service.deleteEntry(str(child)))
        self.assertEqual(Path(service.currentFolder), self.roots[0])
        self.assertEqual((service.searchQuery, service.sortMode), ("Beta", "shapes-desc"))

    def test_empty_and_multiple_selection_remain_explicit_on_return(self):
        service = self.service
        self.select("Alpha.json")
        index = next(i for i, row in enumerate(service.explorerModel.rows) if row["name"] == "Beta.json")
        service.selectExplorerEntry(index, True, False)
        service.setSource(1)
        service.setSource(0)
        self.assertEqual(service.explorerSelectionCount, 2)
        service.clearExplorerSelection()
        service.clearSelection()
        service.setSource(1)
        service.setSource(0)
        service.refresh()
        self.assertEqual(service.selectedPath, "")
        self.assertEqual(service.explorerSelectionCount, 0)

    def test_consumer_states_and_background_refresh_are_isolated(self):
        service = self.service
        service.setSearchQuery("Alpha")
        self.select("Alpha.json")
        service.setNavigationConsumer("community")
        service.setSource(3)
        service.setSearchQuery("Beta")
        service.setNavigationConsumer("outputs")
        service.refreshLibraryOutputs()
        self.assertEqual(service.sourceIndex, 0)
        self.assertEqual(service.searchQuery, "Alpha")
        self.assertEqual(Path(service.selectedPath).name, "Alpha.json")
        service.setNavigationConsumer("community")
        self.assertEqual(service.sourceIndex, 3)
        self.assertEqual(service.searchQuery, "Beta")
        service.setNavigationConsumer("arbitrary-owner")
        self.assertEqual(service.navigationConsumer, "community")

    def test_navigation_memory_and_histories_are_bounded(self):
        service = self.service
        for index in range(90):
            folder = self.roots[0] / f"Folder {index}"
            folder.mkdir()
            (folder / ".kfps-output-folder").write_text("{}")
            service.openExplorerFolder(str(folder))
            service.setSearchQuery("x" * 2000)
        self.assertLessEqual(len(service._navigation_states), 64)
        self.assertLessEqual(len(service._back_history), 64)
        self.assertLessEqual(len(service.searchQuery), 512)

    def test_workspace_result_selects_outputs_before_category_and_path(self):
        service = self.service
        service.setSearchQuery("Alpha")
        service.setExplorerScroll(service.navigationKey, 81)
        service.setNavigationConsumer("community")
        service.setSource(3)
        service.openExplorerFolder(str(self.roots[3] / "Review"))
        service.setSearchQuery("Child")
        service.setSortMode("name-asc")
        self.select("Child.json")
        service.setExplorerScroll(service.navigationKey, 42)
        navigate = Mock()
        owner = SimpleNamespace(services={"outputs": service}, navigate=navigate)
        target = str(self.roots[2] / "Beta.json")
        WorkspaceTools._open_output(owner, target, 2)
        self.assertEqual(service.navigationConsumer, "outputs")
        self.assertEqual(service.sourceIndex, 2)
        self.assertEqual(Path(service.selectedPath), Path(target))
        navigate.assert_called_once_with("outputs")
        service.setSource(0)
        self.assertEqual((service.searchQuery, service.explorerScrollY), ("Alpha", 81))
        service.setNavigationConsumer("community")
        self.assertEqual(service.sourceIndex, 3)
        self.assertEqual(Path(service.currentFolder), self.roots[3] / "Review")
        self.assertEqual((service.searchQuery, service.sortMode, service.explorerScrollY),
                         ("Child", "name-asc", 42))
        self.assertEqual(Path(service.selectedPath).name, "Child.json")

    def test_community_download_completion_refreshes_without_navigation(self):
        service = self.service
        owner = SimpleNamespace(_closed=False, _busy_count=1, jsons=service,
                                log=Mock(), changed=Mock())
        for consumer, category, query in (("outputs", 1, "Alpha"), ("community", 2, "Beta")):
            with self.subTest(consumer=consumer):
                service.setNavigationConsumer(consumer)
                service.setSource(category)
                service.setSearchQuery(query)
                self.select(query + ".json")
                service.setExplorerScroll(service.navigationKey, 37)
                before = (service.navigationKey, service.selectedPath)
                with patch.object(service, "refreshLibraryOutputs", wraps=service.refreshLibraryOutputs) as refresh:
                    CommunityService._apply_result(owner, "download", {
                        "ok": True, "value": {"path": str(self.roots[3] / "Beta.json"), "title": "Beta"}})
                refresh.assert_called_once_with()
                self.assertEqual((service.navigationKey, service.selectedPath), before)
                self.assertEqual((service.searchQuery, service.explorerScrollY), (query, 37))
                service._source_scan_generation[3] = 5
                service._apply_source_index_result(3, 5, service._source_index_cache[3], "")
                self.assertEqual((service.navigationKey, service.selectedPath), before)
        with patch.object(service, "refreshLibraryOutputs") as refresh:
            CommunityService._apply_result(owner, "download", {"ok": False, "message": "Download failed"})
            refresh.assert_not_called()
            owner._closed = True
            CommunityService._apply_result(owner, "download", {"ok": True, "value": {}})
            refresh.assert_not_called()

    def test_community_page_selects_its_consumer_on_both_activation_paths(self):
        source = (UI / "qml/pages/CommunityPage.qml").read_text(encoding="utf-8")
        self.assertRegex(source, r'Component\.onCompleted:\s*\{\s*if \(visible\) jsonService\.setNavigationConsumer\("community"\)')
        self.assertRegex(source, r'onVisibleChanged:\s*if \(visible\)\s*\{\s*jsonService\.setNavigationConsumer\("community"\)')

    def test_real_community_outputs_activation_and_result_route_offscreen(self):
        from test_output_category_tabs import OutputCategoryTabsTests, SCRIPT

        # Reuse the audited, isolated application bootstrap and subprocess runner.
        bootstrap, separator, _ = SCRIPT.partition("def run(app, engine, shutdown):")
        self.assertTrue(separator)
        probe = bootstrap + textwrap.dedent(r'''
            def run(app, engine, shutdown):
                from types import SimpleNamespace
                from kfps_ui.workspace_tools import WorkspaceTools
                window = engine.rootObjects()[0]
                context = engine.rootContext()
                context.setContextProperty("screenshotMode", True)
                controller = context.contextProperty("appController")
                service = context.contextProperty("jsonService")
                community = context.contextProperty("communityService")
                timer = QTimer()
                stage = [0]
                retained = {}
                def ready():
                    pending = [window.contentItem()]
                    while pending:
                        item = pending.pop()
                        retained[id(item)] = item
                        if item.objectName() == "CachedPageHost":
                            expression = QQmlExpression(qmlContext(item), item, "currentLoader.status")
                            value = expression.evaluate()[0]
                            assert not expression.hasError()
                            return value == 1
                        pending.extend(item.childItems())
                    return False
                def check():
                    try:
                        if len(service._source_index_cache) != 4 or not ready():
                            return
                        if stage[0] == 0:
                            assert service.navigationConsumer == "outputs"
                            service.setSource(1)
                            service.setSearchQuery("QA 1")
                            service.setSortMode("name-asc")
                            service.selectPath(str(roots[1] / "QA 1 - 1.json"))
                            checked.append("initial-outputs")
                            controller.navigate("community")
                        elif stage[0] == 1:
                            assert service.navigationConsumer == "community"
                            service.setSource(3)
                            service.setSearchQuery("QA 3")
                            service.setSortMode("shapes-desc")
                            service.selectPath(str(roots[3] / "QA 3 - 2.json"))
                            checked.append("community-completed-consumer")
                            controller.navigate("outputs")
                        elif stage[0] == 2:
                            assert service.navigationConsumer == "outputs"
                            assert (service.sourceIndex, service.searchQuery, service.sortMode) == (1, "QA 1", "name-asc")
                            assert Path(service.selectedPath).name == "QA 1 - 1.json"
                            community._apply_result("download", {"ok": True, "value": {"path": str(roots[3] / "QA 3 - 0.json")}})
                            checked.append("outputs-visible-restored-and-download-completed")
                        elif stage[0] == 3:
                            assert service.navigationConsumer == "outputs"
                            assert service.sourceIndex == 1 and service.searchQuery == "QA 1"
                            checked.append("background-library-refresh-no-navigation")
                            controller.navigate("community")
                        elif stage[0] == 4:
                            assert service.navigationConsumer == "community"
                            assert (service.sourceIndex, service.searchQuery, service.sortMode) == (3, "QA 3", "shapes-desc")
                            assert Path(service.selectedPath).name == "QA 3 - 2.json"
                            owner = SimpleNamespace(services={"outputs": service}, navigate=controller.navigate)
                            WorkspaceTools._open_output(owner, str(roots[2] / "QA 2 - 2.json"), 2)
                            checked.append("community-visible-restored-and-result-route")
                        elif stage[0] == 5:
                            assert service.navigationConsumer == "outputs" and service.sourceIndex == 2
                            assert Path(service.selectedPath).name == "QA 2 - 2.json"
                            checked.append("result-selection-survived-qml-activation")
                            assert window.grabWindow().save(str(profile / "outputs.png"))
                            timer.stop()
                            app.quit()
                            return
                        stage[0] += 1
                    except BaseException:
                        errors.append(traceback.format_exc())
                        timer.stop()
                        app.quit()
                timer.timeout.connect(check)
                timer.start(350)
                QTimer.singleShot(25000, app.quit)
                return execute(app, engine, shutdown)
            module.exec_qml_application = run
            sys.argv = ["app.py", "--demo", "--skip-startup-index", "--page", "outputs", "--width", str(width), "--height", str(height)]
            with patch.object(module.AppPaths, "discover", return_value=paths), \
                    patch.object(module.FullLiveryService, "_resolve_initial_game_folder", return_value=""):
                assert module.main() == 0
            logging.shutdown()
            assert not errors, (errors, qml_errors)
            assert len(checked) == 6, checked
            assert not qml_errors, qml_errors
            (profile / "result.json").write_text(json.dumps({"checked": checked, "theme": theme, "size": [width, height]}))
        ''')
        with patch("test_output_category_tabs.SCRIPT", probe), \
                patch.dict(os.environ, {"KFPS_OUTPUTS_SINGLE_CASE": "1"}):
            OutputCategoryTabsTests().test_real_outputs_and_liveries_pages_offscreen()

    def test_inactive_state_follows_rename_and_prunes_delete(self):
        service = self.service
        self.select("Alpha.json")
        service.setSource(1)
        old = self.roots[0] / "Alpha.json"
        self.assertTrue(service.renameEntry(str(old), "Renamed.json"))
        service.setSource(0)
        self.assertEqual(Path(service.selectedPath).name, "Renamed.json")
        service.setSource(1)
        self.assertTrue(service.deleteEntry(str(self.roots[0] / "Renamed.json")))
        self.assertFalse(any(state["selected"].endswith("Renamed.json") for state in service._navigation_states.values()))
        service.setSource(0)
        self.assertEqual(service.selectedPath, "")
        self.assertEqual(service.explorerSelectionCount, 0)

    def test_action_state_rejects_ambiguous_missing_and_external_paths(self):
        service = self.service
        valid = self.roots[0] / "Alpha.json"
        self.assertTrue(service.artworkActionState(str(valid), 1)["canEdit"])
        for path, count in ((valid, 2), (self.roots[0], 1), (self.paths.runtime_root / "fake.json", 1), ("", 0)):
            state = service.artworkActionState(str(path), count)
            self.assertFalse(state["canEdit"])
            self.assertFalse(state["canPlace"])
            self.assertFalse(state["canExport"])
            self.assertFalse(state["canShow"])
            self.assertTrue(state["reason"])
        valid.unlink()
        self.assertFalse(service.artworkActionState(str(valid), 1)["canEdit"])
        library = service.artworkActionState(str(self.roots[3] / "Alpha.json"), 1)
        self.assertTrue(library["canEdit"])
        self.assertFalse(library["canExport"])
        self.assertTrue(library["exportReason"])

    def make_editor(self):
        with patch.object(EditorService, "refresh"):
            editor = EditorService(self.paths, Mock(), Mock(), Mock())
        self.addCleanup(editor.close)
        return editor

    def test_studio_adapter_uses_validated_bridge_payload_and_preserves_source(self):
        editor = self.make_editor()
        path = self.roots[0] / "Alpha.json"
        before = path.read_bytes()
        bridge = UI.parent / "tools/livery-studio/src/kfps_livery_lab/host_bridge.py"
        with patch("kfps_ui.editor_service._studio_module_path", return_value=bridge), \
                patch.object(editor, "_launch_studio_worker") as launch, \
                patch.object(editor, "_start_thread", side_effect=lambda **kw: kw["target"](*kw["args"])):
            editor.launchJsonInLiveryStudio(str(path))
        launch.assert_called_once()
        request = launch.call_args.args[0]
        self.assertEqual(request["name"], "Alpha")
        self.assertEqual(len(request["vinyl"]["shapes"]), 1)
        self.assertEqual(before, path.read_bytes())
        self.assertNotIn("path", request)

    def test_studio_adapter_rejects_invalid_oversized_and_outside_payloads(self):
        editor = self.make_editor()
        bridge = UI.parent / "tools/livery-studio/src/kfps_livery_lab/host_bridge.py"
        outside = self.paths.app_root / "outside.json"
        self.write_json(outside)
        target = self.roots[0] / "Invalid.json"
        with patch("kfps_ui.editor_service._studio_module_path", return_value=bridge), \
                patch.object(editor, "_launch_studio_worker") as launch, \
                patch.object(editor, "_start_thread", side_effect=lambda **kw: kw["target"](*kw["args"])):
            for value in ("{}", '{"shapes":[]}', "not json", " " * (8 * 1024 * 1024 + 1)):
                target.write_text(value)
                editor.launchJsonInLiveryStudio(str(target))
                self.assertFalse(editor.studioLaunching)
            for path in ("", str(outside), str(self.roots[0]), str(self.roots[0] / "missing.json")):
                editor.launchJsonInLiveryStudio(path)
                self.assertFalse(editor.studioLaunching)
            launch.assert_not_called()

    def test_studio_adapter_does_not_queue_duplicate_or_closed_launches(self):
        editor = self.make_editor()
        with patch.object(editor, "_start_thread") as start:
            editor.launchJsonInLiveryStudio(str(self.roots[0] / "Alpha.json"))
            editor.launchJsonInLiveryStudio(str(self.roots[0] / "Beta.json"))
            self.assertEqual(start.call_count, 1)
            editor.close()
            editor.launchJsonInLiveryStudio(str(self.roots[0] / "Alpha.json"))
            self.assertEqual(start.call_count, 1)

    def test_studio_adapter_rejects_nonfinite_duplicate_fields_and_invalid_theme(self):
        editor = self.make_editor()
        bridge = UI.parent / "tools/livery-studio/src/kfps_livery_lab/host_bridge.py"
        target = self.roots[0] / "Invalid.json"
        with patch("kfps_ui.editor_service._studio_module_path", return_value=bridge), \
                patch.object(editor, "_launch_studio_worker") as launch, \
                patch.object(editor, "_start_thread", side_effect=lambda **kw: kw["target"](*kw["args"])):
            for value in ('{"shapes":[],"shapes":[]}', '{"shapes":NaN}'):
                target.write_text(value)
                editor.launchJsonInLiveryStudio(str(target))
                self.assertFalse(editor.studioLaunching)
            self.write_json(target)
            editor.launchJsonInLiveryStudio(str(target), {"variables": {"--bg": "url(https://example.com)"}})
            self.assertFalse(editor.studioLaunching)
            launch.assert_not_called()

    def test_reveal_only_accepts_existing_output_files(self):
        desktop = DesktopService(self.paths, Mock())
        with patch("kfps_ui.desktop_service.subprocess.Popen") as spawn:
            self.assertTrue(desktop.revealOutputFile(str(self.roots[0] / "Alpha.json")))
            command = spawn.call_args.args[0]
            self.assertIn("/select,", command[-1])
            self.assertIn("Alpha.json", command[-1])
            spawn.reset_mock()
            for value in ("", str(self.paths.app_root / "outside.json"), str(self.roots[0])):
                self.assertFalse(desktop.revealOutputFile(value))
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
