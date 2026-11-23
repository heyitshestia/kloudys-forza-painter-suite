"""Synthetic parts fidelity regressions; no game, GPU or external reader."""
from contextlib import ExitStack
import copy
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'tools/livery-studio/src'), str(ROOT), str(Path(__file__).parent)]
from kfps_livery_lab import prepare, project_handoff, part_names, garage_build
from tools.livery import portable_mesh_converter
import test_studio_part_names as naming


def option(part, ident, **extra):
    return {'part_type': part, 'id': ident, 'supported': True, 'car_body_id': -1, **extra}


def mapping(*pairs, current=False):
    return {'source': 'synthetic qualified joins', 'reference_only': not current,
            'same_build_verified': current,
            'parent_map': [{'parent_upgrade_id': p, 'body_option_id': b} for p, b in pairs]}


def build(parts):
    value = {'version': 1, 'parts': {part: parts.get(part) for part in garage_build.BODY_PARTS}}
    value['fingerprint'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return value


class GarageFitmentTests(unittest.TestCase):
    def resolve(self, fitment, *, parent=10, prepared=False):
        options = [option('CarBody', 1), option('Hood', 7, car_body_id=parent)]
        value = build({'CarBody': 1, 'Hood': 7})
        if not prepared:
            return garage_build.resolve_build(value, options, fitment)
        document = {'scenes': [{'extras': {'kfps_part_options': options}}]}
        record = {'manifest': {'inspection_runtime': {'fidelity': {'body_compatibility': fitment}}}}
        with patch.object(portable_mesh_converter, '_glb_payloads', return_value=(document, b'')):
            return garage_build.resolve_prepared_build(value, record, {'api/local-mesh': ('synthetic',)})

    def test_explicit_unresolved_selected_parent_is_rejected_in_both_paths(self):
        for prepared in (False, True):
            for graph in (mapping(), mapping((10, 1))):
                with self.subTest(prepared=prepared, graph=graph), self.assertRaisesRegex(ValueError, 'unresolved'):
                    self.resolve({**graph, 'unresolved_parent_ids': [10]}, prepared=prepared)

    def test_unrelated_unresolved_parent_does_not_block_exact_selected_parts(self):
        for prepared in (False, True):
            result = self.resolve({**mapping((10, 1)), 'unresolved_parent_ids': [20]}, prepared=prepared)
            self.assertEqual({'CarBody': 1, 'Hood': 7}, result)

    def test_unknown_stays_distinct_from_conflict(self):
        for prepared in (False, True):
            for graph in (None, {}, mapping()):
                self.assertEqual({'CarBody': 1, 'Hood': 7}, self.resolve(graph, prepared=prepared))
            with self.assertRaisesRegex(ValueError, 'Ambiguous'):
                self.resolve(mapping((10, 1), (10, 2)), prepared=prepared)

    def test_malformed_graph_is_value_error_not_type_error(self):
        malformed = [False, 'map', [], {'source': 'test', 'parent_map': None},
                     {'source': 'test', 'parent_map': {}}, {**mapping(), 'parent_map': [None]},
                     {**mapping(), 'unresolved_parent_ids': None},
                     {**mapping(), 'unresolved_parent_ids': {}},
                     {**mapping(), 'unresolved_parent_ids': [[10]]},
                     {**mapping(), 'unresolved_parent_ids': [True]},
                     {**mapping(), 'unresolved_parent_ids': [-1]},
                     {**mapping(), 'unresolved_parent_ids': [2**31]},
                     {**mapping(), 'unresolved_parent_ids': [10] * 4097},
                     {**mapping(), 'parent_map': mapping((10, 1))['parent_map'] * 4097},
                     mapping((10, None)), mapping((10, '1')), mapping((True, 1)),
                     mapping((10, True)), mapping((10, -1)), mapping((10, 2**31))]
        for prepared in (False, True):
            for graph in malformed:
                with self.subTest(prepared=prepared, graph=str(graph)[:100]), self.assertRaises(ValueError):
                    self.resolve(graph, prepared=prepared)

    def test_malformed_selected_parent_does_not_escape_as_type_error(self):
        for parent in ([], {}, True, '10', 2**31):
            with self.subTest(parent=parent), self.assertRaises(ValueError):
                self.resolve(mapping((10, 1)), parent=parent)


class ProjectPartsTests(unittest.TestCase):
    def validate(self, options, parts, fitment=None):
        vehicle = {'car_id': 1, 'model_code': 'TEST_1'}
        value = {'format': 'kfps-livery-layout-v1', 'vehicle': vehicle,
                 'vinyls': [], 'placements': [], 'vehicle_parts': parts}
        document = {'scenes': [{'extras': {'kfps_part_options': options}}]}
        fidelity = {'body_compatibility': fitment} if fitment is not None else {}
        prepared = {'editor_config': {'vehicle': vehicle, 'sections': []},
                    'manifest': {'inspection_runtime': {'fidelity': fidelity}}}
        with patch.object(portable_mesh_converter, '_glb_payloads', return_value=(document, b'')):
            project_handoff.validate_prepared_project(value, prepared, {'api/local-mesh': ('synthetic',)})

    def test_duplicate_id_rejected_even_if_only_one_row_is_supported(self):
        for supported in (True, False):
            with self.subTest(supported=supported), self.assertRaisesRegex(ValueError, 'component|ambiguous'):
                self.validate([option('Hood', 7), option('Hood', 7, supported=supported)], {'Hood': 7})

    def test_conflict_and_undeclared_target_are_not_unknown(self):
        options = [option('CarBody', 1, stock=True), option('Hood', 7, car_body_id=10)]
        for fitment in (mapping((10, 1), (10, 999)), mapping((10, 999)),
                        {**mapping(), 'unresolved_parent_ids': [10]}):
            with self.subTest(fitment=fitment), self.assertRaises(ValueError):
                self.validate(options, {'CarBody': 1, 'Hood': 7}, fitment)
        self.validate(options, {'CarBody': 1, 'Hood': 7})

    def test_exact_declared_empty_part_remains_supported(self):
        self.validate([option('RearWing', 7, empty=True)], {'RearWing': 7})

    def test_duplicate_implicit_body_cannot_qualify_an_explicit_child(self):
        options = [option('CarBody', 1, stock=True), option('CarBody', 1, supported=False),
                   option('Hood', 7, car_body_id=10)]
        with self.assertRaises(ValueError):
            self.validate(options, {'Hood': 7}, mapping((10, 1)))

    def test_malformed_relationships_raise_a_clear_validation_error(self):
        options = [option('CarBody', 1, stock=True), option('Hood', 7, car_body_id=10)]
        for fitment in ({**mapping(), 'unresolved_parent_ids': {}},
                        {**mapping(), 'unresolved_parent_ids': [[10]]},
                        mapping((10, None)), mapping((True, 1))):
            with self.subTest(fitment=fitment), self.assertRaises(ValueError):
                self.validate(options, {'Hood': 7}, fitment)


class NamingIndependenceTests(unittest.TestCase):
    setUp = naming.PartNamesTests.setUp
    write_strings = naming.PartNamesTests.write_strings
    change_db = naming.PartNamesTests.change_db
    load = naming.PartNamesTests.load
    add_non_visual = naming.PartNamesTests.add_non_visual

    def installed(self, **kwargs):
        cached = {'database': self.database.read_bytes(), 'provenance': {'current': True}}
        with patch.object(part_names, 'load_installed_catalogue', return_value=cached):
            return part_names.load_part_names(self.game, self.vehicle, self.options, **kwargs)

    def test_missing_empty_or_invalid_strings_preserve_exact_body_map(self):
        expected = self.installed()['body_compatibility']['parent_map']
        for mode in ('missing', 'empty', 'corrupt'):
            self.write_strings()
            if mode == 'missing':
                self.archive.unlink()
            elif mode == 'empty':
                self.strings = {}
                self.write_strings()
            else:
                self.archive.write_bytes(b'not a zip')
            with self.subTest(mode=mode):
                result = self.installed()
                self.assertIsNotNone(result['body_compatibility'])
                self.assertEqual(expected, result['body_compatibility']['parent_map'])
                self.assertTrue(result['warnings'])

    def test_missing_manufacturer_does_not_remove_structural_body_join(self):
        expected = self.installed()['body_compatibility']['parent_map']
        self.change_db('UPDATE List_UpgradeCarBody SET ManufacturerID=NULL')
        result = self.installed()
        self.assertEqual(expected, result['body_compatibility']['parent_map'])
        self.assertTrue(all(row['manufacturer'] is None for row in result['names'] if row['part_type'] == 'CarBody'))

    def test_missing_optional_label_table_keeps_structure(self):
        expected = self.installed()['body_compatibility']['parent_map']
        for table in ('List_PartManufacturer', 'UpgradeTypes', 'Upgrades'):
            original = part_names._rows
            with patch.object(part_names, '_rows', wraps=part_names._rows) as rows:
                def read(db, name, *args):
                    if name == table:
                        raise part_names._InvalidData('metadata-table-unavailable:' + table)
                    return original(db, name, *args)
                rows.side_effect = read
                with self.subTest(table=table):
                    self.assertEqual(expected, self.installed()['body_compatibility']['parent_map'])

    def test_fixed_stock_and_nonvisual_qualification_survive_label_failure(self):
        self.add_non_visual()
        expected = self.installed()['non_visual_options']
        self.archive.unlink()
        self.assertEqual(expected, self.installed()['non_visual_options'])
        self.change_db('DELETE FROM List_UpgradeCarBody WHERE Id=344100')
        for family, (table, *_) in naming.FAMILIES.items():
            if family != 'CarBody':
                self.change_db(f'UPDATE {table} SET CarBodyID=344000, IsStock=1')
        self.options = []
        result = self.installed(fixed_body=True)
        self.assertIn(('CarBody', 344000), {(r['part_type'], r['id']) for r in result['fixed_stock_options']})

    def test_bad_structural_identity_stays_rejected_with_missing_labels(self):
        self.archive.unlink()
        self.change_db('UPDATE Data_Car SET MediaName="WRONG"')
        result = self.installed()
        self.assertIsNone(result['body_compatibility'])
        self.assertEqual([], result['fixed_stock_options'])

    def test_interrupted_optional_label_read_is_not_treated_as_missing_labels(self):
        with patch.object(part_names, '_read', side_effect=InterruptedError('cancelled')):
            with self.assertRaises(InterruptedError):
                self.installed()


class ReferencePrecedenceTests(unittest.TestCase):
    def choose(self, reference, installed, *, current=True):
        names = {'body_compatibility': installed, 'same_build_verified': current,
                 'reference_only': not current, 'provenance': {
                     'current': current, 'database_sha256': 'a' * 64}}
        return prepare.select_body_compatibility(reference, names)

    def test_current_exact_join_wins_over_optional_old_reference(self):
        expected = mapping((10, 1), current=True)
        result, warnings = self.choose(mapping((10, 2)), expected)
        self.assertEqual(expected['parent_map'], result['parent_map'])
        self.assertTrue(warnings)

    def test_partial_current_map_does_not_adopt_unqualified_reference_rows(self):
        result, warnings = self.choose(mapping((10, 1), (20, 2)), mapping((10, 1), current=True))
        self.assertEqual(mapping((10, 1))['parent_map'], result['parent_map'])
        self.assertEqual([20], result['unresolved_parent_ids'])
        self.assertTrue(warnings)

    def test_conflict_without_current_evidence_is_retained_not_a_viewer_exception(self):
        result, warnings = self.choose(mapping((10, 1)), mapping((10, 2)), current=False)
        self.assertEqual({1, 2}, {r['body_option_id'] for r in result['parent_map']})
        self.assertTrue(warnings)

    def test_absent_reference_and_agreement_remain_simple(self):
        value = mapping((10, 1), current=True)
        result, warnings = self.choose(None, value)
        self.assertEqual(value, result)
        self.assertEqual([], warnings)
        result, warnings = self.choose(mapping((10, 1)), value)
        self.assertEqual(value, result)
        self.assertEqual([], warnings)

    def test_bad_or_duplicate_current_mapping_does_not_override_reference(self):
        for bad in (mapping((10, 1), (10, 2), current=True),
                    mapping((True, 1), current=True), mapping((10, -1), current=True)):
            result, warnings = self.choose(mapping((10, 3)), bad)
            self.assertFalse(result.get('same_build_verified', False))
            self.assertTrue(warnings)
            self.assertIn(10, result['unresolved_parent_ids'])

    def test_qualification_requires_all_current_flags_and_digest(self):
        base = {'body_compatibility': mapping((10, 1), current=True), 'same_build_verified': True,
                'reference_only': False, 'provenance': {'current': True, 'database_sha256': 'a' * 64}}
        for change in ({'reference_only': True}, {'same_build_verified': False},
                       {'provenance': {'current': False, 'database_sha256': 'a' * 64}},
                       {'provenance': {'current': True, 'database_sha256': 'bad'}}):
            with self.subTest(change=change):
                result, warnings = prepare.select_body_compatibility(mapping((10, 2)), {**base, **change})
                self.assertFalse(result['same_build_verified'])
                self.assertIn(10, result['unresolved_parent_ids'])
                self.assertTrue(warnings)

    def test_declared_missing_relations_and_unsupported_bodies_stay_unresolved(self):
        base = {'body_compatibility': mapping((10, 1), current=True), 'same_build_verified': True,
                'reference_only': False, 'provenance': {'current': True, 'database_sha256': 'a' * 64}}
        for body in ([option('CarBody', 1)], [option('CarBody', 1, supported=False)],
                     [option('CarBody', 1), option('CarBody', 1)]):
            result, warnings = prepare.select_body_compatibility(None, base,
                [*body, option('Hood', 7, car_body_id=20)])
            self.assertIn(20, result['unresolved_parent_ids'])
            self.assertTrue(warnings)
            if len(body) > 1 or body[0]['supported'] is False:
                self.assertFalse(result['same_build_verified'])

    def test_selection_does_not_mutate_input_evidence(self):
        old, new = mapping((10, 2)), mapping((10, 1), current=True)
        before = copy.deepcopy((old, new))
        result, _ = self.choose(old, new)
        result['parent_map'][0]['body_option_id'] = 99
        self.assertEqual(before, (old, new))


class PreparationIntegrationTests(unittest.TestCase):
    def test_prepared_receipt_reopens_with_current_mapping_and_reports_gaps(self):
        from PIL import Image
        from tools.livery import vehicle_assets
        from kfps_livery_lab import converter_process, material_preview, render_adapter, wheel_fitment
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary)
            game, output = root / 'game', root / 'output'
            source = game / 'media/Cars/CAR_1.zip'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'synthetic car archive; no game data')
            output.mkdir()
            converter = root / 'converter.exe'
            converter.write_bytes(b'never executed')
            options = [option('CarBody', 1, stock=True), option('CarBody', 2),
                       option('Hood', 7, car_body_id=10), option('FrontBumper', 8, car_body_id=20)]
            document = {'scenes': [{'extras': {'kfps_part_options': options}}], 'meshes': []}
            reference = {'car_id': 1, 'catalog_sha256': 'b' * 64, 'body_options': [
                {'option_id': 2, 'parent_id': 10, 'is_stock': True,
                 'native_upgrade': {'Id': 2, 'Ordinal': 1, 'CarBodyID': 10, 'IsStock': 1},
                 'native_body': {'Id': 10}}]}
            names = {'body_compatibility': mapping((10, 1), current=True), 'same_build_verified': True,
                     'reference_only': False, 'provenance': {'current': True, 'database_sha256': 'a' * 64}}
            coverage = {'summary': {'uv_integrity_errors': 0, 'all_livery_surfaces_have_uv3': True},
                        'game_equivalence_verified': False, 'source_decoder_verified': False,
                        'materials': {}, 'wheels': {}, 'limitations': []}
            def convert(_asset, target, **_kwargs):
                target.write_bytes(b'synthetic GLB; validator mocked')
            def render(_input, _asset, target, **_kwargs):
                for name in ('paint.png', 'mask0.png', 'mask1.png', 'mask2.png'):
                    Image.new('RGBA', (2, 2)).save(target / name)
                (target / 'index.json').write_text('{}')
                return {'format': 'synthetic', 'uv_contract': {'u_scale': 1}, 'assembly': {},
                        'paint_size': [2, 2], 'mask_size': [2, 2], 'filters': {}, 'sections': [],
                        'quality_scale': 1, 'quality_source': 'test', 'cache_hit': False,
                        'files': {'paint': 'paint.png', 'masks': ['mask0.png', 'mask1.png', 'mask2.png']}}
            for target, name, kwargs in (
                (prepare, 'workspace_environment', {'return_value': output}),
                (prepare, 'load_baseline', {'return_value': ROOT}),
                (prepare, 'lab_converter', {'return_value': converter}),
                (prepare, 'audit_components', {'side_effect': lambda *_: copy.deepcopy(coverage)}),
                (vehicle_assets, '_car_clip_in_archive', {'return_value': (1, 'car.clipd')}),
                (vehicle_assets, 'read_projection_metadata', {'return_value': {'sections': []}}),
                (portable_mesh_converter, '_glb_payloads', {'return_value': (document, b'')}),
                (portable_mesh_converter, 'validate_local_chassis_glb', {'return_value': {'valid': True}}),
                (converter_process, 'convert_vehicle_model_to_glb', {'side_effect': convert}),
                (material_preview, 'prepare_material_preview', {'return_value': {
                    'profile': 'synthetic', 'declarations': [], 'assets': [], 'summary': {}, 'omissions': []}}),
                (part_names, 'load_part_names', {'return_value': names}),
                (wheel_fitment, 'read_reference_record', {'return_value': reference}),
                (wheel_fitment, 'placeholder_assembly', {'return_value': {'wheel_fitment': {}}}),
                (render_adapter, 'build_authoring_atlases', {'side_effect': render}),
            ):
                stack.enter_context(patch.object(target, name, **kwargs))
            first = prepare.prepare_car(ROOT, game, source.name, output)
            reopened = json.loads((output / 'prepared.json').read_text())
            self.assertEqual(first, reopened)
            fidelity = reopened['manifest']['inspection_runtime']['fidelity']
            self.assertEqual(mapping((10, 1))['parent_map'], fidelity['body_compatibility']['parent_map'])
            self.assertEqual([20], fidelity['body_compatibility']['unresolved_parent_ids'])
            self.assertTrue(fidelity['limitations'])
            project = {'format': 'kfps-livery-layout-v1', 'vehicle': {'car_id': 1, 'model_code': 'CAR_1'},
                       'vinyls': [], 'placements': [], 'vehicle_parts': {'CarBody': 1, 'Hood': 7}}
            project_handoff.validate_prepared_project(project, reopened, {'api/local-mesh': ('synthetic',)})
            with self.assertRaisesRegex(ValueError, 'unresolved'):
                project_handoff.validate_prepared_project({**project, 'vehicle_parts': {'FrontBumper': 8}},
                    reopened, {'api/local-mesh': ('synthetic',)})
            garage_build.resolve_prepared_build(build({'CarBody': 1, 'Hood': 7, 'FrontBumper': 8}),
                {**reopened, 'manifest': {'inspection_runtime': {'fidelity': {
                    'body_compatibility': mapping((10, 1), (20, 1))}}}}, {'api/local-mesh': ('synthetic',)})
            with self.assertRaisesRegex(ValueError, 'unresolved'):
                garage_build.resolve_prepared_build(build({'CarBody': 1, 'Hood': 7, 'FrontBumper': 8}),
                    reopened, {'api/local-mesh': ('synthetic',)})
            second = prepare.prepare_car(ROOT, game, source.name, output)
            self.assertEqual({'mesh': True, 'render': True}, second['cache'])
            self.assertEqual(fidelity, second['manifest']['inspection_runtime']['fidelity'])
            for module in ('prepare.py', 'part_names.py', 'garage_build.py'):
                with self.subTest(old_receipt_module=module):
                    cached = json.loads((output / 'prepared.json').read_text())
                    cached['manifest']['inspection_runtime']['fidelity']['body_compatibility'] = mapping((20, 1))
                    prepare.atomic_json(output / 'prepared.json', cached)
                    receipt = json.loads((output / 'preparation-receipt.json').read_text())
                    self.assertEqual(prepare.file_hash(Path(prepare.__file__).with_name(module)),
                                     receipt['dependencies']['code']['files']['lab/' + module])
                    receipt['dependencies']['code']['files']['lab/' + module] = '0' * 64
                    receipt['prepared_sha256'] = prepare.file_hash(output / 'prepared.json')
                    prepare.atomic_json(output / 'preparation-receipt.json', receipt)
                    rebuilt = prepare.prepare_car(ROOT, game, source.name, output)
                    self.assertFalse(rebuilt['cache']['render'])
                    self.assertEqual(fidelity, rebuilt['manifest']['inspection_runtime']['fidelity'])
            names['body_compatibility'] = mapping((10, 2), current=True)
            changed = prepare.prepare_car(ROOT, game, source.name, output)
            self.assertFalse(changed['cache']['render'])
            self.assertEqual(mapping((10, 2))['parent_map'],
                changed['manifest']['inspection_runtime']['fidelity']['body_compatibility']['parent_map'])


if __name__ == '__main__':
    unittest.main()
