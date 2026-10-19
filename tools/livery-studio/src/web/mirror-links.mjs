// Native section coordinates are Y-up; these matrices are not canvas matrices.
const F = [-1, 0, 0, 1, 0, 0];
const LIMITS = {x:[-4096,4096],y:[-4096,4096],scaleX:[.01,8],scaleY:[.01,8],rotation:[-3600,3600],skew:[-4,4],opacity:[0,1]};
const MODES = new Set(['mirror-artwork', 'readable-lettering']);
const zero = n => n === 0 ? 0 : n;
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const text = (value, limit, label) => {
  if (typeof value !== 'string' || !value.trim() || value.length > limit) throw Error(`Invalid ${label}.`);
  return value;
};
const finite = (value, low, high, label) => {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < low || value > high) throw Error(`Invalid ${label}.`);
  return value;
};
const modeValid = mode => { if (!MODES.has(mode)) throw Error('Invalid mirror mode.'); };
const pairedSections = (a,b) => (a === 'Left' && b === 'Right') || (a === 'Right' && b === 'Left') ||
  (a === 'LeftWindow' && b === 'RightWindow') || (a === 'RightWindow' && b === 'LeftWindow');
const multiply = (m,n) => [m[0]*n[0]+m[2]*n[1],m[1]*n[0]+m[3]*n[1],
  m[0]*n[2]+m[2]*n[3],m[1]*n[2]+m[3]*n[3],m[0]*n[4]+m[2]*n[5]+m[4],m[1]*n[4]+m[3]*n[5]+m[5]].map(zero);
const inverse = m => {
  const det=m[0]*m[3]-m[1]*m[2];
  if (!Number.isFinite(det) || Math.abs(det)<1e-12) throw Error('Singular mirror calibration.');
  return [m[3]/det,-m[1]/det,-m[2]/det,m[0]/det,(m[2]*m[5]-m[3]*m[4])/det,(m[1]*m[4]-m[0]*m[5])/det].map(zero);
};
const nearMatrix = (a,b) => a.every((v,i)=>Math.abs(v-b[i])<=1e-10*Math.max(1,Math.abs(v),Math.abs(b[i])));

function checkPlacement(p) {
  if (!object(p)) throw Error('Invalid placement.');
  text(p.id,100,'placement ID'); text(p.vinylId,100,'vinyl ID'); text(p.section,100,'section');
  for (const [key,[low,high]] of Object.entries(LIMITS)) finite(key==='skew' && p[key]===undefined ? 0 : p[key],low,high,key);
  if (typeof p.visible !== 'boolean') throw Error('Invalid placement visibility.');
}

function checkShapes(shapes) {
  if (!Array.isArray(shapes) || !shapes.length || shapes.length>3000) throw Error('Artwork requires 1-3000 native shapes.');
  for (const s of shapes) {
    if (!object(s) || s.is_raster_logo || s.raster_id || !Number.isInteger(s.type) || s.type<0x100000 || s.type>0x107fff ||
      (s.type_word!==undefined && s.type_word!==s.type-0x100000)) throw Error('Invalid native shape type.');
    const d=s.data;
    if (!Array.isArray(d) || d.length<5 || d.length>7 || !Array.from(d).every(v=>typeof v==='number' && Number.isFinite(v))) throw Error('Invalid native shape data.');
    if (Math.abs(d[0])>=50000 || Math.abs(d[1])>=50000 || Math.abs(d[2])<=1e-6 || Math.abs(d[2])>=200 ||
      Math.abs(d[3])<=1e-6 || Math.abs(d[3])>=200 || Math.abs(d[4])>10000 || Math.abs(d[5]??0)>=200) throw Error('Native shape transform is out of range.');
    const mask=d.length===7?d[6]:null;
    if ((mask!==null && ![0,1].includes(mask)) || (s.mask!==undefined && (typeof s.mask!=='boolean' || (mask!==null && Number(s.mask)!==mask)))) throw Error('Invalid native shape mask.');
    if (!Array.isArray(s.color) || s.color.length!==4 || !Array.from(s.color).every(v=>Number.isInteger(v) && v>=0 && v<=255)) throw Error('Invalid native shape color.');
  }
}

/** Exact native X reflection; signed shape scales remain supported by the exporter. */
export function reflectArtwork(shapes) {
  checkShapes(shapes);
  return shapes.map(s=>{
    const next=structuredClone(s);
    for (const index of [0,2,4]) next.data[index]=zero(-next.data[index]);
    if (next.data.length>=6) next.data[5]=zero(-next.data[5]);
    return next;
  });
}

