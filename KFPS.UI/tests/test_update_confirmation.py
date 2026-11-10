"""The Update dialog must stay usable after embedding KFPS in the workspace."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class UpdateConfirmationTests(unittest.TestCase):
    def test_real_update_page_confirmation_and_handoff(self):
        for mode in ('workspace', 'legacy'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix='kfps-update-dialog-') as temporary:
                output = Path(temporary)/'evidence'
                command = [sys.executable, '-I', '-B', str(ROOT/'KFPS.UI/tools/test_update_confirmation.py'),
                           '--output', str(output)]
                if mode == 'legacy':
                    command.append('--legacy')
                result = subprocess.run(command, capture_output=True, text=True, timeout=75)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                report = json.loads((output/'results.json').read_text(encoding='utf-8'))
                self.assertTrue(report['passed'], report)
                self.assertEqual(12, len(report['checks']))
                self.assertEqual(4, len(report['calls']))


if __name__ == '__main__':
    unittest.main()
