"""Open the local Community catalog inside the normal KFPS application."""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import runpy
import sys

UI = Path(__file__).resolve().parents[1]
ROOT = UI.parent
sys.path[:0] = [str(UI / "src"), str(UI / "tools"), str(ROOT)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--native-test", action="store_true")
    parser.add_argument("--theme-test", action="store_true")
    parser.add_argument("--minimized", action="store_true")
    parser.add_argument("--state", default="review")
    args = parser.parse_args()
    name = args.state
    if len(name) > 64 or not name.replace("-", "").replace("_", "").isalnum():
        parser.error("Invalid local Community state name.")
    state = ROOT / "runtime" / "community-preview" / name
    state.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=state / "preview.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    from PySide6.QtCore import qInstallMessageHandler
    from test_community_preview_native import QML_ERRORS

    def qt_message(kind, context, message):
        logging.info("Qt: %s", message)
        if any(part in message for part in ("ReferenceError", "TypeError", "Cannot assign",
                "Unable to assign", "Binding loop", "is not a type", "failed to load")):
            QML_ERRORS.append(message)
        print(message, flush=True)
    qInstallMessageHandler(qt_message)
    sys.argv = [str(UI / "app.py"), "--community-preview", "--community-preview-state",
                name, "--page", "community"]
    if args.test or args.native_test or args.theme_test:
        import faulthandler
        faulthandler.enable()
        faulthandler.dump_traceback_later(90, repeat=True)
        if not args.theme_test:
            # Nested QTest waits can deadlock Qt's threaded loop during a theme swap.
            # The separate asynchronous theme test exercises the normal render loop.
            os.environ.setdefault("QSG_RENDER_LOOP", "basic")
        sys.argv += ["--community-preview-test", "themes" if args.theme_test else "workflows", "--community-preview-background",
                     "--width", "1280", "--height", "800", "--theme-preview", "Night Blossom"]
        if args.test and not args.native_test and not args.theme_test:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"
    elif args.minimized:
        sys.argv += ["--community-preview-minimized"]
    runpy.run_path(str(UI / "app.py"), run_name="__main__")


if __name__ == "__main__":
    main()
