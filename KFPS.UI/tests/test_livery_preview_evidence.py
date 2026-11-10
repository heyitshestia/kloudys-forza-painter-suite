"""Data-only preview evidence and the read-only preparation return contract."""
from __future__ import annotations

import copy
from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/livery-studio/src')]

from kfps_livery_lab import preview_evidence as evidence
from kfps_livery_lab import readonly_prepare


def preparation():
    return {
        'manifest': {'vehicle': {'car_id': 42}, 'inspection_runtime': {
            'fidelity': {
                'summary': {
                    'declared_parts': 18, 'converted_options': 15,
                    'mesh_primitives': 686, 'missing_local_model_references': 2,
                    'external_model_references': 3, 'unrepresented_options': 1,
                    'blocked_options': 0, 'model_membership_mismatches': 0,
                    'blocked_model_membership_omissions': 0,
                    'direct_uv3_primitives': 47, 'missing_uv3_primitives': 0,
                    'unsupported_livery_surface_primitives': 0,
                    'verified_uv_channels': 2631, 'uv_integrity_errors': 0,
                    'uv_channel_omissions': 0,
                },
                'materials': 'neutral-inspection', 'wheels': 'inspection-stand-ins',
                'game_equivalence_verified': False,
                'limitations': [
                    'UV fingerprints verify importer-to-GLB copy integrity, not the game parser or shader.',
                    'Manifest references include alternate LOD files; partial entries are not automatically missing visible parts.',
                    'A declared empty option is distinct from a failed or unresolved model.',
                    'No in-game geometry, fitment, texture, mask or projection equivalence has been established.',
                ],
            },
            'native_textures': {
                'summary': {'total_meshes': 686, 'staged_meshes': 4,
                            'omitted_meshes': 2, 'ignored_meshes': 680, 'distinct_assets': 1},
                'omissions': [
                    {'mesh_index': 2, 'reason': 'unverified-material-declaration'},
                    {'mesh_index': 3, 'reason': 'unverified-material-declaration'},
                ],
            },
            'render_contract': {'quality_scale': 1, 'paint_size': [2048, 907],
                                'mask_size': [2048, 1024], 'uv_contract': {'native': True},
                                'assembly': {'wheel_fitment': {'status': 'unavailable'}},
                                'sections': [{'section': 'Front', 'slot_index': 0}]},
        }},
        'conversion': {'process': {'report': {
            'mesh_count': 686, 'unresolved_instance_count': 0,
            'skipped_optional_instance_count': 3,
        }}},
        'cache': {'mesh': True}, 'signature': {'source': 'fixture'},
        'validation': {},
        'files': {'mesh': 'mesh/vehicle.glb', 'paint': 'render/paint.png',
                  'coverage': 'component-coverage.json', 'masks': ['render/mask.png'],
                  'native_textures': {}},
    }


def final_contract():
    return {'format': 'fixture', 'quality_scale': 4, 'paint_size': [8192, 3628],
            'mask_size': [2048, 2048], 'quality_source': 'mixed-original-and-vector',
            'quality_notes': ['Top: retained original resolution because referenced artwork is unavailable locally'],
            'sections': [{'section': 'Top', 'slot_index': 2}, {'section': 'Left', 'slot_index': 3}],
            'assembly': {'wheel_fitment': {'status': 'reference-sized'}},
            'uv_contract': {}, 'filters': {}, 'files': {'paint': 'section-paint.png'}}


class PreviewEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.prepared = preparation()
        self.contract = final_contract()

    def build(self):
        return evidence.build_preview_evidence(self.prepared, self.contract)

    def rows(self, key):
        return {row['label']: row for row in self.build()[key]}

    def test_final_contract_is_authoritative(self):
        result = self.build()
        self.assertEqual(4, result['quality_scale'])
        self.assertEqual([8192, 3628], result['paint_size'])
        self.assertEqual([2048, 2048], result['mask_size'])
        self.assertIs(True, result['mesh_cache_hit'])
        self.assertEqual([{'name': 'Top', 'slot_index': 2}, {'name': 'Left', 'slot_index': 3}], result['sections'])
        self.assertEqual(4, result['limitation_count'])
        self.assertEqual('Reference-sized inspection stand-ins', self.rows('materials')['Wheel preview']['value'])
        self.assertTrue(any('original resolution' in text for text in result['warnings']))

    def test_counts_keep_their_actual_units_and_never_claim_parity(self):
        rows = self.rows('geometry')
        self.assertEqual('686', rows['Converted meshes']['value'])
        self.assertEqual('686', rows['Mesh primitives']['value'])
        self.assertEqual('2', rows['Missing local model references']['value'])
        self.assertEqual('1', rows['Unrepresented upgrade options']['value'])
        self.assertEqual('warning', rows['Missing local model references']['tone'])
        self.assertEqual('2631', rows['UV channels with verified copy integrity']['value'])
        self.assertEqual('0', rows['Unresolved required model instances']['value'])
        self.assertEqual('3', rows['Skipped optional model instances']['value'])
        warnings = ' '.join(self.build()['warnings'])
        self.assertIn('not the game parser or shader', warnings)
        self.assertIn('alternate LOD', warnings)
        self.assertIn('game equivalence is not established', warnings)
        self.prepared['manifest']['inspection_runtime']['fidelity']['game_equivalence_verified'] = True
        self.assertIn('game equivalence is not established', ' '.join(self.build()['warnings']))

    def test_material_staging_is_not_total_material_support(self):
        rows = self.rows('materials')
        self.assertEqual('4', rows['Meshes with staged native textures']['value'])
        self.assertEqual('680', rows['Meshes outside the native texture profile']['value'])
        self.assertEqual('2', rows['Omitted: unverified declaration']['value'])
        self.assertEqual('Neutral inspection', rows['Material baseline']['value'])

    def test_missing_data_is_unknown_not_zero_or_success(self):
        result = evidence.build_preview_evidence({}, {})
        for key in ('quality_scale', 'paint_size', 'mask_size', 'mesh_cache_hit', 'limitation_count'):
            self.assertIsNone(result[key], key)
        self.assertEqual([], result['geometry'])
        self.assertEqual([], result['materials'])
        self.assertEqual([], result['sections'])
        self.assertTrue(result['warnings'])

    def test_missing_final_values_do_not_fall_back_to_preparation(self):
        self.contract = {}
        result = self.build()
        self.assertIsNone(result['quality_scale'])
        self.assertIsNone(result['paint_size'])
        self.assertIsNone(result['mask_size'])
        self.assertEqual([], result['sections'])

    def test_cache_false_is_distinct_from_unknown(self):
        for value, expected in [(False, False), (True, True), (0, None), (1, None), ('false', None), (None, None)]:
            with self.subTest(value=value):
                self.prepared['cache']['mesh'] = value
                self.assertIs(expected, self.build()['mesh_cache_hit'])

    def test_only_supported_final_quality_levels_are_reported(self):
        for value in (1, 2, 4, 0, 3, 8):
            self.contract['quality_scale'] = value
            self.assertEqual(value if value in (1, 2, 4) else None, self.build()['quality_scale'])

    def test_malformed_containers_do_not_raise_or_leak(self):
        for value in (None, True, 1, 'private', [], object()):
            with self.subTest(value=value):
                json.dumps(evidence.build_preview_evidence(value, value), allow_nan=False)
                self.prepared['manifest'] = value
                json.dumps(self.build(), allow_nan=False)
        for key in ('fidelity', 'native_textures'):
            for value in (None, [], 'private', True):
                self.prepared = preparation()
                self.prepared['manifest']['inspection_runtime'][key] = value
                json.dumps(self.build(), allow_nan=False)

    def test_nested_malformed_summaries_and_diagnostics_are_ignored(self):
        for value in (None, [], 'private', False, object()):
            with self.subTest(value=value):
                runtime = self.prepared['manifest']['inspection_runtime']
                runtime['fidelity']['summary'] = value
                runtime['native_textures'].update(summary=value, omissions=value)
                self.prepared.update(cache=value, conversion={'process': {'report': value}})
                self.contract['assembly'] = value
                result = self.build()
                self.assertEqual([], result['geometry'])
                self.assertIsNone(result['mesh_cache_hit'])
                json.dumps(result, allow_nan=False)
                self.prepared['conversion'] = {'process': value}
                self.assertEqual([], self.build()['geometry'])
                self.prepared['conversion'] = value
                self.assertEqual([], self.build()['geometry'])

    def test_bool_and_other_invalid_numbers_are_not_coerced(self):
        for value in (True, False, -1, 1.5, '4', float('nan'), float('inf'), 10**100):
            with self.subTest(value=value):
                runtime = self.prepared['manifest']['inspection_runtime']
                runtime['fidelity']['summary'] = {'mesh_primitives': value, 'verified_uv_channels': value}
                runtime['native_textures']['summary'] = {'staged_meshes': value}
                self.prepared['conversion']['process']['report'] = {'mesh_count': value}
                self.contract.update(quality_scale=value, paint_size=[value, 1024], mask_size=[2048, value],
                                     sections=[{'section': 'Top', 'slot_index': value}])
                result = self.build()
                self.assertEqual([], result['geometry'])
                self.assertNotIn('Meshes with staged native textures', self.rows('materials'))
                self.assertIsNone(result['quality_scale'])
                self.assertIsNone(result['paint_size'])
                self.assertIsNone(result['mask_size'])
                self.assertEqual([], result['sections'])
                json.dumps(result, allow_nan=False)

    def test_real_zeros_are_kept_but_invalid_dimensions_are_unknown(self):
        self.assertEqual('0', self.rows('geometry')['UV copy-integrity errors']['value'])
        for value in ([], [0, 1], [1], [1, 2, 3], '2048x1024', {'width': 2048}, [1, None]):
            with self.subTest(value=value):
                self.contract.update(paint_size=value, mask_size=value)
                self.assertIsNone(self.build()['paint_size'])
                self.assertIsNone(self.build()['mask_size'])

    def test_wheel_status_uses_final_assembly_not_generic_fidelity(self):
        self.contract['assembly']['wheel_fitment']['status'] = 'unavailable'
        self.assertEqual('No qualified wheel stand-ins', self.rows('materials')['Wheel preview']['value'])

    def test_sections_are_bounded_allowlisted_and_deduplicated(self):
        self.contract['sections'] = [None, {}, {'section': 'Top', 'slot_index': True},
                                     {'section': 'C:/private/car', 'slot_index': 0},
                                     *self.contract['sections'], *self.contract['sections']]
        self.assertEqual([{'name': 'Top', 'slot_index': 2}, {'name': 'Left', 'slot_index': 3}], self.build()['sections'])

    def test_no_path_or_free_text_is_exposed(self):
        secrets = [r'C:\Users\Private\car.zip', 'C:/Users/Private/car.zip',
                   r'\\server\private\car.zip', '/home/private/car.zip',
                   'file:///C:/Private/car.zip', 'game:/media/private/car.zip',
                   'C%3A%5CPrivate%5Ccar.zip', 'parity verified <script>private</script>']
        for secret in secrets:
            with self.subTest(secret=secret):
                runtime = self.prepared['manifest']['inspection_runtime']
                runtime['fidelity'].update(materials=secret, wheels=secret, limitations=[secret])
                runtime['native_textures']['omissions'] = [{'reason': secret, 'source_path': secret}]
                self.prepared['conversion']['process'].update(stdout=secret, stderr=secret, output=secret)
                self.prepared['conversion']['process']['report']['unresolved_paths'] = [secret]
                self.contract.update(quality_notes=[secret], quality_source=secret,
                                     assembly={'wheel_fitment': {'status': secret, 'reason': secret}},
                                     sections=[{'section': secret, 'slot_index': 0}])
                encoded = json.dumps(self.build(), allow_nan=False)
                self.assertNotIn(secret, encoded)
                self.assertNotIn('Private', encoded)
                self.assertNotIn('private', encoded)
                self.assertEqual(1, self.build()['limitation_count'])

    def test_large_lists_and_text_have_explicit_output_bounds(self):
        runtime = self.prepared['manifest']['inspection_runtime']
        runtime['fidelity']['limitations'] = ['x' * 10000] * (evidence.MAX_SCAN_ITEMS + 1)
        runtime['native_textures']['omissions'] = [{'reason': 'unverified-material-declaration'}] * (evidence.MAX_SCAN_ITEMS + 1)
        self.contract['sections'] = [{'section': 'Top', 'slot_index': n} for n in range(evidence.MAX_SCAN_ITEMS + 1)]
        result = self.build()
        self.assertIsNone(result['limitation_count'])
        self.assertLessEqual(len(result['geometry']), evidence.MAX_ROWS)
        self.assertLessEqual(len(result['materials']), evidence.MAX_ROWS)
        self.assertLessEqual(len(result['warnings']), evidence.MAX_WARNINGS)
        self.assertLessEqual(len(result['sections']), evidence.MAX_SECTIONS)
        self.assertTrue(any('first' in text and 'omission' in text for text in result['warnings']))
        self.assertTrue(any('section' in text.lower() and 'truncated' in text for text in result['warnings']))
        for row in result['geometry'] + result['materials']:
            for key in ('label', 'value', 'tone'):
                self.assertLessEqual(len(row[key]), evidence.MAX_TEXT)
        self.assertTrue(all(len(text) <= evidence.MAX_TEXT for text in result['warnings']))
        self.assertLess(len(json.dumps(result)), 12000)

    def test_many_omission_reasons_are_compacted_without_losing_sample_counts(self):
        native = self.prepared['manifest']['inspection_runtime']['native_textures']
        native['omissions'] = [{'reason': reason} for reason in evidence.OMISSION_REASONS]
        rows = [row for row in self.build()['materials'] if row['label'].startswith('Omitted: ')]
        self.assertLessEqual(len(rows), evidence.MAX_OMISSION_REASONS + 1)
        self.assertEqual(len(native['omissions']), sum(int(row['value']) for row in rows))

    def test_combined_warnings_preserve_partial_list_notices(self):
        runtime = self.prepared['manifest']['inspection_runtime']
        runtime['fidelity']['limitations'] += [
            'Optional wheel/body reference is unavailable (missing-reference).',
            'Future limitation', None,
        ]
        runtime['native_textures'] = {
            'omissions': [{'reason': 'asset-limit-reached'}] * (evidence.MAX_SCAN_ITEMS + 1),
        }
        self.contract['sections'] = [None] + [
            {'section': 'Top', 'slot_index': n} for n in range(evidence.MAX_SCAN_ITEMS + 1)]
        warnings = self.build()['warnings']
        self.assertLessEqual(len(warnings), evidence.MAX_WARNINGS)
        self.assertTrue(any('first' in item and 'omission' in item for item in warnings))
        self.assertTrue(any('Section evidence is truncated' in item for item in warnings))

    def test_empty_limitation_list_is_distinct_from_unavailable(self):
        fidelity = self.prepared['manifest']['inspection_runtime']['fidelity']
        fidelity['limitations'] = []
        self.assertEqual(0, self.build()['limitation_count'])
        for value in (None, '', 'limitation', [''], ['   '], [False]):
            fidelity['limitations'] = value
            self.assertIsNone(self.build()['limitation_count'])

    def test_malformed_lists_and_unknown_reasons_are_explicit(self):
        runtime = self.prepared['manifest']['inspection_runtime']
        runtime['fidelity']['limitations'] = [None, False, {}]
        runtime['native_textures']['omissions'] = [None, {}, {'reason': []}, {'reason': 'future-reason'}]
        self.contract['sections'] = 'Top'
        result = self.build()
        self.assertIsNone(result['limitation_count'])
        self.assertEqual('4', self.rows('materials')['Omitted: unrecognized or invalid reason']['value'])
        self.assertEqual([], result['sections'])

    def test_pure_deterministic_json_without_input_mutation(self):
        before = copy.deepcopy((self.prepared, self.contract))
        with patch('builtins.open', side_effect=AssertionError('No file reads')), \
             patch.object(Path, 'open', side_effect=AssertionError('No file reads')):
            result = self.build()
            self.assertEqual(result, self.build())
            self.assertEqual(result, json.loads(json.dumps(result, allow_nan=False)))
        self.assertEqual(before, (self.prepared, self.contract))
        result['paint_size'][0] = 1
        result['sections'][0]['name'] = 'Changed'
        self.assertEqual(before, (self.prepared, self.contract))


