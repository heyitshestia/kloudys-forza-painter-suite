"""Connection paths are validated without creating storage or changing the root."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "KFPS.UI/src"))
from kfps_ui.workspace_paths import workspace_connection_dir


class WorkspacePathTests(unittest.TestCase):
    def test_absent_storage_is_returned_without_being_created(self):
        with tempfile.TemporaryDirectory(prefix="workspace-path-") as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(workspace_connection_dir(root), root / "runtime/workspace")
            self.assertFalse((root / "runtime").exists())

    def test_existing_regular_storage_is_accepted(self):
        with tempfile.TemporaryDirectory(prefix="workspace-path-") as temporary:
            root = Path(temporary).resolve()
            directory = root / "runtime/workspace"
            directory.mkdir(parents=True)
            self.assertEqual(workspace_connection_dir(root), directory)

    def test_each_storage_component_rejects_symlinks_and_junctions(self):
        with tempfile.TemporaryDirectory(prefix="workspace-path-") as temporary:
            root = Path(temporary).resolve()
            for component in (root / "runtime", root / "runtime/workspace"):
                for predicate in ("is_symlink", "is_junction"):
                    with self.subTest(component=component.name, predicate=predicate), \
                            patch.object(Path, predicate, autospec=True,
                                         side_effect=lambda path: path == component):
                        with self.assertRaisesRegex(RuntimeError, "redirected"):
                            workspace_connection_dir(root)

    def test_resolved_destination_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="workspace-path-") as temporary:
            root = Path(temporary).resolve()
            directory = root / "runtime/workspace"
            with patch.object(Path, "resolve", autospec=True,
                              side_effect=lambda path: root / "other" if path == directory else path):
                with self.assertRaisesRegex(RuntimeError, "redirected"):
                    workspace_connection_dir(root)


if __name__ == "__main__":
    unittest.main()
