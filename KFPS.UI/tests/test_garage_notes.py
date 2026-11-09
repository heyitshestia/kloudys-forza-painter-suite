import json
from pathlib import Path
import sys
import tempfile
import sqlite3
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'KFPS.UI/src'), str(ROOT / 'tools/livery-studio/src')]
from kfps_ui.garage_index import GarageError, normalize_garage
from kfps_ui.garage_notes import GarageNotes, inspect_project, resolve_project
from test_garage_index import car


def project(car_id=123):
    return {'format': 'kfps-livery-layout-v1', 'vehicle': {'car_id': car_id, 'model_code': 'QA_CAR'},
            'vinyls': [], 'placements': [], 'vehicle_parts': {'RearWing': 4}}


class GarageNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.notes = GarageNotes(self.root / 'notes.json')
        self.row = normalize_garage([car()])[0]
        self.file = self.root / 'build.json'
        self.file.write_text(json.dumps(project()))

    def test_named_comparison_reopens_without_profile_or_full_project(self):
        entry = self.notes.add('Wing test', self.row)
        linked = inspect_project(self.file, 123, ROOT)
        self.notes.link(entry['id'], linked)
        reopened = self.notes.load()[0]
        self.assertEqual('Wing test', reopened['name'])
        self.assertEqual(self.row, reopened['car'])
        self.assertNotIn('vinyls', reopened['project'])
        self.assertEqual('current', resolve_project(reopened['project'], ROOT)['status'])

    def test_reject_wrong_model_invalid_project_and_bad_names(self):
        for name in ('', 'a\nb', 'x' * 81):
            with self.assertRaises(GarageError): self.notes.add(name, self.row)
        with self.assertRaises(GarageError): inspect_project(self.file, 456, ROOT)
        self.file.write_text(json.dumps({**project(), 'placements': [{'visible': True}]}))
        with self.assertRaises(GarageError): inspect_project(self.file, 123, ROOT)

    def test_changed_and_missing_project_do_not_change_comparison(self):
        entry = self.notes.add('Baseline', self.row)
        self.notes.link(entry['id'], inspect_project(self.file, 123, ROOT))
        saved = self.notes.load()[0]
        self.file.write_text(json.dumps({**project(), 'vehicle_parts': {'RearWing': 8}}))
        self.assertEqual('changed', resolve_project(saved['project'], ROOT)['status'])
        self.file.unlink()
        self.assertEqual('missing', resolve_project(saved['project'], ROOT)['status'])
        self.assertEqual(saved, self.notes.load()[0])

    def test_managed_revision_follows_stable_id_read_only(self):
        from kfps_livery_lab.project_storage import ProjectStore
        store = ProjectStore(self.root / 'projects')
        value = project()
        first = store.save(value['vehicle'], {'name': 'Managed', 'project': value})['entry']
        files = list(store.root.rglob(first['file_name']))
        linked = inspect_project(files[0], 123, ROOT)
        value['vehicle_parts']['RearWing'] = 77
        second = store.save(value['vehicle'], {'id': first['id'], 'expected_revision': first['revision'],
                                               'name': 'Managed', 'project': value})['entry']
        before = {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()}
        resolved = resolve_project(linked, ROOT)
        self.assertEqual('changed', resolved['status'])
        self.assertEqual(second['file_name'], Path(resolved['path']).name)
        self.assertEqual(before, {p: p.read_bytes() for p in store.root.rglob('*') if p.is_file()})

    def test_project_checks_support_cancellation_and_reject_sql_views(self):
        from kfps_livery_lab.project_storage import ProjectStore
        store = ProjectStore(self.root / 'projects')
        value = project()
        saved = store.save(value['vehicle'], {'name': 'Managed', 'project': value})['entry']
        linked = inspect_project(next(store.root.rglob(saved['file_name'])), 123, ROOT)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError): resolve_project(linked, ROOT, cancel=cancel)
        with sqlite3.connect(store.path) as db:
            db.execute('ALTER TABLE projects RENAME TO hidden_projects')
            db.execute('CREATE VIEW projects AS SELECT * FROM hidden_projects')
        db.close()
        self.assertEqual('unavailable', resolve_project(linked, ROOT)['status'])

    def test_managed_query_deadline_interrupts_expensive_catalogue(self):
        linked = inspect_project(self.file, 123, ROOT)
        database = self.root / 'storage.sqlite3'
        with sqlite3.connect(database) as db:
            db.execute('PRAGMA user_version=1')
            db.execute('CREATE TABLE cars (key TEXT, car_id INTEGER, model_code TEXT, folder TEXT)')
            db.execute('CREATE TABLE projects (id TEXT, car_key TEXT, file_name TEXT, revision TEXT, bytes INTEGER)')
            db.execute('CREATE TABLE files (car_key TEXT, name TEXT)')
            db.executemany('INSERT INTO projects VALUES (?,?,?,?,?)',
                           [('other', 'x', 'x.json', 'a' * 64, 100)] * 2000)
        db.close()
        linked.update(managedRoot=str(self.root), managedId='a' * 32)
        with patch('kfps_ui.garage_notes.time.monotonic', side_effect=[0] + [99] * 100):
            self.assertEqual('unavailable', resolve_project(linked, ROOT)['status'])

    def test_delete_only_removes_local_reference_and_corrupt_file_is_preserved(self):
        entry = self.notes.add('One', self.row)
        self.notes.link(entry['id'], inspect_project(self.file, 123, ROOT))
        before = self.file.read_bytes()
        self.notes.remove(entry['id'])
        self.assertEqual(before, self.file.read_bytes())
        self.assertEqual([], self.notes.load())
        self.notes.path.write_text('{broken')
        with self.assertRaises(GarageError): self.notes.add('Two', self.row)
        self.assertEqual('{broken', self.notes.path.read_text())


if __name__ == '__main__': unittest.main()
