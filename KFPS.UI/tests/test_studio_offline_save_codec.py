"""Isolated native-save experiments: no installed game or active save access."""
import math
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/livery-studio/src"))
from kfps_livery_lab.prepare import load_baseline
load_baseline(ROOT)
from kfps_livery_lab.save_codec import SaveTemplate, compile_layout, encode_experiment
from kfps_livery_lab.model import ValidationError
from tools.cgroup import forza_source_decoder as decoder

NAMES = decoder.LIVERY_SECTION_NAMES


def shape(x=0, y=0, sx=1, sy=1, angle=0, skew=0):
    return {"type": 0x100065, "data": [x,y,sx,sy,angle,skew,0], "color": [255,64,16,255], "mask": False}


def template_bytes(car_id=4267):
    prefix = bytearray(51)
    prefix[:4] = b"vlrc"
    struct.pack_into("<I", prefix, 4, 2)
    struct.pack_into("<I", prefix, 16, car_id)
    prefix[26:30] = b"yrvl"
    struct.pack_into("<I", prefix, 30, 19)
    prefix[34:42] = b"TEST0001"
    identity = struct.pack("<4fB", 0,0,1,0,0)
    body = b""
    for i in range(11):
        body += struct.pack("<HH",1,1)+bytes(3)
        body += struct.pack("<BBH6f4B",0,2,101,0,0,0,1,1,0,16,64,255,255)
        body += b"\0" + (identity if i < 10 else b"")
    chunk = b"gyvl" + identity + body
    struct.pack_into("<I",prefix,47,len(chunk))
    payload = bytes(prefix)+chunk+b"yrvl"+struct.pack("<11I", *([1]*11))+b"opaque-material-tail"
    packed=zlib.compress(payload)
    return struct.pack("<II",len(packed),len(payload))+packed


def project(shapes=None, section="Left", **placement):
    return {"format":"kfps-livery-layout-v1", "vehicle":{"car_id":4267,"model_code":"test"},
            "vinyls":[{"id":"v", "name":"test", "shapes": shapes or [shape()]}],
            "placements":[{"id":"p","vinylId":"v","section":section,"x":0,"y":0,
                           "scaleX":1,"scaleY":1,"rotation":0,"opacity":1,"visible":True,**placement}]}