export function placementAffine(p) {
  checkPlacement(p);
  const r=p.rotation*Math.PI/180,c=Math.cos(r),s=Math.sin(r),k=p.skew??0;
  return [c*p.scaleX,s*p.scaleX,(c*k-s)*p.scaleY,(s*k+c)*p.scaleY,p.x,p.y].map(zero);
}

/** Optional authoring.links validator. No dependency on layout/authoring modules. */
export function validateMirrorLinks(links, placements) {
  if (!Array.isArray(placements) || placements.length>200) throw Error('Invalid placements.');
  const byId=new Map();
  for (const p of placements) {
    if (!object(p)) throw Error('Invalid placement.');
    text(p.id,100,'placement ID'); text(p.section,100,'section');
    if (byId.has(p.id)) throw Error('Duplicate placement ID.');
    byId.set(p.id,p);
  }
  if (links===undefined) return [];
  if (!Array.isArray(links) || links.length>100) throw Error('Invalid mirror links.');
  const ids=new Set(),used=new Set();
  return Array.from(links).map(link=>{
    if (!object(link)) throw Error('Invalid mirror link.');
    text(link.id,100,'mirror link ID'); text(link.a,100,'mirror endpoint'); text(link.b,100,'mirror endpoint');
    if (ids.has(link.id) || used.has(link.a) || used.has(link.b) || link.a===link.b) throw Error('Duplicate or overlapping mirror link.');
    const a=byId.get(link.a),b=byId.get(link.b);
    if (!a || !b) throw Error('Missing mirror placement.');
    if (link.sectionA!==a.section || link.sectionB!==b.section || !pairedSections(link.sectionA,link.sectionB)) throw Error('Mirror section mismatch. Unlink before changing section.');
    modeValid(link.mode);
    const calibration=link.calibration,m=calibration?.aToB;
    if (!object(calibration) || calibration.kind!=='user-aligned-pair-v1' || !Array.isArray(m) || m.length!==6 ||
      !Array.from(m).every(v=>typeof v==='number' && Number.isFinite(v) && Math.abs(v)<=1e9)) throw Error('Invalid mirror calibration.');
    const det=m[0]*m[3]-m[1]*m[2];
    if (!Number.isFinite(det) || det>=-1e-12) throw Error('Mirror calibration must be a nonsingular reflection.');
    ids.add(link.id);used.add(link.a);used.add(link.b);
    return {id:link.id,a:link.a,b:link.b,sectionA:link.sectionA,sectionB:link.sectionB,mode:link.mode,
      calibration:{kind:'user-aligned-pair-v1',aToB:m.map(zero)}};
  });
}

function checked(project) {
  if (!object(project) || project.format!=='kfps-livery-layout-v1' || !Array.isArray(project.vinyls) || project.vinyls.length>16 ||
    !Array.isArray(project.placements) || project.placements.length>200) throw Error('Invalid project or authoring limits.');
  const sources=new Map(),placements=new Map();
  for (const source of project.vinyls) {
    if (!object(source)) throw Error('Invalid vinyl source.');
    text(source.id,100,'vinyl ID');text(source.name,160,'vinyl name');
    if (sources.has(source.id)) throw Error('Duplicate vinyl ID.');
    if (!Array.isArray(source.shapes) || !source.shapes.length || source.shapes.length>3000) throw Error('Invalid vinyl shape count.');
    sources.set(source.id,source);
  }
  for (const p of project.placements) {
    checkPlacement(p);
    if (placements.has(p.id)) throw Error('Duplicate placement ID.');
    if (!sources.has(p.vinylId)) throw Error('Missing vinyl source.');
    placements.set(p.id,p);
  }
  if (project.authoring!==undefined && (!object(project.authoring) || project.authoring.version!==1)) throw Error('Unsupported authoring version.');
  return {sources,placements,links:validateMirrorLinks(project.authoring?.links,project.placements)};
}

function decomposed(m, previous) {
  const sx=Math.hypot(m[0],m[1]),sy=(m[0]*m[3]-m[1]*m[2])/sx;
  let angle=Math.atan2(m[1],m[0])*180/Math.PI;
  angle+=360*Math.round((previous.rotation-angle)/360);
  if (angle>3600) angle-=360;
  if (angle< -3600) angle+=360;
  const values={x:m[4],y:m[5],scaleX:sx,scaleY:sy,rotation:angle,skew:(m[0]*m[2]+m[1]*m[3])/(sx*sy)};
  for (const [key,value] of Object.entries(values)) {
    const [low,high]=LIMITS[key],epsilon=1e-10*Math.max(1,Math.abs(value));
    finite(value,low-epsilon,high+epsilon,`linked ${key}`);
    values[key]=zero(Math.max(low,Math.min(high,value)));
  }
  return {...previous,...values};
}

