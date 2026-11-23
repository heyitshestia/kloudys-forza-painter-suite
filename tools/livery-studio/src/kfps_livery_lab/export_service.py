"""Build artwork exports without modifying the source template or game saves."""
from datetime import datetime, timezone
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import zipfile

from .model import ValidationError
from .save_codec import SaveTemplate, MAX_PAYLOAD, NAMES, compile_layout, encode_experiment


class ExportService:
    def __init__(self, path, vehicle, sections):
        self.vehicle=vehicle
        self.sections=tuple(sections)
        path=Path(path).absolute()
        if path.suffix.lower()==".kfpslivery":
            with zipfile.ZipFile(io.BytesIO(self._read_local(path,256*1024*1024))) as archive:
                names=archive.namelist()
                if len(names)>256 or len(set(names))!=len(names):raise ValidationError("Invalid template package inventory.")
                raw=self._member(archive,"source/fh6/C_livery",MAX_PAYLOAD)
                header=self._member(archive,"source/fh6/header",65536)
        else:
            if path.name!="C_livery":raise ValidationError("Choose a C_livery export or .kfpslivery package.")
            from .package_handoff import _read_save_pair
            try:
                raw,header=_read_save_pair(path)
            except OSError:
                raise ValidationError('The template artwork or header is missing or unreadable. Retry with a saved copy.') from None
        self.template=SaveTemplate.read(raw,vehicle["car_id"])
        from tools.livery.fh6_save_installer import parse_fh6_header
        self.header=parse_fh6_header(header)
        if (self.header.car_id!=vehicle["car_id"] or self.header.creator_tag!=self.template.payload[34:42]
                or self.header.record_kind not in ("saved","base")):
            raise ValidationError("Template header identity or saved-record kind does not match.")
        from tools.cgroup.forza_source_decoder import clivery_to_layers, layers_to_kfps_json_layers
        flat,flat_report=clivery_to_layers(self.template.payload)
        layers,report=clivery_to_layers(self.template.payload,preserve_groups=True)
        if report['warnings'] or flat_report['warnings'] or len(layers)!=len(flat):
            raise ValidationError('Template artwork did not decode completely with its groups.')
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
            flat_shapes,flat_warnings=layers_to_kfps_json_layers([item for item in flat if item['section']==name],game='fh6')
            without_groups=[{key:value for key,value in shape.items() if not key.startswith('editor_group_')} for shape in shapes]
            if warnings or flat_warnings or without_groups!=flat_shapes:
                self.layout_error="The template contains ambiguous shape identities."
                break
            source_id=f"save-{name}"
            self.layout["vinyls"].append({"id":source_id,"name":f"Saved {name}","shapes":shapes})
            self.layout["placements"].append({"id":f"placement-{name}","vinylId":source_id,"section":name,
                                              "x":0,"y":0,"scaleX":1,"scaleY":1,"rotation":0,"opacity":1,"visible":True})
        self.template_hash=hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _read_local(path,maximum):
        from .package_handoff import _check_source, _stamp
        _check_source(path)
        with path.open("rb") as stream:
            before=os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=maximum:
                raise ValidationError('Choose a regular template package within its size limit.')
            body=stream.read(maximum+1)
            _check_source(path)
            if (_stamp(before)!=_stamp(os.fstat(stream.fileno()))
                    or _stamp(before)!=_stamp(path.stat()) or len(body)!=before.st_size):
                raise ValidationError('The template package changed while reading. Retry with a saved copy.')
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
        return copy.deepcopy(self.layout)

    def _candidate(self, project, title):
        sections=compile_layout(project,self.vehicle["car_id"],self.sections)
        raw,report=encode_experiment(self.template,sections)
        from tools.livery.fh6_save_installer import build_destination_header,parse_fh6_header
        header=build_destination_header(title=title,creator_tag=self.header.creator_tag,
                                        creator_name=self.header.creator_name,car_id=self.vehicle["car_id"],
                                        placement_count=report["shape_count"],now=datetime.now(timezone.utc))
        checked=parse_fh6_header(header)
        if checked.type_value!=report["shape_count"] or checked.record_kind!="saved":
            raise ValidationError("Experimental header failed independent verification.")
        return sections, raw, header, report

    def export_package(self, project, title, *, game_folder=None, vehicle_index_cache=None):
        from tools.livery.package import FullLiveryPackageError, create_full_livery_package
        if not isinstance(title, str) or any(not c.isprintable() for c in title):
            raise ValidationError("Enter a livery name of up to 64 characters.")
        title = " ".join(title.split())
        if not title or len(title.encode("utf-16le")) > 128:
            raise ValidationError("Enter a livery name of up to 64 characters.")
        _, raw, header, _ = self._candidate(project, title)
        # Only the native candidate pair is input to the regular Garage packager.
        with tempfile.TemporaryDirectory(prefix="kfps-studio-export-") as folder:
            root = Path(folder)
            source = root / "C_livery"
            source.write_bytes(raw)
            (root / "header").write_bytes(header)
            output = root / "design.kfpslivery"
            try:
                manifest = create_full_livery_package(
                    source, output, title_override=title, model_code_override=self.vehicle["model_code"],
                    game_folder=game_folder, vehicle_index_cache=vehicle_index_cache)
            except FullLiveryPackageError as exc:
                raise ValidationError(str(exc)) from exc
            vehicle = manifest["vehicle"]
            if (vehicle["car_id"] != self.vehicle["car_id"] or
                    vehicle["model_code"].casefold() != self.vehicle["model_code"].casefold()):
                raise ValidationError("The package does not match the current car.")
            return output.read_bytes()

    def export(self,project):
        sections, raw, header, report = self._candidate(project, "KFPS Experimental Layout")
        report.update({"template_sha256":self.template_hash,"source_sha256":hashlib.sha256(raw).hexdigest(),
                       "header_sha256":hashlib.sha256(header).hexdigest(),"installed":False,
                       "limits":{"masks":True,"cross_placement_masks":True,
                                 "raster_decals":False,"same_car_only":True,
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
