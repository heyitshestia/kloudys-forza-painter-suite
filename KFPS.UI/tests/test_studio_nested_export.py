"""Nested editable groups survive Studio section and full-car export."""
import copy
from collections import Counter
from datetime import datetime, timezone
import io
import hashlib
import random
import struct
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_studio_offline_save_codec import NAMES, project, shape, template_bytes, decoder
from test_studio_mask_export import strict_sections
from kfps_livery_lab.save_codec import SaveTemplate, compile_layout, compile_section_vinyl, encode_experiment, unwrap_bounded
from kfps_livery_lab.model import ValidationError
from tools.cgroup.vinyl_document import encode_vinyl_document
from tools.livery.fh6_save_installer import build_destination_header
from kfps_livery_lab.export_service import ExportService


def nested_shapes(mask=False):
    paths = [('a', 'b'), ('a', 'b'), ('a',), ('c',), ()]
    shapes = [shape(x=i*10, sx=.25, sy=.25) for i in range(len(paths))]
    for item, keys in zip(shapes, paths):
        if keys:
            item['editor_group_path'] = [{'id': key, 'name': key.upper()} for key in keys]
            item['editor_group_id'], item['editor_group_name'] = keys[-1], keys[-1].upper()
    if mask:
        shapes[1]['mask'] = True
        shapes[1]['data'][6] = 1
    return shapes


def spans(shapes):
    groups = {}
    for index, item in enumerate(shapes):
        for group in item.get('editor_group_path', []):
            groups.setdefault(group['id'], []).append(index)
    return Counter(tuple(indices) for indices in groups.values())


