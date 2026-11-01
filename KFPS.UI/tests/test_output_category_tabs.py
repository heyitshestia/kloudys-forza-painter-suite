"""Category navigation and real offscreen QML, without external side effects."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = textwrap.dedent(r'''
    import importlib.util
    import json
    import logging
    import os
    from dataclasses import replace
    from pathlib import Path
    import sys
    import traceback
    from unittest.mock import patch

    profile = Path(sys.argv[1]).resolve()
    theme, width, height = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    def audit(event, args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
            raise AssertionError("External activity is forbidden")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            mode, flags = args[1:3]
            writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            if writing and not Path(args[0]).resolve().is_relative_to(profile):
                raise AssertionError("Write outside isolated test")
    sys.addaudithook(audit)
    spec = importlib.util.spec_from_file_location("outputs_test_app", Path.cwd() / "KFPS.UI/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QTimer, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtQml import QQmlExpression, qmlContext
    from PySide6.QtQuick import QQuickItem
    from PIL import Image, ImageDraw

    paths = replace(module.AppPaths.discover(), app_root=profile / "app", runtime_root=profile / "runtime")
    paths.runtime_root.mkdir()
    paths.settings_file.write_text(json.dumps({"theme": theme, "reducedMotion": True, "ambientMotion": False,
        "supportUpscalerNoticeAcknowledged": True, "communityJoinNoticeAcknowledged": True,
        "backgroundRemoverNoticeAcknowledged": True, "dcinsideKoreanNotice202609Acknowledged": True}))
    roots = [paths.generated_root, paths.editor_json_root, paths.exported_root, paths.library_root]
    for source, folder in enumerate(roots):
        folder.mkdir(parents=True)
        for index in range(4):
            name = f"QA {source} - {index}"
            (folder / (name + ".json")).write_text(json.dumps({"metadata": {"layers": index + 1}, "shapes": [
                {"type": 1048677, "data": [0, 0, 1, 1, 0], "color": [255, 100, 100, 255]}
            ] * (index + 1)}))
            image = Image.new("RGBA", (200, 140), (0, 0, 0, 0))
            drawing = ImageDraw.Draw(image)
            for shape in range(index + 1):
                drawing.ellipse((10 + shape * 36, 32, 64 + shape * 36, 96),
                                fill=["#ec4474", "#368fd6", "#42b688", "#efbc3a"][source])
            image.save(folder / (name + ".png"))
    supporter = module.SupporterService
    module.SupporterService = lambda root: supporter(root, endpoint="")
    execute = module.exec_qml_application
    errors, checked, qml_errors = [], [], []
    engine_type = module.QQmlApplicationEngine
    def make_engine():
        engine = engine_type()
        engine.warnings.connect(lambda messages: qml_errors.extend(message.toString() for message in messages))
        return engine
    module.QQmlApplicationEngine = make_engine

    def run(app, engine, shutdown):
        assert app.platformName() == "offscreen"
        window = engine.rootObjects()[0]
        context = engine.rootContext()
        context.setContextProperty("screenshotMode", True)
        print("Scenegraph:", window.rendererInterface().graphicsApi(), flush=True)
        controller = context.contextProperty("appController")
        service = context.contextProperty("jsonService")
        stage = [0]
        navigation = {}
        observed_items = {}
        timer = QTimer()
        def find(name):
            pending = [window.contentItem()]
            names = []
            while pending:
                item = pending.pop()
                observed_items[id(item)] = item
                names.append(item.objectName())
                if item.objectName() == name:
                    return item
                pending.extend(item.childItems())
            raise AssertionError((name, [value for value in names if "Output" in value or "Generated" in value]))
        def js(item, expression):
            command = QQmlExpression(qmlContext(item), item, expression)
            value = command.evaluate()[0]
            assert not command.hasError(), command.error().toString()
            return value
        def tab(index):
            return find("OutputCategoryTab:" + str(index))
        def choose(index):
            js(tab(index), "clicked()")
            assert service.sourceIndex == index
            assert str(roots[index]) == service.currentFolder
            assert not service.canGoUp
            assert len(service.explorerModel.rows) == 4
            assert all(row["entryKind"] == "json" for row in service.explorerModel.rows)
            assert [bool(tab(i).property("checked")) for i in range(4)] == [i == index for i in range(4)]
        def check():
            try:
                if len(service._source_index_cache) != 4:
                    return
                if stage[0] == 0 and window.property("dashboardNavigationVisible"):
                    js(find("ApexDashboard"), 'choose("outputs")')
                    return
                if js(find("CachedPageHost"), "currentLoader.status") != 1:
                    return
                if stage[0] == 0:
                    try:
                        for index in range(4):
                            tab(index)
                    except AssertionError as error:
                        navigation["initial_wait"] = str(error)
                        return
                if stage[0] == 0:
                    assert controller.currentPage == "outputs"
                    assert service.sourceIndex == 0
                    assert find("OutputSearch").property("enabled")
                    choose(0)
                    page = find("OutputsPage")
                    if not page.property("wide"):
                        toggle = find("OutputTransferToggle")
                        js(toggle, "clicked()")
                        assert page.property("showTransferSetup")
                        assert find("OfflineLibraryControls").isVisible()
                        assert not find("OutputFiles").isVisible()
                        js(toggle, "clicked()")
                        assert find("OutputFiles").isVisible()
                    for index in range(4):
                        choose(index)
                    service.selectExplorerEntry(0, False, False)
                    selected = service.selectedPath
                    js(tab(3), "clicked()")
                    assert service.selectedPath == selected
                    assert service.createFolderIn(service.currentFolder, "Review")
                    folder = roots[3] / "Review"
                    service.openExplorerFolder(str(folder))
                    js(tab(3), "clicked()")
                    assert Path(service.currentFolder) == folder
                    assert service.canGoUp
                    service.goBack()
                    assert Path(service.currentFolder) == roots[3]
                    service.goForward()
                    assert Path(service.currentFolder) == folder
                    service.goUp()
                    assert not service.canGoUp
                    assert service.deleteEntry(str(folder))
                    service.jumpToFolder("")
                    assert Path(service.currentFolder) == roots[3]
                    choose(1)
                    search = find("OutputSearch")
                    js(search, 'text = "QA 1 - 2"; textEdited()')
                    assert len(service.explorerModel.rows) == 1
                    assert service.explorerModel.rows[0]["name"] == "QA 1 - 2.json"
                    js(search, 'text = "not present"; textEdited()')
                    assert len(service.explorerModel.rows) == 0
                    js(search, 'text = ""; textEdited()')
                    js(find("OutputSort"), 'currentIndex = 3; activated(3)')
                    assert [row["layers"] for row in service.explorerModel.rows] == [4, 3, 2, 1]
                    tab(1).forceActiveFocus()
                    for key, expected in [(Qt.Key_Right, 2), (Qt.Key_End, 3), (Qt.Key_Right, 0), (Qt.Key_Left, 3), (Qt.Key_Home, 0)]:
                        target = tab(service.sourceIndex)
                        QCoreApplication.sendEvent(target, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
                        assert service.sourceIndex == expected
                    choose(2)
                    # A deleted current folder must fall back to its category, not four tiles.
                    assert service.createFolderIn(service.currentFolder, "Vanishing")
                    gone = roots[2] / "Vanishing"
                    service.openExplorerFolder(str(gone))
                    (gone / ".kfps-output-folder").unlink()
                    gone.rmdir()
                    service.refresh()
                    assert Path(service.currentFolder) == roots[2]
                    assert all(row["entryKind"] != "source" for row in service.explorerModel.rows)
                    checked.append("categories-search-sort-selection-folders-keyboard")
                elif stage[0] == 1:
                    if not all(row.get("previewUrl") for row in service.explorerModel.rows):
                        for row in service.explorerModel.rows:
                            service.requestPreview(row["path"])
                        return
                    tabs = find("OutputCategoryTabs")
                    files = find("OutputFiles")
                    assert tabs.isVisible() and files.isVisible()
                    assert files.height() >= 140, (files.width(), files.height())
                    backup_button = find("GhostButton:Backup imgs")
                    backup = engine.rootContext().contextProperty("backupService")
                    backup_widths = []
                    try:
                        for busy, caption in ((False, "Backup imgs"), (True, "Backing up..."), (False, "Backup imgs")):
                            backup._running = busy
                            backup.changed.emit()
                            app.processEvents()
                            window.grabWindow()
                            pending = list(backup_button.childItems())
                            labels = []
                            while pending:
                                item = pending.pop()
                                pending.extend(item.childItems())
                                if item.property("text") == caption and item.metaObject().indexOfProperty("truncated") >= 0:
                                    labels.append(item)
                            assert len(labels) == 1 and not labels[0].property("truncated"), (
                                caption, backup_button.width(), [(item.width(), item.property("contentWidth"),
                                item.property("truncated"), item.property("font").toString()) for item in labels])
                            backup_widths.append(backup_button.width())
                        assert max(backup_widths) - min(backup_widths) < 1, backup_widths
                    finally:
                        backup._running = False
                        backup.changed.emit()
                    previous = None
                    for index in range(4):
                        item = tab(index)
                        top = item.mapToScene(QPointF(0, 0))
                        end = item.mapToScene(QPointF(item.width(), item.height()))
                        assert 0 <= top.x() < end.x() <= window.width()
                        assert 0 <= top.y() < end.y() <= window.height()
                        assert item.width() >= 100 and item.height() >= 28
                        assert previous is None or top.x() >= previous
                        previous = end.x()
                    assert window.grabWindow().save(str(profile / "outputs.png"))
                    with Image.open(profile / "outputs.png") as capture:
                        colors = capture.convert("RGB").getdata()
                        green_pixels = sum(1 for r, g, b in colors if 40 < r < 90 and 160 < g < 200 and 110 < b < 160)
                        assert green_pixels > 500, ("Missing artwork pixels", green_pixels)
                    checked.append("layout-and-capture")
                    controller.navigate("liveries")
                elif stage[0] == 2:
                    page = window.findChild(QQuickItem, "LiveryPage")
                    if page is None or not page.isVisible():
                        return
                    assert window.findChild(QQuickItem, "liveryWipPreviewOverlay") is None
                    assert window.grabWindow().save(str(profile / "liveries.png"))
                    controller.navigate("outputs")
                    checked.append("liveries-no-modal")
                elif stage[0] == 3:
                    if not find("OutputsPage").isVisible():
                        return
                    assert service.sourceIndex == 2
                    assert len(service.explorerModel.rows) == 4
                    checked.append("retained-navigation")
                    service.setSource(0)
                    assert service.createFolderIn(service.currentFolder, "Scroll review")
                    folder = roots[0] / "Scroll review"
                    payload = (roots[0] / "QA 0 - 0.json").read_bytes()
                    for index in range(80):
                        (folder / f"Scroll {index:03d}.json").write_bytes(payload)
                    service.openExplorerFolder(str(folder))
                    service.refresh()
                    navigation["folder"] = folder
                elif stage[0] == 4:
                    if service.currentSourceIndexing or len(service.explorerModel.rows) != 80:
                        return
                    js(find("OutputSearch"), 'text = "Scroll"; textEdited()')
                    js(find("OutputSort"), 'currentIndex = 1; activated(1)')
                    service.selectExplorerEntry(35, False, False)
                elif stage[0] == 5:
                    if not navigation.get("scrolled"):
                        if js(find("OutputFiles"), "restoringNavigation"):
                            return
                        js(find("OutputFiles"), "contentY = originY + cellHeight * 3")
                        navigation["scrolled"] = True
                        return
                    navigation["scroll"] = js(find("OutputFiles"), "contentY - originY")
                    assert navigation["scroll"] > 0, navigation
                    assert abs(service.explorerScrollY - navigation["scroll"]) < 1, (service.explorerScrollY, navigation)
                    js(tab(1), "clicked()")
                    assert service.searchQuery == "" and service.sortMode == "shapes-desc"
                    js(tab(0), "clicked()")
                elif stage[0] == 6:
                    assert Path(service.currentFolder) == navigation["folder"]
                    assert service.searchQuery == "Scroll" and service.sortMode == "name-asc"
                    assert Path(service.selectedPath).name == "Scroll 035.json"
                    assert service.explorerSelectionCount == 1
                    assert abs(js(find("OutputFiles"), "contentY - originY") - navigation["scroll"]) < 1
                    service.refresh()
                elif stage[0] == 7:
                    if service.currentSourceIndexing:
                        return
                    assert abs(js(find("OutputFiles"), "contentY - originY") - navigation["scroll"]) < 1
                    service.goUp()
                    service.setSearchQuery("QA 0")
                    service.setSortMode("shapes-asc")
                    service.selectExplorerEntry(0, False, False)
                    service.openExplorerFolder(str(navigation["folder"]))
                elif stage[0] == 8:
                    assert service.searchQuery == "Scroll" and service.sortMode == "name-asc"
                    assert abs(js(find("OutputFiles"), "contentY - originY") - navigation["scroll"]) < 1
                    assert Path(service.selectedPath).name == "Scroll 035.json"
                    service.goUp()
                    assert service.searchQuery == "QA 0" and service.sortMode == "shapes-asc"
                    checked.append("independent-category-folder-search-sort-scroll-selection-refresh")
                    editor = context.contextProperty("editorService")
                    desktop = context.contextProperty("desktop")
                    import kfps_ui.editor_service as editor_module
                    calls = []
                    editor.workspace_editor = lambda request: calls.append(("edit", request)) or True
                    editor.workspace_studio = lambda request, cancel: calls.append(("place", request)) or {"message": "Test Studio accepted vinyl"}
                    with patch.object(editor, "_start_thread", side_effect=lambda **kw: kw["target"](*kw["args"])), \
                            patch.object(editor_module, "_studio_module_path", return_value=Path.cwd() / "tools/livery-studio/src/kfps_livery_lab/host_bridge.py"), \
                            patch("kfps_ui.desktop_service.subprocess.Popen") as reveal:
                        launcher = paths.app_root / "KFPS.UI/editor.py"
                        launcher.parent.mkdir(parents=True, exist_ok=True)
                        launcher.touch()
                        for action in ("edit", "place", "export", "show"):
                            button = find("OutputAction:" + action)
                            assert button.property("enabled"), action
                            js(button, "clicked()")
                        assert [item[0] for item in calls] == ["edit", "place"], calls
                        assert calls[0][1]["json"].endswith("QA 0 - 0.json")
                        assert len(calls[1][1]["vinyl"]["shapes"]) == 1
                        assert calls[1][1]["ui_theme"]["name"] == theme
                        assert reveal.call_count == 1
                        assert "/select," in reveal.call_args.args[0][-1]
                        assert not find("OutputAction:edit").property("enabled")
                        assert "starting" in find("OutputActionExplanation").property("text")
                        editor._finish_launch(True, "", "Test editor accepted vinyl")
                        page = find("OutputsPage")
                        js(page, "showTransferSetup = false")
                        js(page, 'openOutputContextMenu(jsonService.selectedPath, jsonService.selectedName, false, "json", 30, 30, jsonService.prepareExplorerContextSelection(0))')
                        for action in ("edit", "place", "export", "show"):
                            assert find("OutputContextAction:" + action).property("text") == find("OutputAction:" + action).property("text")
                        js(find("OutputContextAction:show"), "clicked()")
                        assert reveal.call_count == 2
                        js(page, "infoCardPath = jsonService.selectedPath; infoCardName = jsonService.selectedName; jsonInfoPopup.open()")
                        for action in ("edit", "place", "export", "show"):
                            assert find("OutputInfoAction:" + action).property("text") == find("OutputAction:" + action).property("text")
                        js(find("OutputInfoAction:export"), "clicked()")
                        selected = Path(service.selectedPath)
                        original = selected.read_bytes()
                        selected.unlink()
                        js(page, 'triggerArtworkAction("show", jsonService.selectedPath, 1)')
                        assert reveal.call_count == 2
                        selected.write_bytes(original)
                    assert find("OutputsPage").property("showTransferSetup")
                    js(find("OutputsPage"), "showTransferSetup = false")
                    service.selectAllExplorerEntries()
                    for action in ("edit", "place", "export", "show"):
                        assert not find("OutputAction:" + action).property("enabled"), action
                    assert find("OutputActionExplanation").property("text")
                    checked.append("toolbar-context-preview-actions-busy-stale-target-no-game-writes")
                    assert window.grabWindow().save(str(profile / "outputs-actions.png"))
                    timer.stop()
                    app.quit()
                    return
                stage[0] += 1
            except BaseException as error:
                errors.append(traceback.format_exc())
                window.grabWindow().save(str(profile / "outputs.png"))
                timer.stop()
                app.quit()
        timer.timeout.connect(check)
        timer.start(350)
        QTimer.singleShot(25000, app.quit)
        result = execute(app, engine, shutdown)
        print("Probe stage:", stage[0], "navigation:", navigation, flush=True)
        return result
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


class OutputCategoryTabsTests(unittest.TestCase):
    def test_real_outputs_and_liveries_pages_offscreen(self):
        cases = [("Night Blossom", 1440, 900, "1"), ("Apex Vector", 1024, 768, "1.25"),
                 ("Command Prompt", 1280, 800, "1"), ("Night City 2077", 1280, 800, "2")]
        if os.environ.get("KFPS_OUTPUTS_SINGLE_CASE"):
            cases = cases[:1]
        for theme, width, height, scale in cases:
            with self.subTest(theme=theme, scale=scale), tempfile.TemporaryDirectory(prefix="outputs-tabs-") as directory:
                profile = Path(directory)
                env = {key: value for key, value in os.environ.items() if not key.startswith("KFPS_")}
                env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QML_DISABLE_DISK_CACHE="1",
                           QT_SCALE_FACTOR=scale, KFPS_QML_GRAPHICS="software", KFPS_ACTIVITY_DISABLED="1",
                           KFPS_STARTUP_MUTED="1", QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-background-networking")
                for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
                    location = profile / key.lower()
                    location.mkdir()
                    env[key] = str(location)
                process = subprocess.run([sys.executable, "-I", "-B", "-c", SCRIPT, str(profile), theme, str(width), str(height)],
                                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=40,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                evidence = os.environ.get("KFPS_OUTPUT_TABS_EVIDENCE", "")
                if evidence:
                    target = Path(evidence) / (theme.replace(" ", "-") + "-" + scale)
                    target.mkdir(parents=True, exist_ok=True)
                    for name in ("outputs.png", "outputs-actions.png", "liveries.png", "result.json"):
                        if (profile / name).is_file():
                            shutil.copy2(profile / name, target / name)
                    (target / "process.log").write_text(process.stdout + process.stderr, encoding="utf-8")
                    for log in (profile / "runtime").rglob("*.log"):
                        shutil.copy2(log, target / log.name)
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)


if __name__ == "__main__":
    unittest.main()
