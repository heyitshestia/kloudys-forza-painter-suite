"""Exercise Redline in the real app with an isolated profile and no desktop input."""
from __future__ import annotations

import argparse
import ctypes
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--width", type=int, default=1600)
parser.add_argument("--height", type=int, default=1000)
parser.add_argument("--scale", type=float, default=1)
parser.add_argument("--rhi", action="store_true")
parser.add_argument("--threaded-smoke", action="store_true")
args = parser.parse_args()
if args.threaded_smoke and not args.rhi:
    parser.error("--threaded-smoke requires --rhi")
run = args.output.resolve()
profile = run / "profile"
profile.mkdir(parents=True, exist_ok=True)
os.environ.update(
    QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", QT_SCALE_FACTOR=str(args.scale),
    KFPS_QML_GRAPHICS="software", KFPS_ACTIVITY_DISABLED="1", KFPS_SKIP_STARTUP_INDEX="1",
    KFPS_SKIP_STARTUP_THUMBNAILS="1", KFPS_APP_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE="1",
    APPDATA=str(profile / "roaming"), LOCALAPPDATA=str(profile / "local"),
    QT_QPA_FONTDIR=str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
)
os.environ.pop("QSG_RHI_BACKEND", None)
if args.rhi:
    os.environ.update(QT_QPA_PLATFORM="windows", QT_QUICK_BACKEND="rhi", KFPS_QML_GRAPHICS="d3d11", QSG_RHI_PREFER_SOFTWARE_RENDERER="1", QSG_RENDER_LOOP="threaded" if args.threaded_smoke else "basic")
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI"), str(ROOT / "KFPS.UI/src")]
from PySide6.QtCore import QEvent, QMetaObject, QObject, QPoint, QSize, Qt, QTimer, qInstallMessageHandler
from PySide6.QtGui import QResizeEvent, QWindow
from PySide6.QtQml import QQmlEngine
from PySide6.QtTest import QTest
from PIL import Image, ImageChops
from PIL.ImageQt import fromqimage

messages = []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
spec = importlib.util.spec_from_file_location("redline_test_app", ROOT / "KFPS.UI/app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
paths = module.AppPaths.discover()
sample = profile / "app"
sample.mkdir(exist_ok=True)
shutil.copy2(ROOT / "VERSION", sample / "VERSION")
module.AppPaths.discover = classmethod(lambda cls: replace(paths, app_root=sample, runtime_root=profile / "runtime"))
settings_path = profile / "runtime/qml-shell-settings.json"
settings_path.parent.mkdir(exist_ok=True)
settings_path.write_text(json.dumps({
    "theme": "Redline", "reducedMotion": True, "ambientMotion": False,
    "supportUpscalerNoticeAcknowledged": True, "communityJoinNoticeAcknowledged": True,
    "backgroundRemoverNoticeAcknowledged": True, "dcinsideKoreanNotice202609Acknowledged": True,
}), encoding="utf-8")
protected = [ROOT / "VERSION", ROOT / "runtime/qml-shell-settings.json", *list((ROOT / "settings").glob("*.json"))]
def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None for p in protected}
before = hashes()


def fatal_qml_messages():
    return [m for m in messages if any(s in m for s in (
        "ReferenceError", "TypeError", "SyntaxError", "Unexpected token",
        "Expected token", "Cannot assign", "Unable to assign", "Binding loop", "is not a type",
    )) or ("Cannot open" in m and "/themes/nightcity/" not in m)]


