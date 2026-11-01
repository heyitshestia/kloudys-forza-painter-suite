"""Test-run relocation is explicit and cannot escape its evidence directory."""
import os
import ast
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from _test_evidence import evidence_root, evidence_directory


class EvidencePathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="evidence-path-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.enterContext(patch.dict(os.environ, {"KFPS_TEST_EVIDENCE_ROOT": str(self.root)}))

    def test_explicit_evidence_root_does_not_depend_on_checkout_location(self):
        self.assertEqual(evidence_root(), self.root)
        self.assertEqual(evidence_directory("studio-host"), self.root / "studio-host")
        self.assertFalse((self.root / "studio-host").exists())

    def test_named_override_remains_inside_declared_evidence(self):
        target = self.root / "dirty-transition-20261029/run/studio-host"
        with patch.dict(os.environ, KFPS_STUDIO_HOST_TEST_RUN=str(target)):
            self.assertEqual(evidence_directory("fallback", "KFPS_STUDIO_HOST_TEST_RUN"), target)

    def test_override_cannot_escape_or_use_root_itself(self):
        for path in (self.root, self.root.parent / "outside", self.root / "../outside"):
            with self.subTest(path=path), patch.dict(os.environ, KFPS_STUDIO_HOST_TEST_RUN=str(path)):
                with self.assertRaises(ValueError):
                    evidence_directory("fallback", "KFPS_STUDIO_HOST_TEST_RUN")

    def test_relative_root_or_override_is_rejected(self):
        with patch.dict(os.environ, KFPS_TEST_EVIDENCE_ROOT="relative/runs"):
            with self.assertRaises(ValueError):
                evidence_root()
        with patch.dict(os.environ, KFPS_STUDIO_HOST_TEST_RUN="relative/run"):
            with self.assertRaises(ValueError):
                evidence_directory("fallback", "KFPS_STUDIO_HOST_TEST_RUN")

    def test_drive_root_is_not_an_evidence_scope(self):
        with patch.dict(os.environ, KFPS_TEST_EVIDENCE_ROOT=self.root.anchor):
            with self.assertRaises(ValueError):
                evidence_root()

    def test_default_is_temporary_not_a_sibling_of_the_checkout(self):
        with patch.dict(os.environ, clear=True), patch.object(tempfile, "gettempdir", return_value=str(self.root)):
            self.assertEqual(evidence_root(), self.root / "kfps-test-evidence")

    def test_default_label_cannot_escape(self):
        with self.assertRaises(ValueError):
            evidence_directory("../escape")

    def test_redirected_run_ancestor_is_rejected(self):
        ancestor = self.root / "redirect"
        original = Path.is_symlink
        with patch.object(Path, "is_symlink", lambda path: path == ancestor or original(path)):
            with self.assertRaises(ValueError):
                evidence_directory("redirect/studio-host")

    def test_native_host_bootstrap_accepts_relocated_checkout_before_qt_import(self):
        source = Path(__file__).with_name('test_studio_native_host.py')
        tree = ast.parse(source.read_text(encoding='utf-8'))
        prefix = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module == 'PySide6.QtCore':
                break
            prefix.append(node)
        target = self.root / 'relocated checkout/KFPS.UI/tests/test_studio_native_host.py'
        run = self.root / 'native-host'
        namespace = {'__file__': str(target), '__name__': '_relocation_prefix'}
        created = []
        with patch.dict(os.environ, KFPS_STUDIO_HOST_TEST_RUN=str(run)), patch.object(sys, 'path', list(sys.path)), \
                patch.object(Path, 'mkdir', lambda path, **kwargs: created.append(path)):
            exec(compile(ast.Module(body=prefix, type_ignores=[]), str(source), 'exec'), namespace)
        self.assertEqual(namespace['ROOT'], target.parents[2])
        self.assertEqual(namespace['RUN'], run)
        self.assertTrue(created)
        self.assertTrue(all(path.is_relative_to(self.root) for path in created))
