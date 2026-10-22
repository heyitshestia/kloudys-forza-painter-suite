"""Run the browser-independent mask bitmap lifecycle and memory contracts."""
from pathlib import Path
import shutil
import subprocess
import unittest


class StudioMaskPreviewTests(unittest.TestCase):
    def test_browser_module_lifecycle_and_memory_contracts(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is required for the browser module contract")
        result = subprocess.run(
            [node, "--test", str(Path(__file__).with_name("studio_mask_preview.mjs"))],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# pass 9", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
