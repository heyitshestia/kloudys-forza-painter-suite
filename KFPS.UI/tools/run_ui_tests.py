"""Run UI tests with one correctly initialized Qt Widgets application."""
import argparse
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pattern', default='test*.py')
    args = parser.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('QT_QUICK_BACKEND', 'software')
    os.environ.setdefault('KFPS_ACTIVITY_DISABLED', '1')
    sys.path[:0] = [str(ROOT), str(ROOT/'KFPS.UI/src'), str(ROOT/'KFPS.Editor/src')]
    # A QCoreApplication cannot later become QApplication during test discovery.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    suite = unittest.defaultTestLoader.discover(str(ROOT/'KFPS.UI/tests'), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    app.clipboard().clear()
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