export function mapLinkedPlacement(source, target, link, editedId) {
  checkPlacement(source);checkPlacement(target);
  validateMirrorLinks([link],[source,target]);
  if (source.id!==editedId || ![link.a,link.b].includes(editedId) || target.id===(editedId)) throw Error('Invalid mirror propagation endpoints.');
  const h=editedId===link.a?link.calibration.aToB:inverse(link.calibration.aToB);
  const matrix=multiply(multiply(h,placementAffine(source)),F);
  const next=nearMatrix(matrix,placementAffine(target))?{...target}:decomposed(matrix,target);
  next.opacity=source.opacity;next.visible=source.visible;
  return next;
}

const result = (project, details={}) => ({project,changedPlacementIds:[],changedSourceIds:[],removedPlacementIds:[],removedLinkIds:[],...details});
const withLinks = (project,links) => ({...project,authoring:{...project.authoring,version:1,links}});
function freshId(id,sources) { text(id,100,'new vinyl ID'); if (sources.has(id)) throw Error('A new immutable vinyl source ID is required.'); }
function replaceSources(project, placements, added, replaced) {
  const used=new Set(placements.map(p=>p.vinylId));
  const vinyls=[...project.vinyls.filter(v=>!replaced.has(v.id) || used.has(v.id)),...added];
  if (vinyls.length>16) throw Error('The 16-vinyl source limit is reached.');
  return {...project,placements,vinyls};
}
function copySource(source,id,mode) {
  checkShapes(source.shapes);
  return {id,name:source.name,shapes:mode==='mirror-artwork'?reflectArtwork(source.shapes):structuredClone(source.shapes)};
}
function allowChange(project, ids) {
  const locked=project.authoring?.locked;
  if (Array.isArray(locked) && ids.some(id=>locked.includes(id))) throw Error('Unlock both linked placements before editing.');
}

/** Link two already aligned placements. B's artwork is replaced, its pose is kept. */
export function linkPlacements(project, options) {
  const {sources,placements,links}=checked(project);
  if (!object(options)) throw Error('Invalid link options.');
  const {id,sourceId,targetId,mode,targetVinylId}=options;
  text(id,100,'mirror link ID');modeValid(mode);freshId(targetVinylId,sources);
  const a=placements.get(sourceId),b=placements.get(targetId);
  if (!a || !b) throw Error('Choose two existing placements.');
  allowChange(project,[a.id,b.id]);
  const link={id,a:a.id,b:b.id,sectionA:a.section,sectionB:b.section,mode,
    calibration:{kind:'user-aligned-pair-v1',aToB:multiply(multiply(placementAffine(b),F),inverse(placementAffine(a)))}};
  const validated=validateMirrorLinks([...links,link],project.placements);
  const source=copySource(sources.get(a.vinylId),targetVinylId,mode);
  const nextPlacements=project.placements.map(p=>p.id===b.id?{...p,vinylId:targetVinylId,opacity:a.opacity,visible:a.visible}:p);
  const next=withLinks(replaceSources(project,nextPlacements,[source],new Set([b.vinylId])),validated);
  return result(next,{changedPlacementIds:[b.id],changedSourceIds:[targetVinylId]});
}

export function propagateLinkedPlacement(project, editedId) {
  const {placements,links}=checked(project);
  if (!placements.has(editedId)) throw Error('Missing edited placement.');
  const link=links.find(l=>l.a===editedId || l.b===editedId);
  if (!link) return result(project);
  const peerId=link.a===editedId?link.b:link.a;
  allowChange(project,[editedId,peerId]);
  const target=placements.get(peerId),mapped=mapLinkedPlacement(placements.get(editedId),target,link,editedId);
  const fields=[...Object.keys(LIMITS),'visible'];
  if (fields.every(key=>(key==='skew'?(mapped[key]??0):mapped[key])===(key==='skew'?(target[key]??0):target[key]))) return result(project);
  return result({...project,placements:project.placements.map(p=>p.id===peerId?mapped:p)},{changedPlacementIds:[peerId]});
}

