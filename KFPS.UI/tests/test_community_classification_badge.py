"""Render actual gallery labels without using the user's desktop or account."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
from kfps_ui.theme_catalog import THEME_PRESETS


def native(output):
    sys.path.insert(0, str(UI / "src"))
    from PySide6.QtCore import QObject, QPointF, Qt, QUrl
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
    from PySide6.QtQuick import QQuickView
    from PySide6.QtTest import QTest
    app = QGuiApplication([])
    for name in ("segoeui.ttf", "segoeuib.ttf", "malgun.ttf", "meiryo.ttc"):
        path = Path(os.environ.get("SystemRoot", "C:/Windows")) / "Fonts" / name
        if path.is_file(): QFontDatabase.addApplicationFont(str(path))
    view = QQuickView()
    view.setFlags(Qt.Tool | Qt.WindowDoesNotAcceptFocus)
    engine = view.engine()
    engine.addImportPath(str(UI / "qml"))
    engine.rootContext().setContextProperty("assetRoot", QUrl.fromLocalFile(str(UI / "assets")).toString())
    engine.rootContext().setContextProperty("screenshotMode", True)
    component = QQmlComponent(engine)
    component.setData('''
import QtQuick
import Kfps.Theme 1.0
import "../qml/community-preview"
Rectangle {
    id: root
    width: 360; height: 340; color: Theme.surface
    property var row: ({id:"test",title:"Artwork",creator:"Test",state:"available",ends:"future",game:"FH6",shapes:400,score:0,supporter:true,kind:"vinyl",canClaim:true,classification:"handmade"})
    property string language: "en"
    property bool claims: false
    property int clicks: 0
    function ui(en, ko) { return language === "ko" ? ko : language === "ja" && en === "Handmade" ? "手作り" : language === "ja" && en === "Toolmade" ? "ツール制作" : en }
    PreviewArtwork { id: tile; objectName:"tile"; x:10; y:10; width:root.width-20; height:320; artwork:root.row; ui:root.ui; claimMode:root.claims; onChosen:root.clicks++ }
}
'''.encode(), QUrl.fromLocalFile(str(UI / "tests/classification-badge-harness.qml")))
    root = component.create()
    assert root is not None, [e.toString() for e in component.errors()]
    view.setContent(component.url(), component, root)
    view.show(); QTest.qWait(40)

    def expression(code, item=None):
        target = root if item is None else item
        expr = QQmlExpression(QQmlEngine.contextForObject(target), target, code)
        result, _ = expr.evaluate()
        assert not expr.hasError(), expr.error().toString()
        return result

    cases = []
    for theme in THEME_PRESETS:
        expression("Theme.supporterUnlocked=true; Theme.themeName=" + json.dumps(theme.name))
        for width in (220, 360):
            root.setWidth(width); view.resize(width, 340)
            for language in ("en", "ko", "ja"):
                root.setProperty("language", language)
                for classification in ("handmade", "toolmade"):
                    expression("row=Object.assign({},row,{classification:" + json.dumps(classification) + "})")
                    root.setProperty("claims", classification == "handmade")
                    QTest.qWait(15)
                    badge = root.findChild(QObject, "ClassificationBadge:test")
                    claim = root.findChild(QObject, "SelectClaim:test")
                    clock = root.findChild(QObject, "TimedBadge:test")
                    assert badge.isVisible() and clock.isVisible()
                    color = expression("Theme.classificationHandmade" if classification == "handmade" else "Theme.classificationToolmade")
                    assert expression("border.color", badge) == color
                    label = badge.property("label")
                    assert label == ({"en": ["Handmade", "Toolmade"], "ko": ["수작업", "도구 제작"], "ja": ["手作り", "ツール制作"]}[language][classification == "toolmade"])
                    pos = badge.mapToScene(QPointF(0, 0))
                    assert pos.x() >= 10 and pos.x() + badge.width() <= width - 10
                    assert pos.y() > clock.mapToScene(QPointF(0, clock.height())).y()
                    if claim.isVisible():
                        assert pos.y() + badge.height() < claim.mapToScene(QPointF(0, 0)).y()
                    screenshot = view.grabWindow()
                    assert not screenshot.isNull()
                    # Offscreen Qt may return physical pixels with DPR metadata 1.
                    ratio = screenshot.width() / view.width()
                    region = screenshot.copy(round((pos.x()+3)*ratio), round((pos.y()+2)*ratio),
                                             round((badge.width()-6)*ratio), round((badge.height()-4)*ratio))
                    # Interior must contain both label pixels and its themed background.
                    colors = {region.pixelColor(x,y).rgba() for x in range(region.width()) for y in range(region.height())}
                    if len(colors) <= 4:
                        screenshot.save(str(output / "failed.png"))
                        print("capture", screenshot.width(), screenshot.height(), ratio, "view", view.width(), view.height(),
                              "badge", pos.x(), pos.y(), badge.width(), badge.height(), "region", region.width(), region.height(), flush=True)
                    assert len(colors) > 4, (theme.name, language, classification, "label not painted")
                    before = root.property("clicks")
                    QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier,
                                     badge.mapToScene(QPointF(badge.width()/2,badge.height()/2)).toPoint())
                    assert root.property("clicks") == before + 1
                    if width == 360 and language == "en":
                        screenshot.save(str(output / (theme.qml_component + "-" + classification + ".png")))
                    cases.append([theme.name, width, language, classification])
    expression('row=Object.assign({},row,{classification:"unknown"})'); QTest.qWait(20)
    assert not root.findChild(QObject, "ClassificationBadge:test").isVisible()
    view.close()
    (output / "result.json").write_text(json.dumps({"passed": True, "cases": len(cases)}))
    print(f"PASS {len(cases)} rendered classification cases; theme colours, pixels, click passthrough, claims and clock spacing")


class ClassificationBadgeTests(unittest.TestCase):
    def test_labels_are_visible_and_do_not_overlap_or_intercept_clicks(self):
        for scale in ("1", "1.5"):
            with self.subTest(scale=scale), tempfile.TemporaryDirectory() as directory:
                result = subprocess.run([sys.executable, "-B", __file__, "--native", directory],
                    env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software", "QT_SCALE_FACTOR": scale},
                    capture_output=True, text=True, encoding="utf-8", timeout=90,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads((Path(directory)/"result.json").read_text())["cases"], len(THEME_PRESETS) * 2 * 3 * 2)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--native":
        target = Path(sys.argv[2]); target.mkdir(parents=True, exist_ok=True); native(target)
    else:
        unittest.main(verbosity=2)
