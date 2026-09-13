import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UI / "src"), str(UI.parent / "KFPS.Editor/src")]
from kfps_ui.support_window_protocol import MAX_PACKAGE_BYTES, read_source, report_id, window_name


class SupportWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.id = str(uuid.uuid4())
        self.folder = self.root / "runtime/support-reports" / self.id
        self.folder.mkdir(parents=True)
        self.summary = self.folder / "report.json"
        self.summary.write_text(json.dumps({"schema":"kfps-support-report/1","id":self.id}),encoding="utf-8")

    def test_only_uuid_scoped_saved_reports_are_read(self):
        data, metadata = read_source(self.root,self.id)
        self.assertEqual(json.loads(data)["id"],self.id)
        self.assertEqual(metadata["mode"],"json")
        for bad in ("../report.json",self.id.upper(),"",str(uuid.uuid4()) + "/file"):
            with self.assertRaises(ValueError):report_id(bad)
        self.summary.write_text('{"schema":"artwork","id":"' + self.id + '"}')
        with self.assertRaises(ValueError):read_source(self.root,self.id)

    def test_full_package_wins_over_summary_and_size_is_bounded(self):
        package = self.folder / "report.kfps-report.json.gz"
        package.write_bytes(b"x" * MAX_PACKAGE_BYTES)
        data, metadata = read_source(self.root,self.id)
        self.assertEqual(len(data),MAX_PACKAGE_BYTES)
        self.assertEqual(metadata["mode"],"package")
        with package.open("ab") as handle:handle.write(b"x")
        with self.assertRaises(ValueError):read_source(self.root,self.id)

    def test_hardlinked_reports_are_refused(self):
        source = self.root / "private.json"
        source.write_text("private")
        self.summary.unlink()
        os.link(source,self.summary)
        with self.assertRaises(ValueError):read_source(self.root,self.id)

    def test_instance_names_are_bound_to_installation(self):
        self.assertEqual(window_name(self.root),window_name(self.root / "."))
        self.assertNotEqual(window_name(self.root),window_name(self.root / "other"))

    def test_regular_report_button_uses_native_review_without_external_browser(self):
        from types import SimpleNamespace
        from kfps_ui import support_browser
        handoff = self.folder / "open-report.html"
        handoff.write_text("saved fallback")
        paths = SimpleNamespace(app_root=self.root)
        with patch('kfps_ui.support_window_launch.launch_review',return_value='review') as launch, patch.object(support_browser,'default_browser_executable') as browser:
            self.assertEqual(support_browser.open_support_handoff(str(handoff),paths=paths),'review')
            launch.assert_called_once_with(paths,self.id)
            browser.assert_not_called()

    def test_window_launch_uses_managed_policy_without_report_bytes_in_arguments(self):
        from types import SimpleNamespace
        from kfps_ui.support_window_launch import launch_review
        entry=self.root / 'KFPS.UI/report.py'
        entry.parent.mkdir();entry.write_text('entry')
        paths=SimpleNamespace(app_root=self.root,python_executable=sys.executable)
        with patch('kfps_editor.baseline.launch_command',return_value=(['managed-python','-I',str(entry),'--report-id',self.id],{})) as command, patch('kfps_ui.support_window_launch.subprocess.Popen') as process:
            self.assertEqual(launch_review(paths,self.id),'review')
            self.assertEqual(command.call_args.args[2],['--report-id',self.id])
            self.assertNotIn('report.json',' '.join(process.call_args.args[0]))


if __name__ == '__main__':unittest.main()
