"""Exercise the real main window without desktop focus or audible playback."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
from dataclasses import replace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
scenario = sys.argv[1] if len(sys.argv) > 1 else "normal"
width = int(sys.argv[2]) if len(sys.argv) > 2 else 1280
height = int(sys.argv[3]) if len(sys.argv) > 3 else 760
run_root = Path(os.environ.get("KFPS_STARTUP_TEST_RUN_ROOT", str(ROOT / "runtime/test-runs/ps2-startup")))
RUN = run_root / (f"{scenario}-{width}x{height}" + ("-v2" if scenario == "library" else ""))
profile = RUN / "profile"
if scenario == "library-warm":
    profile = run_root / "library-1280x760-v2/profile"
RUN.mkdir(parents=True, exist_ok=True)
profile.mkdir(parents=True, exist_ok=True)
(RUN / "tmp").mkdir(exist_ok=True)
os.environ.update(TEMP=str(RUN / "tmp"), TMP=str(RUN / "tmp"))
os.environ.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software", KFPS_QML_GRAPHICS="software",
                  KFPS_ACTIVITY_DISABLED="1", KFPS_DISABLE_RTTI_UPDATE="1",
                  KFPS_STARTUP_MUTED="0" if scenario == "muted-start" else "1",
                  QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --remote-allow-origins=*",
                  KFPS_SKIP_STARTUP_THUMBNAILS="1", KFPS_APP_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE="1",
                  QT_QPA_FONTDIR=str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
                  QT_FFMPEG_DECODING_HW_DEVICE_TYPES=",")
sys.path[:0] = [str(ROOT), str(ROOT / "KFPS.UI"), str(ROOT / "KFPS.UI/src")]
from PySide6.QtCore import QObject, QPoint, Qt, QTimer, QMetaObject, qInstallMessageHandler
from PySide6.QtGui import QWindow
from PySide6.QtTest import QTest

messages = []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
spec = importlib.util.spec_from_file_location("startup_test_app", ROOT / "KFPS.UI/app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
original = module.AppPaths.discover()
sample = profile / "app"
sample.mkdir(exist_ok=True)
shutil.copy2(ROOT / "VERSION", sample / "VERSION")
if scenario == "library":
    payload = json.dumps({"shapes":[{"type":1048677,"data":[i%30*12,i//30*12,1,1,0,0,0],
                                     "color":[90,140,210,255]} for i in range(300)]})
    for source in ("generated","editor","exported","library"):
        for i in range(375):
            folder = sample / "imgs" / source
            if source != "generated":
                folder = folder / f"collection-{i//25}"
            folder.mkdir(parents=True,exist_ok=True)
            (folder/f"vinyl-{i}.json").write_text(payload,encoding="utf-8")
if scenario in ("library", "library-warm"):
    original_scan = module.JsonService._request_source_scan
    def threaded_scan(self, source, force=False):
        # Keep Qt's offscreen platform, but exercise production's executor branch.
        with patch.dict(os.environ, {"QT_QPA_PLATFORM":"test-threaded-scan"}):
            return original_scan(self,source,force)
    module.JsonService._request_source_scan = threaded_scan
runtime = profile / "runtime"
runtime.mkdir(exist_ok=True)
module.AppPaths.discover = classmethod(lambda cls: replace(original, app_root=sample, runtime_root=runtime))
(runtime / "qml-shell-settings.json").write_text(json.dumps({"theme": "Night Blossom" if scenario == "legacy" else "Original PS2",
    "reducedMotion": scenario == "reduced", "ambientMotion": True,
    "ps2StartupMuted": scenario == "muted-start",
    "supportUpscalerNoticeAcknowledged": True, "communityJoinNoticeAcknowledged": True,
    "backgroundRemoverNoticeAcknowledged": True, "dcinsideKoreanNotice202609Acknowledged": True}), encoding="utf-8")
media = runtime / "theme-assets/ps2/startup.mp4"
media.parent.mkdir(parents=True, exist_ok=True)
if scenario == "corrupt":
    media.write_bytes(b"not a valid movie")
elif scenario == "audio-only":
    import wave
    with wave.open(str(media), "wb") as audio_fixture:
        audio_fixture.setnchannels(1)
        audio_fixture.setsampwidth(2)
        audio_fixture.setframerate(8000)
        audio_fixture.writeframes(b"\x00\x00" * 1600)
elif scenario not in ("missing", "packaged"):
    shutil.copy2(ROOT / "KFPS.UI/assets/themes/ps2/startup.mp4", media)
if scenario == "missing":
    original_service = module.StartupSequenceService
    class MissingAssetService(original_service):
        def __init__(self, paths, *args, **kwargs):
            super().__init__(replace(paths, asset_root=profile / "missing-assets"), *args, **kwargs)
    module.StartupSequenceService = MissingAssetService

results = []
def check(value, name):
    results.append({"test":name,"passed":bool(value)})
    if not value:
        raise AssertionError(name)

def install(app, window, controller, community, settings, jsons, args):
    start = time.monotonic()
    cpu_start = time.process_time()
    def items():
        stack = [window.contentItem()]
        while stack:
            item = stack.pop(); yield item; stack.extend(item.childItems())
    def find(name):
        return next((item for item in items() if item.objectName() == name), None)
    def wait(predicate, timeout=22000):
        until = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < until:
            QTest.qWait(50)
        return bool(predicate())
    def click(name):
        target = find(name)
        check(target is not None and target.isVisible(), "reachable " + name)
        # Theme changes can reflow the cached Settings page after its first paint.
        previous = None
        for _ in range(20):
            point = target.mapToScene(target.boundingRect().center()).toPoint()
            QTest.qWait(100)
            if point == previous:
                break
            previous = point
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, target.mapToScene(target.boundingRect().center()).toPoint())
        QTest.qWait(70)
    def capture(name):
        if name == "menu":
            dashboard = find("Ps2Dashboard")
            check(wait(lambda:dashboard.property("reveal") >= .99,2000), "menu entrance completes before capture")
            QTest.qWait(50)
        target = RUN / (name + ".png")
        window.grabWindow().save(str(target))
        if name in ("opening", "flight", "logo"):
            import numpy as np
            from PIL import Image
            data=np.array(Image.open(target).convert("RGB"))
            h,w=data.shape[:2]
            center=data[h//4:h*3//4,w//4:w*3//4]
            check(int((center.max(axis=2)>30).sum())>100, name + " has visible decoded pixels")
    def checks():
        try:
            if scenario == "legacy":
                check(find("Ps2Startup") is None, "legacy theme has no cinematic")
                check(find("ApplicationWorkspace").isVisible(), "legacy workspace remains accessible")
                return
            intro, menu = find("Ps2Startup"), find("Ps2Dashboard")
            check(intro is not None, "startup component loaded")
            for name in ("Ps2StartupMute", "Ps2StartupSkip", "Ps2DashboardEnter", "Ps2DashboardBack", "Ps2DashboardCredits"):
                check(find(name) is None, "removed control: " + name)
            if scenario in ("missing", "reduced", "corrupt", "audio-only"):
                check(wait(lambda:menu.isVisible(),6000), scenario + " opens menu without trapping user")
                check(not intro.isVisible(), "cinematic inactive after bypass")
                capture("menu")
                return
            check(intro.isVisible(), "intro in real main window")
            check(intro.parentItem().objectName() == "ApplicationBody", "intro belongs to body, not popup")
            check(not menu.isVisible(), "menu waits behind intro")
            check(not find("ApplicationWorkspace").isVisible(), "workspace not exposed during startup")
            service = intro.property("service")
            if scenario == "packaged":
                check("/KFPS.UI/assets/themes/ps2/startup.mp4" in service.source, "uses the packaged movie without a runtime override")
            initial_ready = service.ready
            player = service._player
            audio = service._audio
            check(player is not None, "native MediaPlayer loaded")
            check(audio.property("muted"), "tests are silent")
            if scenario == "muted-start":
                check(settings.ps2StartupMuted and service.muted, "saved mute applied before initial playback")
            check(wait(lambda:int(player.property("position"))>700,5000), "decoder advances")
            if scenario == "slow":
                service._ready = False
                jsons._indexing_sources.add(999)
            if scenario == "close":
                click("TitleBarButton:close")
                check(not window.isVisible(), "close button closes during playback")
                return
            if scenario == "theme":
                settings.theme = "Night Blossom"
                QTest.qWait(200)
                check(find("Ps2Startup") is None, "theme switch destroys playback")
                settings.theme = "Original PS2"
                QTest.qWait(200)
                check(find("Ps2Dashboard").isVisible(), "returning to theme opens menu without replay")
                return
            if scenario == "skip":
                QTest.keyClick(window, Qt.Key_Escape)
                QTest.qWait(100)
                check(menu.isVisible() and not intro.isVisible(), "skip opens menu directly")
                check(int(player.property("position")) == 0, "skip stops soundtrack")
                return
            if scenario == "reduce-live":
                settings.reducedMotion = True
                QTest.qWait(100)
                check(menu.isVisible() and not intro.isVisible(), "reduced motion stops active cinematic")
                return
            if scenario == "normal":
                drag = window.findChild(QObject, "TitleBarDragHandler")
                moves=[]
                drag.activeChanged.connect(lambda: moves.append(drag.property("active")))
                origin=QPoint(window.width()//2,12)
                QTest.mousePress(window,Qt.LeftButton,Qt.NoModifier,origin)
                QTest.mouseMove(window,origin+QPoint(40,0),30)
                QTest.mouseMove(window,origin+QPoint(70,0),30)
                QTest.mouseRelease(window,Qt.LeftButton,Qt.NoModifier,origin+QPoint(70,0))
                check(True in moves,"title-bar move remains available during intro")
                click("TitleBarButton:max")
                check(window.visibility() == QWindow.Maximized, "maximize works during intro")
                click("TitleBarButton:max")
                window.resize(width,height)
                click("TitleBarButton:min")
                check(window.visibility() == QWindow.Minimized, "minimize works during intro")
                QTest.qWait(100)
                paused = int(player.property("position"))
                QTest.qWait(450)
                check(abs(int(player.property("position"))-paused)<100, "minimize pauses picture and sound together")
                window.showNormal()
                check(wait(lambda:int(player.property("position"))>paused+200,2500), "restore resumes shared timeline")
                QTest.mouseMove(window,QPoint(15,window.height()//2))
            check(wait(lambda:int(player.property("position"))>2800), "opening sequence reaches cue")
            capture("opening")
            check(wait(lambda:int(player.property("position"))>8300), "camera flight reaches cue")
            capture("flight")
            check(wait(lambda:int(player.property("position"))>14950), "final logo follows sound cue")
            capture("logo")
            if scenario == "slow":
                check(wait(lambda:intro.property("waiting"),4000), "slow load holds silent end state")
                capture("waiting")
                jsons._indexing_sources.clear()
                service._check_ready()
            check(wait(lambda:menu.isVisible(),5000), "sound completion hands off to menu")
            check(not intro.isVisible(), "cinematic released after handoff")
            check(int(player.property("position")) == 0, "media stopped after handoff")
            capture("menu")
            check(not jsons.indexing, "output index ready before menu")
            if scenario in ("library", "library-warm"):
                total = sum(len(index.get("rows",[])) for index in jsons._source_index_cache.values())
                check(total == 1500, "all 1500 synthetic outputs indexed during intro")
            click("Ps2HomeConfiguration")
            QTest.qWait(300)
            check(controller.currentPage == "settings", "menu opens real KFPS settings")
            check(find("Ps2IntroMuteSetting").isVisible(), "persistent mute setting remains available")
            check(find("Ps2TestIntro") is None, "recording button removed from application")
            from kfps_ui.settings_service import SettingsService
            before = settings.ps2StartupMuted
            click("Ps2IntroMuteSetting")
            check(settings.ps2StartupMuted != before, "mute setting toggles")
            check(SettingsService(runtime / "qml-shell-settings.json").ps2StartupMuted == (not before), "mute survives settings reload")
            capture("settings")
            settings.theme = "Night Blossom"
            QTest.qWait(250)
            check(not find("Ps2IntroMuteSetting").isVisible(), "mute setting hidden outside PS2")
            settings.theme = "Original PS2"
            QTest.qWait(250)
            check(find("Ps2Dashboard").isVisible() and not find("Ps2Startup").isVisible(), "theme return does not replay startup")
            click("Ps2HomeConfiguration")
            QTest.qWait(250)
            intro, menu = find("Ps2Startup"), find("Ps2Dashboard")
            click("Ps2DashboardLaunch")
            check(menu.isVisible() and not intro.isVisible(), "return to menu never replays startup")
        except Exception as exc:
            capture("failure")
            results.append({"error":repr(exc)})
        finally:
            failures=[m for m in messages if any(s in m for s in ("ReferenceError", "TypeError", "is not a type", "failed to load component", "Binding loop", "Unable to assign", "Failed to get image", "Invalid image provider"))]
            results.append({"test":"no QML failures", "passed":not failures,"errors":failures})
            payload={"scenario":scenario,"elapsed":time.monotonic()-start,"cpuSeconds":time.process_time()-cpu_start,
                     "framesDecoded": service._frame_revision if 'service' in locals() else 0,
                     "loadingReadySeconds": service._ready_elapsed if 'service' in locals() else None,
                     "readyAtFirstCheck": initial_ready if 'initial_ready' in locals() else None,
                     "checks":results,"messages":messages}
            (RUN / "results.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
            print(json.dumps(payload,indent=2))
            app.exit(1 if any(r.get("passed") is False or "error" in r for r in results) else 0)
    QTimer.singleShot(300,checks)
module.install_development_harness = install
sys.argv=[str(ROOT / "KFPS.UI/app.py"),"--demo","--startup-preview","--allow-source-download","--width",str(width),"--height",str(height)]
raise SystemExit(module.main())
