import copy
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_studio_offline_save_codec import project, shape, NAMES
from kfps_livery_lab.save_codec import compile_layout, compile_section_vinyl
from kfps_livery_lab.model import ValidationError, NativeVinylRenderer


class SectionExportTests(unittest.TestCase):
    def test_section_export_ignores_preview_part_configuration_but_game_export_does_not(self):
        value=project(x=83,y=-42,skew=.5,rotation=32)
        expected=compile_layout(value,4267,NAMES)["Left"]
        value["vehicle_parts"]={"CarBody":3761100}
        result=compile_section_vinyl(value,4267,NAMES,"Left")
        self.assertEqual([{key:item for key,item in s.items() if not key.startswith("editor_group_")}
                          for s in result["shapes"]],expected)
        self.assertTrue(all(s["editor_group_id"]=="studio-p" for s in result["shapes"]))
        with self.assertRaises(ValidationError):compile_layout(value,4267,NAMES)

    def test_front_section_uses_native_vinyl_limit_not_livery_cap(self):
        value=project([shape()]*1100,section="Front")
        self.assertEqual(len(compile_section_vinyl(value,4267,NAMES,"Front")["shapes"]),1100)
        with self.assertRaises(ValidationError):compile_layout(value,4267,NAMES)

    def test_top_section_uses_fls_3000_shape_fallback(self):
        value=project([shape()]*3000,section="Top")
        self.assertEqual(len(compile_layout(value,4267,NAMES)["Top"]),3000)
        self.assertEqual(len(compile_section_vinyl(value,4267,NAMES,"Top")["shapes"]),3000)

    def test_isolated_mask_is_retained_and_reopens_in_native_renderer(self):
        masked=shape(sx=.3,sy=.3);masked["mask"]=True;masked["data"][6]=1
        value=project([shape(),masked],skew=.7,rotation=40)
        result=compile_section_vinyl(value,4267,NAMES,"Left")
        self.assertTrue(result["shapes"][1]["mask"])
        self.assertEqual(result["shapes"][1]["data"][6],1)
        self.assertTrue(NativeVinylRenderer()(result)["png"].startswith("data:image/png;base64,"))
        self.assertTrue(compile_layout(value,4267,NAMES)["Left"][1]["mask"])
        other=copy.deepcopy(value["placements"][0]);other["id"]="other";value["placements"].append(other)
        combined=compile_section_vinyl(value,4267,NAMES,"Left")
        self.assertEqual([False,True,False,True],[s["mask"] for s in combined["shapes"]])

    def test_other_sections_are_not_merged_and_input_is_unchanged(self):
        value=project();other=copy.deepcopy(value["placements"][0]);other.update(id="other",section="Top",x=200)
        value["placements"].append(other);before=copy.deepcopy(value)
        self.assertEqual(len(compile_section_vinyl(value,4267,NAMES,"Left")["shapes"]),1)
        self.assertEqual(value,before)
        with self.assertRaisesRegex(ValidationError,"visible"):compile_section_vinyl(value,4267,NAMES,"Right")
        with self.assertRaisesRegex(ValidationError,"valid car section"):compile_section_vinyl(value,4267,NAMES,"../Top")

    def test_placements_stay_separate_groups_through_offline_roundtrip(self):
        from tools.cgroup.vinyl_document import encode_vinyl_document
        from tools.cgroup.forza_source_decoder import cgroup_to_layers
        value=project([shape(),shape(x=20)])
        other=copy.deepcopy(value["placements"][0]);other.update(id="other",x=100)
        value["placements"].append(other)
        document=compile_section_vinyl(value,4267,NAMES,"Left")
        self.assertEqual(["studio-p"]*2+["studio-other"]*2,
                         [s["editor_group_id"] for s in document["shapes"]])
        for game in ("fh4","fh5","fh6","fm8"):
            payload,report=encode_vinyl_document(document,game)
            layers,decoded=cgroup_to_layers(payload,game)
            self.assertEqual(4,len(layers));self.assertEqual(2,report["groups"])
            self.assertEqual([],decoded["warnings"])


if __name__=="__main__":unittest.main()
