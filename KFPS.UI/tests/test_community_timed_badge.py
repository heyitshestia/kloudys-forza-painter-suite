"""Render the real thumbnail badge across themes, including icon-free themes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

UI = Path(__file__).resolve().parents[1]


def native(output):
    sys.path.insert(0, str(UI / 'src'))
    from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
    from PySide6.QtGui import QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
    from PySide6.QtQuick import QQuickView
    from PySide6.QtTest import QTest
    from kfps_ui.theme_catalog import THEME_PRESETS
    app = QGuiApplication([])
    # Qt's offscreen Windows platform does not discover installed system fonts.
    fonts = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'Fonts'
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'consola.ttf', 'tahoma.ttf', 'malgun.ttf'):
        path = fonts / name
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    view = QQuickView()
    view.setFlags(Qt.Tool | Qt.WindowDoesNotAcceptFocus)
    engine = view.engine()
    engine.addImportPath(str(UI / 'qml'))
    engine.rootContext().setContextProperty('assetRoot', QUrl.fromLocalFile(str(UI / 'assets')).toString())
    engine.rootContext().setContextProperty('screenshotMode', True)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import Kfps.Theme 1.0
import "../qml/community-preview"
Rectangle {
    id: root
    width: 340; height: 310; color: "#444444"
    property var row: ({id:"test", title:"Timed artwork", creator:"TestCreator", state:"upcoming", ends:"future", window:"20 Sep 2026, 13:00 - 16:00", game:"FH6", shapes:3000, score:0})
    property string language: "en"
    property int clicks: 0
    function ui(en, ko) { return language === "ko" ? ko : en }
    PreviewArtwork { x:10; y:10; width:320; height:290; artwork:root.row; ui:root.ui; onChosen:root.clicks++ }
}
''', QUrl.fromLocalFile(str(UI / 'tests/timed-badge-harness.qml')))
    root = component.create()
    assert root is not None, [error.toString() for error in component.errors()]
    view.setContent(component.url(), component, root)
    view.show(); view.lower(); QTest.qWait(80)
    def expression(code):
        value = QQmlExpression(QQmlEngine.contextForObject(root), root, code)
        value.evaluate()
        assert not value.hasError(), value.error().toString()
    cases = []
    for theme in THEME_PRESETS:
        expression('Theme.supporterUnlocked=true; Theme.themeName=' + json.dumps(theme.name))
        for language in ('en', 'ko'):
            root.setProperty('language', language)
            for status, expected in (('upcoming', '#b42335'), ('available', '#087443'), ('expired', '#b42335')):
                QTest.mouseMove(view, QPoint(0, 0))
                expression('row=Object.assign({},row,{state:' + json.dumps(status) + ',ends:"future"})')
                QTest.qWait(40)
                badge = root.findChild(QObject, 'TimedBadge:test')
                assert badge is not None and badge.isVisible()
                assert badge.property('color').name() == expected
                assert bool(badge.property('available')) == (status == 'available')
                label = badge.property('label')
                assert ('기간 한정' if language == 'ko' else 'Timed release') in label
                image = view.grabWindow()
                assert not image.isNull()
                corner = badge.mapToScene(QPointF(0, 0))
                scale = image.devicePixelRatio()
                region = image.copy(round((corner.x()+5)*scale), round((corner.y()+4)*scale), round(22*scale), round(20*scale))
                whites = sum(region.pixelColor(x,y).red() > 235 and region.pixelColor(x,y).green() > 235 and region.pixelColor(x,y).blue() > 235
                    for x in range(region.width()) for y in range(region.height()))
                assert whites >= 12, (theme.name, status, 'Clock icon missing', whites)
                point = badge.mapToScene(QPointF(badge.width()/2, badge.height()/2)).toPoint()
                before = root.property('clicks')
                QTest.mouseClick(view, Qt.LeftButton, Qt.NoModifier, point)
                assert root.property('clicks') == before+1, 'Badge swallowed artwork click'
                if language == 'en': image.save(str(output / (theme.qml_component + '-' + status + '.png')))
                cases.append({'theme': theme.name, 'language': language, 'state': status, 'clock_pixels': whites})
            expression('row=Object.assign({},row,{ends:null})'); QTest.qWait(10)
            assert not root.findChild(QObject, 'TimedBadge:test').isVisible()
    view.close()
    (output / 'timed-badge.json').write_text(json.dumps({'passed': True, 'cases': cases}, indent=2), encoding='utf-8')
    print('PASS timed badge: 54 rendered cases, 18 non-timed cases, click passthrough')


class TimedBadgeTests(unittest.TestCase):
    def test_clock_is_visible_colored_and_does_not_block_thumbnail_clicks(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, __file__, '--native', directory],
                env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'PYTHONUTF8': '1'},
                capture_output=True, text=True, encoding='utf-8', timeout=90,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((Path(directory) / 'timed-badge.json').read_text())
            self.assertTrue(report['passed'])
            self.assertEqual(len(report['cases']), 54)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--native':
        target = Path(sys.argv[2]); target.mkdir(parents=True, exist_ok=True)
        native(target)
    else:
        unittest.main()
