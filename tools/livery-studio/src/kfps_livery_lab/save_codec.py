"""Constrained, experimental FH6 artwork-stream writer; never installs a save.

Opaque envelope/material bytes are preserved from an owned, same-car export.
This is decoder-verified research output, not a claim of game acceptance.
"""
from dataclasses import dataclass
import math
from pathlib import Path
import struct
import zlib

from .model import ValidationError, validate_shapes, _number

MAX_PAYLOAD = 16 * 1024 * 1024
NAMES = ("Front", "Back", "Top", "Left", "Right", "Spoiler", "FrontWindshield",
         "BackWindshield", "TopWindow", "LeftWindow", "RightWindow")
# User-approved FLS fallback, not verified per-car or fitted-part permissions.
CAPS = {name: 3000 if name in ("Top", "Left", "Right") else 1000 for name in NAMES}


def section_limit_policy():
    return {"id": "fls-section-caps-v1", "section_caps": dict(CAPS),
            "per_car_verified": False, "surface_compatibility": "check_in_game",
            "source_revision": "371512079244cda83b12c82ed45df00251be68fd"}


def unwrap_bounded(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_PAYLOAD:
        raise ValidationError("Save container exceeds the experimental size limit.")
    if raw.startswith(b"vlrc"):
        return raw
    offset = 0
    chunks = []
    total = 0
    while offset < len(raw):
        if offset + 8 > len(raw) or len(chunks) >= 128:
            raise ValidationError("Invalid save compression framing.")
        packed, unpacked = struct.unpack_from("<II", raw, offset)
        offset += 8
        if not packed or not unpacked or offset + packed > len(raw) or total + unpacked > MAX_PAYLOAD:
            raise ValidationError("Invalid or excessive save compression sizes.")
        try:
            stream = zlib.decompressobj()
            data = stream.decompress(raw[offset:offset+packed], unpacked+1)
        except zlib.error as exc:
            raise ValidationError("Unreadable compressed save.") from exc
        if len(data) != unpacked or not stream.eof or stream.unused_data or stream.unconsumed_tail:
            raise ValidationError("Save compression size or stream does not match.")
        chunks.append(data)
        total += unpacked
        offset += packed
    return b"".join(chunks)


@dataclass(frozen=True)
class SaveTemplate:
    original: bytes
    payload: bytes
    body_start: int
    body_end: int
    gyvl: int
    transitions: tuple[bytes, ...]
    car_id: int

    @classmethod
    def read(cls, raw, car_id):
        from tools.cgroup import forza_source_decoder as decoder
        try:
            return cls._read(raw, car_id)
        except ValidationError:
            raise
        except (decoder.DecodeError, RecursionError, struct.error, ValueError, IndexError) as exc:
            raise ValidationError("The save template is malformed or its group nesting is unsupported.") from exc

    @classmethod
    def _read(cls, raw, car_id):
        from tools.cgroup import forza_source_decoder as decoder
        payload = unwrap_bounded(raw)
        if len(payload) < 120 or payload[:4] != b"vlrc" or struct.unpack_from("<I",payload,4)[0] != 2:
            raise ValidationError("Only the observed FH6 version-2 save envelope is supported.")
        if struct.unpack_from("<I",payload,16)[0] != car_id:
            raise ValidationError("The save template belongs to a different car.")
        body, counts, meta = decoder.extract_livery_payload(payload)
        start, end, gyvl = meta["body_start"],meta["body_end"],meta["gyvl_offset"]
        if (gyvl != 51 or payload[26:30] != b"yrvl" or struct.unpack_from("<I",payload,30)[0] != 19
                or payload[end:end+4] != b"yrvl" or end+48 > len(payload)
                or struct.unpack_from("<I",payload,gyvl-4)[0] != end-gyvl):
            raise ValidationError("Unrecognized save chunk framing; no file was changed.")
        if not 0 < sum(counts) <= 25000:
            raise ValidationError("Unsupported save placement counts.")
        if payload[gyvl+4:start] != struct.pack("<4fB",0,0,1,0,0):
            raise ValidationError("The template uses an unsupported root transform.")
        privacy = decoder.inspect_clivery_privacy(payload)
        if not privacy["source_owned"] or privacy["contains_foreign_groups"]:
            raise ValidationError("An owned save without foreign groups is required.")
        layers, report = decoder.clivery_to_layers(payload)
        if report["warnings"] or len(layers) != sum(counts):
            raise ValidationError("Save template did not decode completely.")
        transitions = []
        pos = 0
        for slot,name in enumerate(NAMES):
            items = [layer for layer in layers if layer["section"] == name]
            if items:
                if items[0]["section_start"] != pos:
                    raise ValidationError("Unrecognized section boundary.")
                leaf_end = max(layer["source_offset"] + (31 if layer["marker_hex"] == "02" else 32) for layer in items)
                if body[leaf_end:leaf_end+1] not in (b"\0",b"\1"):
                    raise ValidationError("Unrecognized terminal shape state.")
                pos = leaf_end+1
            else:
                if body[pos:pos+6] != bytes(6):
                    raise ValidationError("Unrecognized empty section framing.")
                pos += 6
            if slot < 10:
                transition=body[pos:pos+17]
                if len(transition)!=17 or transition[-1]!=0:
                    raise ValidationError("Unrecognized inter-section transform.")
                values=struct.unpack("<4f",transition[:16])
                if not all(math.isfinite(v) for v in values):
                    raise ValidationError("Invalid inter-section transform.")
                transitions.append(transition)
                pos += 17
        if pos != len(body):
            raise ValidationError("Unrecognized trailing artwork data.")
        return cls(raw,payload,start,end,gyvl,tuple(transitions),car_id)


def _resolve(kind):
    from tools.cgroup.forza_source_decoder import canonical_resource_for_word
    return canonical_resource_for_word(kind-0x100000)


def _bounded(value,low,high,label):
    number=_number(value,label)
    if not low <= number <= high:
        raise ValidationError(f"{label} is out of range.")
    return number


def _source_fits(shapes):
    import json_preview_renderer as renderer
    for shape in shapes:
        if not shape["color"][3] and not shape["mask"]:continue
        resource=renderer._resolve_vinyl_resource(shape["type"],{"type":shape["type"]})
        triangles=renderer._resource_alpha_triangles(*resource) if resource else None
        if not triangles:raise ValidationError("The source has no exact native geometry for export.")
        for points,alpha in triangles:
            transformed=renderer._transform_resource_polygon(points,shape["data"])
            if any(abs(x)>1024 or abs(y)>512 for x,y in transformed):
                raise ValidationError("The source vinyl extends outside the preview canvas. Center or resize its shapes in the vinyl editor before exporting.")


def compile_layout(project,car_id,sections):
    return _compile_layout(project,car_id,sections)


def compile_section_vinyl(project,car_id,sections,section):
    if section not in sections or section not in NAMES:
        raise ValidationError("Choose a valid car section.")
    result=_compile_layout(project,car_id,sections,target_section=section)
    return {"shapes":result[section]}


def _compile_layout(project,car_id,sections,*,target_section=None):
    if not isinstance(project,dict) or project.get("format")!="kfps-livery-layout-v1":
        raise ValidationError("Expected a livery layout project.")
    parts=project.get("vehicle_parts",{})
    if not isinstance(parts,dict):
        raise ValidationError("Invalid vehicle part configuration.")
    if parts and target_section is None:
        raise ValidationError("Configured body/parts are saved in the layout, but experimental game export cannot yet encode or verify them. Restore the stock preview to export artwork against the template.")
    if not isinstance(project.get("vehicle"),dict) or type(project["vehicle"].get("car_id")) is not int or project["vehicle"]["car_id"]!=car_id:
        raise ValidationError("The layout belongs to a different car.")
    sources=project.get("vinyls");placements=project.get("placements")
    if not isinstance(sources,list) or not isinstance(placements,list) or len(sources)>16 or len(placements)>200:
        raise ValidationError("Layout exceeds the authoring limits.")
    lookup={}; ids=set(); checked_sources=set()
    section_placements=[p for p in placements if isinstance(p,dict) and p.get("section")==target_section and p.get("visible") is True and p.get("opacity",0)!=0]
    isolated_mask=target_section is not None and len(section_placements)==1
    for source in sources:
        if not isinstance(source,dict) or not isinstance(source.get("id"),str) or not source["id"] or len(source["id"])>100 or source["id"] in lookup:
            raise ValidationError("Invalid or duplicate vinyl ID.")
        lookup[source["id"]]=validate_shapes({"shapes":source.get("shapes")},_resolve)
    output={name:[] for name in NAMES}
    for p in placements:
        if (not isinstance(p,dict) or not isinstance(p.get("id"),str) or not p["id"] or len(p["id"])>100
                or p["id"] in ids or not isinstance(p.get("vinylId"),str) or p["vinylId"] not in lookup
                or p.get("section") not in sections or p.get("section") not in NAMES or type(p.get("visible")) is not bool):
            raise ValidationError("Invalid placement, section or source.")
        ids.add(p["id"])
        x=_bounded(p.get("x"),-4096,4096,"X");y=_bounded(p.get("y"),-4096,4096,"Y")
        sx=_bounded(p.get("scaleX"),.01,8,"Scale X");sy=_bounded(p.get("scaleY"),.01,8,"Scale Y")
        rotation=_bounded(p.get("rotation"),-3600,3600,"Rotation")
        placement_skew=_bounded(p.get("skew",0),-4,4,"Skew")
        opacity=_bounded(p.get("opacity"),0,1,"Opacity")
        if not p["visible"] or opacity==0 or (target_section is not None and p["section"]!=target_section):continue
        native=lookup[p["vinylId"]]
        if any(shape["mask"] for shape in native) and (not isolated_mask or opacity!=1):
            raise ValidationError("Export cannot preserve isolated masks across multiple vinyls or group opacity. Export this masked vinyl on its own at full opacity.")
        if opacity!=1 and sum(shape["color"][3]>0 for shape in native)>1:
            raise ValidationError("Multi-shape vinyl opacity must be 1 for experimental export; isolated group opacity cannot be flattened exactly.")
        if p["vinylId"] not in checked_sources:
            _source_fits(native)
            checked_sources.add(p["vinylId"])
        rad=math.radians(rotation);c=math.cos(rad);s=math.sin(rad)
        m00=c*sx;m01=(c*placement_skew-s)*sy
        m10=s*sx;m11=(s*placement_skew+c)*sy
        target=output[p["section"]]
        for shape in native:
            px,py,psx,psy,pr,skew,_=shape["data"]
            alpha=math.floor(shape["color"][3]*opacity+.5)
            if not alpha and not shape["mask"]:continue
            # Compose placement and native leaf matrices, then QR-decompose into
            # rotation/shear/signed scale. Positions use the same Y-up convention.
            theta=math.radians(pr);co=math.cos(theta);si=math.sin(theta)
            a=(m00*co+m01*si)*psx
            b=(m00*(co*skew-si)+m01*(si*skew+co))*psy
            cc=(m10*co+m11*si)*psx
            d=(m10*(co*skew-si)+m11*(si*skew+co))*psy
            ax=math.hypot(a,cc)*(-1 if a*d-b*cc<0 else 1)
            angle=math.atan2(cc/ax,a/ax)
            cr=math.cos(angle);sr=math.sin(angle)
            ay=-sr*b+cr*d
            shear=(cr*b+sr*d)/ay
            data=[x+m00*px+m01*py,y+m10*px+m11*py,ax,ay,math.degrees(angle)%360,shear,0]
            data[6]=int(shape["mask"])
            transformed={"type":shape["type"],"data":data,"color":[*shape["color"][:3],alpha],"mask":shape["mask"]}
            target.append(transformed)
            cap=3000 if target_section is not None else CAPS[p["section"]]
            if len(target)>cap:
                raise ValidationError(f"{p['section']} exceeds the {cap}-shape export cap.")
    if not any(output.values()):raise ValidationError("At least one visible shape is required for export.")
    for shapes in output.values():
        if shapes:validate_shapes({"shapes":shapes},_resolve)
    return output


def encode_experiment(template,sections):
    from tools.cgroup import forza_source_decoder as decoder
    if not isinstance(sections,dict) or set(sections)-set(NAMES):
        raise ValidationError("Unknown export section.")
    body=bytearray(); counts=[]; expected=[]
    for index,name in enumerate(NAMES):
        shapes=sections.get(name,[])
        if not isinstance(shapes,list) or len(shapes)>CAPS[name]:
            raise ValidationError(f"{name} exceeds the experimental shape cap.")
        shapes=validate_shapes({"shapes":shapes},_resolve) if shapes else []
        if any(shape["mask"] for shape in shapes):
            raise ValidationError("Experimental mask serialization is not enabled.")
        count=len(shapes);counts.append(count)
        blocks=(count+7)//8
        body.extend(struct.pack("<HH",count,blocks)+bytes(2+blocks))
        for i,shape in enumerate(shapes):
            x,y,sx,sy,angle,skew,_=shape["data"]
            if name=="Spoiler":x,y,angle=-x,-y,(angle-180)%360
            r,g,b,a=shape["color"]
            # First leaf is unframed; each preceding leaf contributes its mask byte.
            body.extend(struct.pack("<BH6f4BB",2,shape["type_word"],angle%360,x,y,sx,sy,skew,b,g,r,a,0))
            expected.append((name,shape))
        if index<10:body.extend(template.transitions[index])
    if not expected:raise ValidationError("At least one visible shape is required for export.")
    if b"yrvl" in body:
        raise ValidationError("Artwork bytes collide with the current KFPS section-marker parser; export is unsupported without changing artwork.")
    prefix=bytearray(template.payload[:template.body_start])
    struct.pack_into("<I",prefix,template.gyvl-4,len(prefix)-template.gyvl+len(body))
    tail=bytearray(template.payload[template.body_end:])
    struct.pack_into("<11I",tail,4,*counts)
    payload=bytes(prefix)+bytes(body)+bytes(tail)
    decoded,report=decoder.clivery_to_layers(payload)
    if report["warnings"] or len(decoded)!=len(expected):
        raise ValidationError("Edited save failed independent structural decoding.")
    for actual,(section,shape) in zip(decoded,expected):
        if actual["section"]!=section or actual["shape_id"]!=shape["type_word"] or actual["color_rgba"]!=shape["color"] or actual["mask"]:
            raise ValidationError("Edited save failed shape/color/order verification.")
        # Compare effective matrices, not a particular mirrored decomposition.
        values=actual["data"]
        for left,right in zip(values[:2],shape["data"][:2]):
            if not math.isclose(left,right,rel_tol=2e-6,abs_tol=2e-4):raise ValidationError("Edited position verification failed.")
        def matrix(data):
            _,_,sx,sy,angle,skew,*_=data;c=math.cos(math.radians(angle));s=math.sin(math.radians(angle))
            return (c*sx,s*sx,(c*skew-s)*sy,(s*skew+c)*sy)
        if any(not math.isclose(a,b,rel_tol=2e-5,abs_tol=2e-4) for a,b in zip(matrix(values),matrix(shape["data"]))):
            raise ValidationError("Edited transform verification failed.")
    privacy=decoder.inspect_clivery_privacy(payload)
    if not privacy["source_owned"] or privacy["contains_foreign_groups"]:
        raise ValidationError("Edited save failed ownership verification.")
    packed=zlib.compress(payload)
    result=struct.pack("<II",len(packed),len(payload))+packed
    if unwrap_bounded(result)!=payload:raise ValidationError("Compressed output failed verification.")
    return result,{"format":"kfps-livery-experiment-v1","experimental":True,"game_acceptance_verified":False,
                   "independent_decode_verified":True,"car_id":template.car_id,"shape_count":len(expected),
                   "section_limit_policy":section_limit_policy(),
                   "section_counts":dict(zip(NAMES,counts)),"opaque_envelope_and_material_tail_preserved":True}
