from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import forza_generator_v2
import generator_backend


class GenerationReliabilityTests(unittest.TestCase):
    def test_forwarded_generator_output_is_always_utf8(self):
        buffer = io.BytesIO()
        with patch.object(forza_generator_v2.sys, "stdout", SimpleNamespace(buffer=buffer)):
            forza_generator_v2.write_forwarded_output("Search timing: 25 \u00b5s")
        self.assertEqual("Search timing: 25 \u00b5s\n", buffer.getvalue().decode("utf-8"))

    def test_final_json_and_preview_are_atomic_nonempty_files(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            json_path = root / "finals" / "sample.100v2.json"
            preview_path = root / "previews" / "sample.preview.100v2.png"

            forza_generator_v2.save_json(json_path, {"shapes": [{"type": 16}]})
            forza_generator_v2.save_png(preview_path, Image.new("RGBA", (16, 16), (10, 20, 30, 255)))
            forza_generator_v2.require_saved_file(json_path, "JSON")
            forza_generator_v2.require_saved_file(preview_path, "preview")

            self.assertEqual(16, json.loads(json_path.read_text(encoding="utf-8"))["shapes"][0]["type"])
            with Image.open(preview_path) as preview:
                self.assertEqual((16, 16), preview.size)
            self.assertEqual([], list(root.rglob("*.tmp")))

    def test_app_generation_command_uses_100_step_live_previews(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            image_path = root / "source.png"
            settings_path = root / "settings.ini"
            output_dir = root / "output"
            Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(image_path)
            settings_path.write_text("stopAt = 200\nsaveAt = 100,200\n", encoding="utf-8")
            setting = {"path": settings_path, "values": {"stopAt": "200", "saveAt": "100,200"}}

            command = generator_backend.build_generator_command(image_path, setting, output_dir=output_dir)
            option_index = command.index("--live-preview-every")
            self.assertEqual("100", command[option_index + 1])

            metadata = json.loads((output_dir / "reports" / "source.v2.run_metadata.json").read_text(encoding="utf-8"))
            self.assertEqual("100", metadata["generator_command_options"]["live_preview_every"])

if __name__ == "__main__":
    unittest.main()
