"""Section-scoped masks: native bytes, paint order and real export API."""
import copy
from datetime import datetime, timezone
import http.client
import io
import json
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_studio_offline_save_codec import ROOT, NAMES, project, shape, template_bytes, decoder
from kfps_livery_lab.save_codec import SaveTemplate, compile_layout, compile_section_vinyl, encode_experiment, unwrap_bounded
from kfps_livery_lab.model import ValidationError
from kfps_livery_lab.export_service import ExportService
from tools.cgroup.vinyl_document import encode_vinyl_document
from tools.livery.fh6_save_installer import build_destination_header, parse_fh6_header


def masked(**kwargs):
    result=shape(**kwargs)
    result['mask']=True
    result['data'][6]=1
    return result


def overlap_project(section='Left'):
    value=project([shape(sx=3,sy=3)],section=section)
    value['vinyls'][0]['shapes'][0]['color']=[0,0,0,255]
    ring=shape(sx=2,sy=2)
    ring['color']=[255,255,255,255]
    value['vinyls'].append({'id':'ring','name':'Masked ring','shapes':[ring,masked(sx=.6,sy=.6)]})
    value['placements'].append({**value['placements'][0],'id':'ring','vinylId':'ring'})
    return value


def strict_sections(raw):
    """Counted native grammar, no scanning/resynchronization or decoder guesses."""
    payload=unwrap_bounded(raw)
    end=51+struct.unpack_from('<I',payload,47)[0]
    if payload[end:end+4]!=b'yrvl':
        raise ValueError('Invalid artwork length')
    counts=struct.unpack_from('<11I',payload,end+4)
    body=payload[72:end]
    pos=0

    def take(n):
        nonlocal pos
        result=body[pos:pos+n]
        if len(result)!=n:
            raise ValueError('Truncated artwork')
        pos+=n
        return result

    def group(nested=False,depth=0):
        if depth>64:
            raise ValueError('Excessive depth')
        marker=None
        if nested:
            if take(1)[0] not in (0,1):
                raise ValueError('Missing group placement state')
            if struct.unpack('<4f',take(16))!=(0,0,1,0):
                raise ValueError('Nonidentity group frame')
            marker=take(1)[0]
            if marker not in (0x20,0x60):
                raise ValueError('Invalid counted group marker')
        count,blocks=struct.unpack('<HH',take(4))
        if blocks!=(count+7)//8 or take(2)!=bytes(2):
            raise ValueError('Invalid bitmap/control header')
        bitmap=take(blocks)
        children=[]
        for i in range(count):
            if bitmap[i//8]&(1<<(i%8)):
                children.append(group(True,depth+1))
            else:
                lead=take(1)[0]
                if lead in (0,1):
                    lead=take(1)[0]
                if lead!=2:
                    raise ValueError('Missing shape record')
                children.append({'leaf':take(30)})
        return {'marker':marker,'children':children}

    def leaves(node):
        return sum(1 if 'leaf' in child else leaves(child) for child in node['children'])

    roots=[]
    for i,count in enumerate(counts):
        root=group()
        if leaves(root)!=count:
            raise ValueError('Leaf count mismatch')
        if count and take(1)[0] not in (0,1):
            raise ValueError('Invalid section terminal mask')
        if i<10:
            take(17)
        roots.append(root)
    if pos!=len(body):
        raise ValueError('Trailing unparsed bytes')
    return roots


class StudioMaskExportTests(unittest.TestCase):
    def test_overlapping_vinyls_export_in_all_sections_and_reopen(self):
        template=SaveTemplate.read(template_bytes(),4267)
        for section in NAMES:
            with self.subTest(section=section):
                value=overlap_project(section)
                original=copy.deepcopy(value)
                sections=compile_layout(value,4267,NAMES)
                raw,report=encode_experiment(template,sections)
                roots=strict_sections(raw)
                self.assertEqual(2,len(roots[NAMES.index(section)]['children']))
                decoded,details=decoder.clivery_to_layers(unwrap_bounded(raw),preserve_groups=True)
                self.assertEqual([],details['warnings'])
                self.assertEqual([False,False,True],[s['mask'] for s in decoded])
                self.assertNotEqual(decoded[0]['editor_group_path'][0],decoded[1]['editor_group_path'][0])
                self.assertEqual(1,report['mask_count'])
                self.assertFalse(report['game_acceptance_verified'])
                self.assertEqual(raw,SaveTemplate.read(raw,4267).original)
                self.assertEqual(original,value)
                document=compile_section_vinyl(value,4267,NAMES,section)
                for game in ('fh4','fh5','fh6','fm8'):
                    native,_=encode_vinyl_document(document,game)
                    layers,check=decoder.cgroup_to_layers(native,game)
                    self.assertEqual([],check['warnings'])
                    self.assertEqual([False,False,True],[s['mask'] for s in layers])

    def test_first_middle_last_consecutive_and_mask_only_shapes(self):
        template=SaveTemplate.read(template_bytes(),4267)
        for flags in ((1,),(1,0),(0,1),(0,1,0),(1,1,0),(0,1,1),(1,0,1,0,1)):
            for alpha in (0,128,255):
                with self.subTest(flags=flags,alpha=alpha):
                    shapes=[masked(x=i*3) if flag else shape(x=i*3) for i,flag in enumerate(flags)]
                    for s in shapes:
                        if s['mask']:s['color']=[55,123,77,alpha]
                    compiled=compile_layout(project(shapes),4267,NAMES)
                    raw,_=encode_experiment(template,compiled)
                    strict_sections(raw)
                    actual,_=decoder.clivery_to_layers(unwrap_bounded(raw))
                    self.assertEqual(list(map(bool,flags)),[s['mask'] for s in actual])
                    self.assertEqual([s['color'] for s in shapes],[s['color_rgba'] for s in actual])

    def test_adjacent_populated_sections_and_bitmap_boundaries(self):
        template=SaveTemplate.read(template_bytes(),4267)
        for count in (1,7,8,9,255,256,1000,3000):
            value=project([masked(sx=.1,sy=.1) if i%3 else shape(sx=.1,sy=.1)
                           for i in range(count)],section='Top')
            if count==1:value['vinyls'][0]['shapes'][0]=masked()
            sections=compile_layout(value,4267,NAMES)
            if count<=1000:
                sections={name:copy.deepcopy(sections['Top']) for name in NAMES}
            with self.subTest(count=count):
                raw,report=encode_experiment(template,sections)
                strict_sections(raw)
                self.assertEqual(sum(len(s) for s in sections.values()),report['shape_count'])
                SaveTemplate.read(raw,4267)

    def test_random_affine_masks_keep_effective_matrices(self):
        rng=random.Random(1022)
        template=SaveTemplate.read(template_bytes(),4267)
        for i in range(80):
            shapes=[shape(),masked(sx=rng.choice([-1,1])*.3,sy=.5,
                                   angle=rng.uniform(-180,180),skew=rng.uniform(-1,1))]
            value=project(shapes,section=NAMES[i%11],x=rng.uniform(-600,600),y=rng.uniform(-200,200),
                          rotation=rng.uniform(-180,180),scaleX=rng.uniform(.2,2),
                          scaleY=rng.uniform(.2,2),skew=rng.uniform(-1,1))
            raw,_=encode_experiment(template,compile_layout(value,4267,NAMES))
            strict_sections(raw)  # encoder separately compares effective matrices

    def test_other_safety_guards_and_no_source_changes(self):
        for mutation in ('opacity','clipped','parts','empty'):
            value=overlap_project()
            if mutation=='opacity':value['placements'][1]['opacity']=.5
            if mutation=='clipped':value['vinyls'][1]['shapes'][1]['data'][0]=2000
            if mutation=='parts':value['vehicle_parts']={'CarBody':123}
            if mutation=='empty':value['placements']=[]
            before=copy.deepcopy(value)
            with self.subTest(mutation=mutation),self.assertRaises(ValidationError):
                compile_layout(value,4267,NAMES)
            self.assertEqual(value,before)

    def test_hidden_masks_do_not_erase_and_later_paint_stays_above(self):
        value=overlap_project()
        value['placements'][1]['visible']=False
        self.assertEqual([False],[s['mask'] for s in compile_section_vinyl(value,4267,NAMES,'Left')['shapes']])
        value['placements'][1]['visible']=True
        value['placements'].reverse()
        self.assertEqual([False,True,False],[s['mask'] for s in compile_section_vinyl(value,4267,NAMES,'Left')['shapes']])


class StudioMaskApiTests(unittest.TestCase):
    def test_real_routes_zip_header_preview_and_saved_layout(self):
        from kfps_livery_lab.server import LiveryLabServer
        run=ROOT/'tools/livery-studio/runs/masks-20261022/api-tests'
        run.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=run) as tmp:
            root=Path(tmp)
            raw=template_bytes()
            header=build_destination_header(title='Synthetic mask template',creator_tag=b'TEST0001',
                                            creator_name='Synthetic',car_id=4267,placement_count=11,
                                            now=datetime(2026,10,22,tzinfo=timezone.utc))
            (root/'C_livery').write_bytes(raw)
            (root/'header').write_bytes(header)
            vehicle={'car_id':4267,'model_code':'test'}
            exporter=ExportService(root/'C_livery',vehicle,NAMES)
            prepared={'files':{'mesh':'mesh.glb','paint':'paint.png','masks':['m0.png','m1.png','m2.png']},
                      'manifest':{'inspection_runtime':{'local_mesh':True}},
                      'editor_config':{'vehicle':vehicle,'paint_size':[2048,1024],
                                       'sections':[{'section':name} for name in NAMES]}}
            for name in ('mesh.glb','paint.png','m0.png','m1.png','m2.png'):
                (root/name).write_bytes(b'synthetic route fixture')
            with patch('kfps_livery_lab.diagnostics.DEFAULT_ROOT',root/'diagnostics'):
                server=LiveryLabServer(prepared,root,root/'host',export_service=exporter,
                                       session_data_root=root/'session')
            try:
                server.start()
                def post(route,value):
                    connection=http.client.HTTPConnection('127.0.0.1',server.httpd.server_port,timeout=30)
                    try:
                        connection.request('POST',f'/{server.token}/api/{route}',json.dumps(value),
                                           {'Content-Type':'application/json'})
                        response=connection.getresponse()
                        return response.status,response.read()
                    finally:connection.close()
                value=overlap_project()
                status,body=post('export-section',{'project':value,'section':'Left'})
                self.assertEqual(200,status,body)
                self.assertEqual(3,len(json.loads(body)['shapes']))
                status,body=post('export-experiment',value)
                self.assertEqual(200,status,body)
                with zipfile.ZipFile(io.BytesIO(body)) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertEqual(value,json.loads(archive.read('layout.kfps-layout.json')))
                    report=json.loads(archive.read('experiment.json'))
                    self.assertTrue(report['limits']['cross_placement_masks'])
                    self.assertFalse(report['installed'])
                    candidate=archive.read('candidate/C_livery')
                    strict_sections(candidate)
                    self.assertEqual(3,parse_fh6_header(archive.read('candidate/header')).type_value)
                    self.assertEqual(candidate,SaveTemplate.read(candidate,4267).original)
                for quality in ('fast','balanced','sharp'):
                    status,body=post('render-vinyl',{'shapes':value['vinyls'][1]['shapes'],'preview_quality':quality})
                    self.assertEqual(200,status,body[:1000])
                    result=json.loads(body)
                    self.assertEqual('ordered-section-v1',result['mask_compositing'])
                    self.assertTrue(result['mask_coverage_png'].startswith('data:image/png;base64,'))
                invalid=copy.deepcopy(value)
                invalid['placements'][1]['opacity']=.5
                self.assertEqual(422,post('export-experiment',invalid)[0])
                self.assertEqual(200,post('export-experiment',value)[0])
                self.assertEqual(raw,(root/'C_livery').read_bytes())
                self.assertEqual(header,(root/'header').read_bytes())
            finally:server.close()


if __name__=='__main__':unittest.main(verbosity=2)
