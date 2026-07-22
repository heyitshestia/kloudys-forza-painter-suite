from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class UpdaterSafetyTests(unittest.TestCase):
    def test_git_checkout_cleanup_preserves_ignored_local_state(self):
        text = (ROOT / "03_update_from_github.bat").read_text(encoding="utf-8")
        lines = text.splitlines()
        clean_line = next(line.strip() for line in lines if line.strip().startswith("git clean "))

        self.assertIn("git clean -fd ", clean_line)
        self.assertNotIn("git clean -fdx", clean_line)
        for exclusion in (
            "runtime/",
            "imgs/",
            "webui-data/",
            "python/",
            "*.kfpskey",
            "node_modules/",
            ".wrangler/",
            ".dev.vars",
            ".dev.vars.*",
            ".venv/",
        ):
            with self.subTest(exclusion=exclusion):
                self.assertIn(exclusion, clean_line)

        self.assertNotIn("Get-FileHash", text)
        self.assertIn("[Security.Cryptography.SHA256]::Create()", text)


if __name__ == "__main__":
    unittest.main()