def install(app, window, controller, community, settings, jsons, app_args):
    if args.threaded_smoke:
        steps = [("Redline", page) for page in ("create", "outputs", "liveries", "community", "editor", "tools", "support", "help", "update", "settings")]
        steps += [("Night Blossom", "settings"), ("2049", "create"), ("Redline", "create")]
        results, idle = [], {}
        foreground_handle = ctypes.windll.user32.GetForegroundWindow
        foreground_handle.restype = ctypes.c_void_p
        def finish_smoke(error=None):
            if error is None and fatal_qml_messages():
                error = AssertionError(fatal_qml_messages())
            report = {"steps": results, "error": repr(error) if error else None, "messages": sorted(set(messages)), "protected_unchanged": hashes() == before, "graphics_api": str(window.rendererInterface().graphicsApi()), "render_loop": "threaded", "idle": idle}
            (run / "threaded-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report, indent=2))
            window.close()
            app.exit(1 if error or not report["protected_unchanged"] else 0)
        def sample_idle():
            frames = [0]
            def swapped(): frames[0] += 1
            window.frameSwapped.connect(swapped)
            cpu, wall = time.process_time(), time.perf_counter()
            def sampled():
                window.frameSwapped.disconnect(swapped)
                animations = [obj.metaObject().className() for obj in window.findChildren(QObject) if "Animation" in obj.metaObject().className() and obj.property("running")]
                idle.update(cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall, frames=frames[0], running_animations=animations)
                finish_smoke(AssertionError("Inactive window keeps rendering") if frames[0] > 2 or animations else None)
            QTimer.singleShot(2000, sampled)
        def step(index):
            if index == len(steps):
                QTimer.singleShot(4000, sample_idle)
                return
            theme, page = steps[index]
            settings.theme = theme
            controller.navigate(page)
            started = time.perf_counter()
            def captured():
                try:
                    assert settings.theme == theme and controller.currentPage == page
                    assert not fatal_qml_messages(), fatal_qml_messages()
                    host = window.findChild(QObject, "CachedPageHost")
                    if host.property("item") is None:
                        assert time.perf_counter()-started < 10, "Page not ready: " + page
                        QTimer.singleShot(100, captured)
                        return
                    if theme == "Redline" and page == "create":
                        stack, names = [window.contentItem()], set()
                        while stack:
                            item = stack.pop()
                            if item.isVisible(): names.add(item.objectName())
                            stack.extend(item.childItems())
                        assert {"RedlineConsole", "RedlineWorkbench", "RedlineGenerate"} <= names
                    assert not window.isActive() and foreground_handle() != int(window.winId())
                    frame = window.grabWindow()
                    target = run / f"threaded-{index:02d}-{page}.png"
                    assert not frame.isNull() and frame.save(str(target))
                    with Image.open(target) as image:
                        assert any(hi-lo > 50 for lo,hi in image.convert("RGB").getextrema())
                    results.append({"theme":theme, "page":page, "passed":True})
                    QTimer.singleShot(50, lambda:step(index+1))
                except Exception as error:
                    finish_smoke(error)
            QTimer.singleShot(1200, captured)
        QTimer.singleShot(1500, lambda:step(0))
        return
    results, measurements = [], {}
    def check(condition, name):
        (run / "progress.txt").write_text(name, encoding="utf-8")
        results.append({"test": name, "passed": bool(condition)})
        if not condition:
            raise AssertionError(name)
    def items():
        stack = [window.contentItem()]
        while stack:
            item = stack.pop()
            yield item
            stack.extend(item.childItems())
    def find(name):
        matches = [item for item in items() if item.objectName() == name]
        return next((item for item in matches if item.isVisible()), matches[0] if matches else None)
    def click(name):
        item = find(name)
        if name.startswith("NavButton:") and (item is None or not item.isVisible()):
            groups = {"Create":0, "Outputs":1, "Liveries":1, "Community":2, "Editor":3, "Tools":3, "Settings":4, "Help":4, "Support":4, "Update":4}
            click("RedlineGroup:" + str(groups[name.split(":", 1)[1]]))
            item = find(name)
        check(item is not None and item.isVisible() and item.isEnabled(), "reachable " + name)
        ancestor = item.parentItem()
        while ancestor is not None:
            if ancestor.property("contentY") is not None and ancestor.property("contentHeight") is not None:
                point = item.mapToItem(ancestor, item.boundingRect().center())
                offset = max(0, min(float(ancestor.property("contentHeight")) - ancestor.height(), float(ancestor.property("contentY")) + point.y() - ancestor.height()/2))
                ancestor.setProperty("contentY", offset)
            ancestor = ancestor.parentItem()
        window.grabWindow()
        QTest.qWait(50)
        point = item.mapToScene(item.boundingRect().center()).toPoint()
        check(0 <= point.x() < window.width() and 0 <= point.y() < window.height(), "onscreen " + name)
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point)
        QTest.qWait(150)
    def capture(name):
        window.grabWindow()
        QTest.qWait(60)
        shot = window.grabWindow()
        check(not shot.isNull() and shot.save(str(run / (name + ".png"))), "capture " + name)
        with Image.open(run / (name + ".png")) as image:
            check(any(hi-lo > 60 for lo,hi in image.convert("RGB").getextrema()), "nonblank " + name)
        if args.rhi:
            check(not window.isActive(), "no foreground activation " + name)
        return shot
    def edit(name, text):
        item = find(name)
        item.forceActiveFocus()
        QTest.keyClick(window, Qt.Key_A, Qt.ControlModifier)
        for char in text:
            QTest.keyClick(window, ord(char))
        QTest.keyClick(window, Qt.Key_Tab)
        QTest.qWait(80)
    def finish(error=None):
        if error:
            results.append({"error": repr(error)})
            window.grabWindow().save(str(run / "failure.png"))
        after=hashes()
        report = {"checks": results, "measurements": measurements, "messages": sorted(set(messages)), "error": repr(error) if error else None, "protected_unchanged": after == before, "protected_changes":[path for path in before if before[path]!=after[path]]}
        (run / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"checks":len(results),"error": report["error"],"protected_unchanged": report["protected_unchanged"],"qml_errors":fatal_qml_messages()}))
        window.close()
        app.exit(1 if error or hashes() != before else 0)
    def checks():
        try:
            window.resize(args.width,args.height)
            window.grabWindow()
            if args.rhi and window.contentItem().width() != window.width():
                app.sendEvent(window,QResizeEvent(window.size(),QSize(int(window.contentItem().width()),int(window.contentItem().height()))))
            QTest.qWait(100)
            check(find("RedlineConsole") is not None and find("RedlineWorkbench") is not None,"custom shell and workbench loaded")
            check(not fatal_qml_messages(),"initial QML clean")
            capture("create-empty")
            context=QQmlEngine.contextForObject(window)
            source=context.contextProperty("sourceService")
            generation=context.contextProperty("generationService")
            session=find("CachedPageHost").property("item")
            edit("RedlineLayers","1375")
            check(session.property("templateLayers")=="1375","budget edits authoritative form")
            check(session.property("checkpointValues")=="500,1000,1250,1375","automatic checkpoints preserved")
            settings.theme="2049"
            QTest.qWait(250)
            check(find("ArchiveWorkbench") is not None,"2049 presentation still loads")
            check(session.property("templateLayers")=="1375","state preserved in 2049")
            settings.theme="Night Blossom"
            QTest.qWait(250)
            check(session.property("templateLayers")=="1375","state preserved in original layout")
            settings.theme="Redline"
            QTest.qWait(250)
            from PIL import ImageDraw
            fixture=profile/"source.png"
            art=Image.new("RGBA",(480,480),(0,0,0,0))
            draw=ImageDraw.Draw(art)
            draw.rounded_rectangle((50,50,430,430),radius=35,fill=(35,170,190,255))
            draw.ellipse((130,130,350,350),fill=(210,40,80,255))
            art.save(fixture)
            fixture2=profile/"second.png"
            art.save(fixture2)
            source.setPaths([str(fixture),str(fixture2)])
            QTest.qWait(300)
            check(source.count==2,"multi-image queue retained")
            launches=[]
            original_start=generation._start_single
            generation._start_single=lambda *values: launches.append(values)
            try:
                click("RedlineGenerate")
                check(len(launches)==1 and launches[0][2]=="1375","real queue receives edited budget")
                check(launches[0][3]=="500,1000,1250,1375","real queue receives checkpoints")
                check(Path(launches[0][0])==fixture,"real queue receives chosen source")
            finally:
                generation._start_single=original_start
            check(not find("RedlineStopSafe").isEnabled(),"idle stops disabled")
            shot=capture("source-loaded")
            artwork=find("RedlineArtwork")
            point=artwork.mapToScene(artwork.boundingRect().center())
            pixel=shot.pixelColor(round(point.x()*shot.width()/window.width()),round(point.y()*shot.height()/window.height()))
            check(abs(pixel.red()-210)<5 and abs(pixel.green()-40)<5 and abs(pixel.blue()-80)<5,"artwork colours unfiltered")
            click("RedlineViewOutput")
            check(find("RedlineWorkbench").property("viewIndex")==1,"output view selection")
            click("RedlineToggleLog")
            check(find("RedlineLog").isVisible(),"live log reachable")
            click("RedlineViewSource")
            check(not find("RedlineWorkbench").property("showLog"),"source returns from log")
            settings.manualOverrides=True
            click("RedlineOpenOverrides")
            check(window.findChild(QObject,"RedlineOverrides").property("visible"),"overrides open")
            edit("RedlineOverride:seedValue","42")
            check(session.property("seedValue")=="42","seed updates shared form")
            capture("overrides")
            close=find("RedlineOverridesClose")
            seed=find("RedlineOverride:seedValue")
            check(close.mapToScene(close.boundingRect().topLeft()).y()>=seed.mapToScene(seed.boundingRect().bottomLeft()).y(),"override footer clears inputs")
            click("RedlineOverridesClose")
            for name,key in (("Detail","detailEnabled"),("Luma","lumaEnabled"),("Repair","repairEnabled"),("Boost","boostEnabled")):
                old=session.property(key)
                find("Redline"+name).forceActiveFocus()
                QTest.keyClick(window,Qt.Key_Space)
                QTest.qWait(40)
                check(session.property(key)!=old,"option changes "+key)
            generation._start_single=lambda *values: launches.append(values)
            try:
                click("RedlineGenerate")
                check(all(launches[-1][4:9]),"all options reach real queue")
                check(launches[-1][12]==42,"manual seed reaches real queue")
            finally:
                generation._start_single=original_start
            click("RedlineSourceReport")
            check(window.findChild(QObject,"RedlineSourceReportDialog").property("visible"),"source report opens")
            click("RedlineReportClose")
            simulated=profile/"simulated-run"
            simulated.mkdir(exist_ok=True)
            generation._running=True
            generation._run_dir=str(simulated)
            generation.changed.emit()
            QTest.qWait(80)
            check(not find("RedlineGenerate").isEnabled(),"running prevents duplicate launch")
            click("RedlineStopSafe")
            check((simulated/".v2-stop").read_text().strip()=="stop","safe stop uses real marker")
            if not args.rhi:
                click("RedlineStopNow")
                confirm=next(obj for obj in window.findChildren(QObject) if obj.property("title")=="Stop generation now?")
                check(confirm.property("visible"),"abort requires shared confirmation")
                QMetaObject.invokeMethod(confirm,"close")
                QTest.qWait(100)
                check(not confirm.property("visible"),"abort confirmation can be dismissed")
                window.requestActivate()
                QTest.qWait(120)
            generation._running=False
            generation._run_dir=""
            generation.changed.emit()
            for page in routes:
                click("NavButton:"+page.title())
                check(controller.currentPage==page,"navigation "+page)
                check(find("NavButton:"+page.title()).property("selected"),"selected route "+page)
                button=find("NavButton:"+page.title())
                labels=[item for item in items() if item.objectName()=="RedlineButtonLabel" and item.isVisible() and item.property("text")==page.upper()]
                check(bool(labels) and all(not item.property("truncated") for item in labels),"navigation label fits "+page)
                if page=="outputs":
                    for index in range(4):
                        click("OutputCategoryTab:"+str(index))
                        check(jsons.sourceIndex==index and bool(jsons.currentFolder),"output category "+str(index))
                if page=="community":
                    labels=[item for item in items() if item.isVisible() and item.property("text") in ("Browse", "Upload", "Profile") and item.property("truncated") is not None]
                    check(bool(labels) and all(not item.property("truncated") for item in labels), "community menu labels fit")
                    capture("community")
                if page=="settings":
                    for section in (1, 2, 0):
                        click("RedlineSettingsSection:"+str(section))
                        check(find("RedlineSettingsSection:"+str(section)).property("selected"), "settings section "+str(section))
                        capture("settings-section-"+str(section))
                    combo=next(item for item in items() if item.objectName()=="KfpsComboBox" and item.property("currentText")=="Redline")
                    combo.forceActiveFocus()
                    QTest.keyClick(window,Qt.Key_Space)
                    QTest.qWait(120)
                    window.grabWindow()
                    check(combo.property("down"),"theme menu opens")
                    QTest.keyClick(window,Qt.Key_Home)
                    QTest.keyClick(window,Qt.Key_Return)
                    QTest.qWait(250)
                    check(settings.theme=="Night Blossom","settings selects existing theme")
                    combo.forceActiveFocus()
                    QTest.keyClick(window,Qt.Key_Space)
                    QTest.qWait(120)
                    window.grabWindow()
                    QTest.keyClick(window,Qt.Key_End)
                    QTest.keyClick(window,Qt.Key_Return)
                    QTest.qWait(250)
                    check(settings.theme=="Redline","settings selects Redline")
                if page in ("outputs","liveries","settings"):
                    QTest.mouseMove(window,QPoint(1,1))
                    capture(page)
            if not args.rhi:
                settings.reducedMotion=False
                settings.ambientMotion=True
                window.requestActivate()
                QTest.qWait(250)
                backdrop=find("RedlineBackdrop")
                check(backdrop.property("motionAllowed"),"active ambient enabled")
                frames=[]
                phases=[]
                for _ in range(40):
                    phases.append(backdrop.property("disruption"))
                    frame=fromqimage(window.grabWindow()).convert("RGB")
                    frame.thumbnail((1100,700),Image.Resampling.LANCZOS)
                    frames.append(frame)
                    QTest.qWait(120)
                check(len(set(phases)) > 2,"fragmented background animation moves")
                check(any(ImageChops.difference(frames[0],frame).getbbox() is not None for frame in frames[1:]),"ambient changes rendered pixels")
                frames[0].save(run/"ambient-motion.gif",save_all=True,append_images=frames[1:],duration=120,loop=0,optimize=False)
                for pref,value in (("ambientMotion",False),("reducedMotion",True)):
                    setattr(settings,pref,value)
                    QTest.qWait(80)
                    check(not backdrop.property("motionAllowed"),pref+" stops motion")
                    setattr(settings,pref,not value)
                controller.navigate("outputs")
                QTest.qWait(20)
                check(find("RedlinePageTransition").property("progress")<1,"route transition begins")
                transition_frames=[]
                for _ in range(16):
                    frame=fromqimage(window.grabWindow()).convert("RGB")
                    frame.thumbnail((1100,700),Image.Resampling.LANCZOS)
                    transition_frames.append(frame)
                    QTest.qWait(24)
                check(ImageChops.difference(transition_frames[0],transition_frames[-1]).getbbox() is not None, "block reveal changes rendered pixels")
                transition_frames[0].save(run/"route-reveal.gif",save_all=True,append_images=transition_frames[1:],duration=45,loop=0,optimize=False)
                QTest.qWait(350)
                check(find("RedlinePageTransition").property("contentOffsetX")==0,"route transition settles")
                window.showMinimized()
                QTest.qWait(80)
                check(not backdrop.property("motionAllowed"),"minimized stops motion")
                window.showNormal()
                other=QWindow(); other.resize(16,16); other.show(); other.requestActivate()
                QTest.qWait(100)
                check(not backdrop.property("motionAllowed"),"inactive stops motion")
                other.close()
            settings.reducedMotion=True
            controller.navigate("create")
            QTest.qWait(200)
            if args.rhi:
                review_art=ROOT/"KFPS.UI/assets/mini-kloudy.png"
                with Image.open(review_art) as image:
                    expected_width=image.width
                source.setPaths([str(review_art)])
                started=time.perf_counter()
                while find("RedlineArtwork").property("implicitWidth") != expected_width and time.perf_counter()-started < 5:
                    QTest.qWait(80)
                check(find("RedlineArtwork").property("implicitWidth")==expected_width, "review artwork loaded")
                QTest.mouseMove(window,QPoint(1,1))
                QTest.qWait(200)
                capture("create-product-art")
            settings.save()
            check(json.loads(settings_path.read_text())["theme"]=="Redline","theme persists")
            check(hashes()==before,"personal settings unchanged")
            check(not fatal_qml_messages(),"no new QML errors")
            frames=[0]
            def swapped(): frames[0]+=1
            window.frameSwapped.connect(swapped)
            wall,cpu=time.perf_counter(),time.process_time()
            def idle_complete():
                try:
                    window.frameSwapped.disconnect(swapped)
                    measurements["idle"]={"frames":frames[0],"cpu_seconds":time.process_time()-cpu,"wall_seconds":time.perf_counter()-wall}
                    check(not find("RedlineBackdrop").property("motionAllowed"),"idle ambient stopped")
                    if args.rhi: check(frames[0]<=2,"native inactive rendering stopped")
                    click("TitleBarButton:close")
                    check(not window.isVisible(),"native close works")
                    finish()
                except Exception as error: finish(error)
            QTimer.singleShot(2000,idle_complete)
        except Exception as error:
            finish(error)
    routes=("outputs","liveries","community","editor","tools","support","help","update","settings","create")
    window.setProperty("liveryWipNoticeAcknowledged",True)
    def cold(index=0):
        if index==len(routes):
            QTimer.singleShot(100,checks)
            return
        controller.navigate(routes[index])
        started=time.perf_counter()
        def poll():
            if fatal_qml_messages(): finish(AssertionError(fatal_qml_messages())); return
            host=window.findChild(QObject,"CachedPageHost")
            if host is not None and host.property("item") is not None and host.property("currentPage")==routes[index]:
                QTimer.singleShot(0,lambda:cold(index+1))
            elif time.perf_counter()-started>10: finish(TimeoutError(routes[index]))
            else: QTimer.singleShot(50,poll)
        QTimer.singleShot(50,poll)
    QTimer.singleShot(1000,cold)


module.install_development_harness=install
sys.argv=[str(ROOT/"KFPS.UI/app.py"),"--allow-source-download","--demo","--theme-preview","Redline","--width",str(args.width),"--height",str(args.height),"--page","create"]
if args.rhi: sys.argv.append("--community-preview-background")
def timeout():
    (run/"timeout.txt").write_text("Test exceeded 180 seconds.\n"+"\n".join(messages[-60:]),encoding="utf-8")
    os._exit(124)
watchdog=threading.Timer(180,timeout)
watchdog.daemon=True
watchdog.start()
raise SystemExit(module.main())
