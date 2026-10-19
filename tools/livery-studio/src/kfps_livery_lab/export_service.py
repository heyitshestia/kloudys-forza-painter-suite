"""Read-only template loading and in-memory, explicitly experimental ZIP output."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import zipfile

from .model import ValidationError
from .save_codec import SaveTemplate, MAX_PAYLOAD, NAMES, compile_layout, encode_experiment


class ExportService:
    def __init__(self, path, vehicle, sections):
        self.vehicle=vehicle
        self.sections=tuple(sections)
        path=Path(path).resolve(strict=True)
        if path.suffix.lower()==".kfpslivery":
            with zipfile.ZipFile(io.BytesIO(self._read_local(path,256*1024*1024))) as archive:
                names=archive.namelist()
                if len(names)>256 or len(set(names))!=len(names):raise ValidationError("Invalid template package inventory.")
                raw=self._member(archive,"source/fh6/C_livery",MAX_PAYLOAD)
                header=self._member(archive,"source/fh6/header",65536)
        else:
            if path.name!="C_livery":raise ValidationError("Choose a C_livery export or .kfpslivery package.")
            header_path=path.parent/"header"
            raw=self._read_local(path,MAX_PAYLOAD);header=self._read_local(header_path,65536)
        self.template=SaveTemplate.read(raw,vehicle["car_id"])
        from tools.livery.fh6_save_installer import parse_fh6_header
        self.header=parse_fh6_header(header)
        if (self.header.car_id!=vehicle["car_id"] or self.header.creator_tag!=self.template.payload[34:42]
                or self.header.record_kind not in ("saved","base")):
            raise ValidationError("Template header identity or saved-record kind does not match.")
        from tools.cgroup.forza_source_decoder import clivery_to_layers, layers_to_kfps_json_layers
        layers,report=clivery_to_layers(self.template.payload)
        self.count=len(layers)
        if self.header.type_value!=self.count:
            raise ValidationError("Template header and artwork placement counts do not match.")
        self.layout={"format":"kfps-livery-layout-v1","vehicle":{key:vehicle[key] for key in ("car_id","model_code")},
                     "vinyls":[],"placements":[]}
        self.layout_error=""
        for name in NAMES:
            items=[layer for layer in layers if layer["section"]==name]
            if not items:continue
            if name not in self.sections or len(items)>3000 or any(layer["is_raster_logo"] for layer in items):
                self.layout_error="This save has raster decals or an unsupported section; its artwork cannot be opened exactly."
                break
            shapes,warnings=layers_to_kfps_json_layers(items,game="fh6")
            if warnings:
                self.layout_error="The template contains ambiguous shape identities."
                break
            source_id=f"save-{name}"
            self.layout["vinyls"].append({"id":source_id,"name":f"Saved {name}","shapes":shapes})
            self.layout["placements"].append({"id":f"placement-{name}","vinylId":source_id,"section":name,
                                              "x":0,"y":0,"scaleX":1,"scaleY":1,"rotation":0,"opacity":1,"visible":True})
        self.template_hash=hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _read_local(path,maximum):
        if path.stat().st_size>maximum:raise ValidationError("Template file is too large.")
        with path.open("rb") as stream:
            body=stream.read(maximum+1)
        if not 0<len(body)<=maximum:raise ValidationError("Template file is empty or grew beyond its size limit.")
        return body

    @staticmethod
    def _member(archive,name,maximum):
        info=archive.getinfo(name)
        if not 0<info.file_size<=maximum:raise ValidationError("Template package member is empty or too large.")
        with archive.open(info) as stream:
            body=stream.read(maximum+1)
        if len(body)!=info.file_size:raise ValidationError("Template package member size mismatch.")
        return body

    def capabilities(self):
        return {"enabled":True,"reason":"Experimental output only; game acceptance is unverified.",
                "template_shape_count":self.count,"template_layout_available":not self.layout_error,
                "template_layout_reason":self.layout_error}

    def template_layout(self):
        if self.layout_error:raise ValidationError(self.layout_error)
        return self.layout

    def export(self,project):
        sections=compile_layout(project,self.vehicle["car_id"],self.sections)
        raw,report=encode_experiment(self.template,sections)
        from tools.livery.fh6_save_installer import build_destination_header,parse_fh6_header
        header=build_destination_header(title="KFPS Experimental Layout",creator_tag=self.header.creator_tag,
                                        creator_name=self.header.creator_name,car_id=self.vehicle["car_id"],
                                        placement_count=report["shape_count"],now=datetime.now(timezone.utc))
        checked=parse_fh6_header(header)
        if checked.type_value!=report["shape_count"] or checked.record_kind!="saved":
            raise ValidationError("Experimental header failed independent verification.")
        report.update({"template_sha256":self.template_hash,"source_sha256":hashlib.sha256(raw).hexdigest(),
                       "header_sha256":hashlib.sha256(header).hexdigest(),"installed":False,
                       "limits":{"masks":False,"raster_decals":False,"same_car_only":True,
                                 "multi_shape_group_opacity":False,"clipped_source_geometry":False},
                       "warning":"Not game-validated. Do not treat this as a released KFPS share package."})
        members={"experiment.json":json.dumps(report,indent=2).encode(),
                 "README.txt":b"EXPERIMENTAL - GAME ACCEPTANCE NOT VERIFIED\n\nThis is NOT a .kfpslivery sharing package. Nothing was installed.\nC_livery and header are candidates for isolated compatibility testing only.\nKeep your original game saves and backups. Material data comes from the supplied\nsame-car template; preview materials are not game-identical. No thumbnail is\nincluded because the old template thumbnail would misrepresent the edited art.\nSection caps follow FLS: Top/Left/Right 3000, all other sections 1000.\nThese are fallback authoring limits, not verified per-car rules. Paintable\nsurfaces vary by car and fitted parts; check the result in-game.\n",
                 "candidate/C_livery":raw,"candidate/header":header,
                 "layout.kfps-layout.json":json.dumps(project,ensure_ascii=False,allow_nan=False).encode("utf-8")}
        for name,shapes in sections.items():
            if shapes:members[f"sections/{name}.json"]=json.dumps({"shapes":shapes},allow_nan=False).encode()
        result=io.BytesIO()
        with zipfile.ZipFile(result,"w",compression=zipfile.ZIP_DEFLATED) as archive:
            for name,body in members.items():archive.writestr(name,body)
        output=result.getvalue()
        with zipfile.ZipFile(io.BytesIO(output)) as archive:
            if archive.testzip() or archive.read("candidate/C_livery")!=raw or archive.read("candidate/header")!=header:
                raise ValidationError("Experimental ZIP failed reopen verification.")
        return output
