import {validateMirrorLinks} from './mirror-links.mjs';

export const FORMAT = 'kfps-livery-layout-v1';
export const MAX_VINYLS = 16;
export const MAX_PLACEMENTS = 200;
export const MAX_NATIVE_VINYL_SHAPES = 3000;
export const MAX_PROJECT_BYTES = 32 * 1024 * 1024;
export const SECTION_SIZE = [2048, 1024];
const finite = (value, min, max, label) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) throw Error(`Invalid ${label}.`);
  return value;
};
const text = (value, max, label) => {
  if (typeof value !== 'string' || !value.trim() || value.length > max) throw Error(`Invalid ${label}.`);
  return value;
};
export function emptyProject(vehicle) {
  return { format: FORMAT, vehicle: { car_id: vehicle.car_id, model_code: vehicle.model_code }, vinyls: [], placements: [] };
}
export function validateAuthoring(value, placements) {
  if(value===undefined)return undefined;
  if(!value||typeof value!=='object'||Array.isArray(value)||value.version!==1||
    Object.keys(value).some(key=>!['version','groups','locked','links'].includes(key)))throw Error('Invalid authoring metadata.');
  if(!Array.isArray(placements)||placements.length>MAX_PLACEMENTS)throw Error('Invalid authoring placements.');
  const byId=new Map(placements.map(p=>[p.id,p]));
  if(byId.size!==placements.length)throw Error('Duplicate placement ID.');
  const groups=value.groups===undefined?[]:value.groups,locked=value.locked===undefined?[]:value.locked;
  if(!Array.isArray(groups)||groups.length>MAX_PLACEMENTS/2||!Array.isArray(locked)||locked.length>MAX_PLACEMENTS)throw Error('Invalid authoring groups or locks.');
  const groupIds=new Set(),members=new Set(),lockIds=new Set();
  const normalizedGroups=groups.map(group=>{
    if(!group||typeof group!=='object'||Array.isArray(group)||Object.keys(group).some(key=>!['id','name','placements'].includes(key)))throw Error('Invalid group.');
    const id=text(group.id,100,'group ID'),name=text(group.name,160,'group name');
    if(groupIds.has(id)||!Array.isArray(group.placements)||group.placements.length<2||group.placements.length>MAX_PLACEMENTS)throw Error('Invalid or duplicate group.');
    groupIds.add(id);let section;
    const ids=group.placements.map(member=>{
      text(member,100,'group placement ID');const placement=byId.get(member);
      if(!placement||members.has(member))throw Error('Missing or overlapping group placement.');
      if(section!==undefined&&section!==placement.section)throw Error('Groups must belong to one section.');
      section=placement.section;members.add(member);return member;
    });
    return {id,name,placements:ids};
  });
  const normalizedLocked=locked.map(id=>{
    text(id,100,'locked placement ID');
    if(!byId.has(id)||lockIds.has(id))throw Error('Missing or duplicate locked placement.');
    lockIds.add(id);return id;
  });
  const links=validateMirrorLinks(value.links,placements);
  return normalizedGroups.length||normalizedLocked.length||links.length?
    {version:1,groups:normalizedGroups,locked:normalizedLocked,links}:undefined;
}
export function serializeProject(value, maximumBytes = MAX_PROJECT_BYTES) {
  const json=JSON.stringify(value,null,2);
  if(new TextEncoder().encode(json).byteLength>maximumBytes)throw Error('The layout exceeds the 32 MiB project limit. Remove unused artwork before saving.');
  return json;
}
export function sectionVinylJson(value) {
  if(!value||typeof value!=='object'||Array.isArray(value)||!Array.isArray(value.shapes)||!value.shapes.length||value.shapes.length>MAX_NATIVE_VINYL_SHAPES)throw Error('The section export did not return 1-3000 native shapes. Nothing was downloaded.');
  for(const shape of value.shapes) {
    if(!shape||typeof shape!=='object'||Array.isArray(shape)||!Number.isInteger(shape.type)||shape.type<=0||shape.type>0xffffffff
      ||!Array.isArray(shape.data)||shape.data.length!==7||!shape.data.every(Number.isFinite)||![0,1].includes(shape.data[6])
      ||!Array.isArray(shape.color)||shape.color.length!==4||!shape.color.every(channel=>Number.isInteger(channel)&&channel>=0&&channel<=255)
      ||(shape.mask!==undefined&&(typeof shape.mask!=='boolean'||Number(shape.mask)!==shape.data[6])))throw Error('The section export contains an invalid native shape. Nothing was downloaded.');
  }
  const payload={shapes:value.shapes},limit=8*1024*1024;
  let json=JSON.stringify(payload,null,2);
  if(new TextEncoder().encode(json).byteLength>limit)json=JSON.stringify(payload);
  if(new TextEncoder().encode(json).byteLength>limit)throw Error('The section export exceeds the 8 MiB native vinyl limit. Nothing was downloaded.');
  return json;
}
export function sectionShapeCount(project,section) {
  const counts=new Map(project.vinyls.map(source=>[source.id,source.shapes.length]));
  return project.placements.reduce((total,placement)=>total+(placement.section===section&&placement.visible&&placement.opacity>0?(counts.get(placement.vinylId)||0):0),0);
}
export function validateProject(value, vehicle, sections) {
  if (!value || value.format !== FORMAT) throw Error('This is not a KFPS livery layout project.');
  if (value.vehicle?.car_id !== vehicle.car_id || value.vehicle?.model_code !== vehicle.model_code) throw Error('This project belongs to a different car.');
  if (!Array.isArray(value.vinyls) || value.vinyls.length > MAX_VINYLS || !Array.isArray(value.placements) || value.placements.length > MAX_PLACEMENTS) throw Error('The project exceeds the authoring limits.');
  const ids = new Set(), placementIds = new Set();
  const vinyls = value.vinyls.map(v => {
    if (!v || !Array.isArray(v.shapes) || !v.shapes.length || v.shapes.length > MAX_NATIVE_VINYL_SHAPES) throw Error('Invalid vinyl shapes.');
    const id = text(v.id, 100, 'vinyl ID');
    if (ids.has(id)) throw Error('Duplicate vinyl ID.');
    ids.add(id);
    return { id, name: text(v.name, 160, 'vinyl name'), shapes: structuredClone(v.shapes) };
  });
  const placements = value.placements.map(p => {
    if (!p || !ids.has(p.vinylId) || !sections.includes(p.section)) throw Error('Unknown vinyl or section.');
    const id = text(p.id, 100, 'placement ID');
    if (placementIds.has(id)) throw Error('Duplicate placement ID.');
    placementIds.add(id);
    if (typeof p.visible !== 'boolean') throw Error('Invalid placement visibility.');
    const skew=p.skew===undefined?0:finite(p.skew,-4,4,'skew');
    return { id, vinylId: p.vinylId, section: p.section,
      x: finite(p.x, -4096, 4096, 'X'), y: finite(p.y, -4096, 4096, 'Y'),
      scaleX: finite(p.scaleX, .01, 8, 'scale X'), scaleY: finite(p.scaleY, .01, 8, 'scale Y'),
      rotation: finite(p.rotation, -3600, 3600, 'rotation'), opacity: finite(p.opacity, 0, 1, 'opacity'), visible: p.visible,
      ...(skew?{skew}:{}) };
  });
  const vehicleParts=value.vehicle_parts;
  if(vehicleParts!==undefined) {
    if(!vehicleParts||typeof vehicleParts!=='object'||Array.isArray(vehicleParts)||Object.keys(vehicleParts).length>128)throw Error('Invalid vehicle_parts map.');
    for(const [part,id] of Object.entries(vehicleParts)) {
      text(part,128,'component type');
      if(id!==null&&(typeof id!=='number'||!Number.isSafeInteger(id)))throw Error('Invalid component option ID.');
    }
  }
  const authoring=validateAuthoring(value.authoring,placements);
  return { ...emptyProject(vehicle), vinyls, placements,...(authoring?{authoring}:{}),
    ...(vehicleParts&&Object.keys(vehicleParts).length?{vehicle_parts:Object.fromEntries(Object.entries(vehicleParts))}:{}) };
}
export function makePlacement(project, vinylId, section, sections, id) {
  if (project.placements.length >= MAX_PLACEMENTS) throw Error(`The ${MAX_PLACEMENTS}-placement limit is reached.`);
  if (!project.vinyls.some(v => v.id === vinylId)) throw Error('Choose an existing vinyl source.');
  if (!sections.includes(section)) throw Error('Choose a valid car section.');
  text(id, 100, 'placement ID');
  if (project.placements.some(p => p.id === id)) throw Error('Duplicate placement ID.');
  return { id, vinylId, section, x:0, y:0, scaleX:1, scaleY:1, rotation:0, opacity:1, visible:true };
}
export function movePlacementToSection(placement, section, sections) {
  if (!sections.includes(section)) throw Error('Choose a valid car section.');
  return { ...placement, section };
}
export function scalePlacement(placement, axis, value, locked) {
  if (axis !== 'scaleX' && axis !== 'scaleY') throw Error('Invalid scale axis.');
  finite(value, .01, 8, 'scale');
  const next = { ...placement, [axis]:value };
  if (locked) {
    const other = axis === 'scaleX' ? 'scaleY' : 'scaleX';
    finite(placement[axis], .01, 8, 'scale');
    finite(placement[other], .01, 8, 'scale');
    const scaled = placement[other] * (value / placement[axis]);
    if (!Number.isFinite(scaled) || scaled < .01 - 1e-12 || scaled > 8 + 1e-12) {
      throw Error('Both scales must stay between 0.01 and 8. Unlock the aspect ratio to change one axis independently.');
    }
    // Only absorb floating-point error at the existing format boundaries.
    next[other] = Math.max(.01, Math.min(8, scaled));
  }
  return next;
}
export function placementStepIndex(placements, id, step) {
  if (step !== 1 && step !== -1) throw Error('Invalid reorder direction.');
  const index = placements.findIndex(p => p.id === id);
  if (index < 0) return -1;
  for (let i = index + step; i >= 0 && i < placements.length; i += step) {
    if (placements[i].section === placements[index].section) return i;
  }
  return -1;
}
export function placementMatrix(p) {
  const angle = p.rotation * Math.PI / 180, cos = Math.cos(angle), sin = Math.sin(angle);
  const skew=p.skew??0;
  return [cos * p.scaleX, -sin * p.scaleX, (sin-cos*skew) * p.scaleY, (cos+sin*skew) * p.scaleY, 1024 + p.x, 512 - p.y];
}
export function transformPlacement(placement,patch) {
  if(!patch||typeof patch!=='object'||Array.isArray(patch))throw Error('Invalid transform patch.');
  const limits={x:[-4096,4096],y:[-4096,4096],scaleX:[.01,8],scaleY:[.01,8],rotation:[-3600,3600],skew:[-4,4],opacity:[0,1]};
  const next={...placement};
  for(const [key,value] of Object.entries(patch)) {
    if(!Object.hasOwn(limits,key))throw Error('Unknown transform field.');
    next[key]=finite(value,...limits[key],key);
  }
  if(next.skew===0)delete next.skew;
  return next;
}
export function invertMatrix([a, b, c, d, e, f]) {
  const det = a * d - b * c;
  if (!Number.isFinite(det) || Math.abs(det) < 1e-12) throw Error('Invalid placement transform.');
  return [d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det];
}
export function mapPoint([a, b, c, d, e, f], x, y) { return [a * x + c * y + e, b * x + d * y + f]; }
export function sectionToPaint(section, paintSize) {
  // Baseline affine is atlas -> section: x=ax+by+c, y=dx+ey+f.
  const [a, b, c, d, e, f] = section.atlasToLocal;
  const inverse = invertMatrix([a, d, b, e, c, f]);
  const [sl, st, sr, sb] = section.source_region.map((n, i) => n * SECTION_SIZE[i % 2]);
  const [pl, pt, pr, pb] = section.paint_region.map((n, i) => n * paintSize[i % 2]);
  const sx = (pr - pl) / (sr - sl), sy = (pb - pt) / (sb - st);
  if (![sx, sy].every(n => Number.isFinite(n) && n > 0)) throw Error('Invalid paint region.');
  return [inverse[0] * sx, inverse[1] * sy, inverse[2] * sx, inverse[3] * sy,
    (inverse[4] - sl) * sx + pl, (inverse[5] - st) * sy + pt];
}
export function createHistory(limit = 100, sourceLimit = MAX_VINYLS) {
  let undo = [], redo = [];
  return {
    push(before, after) {
      if (JSON.stringify(before) === JSON.stringify(after)) return false;
      undo.push(structuredClone(before)); if (undo.length > limit) undo.shift(); redo = [];
      while(undo.length && new Set([...(after.vinylIds||[]),...undo.flatMap(state=>state.vinylIds||[])]).size>sourceLimit)undo.shift();
      return true;
    },
    undo(current) { if (!undo.length) return null; redo.push(structuredClone(current)); return undo.pop(); },
    redo(current) { if (!redo.length) return null; undo.push(structuredClone(current)); return redo.pop(); },
    reset() { undo = []; redo = []; },
    retainedVinylIds() { return new Set([...undo, ...redo].flatMap(state => state.vinylIds || [])); },
    get canUndo() { return !!undo.length; }, get canRedo() { return !!redo.length; }
  };
}