/** Atomically propagate a controller transform transaction; source edits use replaceLinkedArtwork. */
export function propagateLinks(beforeProject, afterProject, changedIds) {
  const before=checked(beforeProject),after=checked(afterProject);
  if (!Array.isArray(changedIds) || changedIds.length>200 || changedIds.some(id=>!after.placements.has(id))) throw Error('Invalid changed placement IDs.');
  if (JSON.stringify(before.links)!==JSON.stringify(after.links)) throw Error('Change mirror links in a separate transaction.');
  const changed=new Set(changedIds),updated=new Set();let current=afterProject;
  for (const link of after.links) {
    if (!changed.has(link.a) && !changed.has(link.b)) continue;
    for (const id of [link.a,link.b]) if (before.placements.get(id)?.vinylId!==after.placements.get(id).vinylId) throw Error('Use replaceLinkedArtwork for linked source edits.');
    if (changed.has(link.a) && changed.has(link.b)) {
      allowChange(afterProject,[link.a,link.b]);
      const a=after.placements.get(link.a),b=after.placements.get(link.b),mapped=mapLinkedPlacement(a,b,link,link.a);
      if (!nearMatrix(placementAffine(mapped),placementAffine(b)) || a.opacity!==b.opacity || a.visible!==b.visible) throw Error('Both linked placements changed incompatibly. Edit one side or unlink first.');
    } else {
      const propagated=propagateLinkedPlacement(current,changed.has(link.a)?link.a:link.b);
      current=propagated.project;propagated.changedPlacementIds.forEach(id=>updated.add(id));
    }
  }
  return result(current,{changedPlacementIds:[...updated]});
}

export function replaceLinkedArtwork(project, editedId, source, partnerVinylId) {
  const {sources,placements,links}=checked(project),edited=placements.get(editedId);
  if (!edited || !object(source)) throw Error('Invalid artwork edit.');
  freshId(source.id,sources);text(source.name,160,'vinyl name');checkShapes(source.shapes);
  const link=links.find(l=>l.a===editedId || l.b===editedId),peerId=link?(link.a===editedId?link.b:link.a):null;
  allowChange(project,peerId?[editedId,peerId]:[editedId]);
  const added=[{id:source.id,name:source.name,shapes:structuredClone(source.shapes)}],replaced=new Set([edited.vinylId]);
  if (link) {
    freshId(partnerVinylId,sources);
    if (partnerVinylId===source.id) throw Error('Linked sources require distinct immutable IDs.');
    added.push(copySource(source,partnerVinylId,link.mode));replaced.add(placements.get(peerId).vinylId);
  }
  const nextPlacements=project.placements.map(p=>p.id===editedId?{...p,vinylId:source.id}:p.id===peerId?{...p,vinylId:partnerVinylId}:p);
  return result(replaceSources(project,nextPlacements,added,replaced),{
    changedPlacementIds:peerId?[editedId,peerId]:[editedId],changedSourceIds:added.map(v=>v.id)});
}

export function setMirrorLinkMode(project, linkId, mode, targetVinylId) {
  const {sources,placements,links}=checked(project),link=links.find(l=>l.id===linkId);
  modeValid(mode);if (!link) throw Error('Missing mirror link.');
  if (mode===link.mode) return result(project);
  allowChange(project,[link.a,link.b]);freshId(targetVinylId,sources);
  const a=placements.get(link.a),b=placements.get(link.b),source=copySource(sources.get(a.vinylId),targetVinylId,mode);
  const nextPlacements=project.placements.map(p=>p.id===b.id?{...p,vinylId:targetVinylId}:p);
  return result(withLinks(replaceSources(project,nextPlacements,[source],new Set([b.vinylId])),links.map(l=>l.id===linkId?{...l,mode}:l)),
    {changedPlacementIds:[b.id],changedSourceIds:[targetVinylId]});
}

export function unlinkMirror(project, linkId) {
  const {links}=checked(project);
  if (!links.some(l=>l.id===linkId)) throw Error('Missing mirror link.');
  return result(withLinks(project,links.filter(l=>l.id!==linkId)),{removedLinkIds:[linkId]});
}

export function removeLinkedPlacement(project, placementId) {
  const {placements,links}=checked(project),removed=placements.get(placementId);
  if (!removed) throw Error('Missing placement.');
  allowChange(project,[placementId]);
  const removedLinks=links.filter(l=>l.a===placementId || l.b===placementId);
  let next=replaceSources(project,project.placements.filter(p=>p.id!==placementId),[],new Set([removed.vinylId]));
  if (project.authoring) {
    const authoring={...project.authoring,links:links.filter(l=>!removedLinks.includes(l))};
    if (Array.isArray(authoring.locked)) authoring.locked=authoring.locked.filter(id=>id!==placementId);
    if (Array.isArray(authoring.groups)) authoring.groups=authoring.groups.map(g=>({...g,placements:g.placements.filter(id=>id!==placementId)})).filter(g=>g.placements.length>=2);
    next={...next,authoring};
  }
  return result(next,{removedPlacementIds:[placementId],removedLinkIds:removedLinks.map(l=>l.id)});
}