class NestedExportTests(unittest.TestCase):
    def test_first_section_child_has_no_preceding_state(self):
        template = SaveTemplate.read(template_bytes(), 4267)
        for grouped in (False, True):
            item = shape()
            if grouped:
                item['editor_group_path'] = [{'id':'g','name':'G'}]
            raw, _ = encode_experiment(template, {'Front':[item]})
            body, _, _ = decoder.extract_livery_payload(unwrap_bounded(raw))
            prefix = struct.pack('<HHH',1,1,0) + bytes([int(grouped)])
            first = struct.pack('<4fB',0,0,1,0,0x20) if grouped else b'\x02'
            with self.subTest(grouped=grouped):
                self.assertTrue(body.startswith(prefix + first), body[:28].hex())

    def test_section_keeps_source_hierarchy_below_each_placement(self):
        value = project(nested_shapes())
        value['placements'].append({**value['placements'][0], 'id':'second', 'x':120})
        original = copy.deepcopy(value)
        document = compile_section_vinyl(value, 4267, NAMES, 'Left')
        native, _ = encode_vinyl_document(document)
        actual, report = decoder.cgroup_to_layers(native)
        self.assertFalse(report['warnings'])
        expected = Counter({(0,1,2,3,4):1, (0,1,2):1, (0,1):1, (3,):1,
                            (5,6,7,8,9):1, (5,6,7):1, (5,6):1, (8,):1})
        self.assertEqual(expected, spans(actual))
        self.assertEqual(value, original)

    def test_full_car_keeps_groups_and_masks_in_every_section(self):
        template = SaveTemplate.read(template_bytes(), 4267)
        for name in NAMES:
            for mask in (False, True):
                with self.subTest(section=name, mask=mask):
                    sections = compile_layout(project(nested_shapes(mask), section=name), 4267, NAMES)
                    raw, report = encode_experiment(template, sections)
                    strict_sections(raw)
                    SaveTemplate.read(raw, 4267)
                    actual, decoded = decoder.clivery_to_layers(unwrap_bounded(raw), preserve_groups=True)
                    self.assertFalse(decoded['warnings'])
                    expected = Counter({(0,1,2,3,4):1, (0,1,2):1, (0,1):1, (3,):1})
                    if mask:
                        expected[(1,)] += 1
                    self.assertEqual(expected, spans(actual))
                    self.assertEqual([False, mask, False, False, False], [s['mask'] for s in actual])
                    self.assertTrue(report['nested_groups_verified'])

    def test_conflicting_group_parents_are_rejected(self):
        shapes = nested_shapes()
        shapes[3]['editor_group_path'] = [{'id':'c','name':'C'}, {'id':'b','name':'B'}]
        shapes[3]['editor_group_id'], shapes[3]['editor_group_name'] = 'b', 'B'
        with self.assertRaisesRegex(ValidationError, 'group'):
            compile_layout(project(shapes), 4267, NAMES)

    def test_placement_ids_cannot_collide_with_nested_source_ids(self):
        value=project(nested_shapes())
        value['placements'].append({**value['placements'][0],
            'id':'p-'+hashlib.sha256(b'a').hexdigest(),'x':100})
        sections=compile_layout(value,4267,NAMES)
        _,report=encode_experiment(SaveTemplate.read(template_bytes(),4267),sections)
        self.assertEqual(10,report['shape_count'])

    def test_interleaved_groups_keep_order_and_report_split(self):
        shapes = nested_shapes()
        shapes.append(copy.deepcopy(shapes[0]))
        template = SaveTemplate.read(template_bytes(), 4267)
        sections = compile_layout(project(shapes), 4267, NAMES)
        raw, report = encode_experiment(template, sections)
        actual, _ = decoder.clivery_to_layers(unwrap_bounded(raw), preserve_groups=True)
        self.assertEqual(6, len(actual))
        self.assertEqual([0,10,20,30,40,0], [round(s['data'][0]) for s in actual])
        self.assertTrue(any('interleaved' in warning for warning in report['warnings']))

    def test_transparent_native_leaf_and_mask_only_groups_roundtrip(self):
        template = SaveTemplate.read(template_bytes(), 4267)
        for mask in (False, True):
            leaf = shape()
            leaf['color'][3] = 0
            leaf['mask'], leaf['data'][6] = mask, int(mask)
            raw, report = encode_experiment(template, {'Left':[leaf]})
            strict_sections(raw)
            actual, decoded = decoder.clivery_to_layers(unwrap_bounded(raw), preserve_groups=True)
            self.assertFalse(decoded['warnings'])
            self.assertEqual(1, len(actual))
            self.assertEqual(mask, actual[0]['mask'])
            self.assertEqual(0, actual[0]['color_rgba'][3])

    def test_depth_limit_is_explicit_before_writing(self):
        leaf = shape()
        leaf['editor_group_path'] = [{'id':str(i),'name':str(i)} for i in range(64)]
        with self.assertRaisesRegex(ValidationError, '64-level'):
            compile_layout(project([leaf]), 4267, NAMES)

    def test_seeded_nested_mask_sequences_keep_native_grammar(self):
        template = SaveTemplate.read(template_bytes(),4267)
        for seed in range(24):
            rng=random.Random(seed)
            shapes=[]
            for index in range(40):
                item=shape(x=index-20,y=seed,sx=.2,sy=.3,angle=rng.randrange(360))
                item['mask']=rng.randrange(4)==0
                item['data'][6]=int(item['mask'])
                if index%7:
                    path=[{'id':f'root-{index//10}','name':'Root'}]
                    if index%3:
                        path.append({'id':f'child-{index//10}-{index//3}','name':'Child'})
                    item['editor_group_path']=path
                shapes.append(item)
            with self.subTest(seed=seed):
                sections=compile_layout(project(shapes,section=NAMES[seed%len(NAMES)]),4267,NAMES)
                raw,report=encode_experiment(template,sections)
                strict_sections(raw)
                SaveTemplate.read(raw,4267)
                actual,decoded=decoder.clivery_to_layers(unwrap_bounded(raw),preserve_groups=True)
                self.assertFalse(decoded['warnings'])
                self.assertEqual([s['mask'] for s in shapes],[s['mask'] for s in actual])
                self.assertTrue(report['nested_groups_verified'])

    def test_full_section_budget_reopens_with_nested_groups(self):
        shapes=[]
        for index in range(3000):
            item=shape(x=index%100-50,y=index//100-15,sx=.1,sy=.1)
            item['editor_group_path']=[{'id':str(index//100),'name':'Block'},
                                      {'id':'nested-'+str(index//10),'name':'Detail'}]
            shapes.append(item)
        sections=compile_layout(project(shapes),4267,NAMES)
        raw,report=encode_experiment(SaveTemplate.read(template_bytes(),4267),sections)
        strict_sections(raw)
        self.assertEqual(3000,report['shape_count'])
        self.assertTrue(report['nested_groups_verified'])
        self.assertEqual(3000,len(decoder.clivery_to_layers(SaveTemplate.read(raw,4267).payload)[0]))
        for item in shapes:
            item.pop('editor_group_path')
        canonical=project(shapes)
        canonical['vinyls'][0]['id']='save-Left'
        canonical['placements'][0].update(id='placement-Left',vinylId='save-Left')
        raw,report=encode_experiment(SaveTemplate.read(template_bytes(),4267),compile_layout(canonical,4267,NAMES))
        strict_sections(raw)
        actual,_=decoder.clivery_to_layers(SaveTemplate.read(raw,4267).payload,preserve_groups=True)
        self.assertEqual(3000,len(actual))
        self.assertFalse(spans(actual))

    def test_template_roundtrips_do_not_add_groups_or_change_finishes(self):
        template = SaveTemplate.read(template_bytes(), 4267)
        raw, _ = encode_experiment(template, compile_layout(project(nested_shapes(True)),4267,NAMES))
        expected, _ = decoder.clivery_to_layers(unwrap_bounded(raw),preserve_groups=True)
        expected_spans = spans(expected)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            header = build_destination_header(title='Nested fixture',creator_tag=b'TEST0001',
                creator_name='Fixture',car_id=4267,placement_count=5,now=datetime.now(timezone.utc))
            (root/'header').write_bytes(header)
            for _ in range(3):
                (root/'C_livery').write_bytes(raw)
                service = ExportService(root/'C_livery',{'car_id':4267,'model_code':'test'},NAMES)
                layout = service.template_layout()
                self.assertEqual(expected_spans,spans(layout['vinyls'][0]['shapes']))
                body = service.export(layout)
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    raw = archive.read('candidate/C_livery')
                    self.assertEqual(5, len(decoder.clivery_to_layers(unwrap_bounded(raw))[0]))
                reopened = SaveTemplate.read(raw,4267)
                self.assertEqual(template.payload[template.body_end+48:],reopened.payload[reopened.body_end+48:])
                actual,_ = decoder.clivery_to_layers(reopened.payload,preserve_groups=True)
                self.assertEqual(expected_spans,spans(actual))
                layout['vinyls'].clear()
                self.assertTrue(service.template_layout()['vinyls'])


if __name__ == '__main__':
    unittest.main()