class ReadonlyPreparationEvidenceTests(unittest.TestCase):
    """Exercise the actual orchestration, with all disk/converter boundaries mocked."""

    def setUp(self):
        self.prepared, self.contract = preparation(), final_contract()
        self.asset = SimpleNamespace(car_id=42, model_code='TEST', archive_mtime_ns=1,
                                     archive_name='test.zip')
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.mocks = {}
        replacements = {
            'installation_cache_lease': lambda *args, **kwargs: nullcontext(),
            'cache_lease': lambda *args, **kwargs: nullcontext(),
            'workspace_lock': lambda *args, **kwargs: nullcontext(),
            'cache_root': ROOT / 'runtime/unused-preview-evidence-test',
            'prepare_entry': ROOT / 'runtime/unused-preview-evidence-test/cars/test',
            'ordinary_path': lambda path, root: path,
            'within': lambda path, root: path,
            'io_path': MagicMock(), 'verify_inventory': None, 'admit_artifact': None,
            'seal_inventory': None, 'enforce_budget': None,
            'file_hash': 'a' * 64, 'prepare_car': self.prepared,
            'build_saved_atlas': self.contract, 'make_display_manifest': {'display': True},
            'write_descriptor': ROOT / 'runtime/unused-preview-descriptor.json',
            'prune_cache': {'bytes': 10, 'budget_bytes': 100},
        }
        replacements['io_path'].exists.return_value = False
        for name, replacement in replacements.items():
            kwargs = {'side_effect': replacement} if callable(replacement) and not isinstance(replacement, MagicMock) else {'return_value': replacement}
            self.mocks[name] = self.stack.enter_context(patch.object(readonly_prepare, name, **kwargs))
        self.stack.enter_context(patch.object(readonly_prepare.os, 'utime'))
        self.stack.enter_context(patch('tools.livery.package.validate_livery_inspection_artifact',
                                      return_value={'livery': {'target_car_id': 42}}))

    def test_return_adds_only_evidence_and_preserves_existing_fields(self):
        result = readonly_prepare.prepare_readonly(ROOT, ROOT / 'unused-game', self.asset,
                                                  ROOT / 'unused-package', quality_scale=4,
                                                  layer_provider=lambda: [])
        self.assertEqual({'readonly_descriptor', 'readonly_descriptor_sha256', 'mesh_path',
                          'render_root', 'render_contract', 'mesh_cache_hit', 'cache_usage',
                          'quality_notes', 'preview_evidence'}, set(result))
        self.assertIs(self.contract, result['render_contract'])
        self.assertIs(self.contract['quality_notes'], result['quality_notes'])
        self.assertEqual('a' * 64, result['readonly_descriptor_sha256'])
        self.assertIs(True, result['mesh_cache_hit'])
        self.assertEqual({'bytes': 10, 'budget_bytes': 100}, result['cache_usage'])
        self.assertEqual(str(self.mocks['write_descriptor'].return_value), result['readonly_descriptor'])
        self.assertTrue(result['mesh_path'].endswith(str(Path('mesh/vehicle.glb'))))
        self.assertIn('saved-atlases', result['render_root'])
        self.assertEqual(evidence.build_preview_evidence(self.prepared, self.contract), result['preview_evidence'])
        self.assertEqual(4, result['preview_evidence']['quality_scale'])
        self.assertEqual('No qualified wheel stand-ins', next(row['value'] for row in result['preview_evidence']['materials'] if row['label'] == 'Wheel preview'))
        self.assertNotIn('preview_evidence', self.mocks['write_descriptor'].call_args.args[1])
        json.dumps(result['preview_evidence'], allow_nan=False)

    def test_preparation_failure_is_not_hidden_by_evidence(self):
        self.mocks['build_saved_atlas'].side_effect = ValueError('fixture failure')
        with self.assertRaisesRegex(ValueError, 'fixture failure'):
            readonly_prepare.prepare_readonly(ROOT, ROOT / 'unused-game', self.asset, ROOT / 'unused-package')
        self.mocks['write_descriptor'].assert_not_called()
        self.mocks['seal_inventory'].assert_called_once()
        self.mocks['enforce_budget'].assert_called_once()

    def test_actual_fallback_quality_and_cache_miss_reach_return_data(self):
        self.prepared['cache']['mesh'] = False
        self.contract.update(quality_scale=1, paint_size=[2048, 907],
                             quality_source='package-section-images', quality_notes=[])
        result = readonly_prepare.prepare_readonly(ROOT, ROOT / 'unused-game', self.asset,
                                                  ROOT / 'unused-package', quality_scale=4,
                                                  layer_provider=lambda: [])
        self.assertIs(False, result['mesh_cache_hit'])
        self.assertIs(False, result['preview_evidence']['mesh_cache_hit'])
        self.assertEqual(1, result['preview_evidence']['quality_scale'])
        self.assertEqual([2048, 907], result['preview_evidence']['paint_size'])
        self.assertEqual([], result['quality_notes'])

    def test_missing_optional_evidence_does_not_break_preparation(self):
        runtime = self.prepared['manifest']['inspection_runtime']
        runtime.update(fidelity=None, native_textures=[])
        self.prepared['conversion'] = None
        result = readonly_prepare.prepare_readonly(ROOT, ROOT / 'unused-game', self.asset, ROOT / 'unused-package')
        self.assertEqual([], result['preview_evidence']['geometry'])
        self.assertIsNone(result['preview_evidence']['limitation_count'])
        self.assertIs(self.contract, result['render_contract'])

    def test_cancellation_preserves_existing_cleanup_and_never_converts(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(InterruptedError):
            readonly_prepare.prepare_readonly(ROOT, ROOT / 'unused-game', self.asset,
                                              ROOT / 'unused-package', cancel_event=cancel)
        self.mocks['prepare_car'].assert_not_called()
        self.mocks['build_saved_atlas'].assert_not_called()
        self.mocks['write_descriptor'].assert_not_called()
        self.mocks['seal_inventory'].assert_called_once()
        self.mocks['enforce_budget'].assert_called_once()


if __name__ == '__main__':
    unittest.main()
