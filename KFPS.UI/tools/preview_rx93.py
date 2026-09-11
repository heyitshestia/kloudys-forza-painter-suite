"""Run the actual native shell with disposable state, never the installed app's data.

Pass normal app.py preview/capture arguments. A visible demo is used without capture
arguments. All persistent paths point into an automatically cleaned temporary root.
"""
from __future__ import annotations

import runpy
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
sys.path.insert(0, str(UI.parent))
from kfps_ui.app_paths import AppPaths


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kfps-rx93-preview-") as temporary:
        root = Path(temporary)
        paths = AppPaths(root, UI, UI / "qml", UI / "assets", root / "runtime", root / "python.exe")
        from kfps_ui.settings_service import SettingsService
        preview_settings = SettingsService(paths.settings_file)
        if os.environ.get("KFPS_RX93_PUBLIC"):
            preview_settings.theme = "RX-93 Psycho-Frame"
        (root / "VERSION").write_text((UI.parent / "VERSION").read_text(encoding="utf-8"), encoding="utf-8")
        if not os.environ.get("KFPS_RX93_AUDIT"):
            for name in ("supportUpscalerNoticeAcknowledged", "communityJoinNoticeAcknowledged", "backgroundRemoverNoticeAcknowledged", "dcinsideKoreanNotice202609Acknowledged"):
                preview_settings._data[name] = True
            preview_settings.save()
        args = sys.argv[1:]
        if "--theme-preview" not in args and not os.environ.get("KFPS_RX93_PUBLIC"):
            args = ["--theme-preview", "RX-93 Psycho-Frame", *args]
        if "--width" not in args:
            args += ["--width", "1440", "--height", "900"]
        sys.argv = [str(UI / "app.py"), "--demo", "--allow-source-download", "--skip-startup-index", "--skip-startup-thumbnails", *args]
        from contextlib import ExitStack
        with ExitStack() as stack:
            stack.enter_context(patch.object(AppPaths, "discover", return_value=paths))
            if "--screenshot-dir" in args or "--screenshot" in args:
                from audit_rx93_native import install_capture
                stack.enter_context(patch("kfps_ui.development_harness.install_development_harness", install_capture))
            if os.environ.get("KFPS_RX93_AUDIT"):
                from audit_rx93_native import install_audit
                stack.enter_context(patch("kfps_ui.development_harness.install_development_harness", install_audit))
            runpy.run_path(str(UI / "app.py"), run_name="__main__")


if __name__ == "__main__":
    main()
