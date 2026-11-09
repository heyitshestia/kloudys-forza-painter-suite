"""Synthetic cache lifecycle and real child-process boundary tests; no game reads."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))
from kfps_livery_lab import catalogue_cache as subject


def database(version=17, statements=()):
    with closing(sqlite3.connect(":memory:")) as db:
        db.executescript("""
            CREATE TABLE VersionInfo (database_version INTEGER);
            CREATE TABLE Data_Car (Id INTEGER, MediaName TEXT);
            INSERT INTO Data_Car VALUES (7, 'TEST_Model_01');
            CREATE TABLE Data_CarBody (Id INTEGER);
            INSERT INTO Data_CarBody VALUES (700);
            CREATE TABLE List_PartManufacturer (Id INTEGER, PartManufacturer TEXT);
            CREATE TABLE UpgradeTypes (Id INTEGER, PartName TEXT, IsException INTEGER, Name TEXT);
            CREATE TABLE Upgrades (Id INTEGER, TypeId TEXT, Level INTEGER, IsException INTEGER, Name TEXT);
            CREATE TABLE Data_UpgradePart (Id INTEGER, TableName TEXT, CategoryName TEXT,
                PartName TEXT, HasRequiresGraphics INTEGER);
        """)
        db.execute("INSERT INTO VersionInfo VALUES (?)", (version,))
        for table in subject.PART_TABLES:
            db.execute(f'CREATE TABLE "{table}" (Id INTEGER, Ordinal INTEGER, CarBodyID INTEGER, '
                       'Level INTEGER, IsStock INTEGER, ManufacturerID INTEGER, RequiresGraphics INTEGER)')
            db.execute(f'INSERT INTO "{table}" VALUES (701,7,700,1,0,0,1)')
        for statement in statements:
            db.execute(statement)
        db.commit()
        return db.serialize()


class CatalogueCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kfps-catalogue-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.game = self.root / "game"
        self.source = self.game / "media/stripped/gamedbRC.slt"
        self.source.parent.mkdir(parents=True)
        self.cache = self.root / "cache"
        self.config = self.root / "missing-provider.json"
        self.valid = database()
        self.source.write_bytes(self.valid)

    def load(self, **kwargs):
        return subject.load_installed_catalogue(self.game, cache_root=self.cache,
            reader_config=self.config, **kwargs)

    def provider(self, body=None):
        self.source.write_bytes(b"synthetic encrypted input")
        self.script = self.root / "reader.py"
        self.count = self.root / "calls.txt"
        (self.root / "payload.sqlite").write_bytes(self.valid)
        self.script.write_text(
            "import pathlib,sys,time,os\n"
            "base=pathlib.Path(__file__).parent\n"
            "assert sys.argv[1:]==['--stdin']\n"
            "assert sys.flags.isolated and sys.flags.dont_write_bytecode\n"
            "assert sys.stdin.buffer.read()==b'synthetic encrypted input'\n"
            "with (base/'calls.txt').open('a') as f: f.write('call\\n')\n"
            + (body or "sys.stdout.buffer.write((base/'payload.sqlite').read_bytes())\n"),
            encoding="utf-8")
        self.config = {"format": "kfps-catalogue-reader-v1", "python": sys.executable,
                       "script": str(self.script)}

    def slots(self):
        return list(self.cache.glob("*/generation-*.bin"))

    def test_plain_refresh_warm_restart_media_root_and_no_provider(self):
        with patch.object(subject, "_run_provider", side_effect=AssertionError("provider invoked")):
            first = self.load()
            self.assertEqual("refreshed", first["status"])
            self.assertEqual(self.valid, first["database"])
            self.assertTrue(first["provenance"]["current"])
            self.assertEqual(17, first["provenance"]["database_version"])
            self.assertEqual(hashlib.sha256(self.valid).hexdigest(), first["provenance"]["source_sha256"])
            second = subject.load_installed_catalogue(self.game / "media", cache_root=self.cache)
            self.assertEqual("cached", second["status"])
            self.assertEqual(first["provenance"], second["provenance"])
        self.assertEqual(1, len(self.slots()))

    def test_two_generations_and_failed_refresh_retains_previous(self):
        for version in range(17, 21):
            self.source.write_bytes(database(version))
            self.assertEqual("refreshed", self.load()["status"])
            self.assertLessEqual(len(self.slots()), 2)
        before = {p: p.read_bytes() for p in self.slots()}
        self.source.write_bytes(b"invalid encrypted file")
        result = self.load()
        self.assertEqual("stale", result["status"])
        self.assertFalse(result["provenance"]["current"])
        self.assertEqual(20, result["provenance"]["database_version"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.slots()})
        self.source.write_bytes(database(21))
        self.assertEqual("refreshed", self.load()["status"])

    def test_provider_real_boundary_warm_reuse_and_script_change(self):
        self.provider()
        self.assertEqual("refreshed", self.load()["status"])
        self.assertEqual("cached", self.load()["status"])
        self.assertEqual("call\n", self.count.read_text())
        with self.script.open("a") as stream:
            stream.write("# provider revision\n")
        self.assertEqual("refreshed", self.load()["status"])
        self.assertEqual("call\ncall\n", self.count.read_text())
        self.assertFalse((self.root / "__pycache__").exists())

    def test_missing_source_is_stale_or_unavailable_and_no_paths_leak(self):
        self.assertEqual("refreshed", self.load()["status"])
        self.source.unlink()
        result = self.load()
        self.assertEqual("stale", result["status"])
        result.pop("database")
        self.assertNotIn(str(self.root), json.dumps(result))
        for path in self.slots():
            raw = path.read_bytes()
            size = int.from_bytes(raw[:4], "little")
            self.assertNotIn(str(self.root), raw[4:4 + size].decode())
        self.cache = self.root / "empty-cache"
        self.assertEqual("unavailable", self.load()["status"])

    def test_same_stamp_changed_bytes_are_not_current(self):
        self.load()
        stamp = self.source.stat()
        changed = database(18)
        self.assertEqual(len(self.valid), len(changed))
        self.source.write_bytes(changed)
        os.utime(self.source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        result = self.load()
        self.assertEqual("refreshed", result["status"])
        self.assertEqual(18, result["provenance"]["database_version"])

    def test_generation_receipt_cannot_cross_installation(self):
        self.load()
        other = self.root / "other-game"
        result = subject.load_installed_catalogue(other, cache_root=self.cache)
        self.assertEqual("unavailable", result["status"])
        identities = list(self.cache.iterdir())
        populated = next(p for p in identities if list(p.glob("generation-*.bin")))
        empty = next(p for p in identities if p != populated)
        (empty / "generation-0.bin").write_bytes((populated / "generation-0.bin").read_bytes())
        result = subject.load_installed_catalogue(other, cache_root=self.cache)
        self.assertEqual("unavailable", result["status"])
        self.assertIsNone(result["database"])
        self.assertIn("cache-invalid", result["warnings"])

    def test_corrupted_newest_generation_falls_back_and_is_rebuilt(self):
        self.load()
        self.source.write_bytes(database(18))
        self.load()
        next(p for p in self.slots() if p.name == "generation-1.bin").write_bytes(b"damaged")
        self.source.unlink()
        result = self.load()
        self.assertEqual("stale", result["status"])
        self.assertEqual(17, result["provenance"]["database_version"])
        self.source.write_bytes(database(18))
        result = self.load()
        self.assertEqual("refreshed", result["status"])
        self.assertEqual(18, result["provenance"]["database_version"])

    def test_cache_hash_and_schema_are_rechecked_on_warm_calls(self):
        self.load()
        slot = self.slots()[0]
        original = slot.read_bytes()
        slot.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        with patch.object(subject, "_snapshot", side_effect=OSError("private path")):
            result = self.load()
        self.assertEqual("unavailable", result["status"])
        slot.write_bytes(original)
        with patch.object(subject, "_validate", side_effect=subject._Invalid("database-invalid")):
            self.assertEqual("unavailable", self.load()["status"])

    def test_required_schema_views_virtuals_duplicates_and_model_aliases(self):
        cases = [
            ["DROP TABLE VersionInfo"],
            ["INSERT INTO VersionInfo VALUES (18)"],
            ["UPDATE VersionInfo SET database_version='bad'"],
            ["DROP TABLE Data_CarBody", "CREATE VIEW Data_CarBody AS SELECT 700 AS Id"],
            ["CREATE VIRTUAL TABLE extra USING fts5(value)"],
            ["INSERT INTO Data_Car SELECT * FROM Data_Car"],
            ["INSERT INTO Data_Car VALUES (8, 'test_MODEL_01')"],
            ["UPDATE Data_Car SET MediaName='../TEST_Model_01'"],
            ["UPDATE Data_Car SET Id=NULL"],
            ["INSERT INTO List_UpgradeRearWing SELECT * FROM List_UpgradeRearWing"],
            ["ALTER TABLE UpgradeTypes RENAME COLUMN Name TO WrongName"],
            ["ALTER TABLE Data_Car ADD COLUMN extra TEXT GENERATED ALWAYS AS (MediaName) VIRTUAL"],
        ]
        for statements in cases:
            with self.subTest(statements=statements):
                with self.assertRaises(subject._Invalid):
                    subject._validate(database(statements=statements))
        for table in subject.REQUIRED_COLUMNS:
            if table == "VersionInfo":
                continue
            with self.subTest(table=table):
                bad = database(statements=[f'INSERT INTO "{table}" (Id) VALUES (123), (123)'])
                with self.assertRaisesRegex(subject._Invalid, "database-identity-ambiguous"):
                    subject._validate(bad)

    def test_sqlite_header_integrity_and_query_budget(self):
        damaged = bytearray(self.valid)
        damaged[100] = 0
        for bad in (b"SQLite format 3\0", self.valid[:-1], bytes(damaged)):
            with self.subTest(length=len(bad)), self.assertRaises(subject._Invalid):
                subject._validate(bad)
        many = database(statements=[
            "WITH RECURSIVE x(n) AS (VALUES(1) UNION ALL SELECT n+1 FROM x WHERE n<1000) "
            "INSERT INTO Data_CarBody SELECT n+1000 FROM x"])
        with patch.object(subject, "MAX_PROGRESS_TICKS", 0):
            with self.assertRaisesRegex(subject._Invalid, "database-validation-limit"):
                subject._validate(many)

    def test_source_and_database_size_bounds(self):
        with patch.object(subject, "MAX_SOURCE_BYTES", 32):
            self.assertIn("source-size-invalid", self.load()["warnings"])
        with patch.object(subject, "MAX_DATABASE_BYTES", len(self.valid) - 1):
            self.assertIn("database-invalid", self.load()["warnings"])
        self.assertEqual([], self.slots())

    def test_source_replaced_during_snapshot_is_rejected(self):
        original = subject._source_stat
        calls = 0

        def replacing(path, maximum=subject.MAX_SOURCE_BYTES):
            nonlocal calls
            calls += 1
            if calls == 2:
                temp = self.source.with_suffix(".replacement")
                temp.write_bytes(self.valid)
                os.replace(temp, self.source)
            return original(path, maximum)

        with patch.object(subject, "_source_stat", side_effect=replacing):
            result = self.load()
        self.assertEqual("unavailable", result["status"])
        self.assertIn("source-changed", result["warnings"])
        self.assertEqual([], self.slots())

    def test_source_changes_during_provider_never_publish(self):
        self.load()
        before = {p: p.read_bytes() for p in self.slots()}
        self.provider()

        def change(*args):
            self.source.write_bytes(b"changed input")
            return self.valid

        with patch.object(subject, "_run_provider", side_effect=change):
            result = self.load()
        self.assertEqual("stale", result["status"])
        self.assertFalse(result["provenance"]["current"])
        self.assertIn("source-changed", result["warnings"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.slots()})

    def test_source_change_at_atomic_commit_preserves_previous(self):
        self.load()
        before = {p: p.read_bytes() for p in self.slots()}
        self.source.write_bytes(database(18))
        original = subject.atomic_stream
        from contextlib import contextmanager

        @contextmanager
        def changing(path):
            with original(path) as stream:
                self.source.write_bytes(b"changed at staging")
                yield stream

        with patch.object(subject, "atomic_stream", changing):
            result = self.load()
        self.assertEqual("stale", result["status"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.slots()})
        self.assertFalse(list(self.cache.rglob("*.tmp")))

    def test_invalid_provider_configs_and_strict_pin_never_execute(self):
        self.provider()
        valid = dict(self.config)
        variants = [{}, {**valid, "format": "wrong"}, {**valid, "python": "python"},
                    {**valid, "script": "reader.py"}, {**valid, "script_sha256": None},
                    {**valid, "script_sha256": ""}, {**valid, "script_sha256": "0" * 64}]
        with patch.object(subject, "_run_provider", side_effect=AssertionError("executed")):
            for config in variants:
                self.config = config
                with self.subTest(config=config):
                    self.assertEqual("unavailable", self.load()["status"])
        self.config = valid
        self.config["script_sha256"] = hashlib.sha256(self.script.read_bytes()).hexdigest().upper()
        self.assertEqual("refreshed", self.load()["status"])
        with self.script.open("a") as stream:
            stream.write("# tampered\n")
        self.assertIn("reader-hash-mismatch", self.load()["warnings"])

    def test_json_provider_and_defaults(self):
        self.provider()
        path = self.root / "runtime/garage/catalogue-reader.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(self.config), encoding="utf-8")
        with patch.object(subject, "APP_ROOT", self.root):
            with patch.object(subject, "_run_provider", side_effect=AssertionError("legacy override executed")):
                self.assertEqual("unavailable", subject.load_installed_catalogue(self.game)["status"])
            result = subject.load_installed_catalogue(self.game, reader_config=path)
            self.assertEqual("refreshed", result["status"])
            self.assertTrue((self.root / "runtime/garage/catalogue").is_dir())

    def test_default_provider_is_app_owned_and_manifest_pinned(self):
        config = subject._reader_configuration(None)
        self.assertEqual(str(ROOT / "tools/garage-reader/catalogue.py"), config["script"])
        self.assertEqual(str(ROOT / "tools/garage-reader/manifest.json"), config["dependencies"][0]["path"])
        self.assertEqual(hashlib.sha256(Path(config["script"]).read_bytes()).hexdigest(), config["script_sha256"])

    def test_provider_changes_during_acquisition_are_not_published(self):
        self.provider()
        original = subject._run_provider

        def changing(*args):
            output = original(*args)
            with self.script.open("a") as stream:
                stream.write("# changed during acquisition\n")
            return output

        with patch.object(subject, "_run_provider", side_effect=changing):
            self.assertIn("reader-changed", self.load()["warnings"])
        self.assertEqual([], self.slots())

    def test_unrelated_view_is_not_executed_or_required(self):
        content = database(statements=["CREATE VIEW optional_view AS SELECT unavailable_function()"])
        self.assertEqual(17, subject._validate(content))

    def test_missing_provider_keeps_exact_matching_cache_current(self):
        self.provider()
        first = self.load()
        self.script.unlink()
        result = self.load()
        self.assertEqual("cached", result["status"])
        self.assertEqual(first["provenance"], result["provenance"])
        self.assertIn("reader-unavailable", result["warnings"])
        self.source.write_bytes(b"changed source")
        result = self.load()
        self.assertEqual("stale", result["status"])
        self.assertFalse(result["provenance"]["current"])

    def test_dependency_pins_refuse_changes_and_new_pin_refreshes(self):
        self.provider()
        dependency = self.root / "helper.py"
        dependency.write_bytes(b"revision = 1\n")
        self.config["dependencies"] = [{"path": str(dependency),
            "sha256": hashlib.sha256(dependency.read_bytes()).hexdigest()}]
        first = self.load()
        self.assertEqual("refreshed", first["status"])
        self.assertEqual("cached", self.load()["status"])
        self.assertEqual("call\n", self.count.read_text())
        dependency.write_bytes(b"revision = 2\n")
        result = self.load()
        self.assertEqual("stale", result["status"])
        self.assertFalse(result["provenance"]["current"])
        self.assertIn("reader-hash-mismatch", result["warnings"])
        self.assertEqual("call\n", self.count.read_text())
        self.config["dependencies"][0]["sha256"] = hashlib.sha256(dependency.read_bytes()).hexdigest()
        self.assertEqual("refreshed", self.load()["status"])
        self.assertEqual("call\ncall\n", self.count.read_text())
        dependency.unlink()
        self.assertEqual("cached", self.load()["status"])

    def test_changed_missing_provider_does_not_inherit_current_approval(self):
        self.provider()
        first = self.load()
        self.config = {**self.config, 'script': str(self.root / 'different-missing.py'),
                       'script_sha256': '0' * 64}
        result = self.load()
        self.assertEqual('stale', result['status'])
        self.assertFalse(result['provenance']['current'])
        self.assertEqual(first['database'], result['database'])

    def test_missing_configuration_does_not_inherit_current_approval(self):
        self.provider()
        self.load()
        self.config = self.root / 'missing-config.json'
        self.assertEqual('stale', self.load()['status'])

    def test_older_receipt_refreshes_without_discarding_last_good_data(self):
        self.provider()
        first = self.load()
        slot = self.slots()[0]
        raw = slot.read_bytes()
        size = int.from_bytes(raw[:4], 'little')
        receipt = json.loads(raw[4:4 + size])
        receipt.pop('reader_config_sha256')
        header = json.dumps(receipt).encode()
        slot.write_bytes(len(header).to_bytes(4, 'little') + header + raw[4 + size:])
        script = self.script.read_bytes()
        self.script.unlink()
        self.assertEqual('stale', self.load()['status'])
        self.script.write_bytes(script)
        refreshed = self.load()
        self.assertEqual('refreshed', refreshed['status'])
        self.assertEqual(first['database'], refreshed['database'])
        self.assertEqual(2, len(self.slots()))

    def test_dependency_config_bounds_and_invalid_pins_fail_closed(self):
        self.provider()
        dependency = self.root / "helper.py"
        dependency.write_bytes(b"revision = 1\n")
        valid = {"path": str(dependency), "sha256": hashlib.sha256(dependency.read_bytes()).hexdigest()}
        for dependencies in (None, {}, [valid] * 9, [{**valid, "path": "helper.py"}],
                             [{**valid, "sha256": None}], [{**valid, "path": str(self.root)}]):
            with self.subTest(dependencies=dependencies):
                self.config["dependencies"] = dependencies
                self.assertEqual("unavailable", self.load()["status"])
        self.assertFalse(self.count.exists())
        self.config["dependencies"] = [valid]
        self.assertEqual("refreshed", self.load()["status"])
        with dependency.open("wb") as stream:
            stream.truncate(subject.MAX_SCRIPT_BYTES + 1)
        self.assertEqual("stale", self.load()["status"])

    def test_failed_same_source_backoff_expires_and_provider_change_bypasses(self):
        self.provider("sys.exit(3)\n")
        with patch.object(subject.time, "time", return_value=100):
            self.assertIn("reader-failed", self.load()["warnings"])
            self.assertIn("retry-backoff", self.load()["warnings"])
        self.assertEqual("call\n", self.count.read_text())
        with patch.object(subject.time, "time", return_value=103):
            self.assertIn("reader-failed", self.load()["warnings"])
        self.assertEqual("call\ncall\n", self.count.read_text())
        self.provider()
        with patch.object(subject.time, "time", return_value=103):
            self.assertEqual("refreshed", self.load()["status"])

    def test_same_source_same_provider_can_recover_after_backoff(self):
        self.provider()
        payload = self.root / "payload.sqlite"
        payload.write_bytes(b"temporarily invalid output")
        with patch.object(subject.time, "time", return_value=100):
            self.assertIn("database-invalid", self.load()["warnings"])
            payload.write_bytes(self.valid)
            self.assertIn("retry-backoff", self.load()["warnings"])
        with patch.object(subject.time, "time", return_value=103):
            self.assertEqual("refreshed", self.load()["status"])
        self.assertEqual("call\ncall\n", self.count.read_text())

    def test_real_provider_timeout_output_limit_and_exit_failure(self):
        cases = [("time.sleep(20)\n", "reader-timeout", "MAX_PROVIDER_SECONDS", .15),
                 ("sys.stdout.buffer.write(b'x'*200000)\n", "reader-output-limit", "MAX_DATABASE_BYTES", 1024),
                 ("sys.stderr.write(str(base)); sys.exit(2)\n", "reader-failed", "MAX_PROVIDER_SECONDS", 5)]
        for index, (body, warning, constant, value) in enumerate(cases):
            self.cache = self.root / f"cache-{index}"
            self.provider(body)
            children = []
            original = subprocess.Popen

            def capture(*args, **kwargs):
                child = original(*args, **kwargs)
                children.append(child)
                return child

            with self.subTest(warning=warning), patch.object(subject, constant, value), \
                    patch.object(subject.subprocess, "Popen", side_effect=capture):
                started = time.monotonic()
                result = self.load()
                self.assertIn(warning, result["warnings"])
                self.assertLess(time.monotonic() - started, 5)
                self.assertTrue(children)
                self.assertTrue(all(child.poll() is not None for child in children))
                self.assertEqual([], self.slots())

    def test_cancelled_refresh_kills_waits_and_propagates_with_prior(self):
        self.load()
        before = {p: p.read_bytes() for p in self.slots()}
        self.provider("time.sleep(20)\n")
        event = threading.Event()
        children = []
        original = subprocess.Popen

        def capture(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            event.set()
            return child

        with patch.object(subject.subprocess, "Popen", side_effect=capture):
            with self.assertRaises(InterruptedError):
                self.load(cancel_event=event)
        self.assertTrue(children)
        self.assertTrue(all(child.poll() is not None for child in children))
        self.assertEqual(before, {p: p.read_bytes() for p in self.slots()})
        self.assertFalse(list(self.cache.rglob("retry.json")))

    def test_cancel_before_io_and_during_snapshot_propagates(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            self.load(cancel_event=event)
        self.assertFalse(self.cache.exists())
        with patch.object(subject, "_snapshot", side_effect=InterruptedError("cancelled")):
            with self.assertRaises(InterruptedError):
                self.load()

    def test_waiting_for_lock_is_cancellable_and_bounded(self):
        self.load()
        store = subject.SafeRoot(self.slots()[0].parent)
        event = threading.Event()
        with subject._lock(store, None):
            with patch.object(subject, "MAX_LOCK_SECONDS", .05):
                self.assertIn("cache-unavailable", self.load()["warnings"])
            with ThreadPoolExecutor(max_workers=1) as pool:
                waiting = pool.submit(self.load, cancel_event=event)
                event.set()
                with self.assertRaises(InterruptedError):
                    waiting.result(timeout=2)

    def test_deep_malformed_receipt_and_provider_json_do_not_escape(self):
        self.load()
        slot = self.slots()[0]
        deep = b"[" * 1200 + b"0" + b"]" * 1200
        slot.write_bytes(len(deep).to_bytes(4, "little") + deep)
        self.source.unlink()
        self.assertIn("cache-invalid", self.load()["warnings"])
        self.provider()
        config = self.root / "deep.json"
        config.write_bytes(deep)
        self.config = config
        self.assertIn("reader-config-invalid", self.load()["warnings"])

    def test_atomic_write_failure_retains_prior_and_retry_is_possible(self):
        self.load()
        before = {p: p.read_bytes() for p in self.slots()}
        self.source.write_bytes(database(18))
        with patch.object(subject, "atomic_stream", side_effect=PermissionError("private path")):
            result = self.load()
        self.assertEqual("stale", result["status"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.slots()})
        self.assertEqual("refreshed", self.load()["status"])

    def test_concurrent_calls_share_one_acquisition(self):
        self.provider("time.sleep(.1)\nsys.stdout.buffer.write((base/'payload.sqlite').read_bytes())\n")
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.load(), range(4)))
        self.assertEqual(1, sum(result["status"] == "refreshed" for result in results))
        self.assertEqual(3, sum(result["status"] == "cached" for result in results))
        self.assertEqual("call\n", self.count.read_text())
        self.assertTrue(all(result["provenance"] == results[0]["provenance"] for result in results))

    def test_restarted_process_uses_disk_cache(self):
        self.provider()
        self.load()
        code = ("import sys,json;sys.path.insert(0,sys.argv[1]);"
                "from kfps_livery_lab.catalogue_cache import load_installed_catalogue;"
                "r=load_installed_catalogue(sys.argv[2],cache_root=sys.argv[3],reader_config=json.loads(sys.argv[4]));"
                "print(r['status'])")
        child = subprocess.run([sys.executable, "-I", "-B", "-c", code,
            str(ROOT / "tools/livery-studio/src"), str(self.game), str(self.cache), json.dumps(self.config)],
            capture_output=True, text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(0, child.returncode, child.stderr)
        self.assertEqual("cached", child.stdout.strip())
        self.assertEqual("call\n", self.count.read_text())

    def test_hardlinked_generation_or_lock_is_not_used_or_modified(self):
        self.load()
        directory = self.slots()[0].parent
        for name in ("generation-0.bin", ".storage.lock"):
            path = directory / name
            original = path.read_bytes()
            outside = self.root / (name + ".outside")
            path.unlink()
            outside.write_bytes(original)
            os.link(outside, path)
            try:
                result = self.load()
                self.assertEqual("unavailable", result["status"])
                self.assertEqual(original, outside.read_bytes())
            finally:
                path.unlink()
                path.write_bytes(original)

    def test_symlinked_cache_root_is_rejected_without_outside_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        try:
            self.cache.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlink privilege unavailable")
        result = self.load()
        self.assertEqual("unavailable", result["status"])
        self.assertEqual([], list(outside.iterdir()))

    @unittest.skipUnless(os.name == "nt", "Windows junction contract")
    def test_junction_cache_root_is_rejected_without_outside_writes(self):
        outside = self.root / "outside"
        outside.mkdir()
        child = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
            "New-Item -ItemType Junction -Path $env:KFPS_TEST_LINK -Target $env:KFPS_TEST_TARGET -ErrorAction Stop | Out-Null"],
            env={**os.environ, "KFPS_TEST_LINK": str(self.cache), "KFPS_TEST_TARGET": str(outside)},
            capture_output=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if child.returncode:
            self.skipTest("junction creation unavailable")
        try:
            self.assertEqual("unavailable", self.load()["status"])
            self.assertEqual([], list(outside.iterdir()))
        finally:
            os.rmdir(self.cache)

    def test_all_public_warnings_are_enumerated(self):
        self.provider("sys.stdout.buffer.write(b'not sqlite')\n")
        for result in (self.load(), self.load()):
            self.assertTrue(set(result["warnings"]).issubset(subject.WARNING_CODES))
            self.assertFalse(result["provenance"]["current"])
            self.assertNotIn(str(self.root), json.dumps({k: v for k, v in result.items() if k != "database"}))


if __name__ == "__main__":
    unittest.main()
