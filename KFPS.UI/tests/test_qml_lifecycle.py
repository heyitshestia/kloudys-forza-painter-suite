from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


class QmlLifecycleTests(unittest.TestCase):
    def test_scene_destroyed_before_context_and_application(self):
        source = Path(__file__).resolve().parents[1] / "src"
        script = r'''
import sys
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from shiboken6 import isValid
from kfps_ui.qml_lifecycle import exec_qml_application
app = QGuiApplication([])
context_object = QObject()
engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("service", context_object)
engine.loadData(b'import QtQuick\nItem { property var retainedService: service }')
scene = engine.rootObjects()[0]
events = []
engine.destroyed.connect(lambda: events.append("destroyed"))
def shutdown():
    assert isValid(engine) and isValid(context_object)
    events.append("shutdown")
QTimer.singleShot(0, lambda: app.exit(7))
assert exec_qml_application(app, engine, shutdown) == 7
assert events == ["shutdown", "destroyed"], events
assert not isValid(engine) and not isValid(scene)
assert isValid(context_object) and isValid(app)

engine = QQmlApplicationEngine()
def failed_shutdown():
    raise RuntimeError("injected close failure")
QTimer.singleShot(0, app.quit)
try:
    exec_qml_application(app, engine, failed_shutdown)
except RuntimeError as exc:
    assert str(exc) == "injected close failure"
else:
    raise AssertionError("Shutdown failure was hidden")
assert not isValid(engine)
'''
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, str(source)],
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
