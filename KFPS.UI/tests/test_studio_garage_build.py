import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/livery-studio/src'))
from kfps_livery_lab.garage_build import BODY_PARTS, validate_build, resolve_build, effective_options, has_fixed_stock_body
from kfps_livery_lab.package_handoff import validate_layout
from kfps_livery_lab import host_bridge


def fixture():
    build = {'version': 1, 'fingerprint': 'a' * 64,
             'parts': {part: 101 + index for index, part in enumerate(BODY_PARTS)}}
    options = [{'part_type': part, 'id': ident, 'supported': True, 'empty': False}
               for part, ident in build['parts'].items()]
    return signed(build), options


def signed(build):
    build['fingerprint'] = hashlib.sha256(json.dumps({'version': build['version'], 'parts': build['parts']},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return build


class GarageBuildTests(unittest.TestCase):
    def test_fixed_stock_requires_geometry_and_current_exact_metadata(self):
        doc = {'scenes': [{'extras': {'kfps_part_options': []}}], 'meshes': [
            {'primitives': [{}], 'extras': {'kfps_part_type': 'CarBody',
             'kfps_stock_part': True, 'kfps_part_option_ids': []}}]}
        self.assertTrue(has_fixed_stock_body(doc))
        doc['scenes'][0]['extras']['kfps_part_options'] = [{'part_type': 'CarBody'}]
        self.assertFalse(has_fixed_stock_body(doc))
        doc['scenes'][0]['extras']['kfps_part_options'] = []
        doc['meshes'][0]['extras']['kfps_stock_part'] = False
        self.assertFalse(has_fixed_stock_body(doc))
        build, options = fixture()
        fixed = {**options[0], 'stock': True, 'baseline': True, 'fixed_stock': True, 'empty': True,
                 'source_kind': 'database-fixed-stock', 'declared_instance_count': 0,
                 'body_option_id': 101, 'body_parent_id': 500, 'car_body_id': -1, 'parent_upgrade_id': -1}
        names = {'source': 'installed fixture', 'same_build_verified': True, 'fixed_stock_options': [fixed]}
        self.assertEqual(build['parts'], resolve_build(build, effective_options(options[1:], names)))
        self.assertEqual(options, effective_options(options, names))
        for change in ({'same_build_verified': False}, {'source': ''}, {'fixed_stock_options': [fixed, fixed]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                resolve_build(build, effective_options(options[1:], {**names, **change}))
        for change in ({'stock': False}, {'id': 999}, {'body_option_id': 999}, {'declared_instance_count': 1},
                       {'supported': False}, {'parent_upgrade_id': 500}, {'source_kind': 'guessed'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                resolve_build(build, effective_options(options[1:], {**names, 'fixed_stock_options': [{**fixed, **change}]}))

    def test_complete_build_is_exact_and_detached(self):
        build, options = fixture()
        before = copy.deepcopy(build)
        self.assertEqual(resolve_build(build, options), build['parts'])
        result = validate_build(build)
        result['parts']['RearWing'] = 500
        self.assertEqual(build, before)

    def test_no_implicit_stock_or_missing_chassis(self):
        for value in (None, -1, 0, 9876):
            build, options = fixture()
            build['parts']['ChassisStiffness'] = value
            signed(build)
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_build(build, options)

    def test_absent_slot_only_accepted_without_positive_id(self):
        build, options = fixture()
        options = [row for row in options if row['part_type'] != 'Hood']
        with self.assertRaises(ValueError):
            resolve_build(build, options)
        for value in (None, -1, 0):
            build['parts']['Hood'] = value
            self.assertNotIn('Hood', resolve_build(signed(build), options))

    def test_empty_option_valid_but_missing_or_duplicate_not_valid(self):
        build, options = fixture()
        options[0]['empty'] = True
        self.assertEqual(resolve_build(build, options), build['parts'])
        with self.assertRaises(ValueError):
            resolve_build(build, [*options, options[0]])
        options[0]['supported'] = False
        with self.assertRaises(ValueError):
            resolve_build(build, options)

    def test_known_incompatible_body_blocked(self):
        build, options = fixture()
        options[1]['car_body_id'] = 500
        fitment = {'source': 'fixture explicit join', 'parent_map': [
            {'parent_upgrade_id': 500, 'body_option_id': 999}]}
        with self.assertRaises(ValueError):
            resolve_build(build, options, fitment)
        fitment['parent_map'][0]['body_option_id'] = build['parts']['CarBody']
        self.assertEqual(resolve_build(build, options, fitment), build['parts'])

    def test_strict_contract(self):
        build, _ = fixture()
        for change in ({'version': True}, {'version': 2}, {'fingerprint': 'bad'},
                       {'parts': {}}, {'privatePath': 'not permitted'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_build({**build, **change})
        for value in (True, 1.5, '101', -2, 2**31):
            malformed = copy.deepcopy(build)
            malformed['parts']['Hood'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_build(malformed)

    def test_explicit_nonvisual_chassis_keeps_id_without_stock_substitution(self):
        build, options = fixture()
        build['parts']['ChassisStiffness'] = 999
        signed(build)
        row = {'part_type': 'ChassisStiffness', 'id': 999, 'car_body_id': 500, 'parent_upgrade_id': 500,
               'supported': True, 'empty': True, 'declared_instance_count': 0,
               'source_kind': 'database-nonvisual', 'requires_graphics': False}
        names = {'source': 'fixture reference', 'non_visual_options': [row]}
        self.assertEqual(resolve_build(build, effective_options(options, names))['ChassisStiffness'], 999)
        for patch in ({'requires_graphics': True}, {'declared_instance_count': 1}, {'source_kind': 'guessed'}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                resolve_build(build, effective_options(options, {**names, 'non_visual_options': [{**row, **patch}]}))
        with self.assertRaises(ValueError):
            resolve_build(build, effective_options(options, {**names, 'non_visual_options': [row, row]}))

    def test_empty_layout_only_with_valid_garage_build(self):
        build, _ = fixture()
        layout = {'format': 'kfps-livery-layout-v1', 'vehicle': {'car_id': 344, 'model_code': 'NIS_FairladyZ_03'},
                  'vinyls': [], 'placements': []}
        with self.assertRaises(ValueError):
            validate_layout(layout)
        layout['garage_build'] = build
        self.assertEqual(validate_layout(layout), layout)
        self.assertEqual(host_bridge.validate_request({'name': 'My build', 'layout': layout})['layout'], layout)

    def test_stale_studio_requires_restart_before_admission(self):
        build, _ = fixture()
        request = {'layout': {'garage_build': build}}
        with patch.object(host_bridge.launcher, '_window_module') as window:
            with self.assertRaisesRegex(ValueError, 'restart'):
                host_bridge._check_package_target(ROOT, {'host_layout_handoff': True}, request)
            window.assert_not_called()


if __name__ == '__main__':
    unittest.main()