class SaveCodecTests(unittest.TestCase):
    def test_body_configuration_is_not_silently_lost_in_game_export(self):
        for configuration in ({'CarBody': 3761100}, {'RearWing': None}, None, [], False):
            value = project()
            value['vehicle_parts'] = configuration
            with self.subTest(configuration=configuration), self.assertRaises(ValidationError):
                compile_layout(value, 4267, NAMES)
        value = project()
        value['vehicle_parts'] = {}
        self.assertTrue(compile_layout(value, 4267, NAMES)['Left'])

    def template(self):
        return SaveTemplate.read(template_bytes(), 4267)

    def test_unchanged_bytes_are_preserved_exactly(self):
        source=template_bytes()
        self.assertEqual(SaveTemplate.read(source,4267).original,source)

    def test_empty_and_all_sections_roundtrip(self):
        template=self.template()
        for active in (NAMES, ["Left"], ["RightWindow"], ["Spoiler"]):
            with self.subTest(active=active):
                sections={name:([shape(8,-9)] if name in active else []) for name in NAMES}
                encoded,report=encode_experiment(template,sections)
                layers,decoded=decoder.clivery_to_layers(decoder.unwrap_forza_container_bytes(encoded,Path("C_livery")))
                self.assertEqual(len(layers),len(active))
                self.assertFalse(decoded["warnings"])
                self.assertTrue(report["independent_decode_verified"])
                for layer in layers:self.assertAlmostEqual(layer["data"][0],8,places=4)

    def test_prefix_tail_and_template_unchanged(self):
        template=self.template()
        encoded,_=encode_experiment(template,{"Left":[shape(12,7)]})
        raw=decoder.unwrap_forza_container_bytes(encoded,Path("C_livery"))
        self.assertEqual(raw[:47],template.payload[:47])
        self.assertTrue(raw.endswith(b"opaque-material-tail"))
        self.assertEqual(template.original,template_bytes())

    def test_affine_composition_and_opacity(self):
        value=project([shape(13,-17,.8,-1.3,33,.2)],x=44,y=-9,scaleX=1.5,scaleY=.6,rotation=71,opacity=.5)
        sections=compile_layout(value,4267,NAMES)
        out=sections["Left"][0]
        self.assertEqual(out["color"][3],128)
        angle=math.radians(71)
        self.assertAlmostEqual(out["data"][0],44+math.cos(angle)*1.5*13-math.sin(angle)*.6*-17)
        self.assertAlmostEqual(out["data"][1],-9+math.sin(angle)*1.5*13+math.cos(angle)*.6*-17)
        encode_experiment(self.template(),sections)

    def test_masks_are_not_silently_flattened(self):
        masked=shape();masked["mask"]=True;masked["data"][6]=1
        with self.assertRaisesRegex(ValidationError,"mask"):
            compile_layout(project([masked]),4267,NAMES)

    def test_group_opacity_and_clipped_source_fail_explicitly(self):
        with self.assertRaisesRegex(ValidationError,"group opacity"):
            compile_layout(project([shape(),shape()],opacity=.5),4267,NAMES)
        with self.assertRaisesRegex(ValidationError,"preview canvas"):
            compile_layout(project([shape(x=2000)]),4267,NAMES)

    def test_compiled_geometry_matches_the_native_preview_convention(self):
        import json_preview_renderer as renderer
        original=shape(12,-18,.7,-1.2,33,.4)
        value=project([original],x=44,y=-9,scaleX=1.5,scaleY=.6,rotation=71)
        compiled=compile_layout(value,4267,NAMES)["Left"][0]
        points=[(-64,-64),(64,-64),(64,64),(-64,64),(0,13)]
        source=renderer._transform_resource_polygon(points,original["data"])
        actual=renderer._transform_resource_polygon(points,compiled["data"])
        c=math.cos(math.radians(71));s=math.sin(math.radians(71))
        for (x,y),(ax,ay) in zip(source,actual):
            self.assertAlmostEqual(ax,44+c*1.5*x-s*.6*y,places=9)
            self.assertAlmostEqual(ay,-9+s*1.5*x+c*.6*y,places=9)

    def test_bad_inputs_and_limits(self):
        for value in (project(section="Unknown"),project(x=float("nan")),project(scaleX=0),project(opacity=2),project(skew=4.01),project(skew=float("nan")),project(skew=True)):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):compile_layout(value,4267,NAMES)
        with self.assertRaises(ValidationError):SaveTemplate.read(template_bytes(),3761)
        with self.assertRaises(ValidationError):SaveTemplate.read(template_bytes()[:-5],4267)
        with self.assertRaises(ValidationError):encode_experiment(self.template(),{"Front":[shape()]*1001})

    def test_placement_skew_matches_preview_and_native_roundtrip(self):
        import json_preview_renderer as renderer
        original=shape(12,-18,.7,-1.2,33,.4)
        points=[(-64,-64),(64,-64),(64,64),(-64,64),(0,13)]
        source=renderer._transform_resource_polygon(points,original["data"])
        for skew in (-4,-.5,0,.7,4):
            with self.subTest(skew=skew):
                value=project([original],x=44,y=-9,scaleX=1.5,scaleY=.6,rotation=71,skew=skew)
                sections=compile_layout(value,4267,NAMES)
                actual=renderer._transform_resource_polygon(points,sections["Left"][0]["data"])
                c=math.cos(math.radians(71));s=math.sin(math.radians(71))
                for (x,y),(ax,ay) in zip(source,actual):
                    self.assertAlmostEqual(ax,44+c*1.5*x+(c*skew-s)*.6*y,places=9)
                    self.assertAlmostEqual(ay,-9+s*1.5*x+(s*skew+c)*.6*y,places=9)
                encode_experiment(self.template(),sections)

    def test_hidden_shapes_are_omitted_and_empty_rejected(self):
        with self.assertRaisesRegex(ValidationError,"visible"):
            compile_layout(project(visible=False),4267,NAMES)

    def test_unowned_rejected(self):
        template=self.template();raw=bytearray(template.payload);struct.pack_into("<I",raw,8,1)
        packed=zlib.compress(raw);source=struct.pack("<II",len(packed),len(raw))+packed
        with self.assertRaisesRegex(ValidationError,"owned"):SaveTemplate.read(source,4267)


if __name__ == "__main__":unittest.main()
