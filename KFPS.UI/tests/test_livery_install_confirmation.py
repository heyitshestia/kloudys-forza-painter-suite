"""Real hosted/legacy confirmation and fixture resolver; install dispatch stubbed."""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class LiveryInstallConfirmationTests(unittest.TestCase):
    def check_mode(self, mode):
        retained = os.environ.get('KFPS_INSTALL_CONFIRMATION_EVIDENCE')
        context = nullcontext(retained) if retained else tempfile.TemporaryDirectory(prefix='kfps-install-dialog-')
        with context as directory:
            output = Path(directory).resolve()/mode
            command = [sys.executable, '-I', '-B', str(ROOT/'KFPS.UI/tools/test_livery_install_confirmation.py'),
                       '--output', str(output)]
            if mode == 'legacy':
                command.append('--legacy')
            result = subprocess.run(command, capture_output=True, text=True, timeout=90,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            report = json.loads((output/'results.json').read_text(encoding='utf-8'))
            self.assertTrue(report['passed'], report)
            self.assertEqual(16, len(report['checks']))
            self.assertEqual(4, len(report['calls']))
            self.assertEqual(2, len(report['images']))
            self.assertEqual(20, report['worker_calls'])
            self.assertEqual(16, report['destination_checks'])
            self.assertEqual(0, report['install_worker_processes'])
            self.assertTrue(report['offscreen'])
            self.assertEqual(mode == 'legacy', report['legacy'])

    def test_hosted_confirmation(self):
        self.check_mode('workspace')

    def test_legacy_confirmation(self):
        self.check_mode('legacy')


if __name__ == '__main__':
    unittest.main(verbosity=2)
