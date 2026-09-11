import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'KFPS.UI/src'), str(ROOT)]
from kfps_ui import support_logs, support_report


class WorkerLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = time.time()

    def write(self, path, text, age=0):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        os.utime(target, (self.now - age, self.now - age))
        return target

    def collect(self):
        return support_logs.collect_worker_logs(self.root, since=self.now - 20,
                                                now=self.now, redact=support_report.redact)

    def test_all_known_workers_and_latest_only_without_reading_artwork(self):
        sources = {
            'runtime/fabric-editor/desktop.log': 'editor-desktop',
            'runtime/qml-transfer-logs/transfer-20260911-120000.log': 'transfer-worker',
            'runtime/qml-generation-logs/generation-20260911-120000.log': 'generator-bridge',
            'imgs/generated/PRIVATE_ART/reports/private_art.v2.worker.log': 'generator-worker',
            'runtime/upscaler/runs/20260911-120000-aabb/native.log': 'upscale-worker',
            'runtime/background-remover/runs/20260911-120000-aabb/worker.log': 'background-worker',
            'runtime/experiments/full-livery/sessions/20260911-120000-aabb/stdout.log': 'livery-worker',
            'runtime/experiments/full-livery/sessions/20260911-120000-aabb/stderr.log': 'livery-worker-stderr',
            'runtime/experiments/full-livery/sessions/viewer-20260911-120000-aabb/stdout.log': 'livery-viewer',
        }
        for path, source in sources.items():
            self.write(path, f'Error: {source} synthetic failure\n', age=40)
        self.write('runtime/qml-transfer-logs/transfer-20260910-120000.log', 'OLD_RUN', age=86400)
        self.write('runtime/fabric-editor/autosave.json', 'PRIVATE_ARTWORK')
        self.write('runtime/support-reports/unrelated.log', 'PRIVATE_REPORT')
        self.write('runtime/upscaler/runs/unrecognized/native.log', 'PRIVATE_UNKNOWN')
        logs, warnings = self.collect()
        self.assertFalse(warnings)
        self.assertEqual({entry['source'] for entry in logs}, set(sources.values()))
        for entry in logs:
            self.assertTrue(entry['previous_session'])
            self.assertEqual(entry['age_seconds'], 40)
            self.assertIn('synthetic failure', entry['text'])
        text = json.dumps(logs)
        for private in ('PRIVATE_', 'OLD_RUN', str(self.root), 'private_art'):
            self.assertNotIn(private, text)

    def test_tail_bounds_redaction_unicode_and_growing_open_file(self):
        path = self.write('runtime/fabric-editor/desktop.log', 'A' * (1024 * 1024))
        with path.open('a', encoding='utf-8') as writer:
            writer.write('\nError: GPU reset\nsession_token=PRIVATE_SESSION\nAuthorization: PRIVATE_AUTH\n')
            writer.write('C:\\Users\\PRIVATE_USER\\drawing.png\nuser@private.example\n')
            writer.write('data:image/png;base64,' + 'B' * 2000 + '\n')
            writer.write('{"shapes":[{"name":"PRIVATE_ART"}]}\n')
            writer.write('\uc624\ub958: \ucc98\ub9ac \uc2e4\ud328\n'); writer.flush()
            logs, warnings = self.collect()
        self.assertFalse(warnings)
        self.assertTrue(logs[0]['truncated'])
        self.assertIn('GPU reset', logs[0]['text'])
        self.assertIn('\ucc98\ub9ac \uc2e4\ud328', logs[0]['text'])
        for value in ('PRIVATE_', 'data:image', 'BBBB', 'private.example'):
            self.assertNotIn(value, json.dumps(logs))
        self.assertLessEqual(len(logs[0]['text']), 2400)

    def test_partial_blob_line_old_future_and_missing_logs(self):
        self.write('runtime/fabric-editor/desktop.log', 'PRIVATE' * 10000)
        self.write('runtime/qml-transfer-logs/transfer-20260911-120000.log', 'OLD', age=8 * 86400)
        self.write('runtime/qml-generation-logs/generation-20260911-120000.log', 'FUTURE', age=-60)
        logs, _ = self.collect()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['text'], '')

    def test_permission_failure_does_not_prevent_other_sources(self):
        target = self.write('runtime/fabric-editor/desktop.log', 'locked')
        self.write('runtime/qml-transfer-logs/transfer-20260911-120000.log', 'Error: transfer failure')
        original = Path.open
        def locked(path, *args, **kwargs):
            if path == target: raise PermissionError('PRIVATE filesystem message')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', locked):
            logs, warnings = self.collect()
        self.assertEqual(len(logs), 1)
        self.assertTrue(warnings)
        self.assertNotIn('PRIVATE', str(warnings))

    def test_linked_files_and_directories_are_not_followed(self):
        private = self.write('private.log', 'PRIVATE OUTSIDE SOURCE')
        target = self.root / 'runtime/fabric-editor/desktop.log'
        target.parent.mkdir(parents=True)
        os.link(private, target)
        self.assertFalse(self.collect()[0])
        target.unlink()
        try:
            target.symlink_to(private)
        except OSError:
            self.skipTest('Symlink creation unavailable on this Windows host')
        self.assertFalse(self.collect()[0])

    def test_discovery_is_bounded(self):
        for index in range(5):
            self.write(f'runtime/qml-transfer-logs/transfer-20260911-12000{index}.log', 'Error: bounded')
        with patch.object(support_logs, 'MAX_ENTRIES', 2):
            _, warnings = self.collect()
        self.assertTrue(any('limit reached' in text for text in warnings))

    def test_real_report_handoff_retains_sources_with_large_korean_logs(self):
        for source, relative, subdir, pattern in support_logs.SOURCES:
            if subdir: continue
            name = 'desktop.log' if source == 'editor-desktop' else ('transfer' if source == 'transfer-worker' else 'generation') + '-20260911-120000.log'
            self.write(f'{relative}/{name}', ('\uc624\ub958: \uc791\uc5c5 \uc2e4\ud328\n' * 500))
        context = {'page': 'editor', 'log': '\uc624\ub958\n' * 4000, 'services': {
            key: {'liveLog': ('\uc624\ub958\uac00 \ubc1c\uc0dd\ud588\uc2b5\ub2c8\ub2e4 ' * 20 + '\n') * 100}
            for key in ('generator', 'transfer')}}
        report = support_report.build_support_report(self.root, context, since=self.now - 30, collect=lambda: {})
        self.assertLessEqual(len(json.dumps(report).encode()), support_report.MAX_REPORT_BYTES)
        self.assertIn('editor-desktop', [entry['source'] for entry in report['technical']['logs']])
        self.assertTrue(all(entry['text'] for entry in report['technical']['logs']))
        path, handoff = support_report.save_handoff(self.root, report)
        self.assertEqual(json.loads(path.read_text()), report)
        self.assertNotIn('fetch(', handoff.read_text())


if __name__ == '__main__': unittest.main()
