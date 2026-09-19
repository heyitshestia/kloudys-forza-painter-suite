from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import generation_paths as paths
import generator_backend as backend
import forza_generator_v2 as wrapper

spec = importlib.util.spec_from_file_location("generation_bridge_paths", ROOT / "KFPS.UI/bridges/generation_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class GenerationPathTests(unittest.TestCase):
    def test_names_are_bounded_extension_safe_and_distinct(self):
        names = ["a" * 240, "a" * 239 + "b", "CON", "nul", "Untitled.16.01.36",
                 "\ud55c\uae00", "\uc774\ubbf8\uc9c0", "image \U0001f600", "image \U0001f601"]
        stems = [paths.generation_artifact_stem(Path(name + ".png")) for name in names]
        self.assertEqual(len(stems), len(set(stems)))
        for stem in stems:
            self.assertLessEqual(len(stem), paths.MAX_STEM)
            self.assertRegex(stem, r"^[A-Za-z0-9_-]+$")
        self.assertEqual("source", paths.generation_artifact_stem(Path("source.png")))

    def test_same_basename_from_different_locations_has_separate_runs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first = paths.generation_run_stem(root / "one/sample.png", root)
            second = paths.generation_run_stem(root / "two/sample.png", root)
            self.assertNotEqual(first, second)
            self.assertEqual(first, paths.generation_run_stem(root / "one/sample.png", root))

    def test_command_metadata_and_worker_log_share_short_stem(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / (("long_processed_" * 17)[:240] + ".png")
            Image.new("RGBA", (8, 8), "red").save(source)
            output = root / "run"
            setting = {"path": root / "settings.ini", "values": {"stopAt": "4", "saveAt": "4"}}
            command = backend.build_generator_command(source, setting, output_dir=output)
            metadata_path = Path(command[command.index("--run-metadata") + 1])
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            stem = paths.generation_artifact_stem(source, output)
            self.assertEqual(source.name, metadata["source_name"])
            self.assertEqual(str(source), metadata["source_image"])
            self.assertEqual(stem, metadata["artifact_stem"])
            self.assertEqual(stem + ".v2.run_metadata.json", metadata_path.name)
            self.assertEqual(stem + ".v2.worker.log", bridge.worker_log_path(output, source).name)
            copied = wrapper.ensure_source_copy(source, output)
            self.assertEqual("source.png", copied.name)
            self.assertEqual(source.read_bytes(), copied.read_bytes())
            Image.new("RGBA", (8, 8), "blue").save(source)
            wrapper.ensure_source_copy(source, output)
            self.assertEqual(source.read_bytes(), copied.read_bytes())
            self.assertLess(paths.path_units(metadata_path), 260)

    def test_run_versions_and_old_results_remain_discoverable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / (("processed_name_" * 5) + ".png")
            with patch.object(backend, "GENERATED_ROOT", root / "generated"):
                first = backend.next_generator_output_dir(source)
                first.mkdir()
                second = backend.next_generator_output_dir(source)
                second.mkdir()
                legacy = backend.legacy_generator_output_dir(source)
                old = backend.GENERATED_ROOT / backend.generator_safe_stem(source)
                for folder in (legacy, old, old.with_name(old.name + "v2")):
                    folder.mkdir()
                self.assertEqual(first.name + "v2", second.name)
                found = backend.generator_output_dirs(source)
                self.assertEqual({first, second, legacy, old, old.with_name(old.name + "v2")}, set(found))
                final = first / "finals" / (paths.generation_artifact_stem(source, first) + ".4v2.json")
                final.parent.mkdir()
                final.write_text('{"shapes": []}', encoding="utf-8")
                preview = first / "previews" / (paths.generation_artifact_stem(source, first) + ".preview.4v2.png")
                preview.parent.mkdir()
                Image.new("RGBA", (8, 8)).save(preview)
                self.assertIn(final, backend.generated_jsons(source))
                self.assertIn(preview, backend.generated_preview_files(source))

    def test_deep_run_shortens_all_artifacts_including_atomic_temporaries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            padding = 166 - paths.path_units(root) - 1
            output = root / ("n" * padding)
            output.mkdir()
            source = root / ("x" * 240 + ".png")
            stem = paths.generation_artifact_stem(source, output)
            for relative in (f"reports/{stem}.v2.run_metadata.json", f"reports/{stem}.v2.worker.log",
                             f"previews/{stem}.prepared.png", f"checkpoints/{stem}.3000.json",
                             f"previews/.{stem}.preview.3000v2.png.4294967295.tmp"):
                target = output / relative
                self.assertLess(paths.path_units(target), 260)
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(b"test")
                self.assertEqual(b"test", target.read_bytes())

    def test_impossibly_deep_output_fails_before_making_directories(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / ("n" * 190)
            with self.assertRaisesRegex(ValueError, "too deeply nested"):
                backend.build_generator_command(Path(td) / "short.png", {"values": {}}, output_dir=output)
            self.assertFalse(output.exists())

    def test_new_run_budget_also_limits_full_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            generated = root / ("n" * (152 - paths.path_units(root) - 1))
            with patch.object(backend, "GENERATED_ROOT", generated):
                source = root / ("x" * 240 + ".png")
                output = backend.next_generator_output_dir(source)
                stem = paths.generation_artifact_stem(source, output)
                target = output / "previews" / f".{stem}.preview.3000v2.png.4294967295.tmp"
                self.assertLess(paths.path_units(target), 260)

    def test_new_write_budget_does_not_block_browsing_legacy_results(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            generated = root / ("n" * (200 - paths.path_units(root) - 1))
            old = generated / "source"
            old.mkdir(parents=True)
            with patch.object(backend, "GENERATED_ROOT", generated):
                self.assertEqual([old], backend.generator_output_dirs(root / "source.png"))

    def test_recovery_finds_old_or_new_checkpoints_without_renaming_them(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / ("old.source." + "x" * 70 + ".png")
            output = root / "run"
            checkpoints = output / "checkpoints"
            checkpoints.mkdir(parents=True)
            old = paths.legacy_artifact_stem(source)
            current = paths.generation_artifact_stem(source, output)
            (checkpoints / f"{old}.4.json").write_text("{}", encoding="utf-8")
            self.assertEqual(old, paths.recovery_checkpoint_stem(source, output))
            self.assertEqual("4", wrapper.checkpoint_tag_for_candidate(checkpoints / f"{old}.4.json", old))
            (checkpoints / f"{current}.4.json").write_text("{}", encoding="utf-8")
            self.assertEqual(current, paths.recovery_checkpoint_stem(source, output))
            self.assertTrue((checkpoints / f"{old}.4.json").is_file())


if __name__ == "__main__":
    unittest.main()
