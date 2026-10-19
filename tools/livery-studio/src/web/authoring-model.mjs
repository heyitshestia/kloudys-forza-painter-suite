import {MAX_PLACEMENTS,MAX_VINYLS,SECTION_SIZE,placementMatrix,mapPoint,transformPlacement,validateAuthoring} from './layout-model.mjs';
export {validateAuthoring} from './layout-model.mjs';

const number=(value,label)=>{
  if(typeof value!=='number'||!Number.isFinite(value))throw Error(`Invalid ${label}.`);
  return value;
};
const identifier=(value,label)=>{
  if(typeof value!=='string'||!value.trim()||value.length>100)throw Error(`Invalid ${label}.`);
  return value;
};
const metadata=project=>project.authoring??{version:1,groups:[],locked:[],links:[]};
function withAuthoring(project,value) {
  const next=validateAuthoring(value,project.placements),{authoring,...rest}=project;
  return next?{...rest,authoring:next}:rest;
}
function unlocked(project,ids) {
  const locks=new Set(project.authoring?.locked??[]);
  if(ids.some(id=>locks.has(id)))throw Error('Unlock all selected placements before editing.');
}
export function selectionIds(project,ids,{expandGroups=false}={}) {
  if(!Array.isArray(project?.placements)||project.placements.length>MAX_PLACEMENTS||!Array.isArray(ids)||ids.length>MAX_PLACEMENTS||typeof expandGroups!=='boolean')throw Error('Invalid selection.');
  const existing=new Set(project.placements.map(p=>p.id)),selected=new Set();
  for(const id of ids){identifier(id,'selection ID');if(!existing.has(id))throw Error('Missing selected placement.');selected.add(id);}
  if(expandGroups)for(const group of project.authoring?.groups??[])if(group.placements.some(id=>selected.has(id)))for(const id of group.placements)selected.add(id);
  return project.placements.filter(p=>selected.has(p.id)).map(p=>p.id);
}
export function isLocked(project,id) {return (project.authoring?.locked??[]).includes(id);}
function selected(project,ids,{editable=false,sameSection=false}={}) {
  const resolved=selectionIds(project,ids),set=new Set(resolved),rows=project.placements.filter(p=>set.has(p.id));
  if(editable)unlocked(project,resolved);
  if(sameSection&&new Set(rows.map(p=>p.section)).size>1)throw Error('Choose placements in one section.');
  return rows;
}
export function groupSelection(project,ids,{id,name}={}) {
  const rows=selected(project,ids,{editable:true,sameSection:true}),members=new Set(rows.map(p=>p.id)),state=metadata(project);
  identifier(id,'group ID');
  if(typeof name!=='string'||!name.trim()||name.length>160)throw Error('Invalid group name.');
  if(rows.length<2)throw Error('Select at least two placements to group.');
  if((state.groups??[]).some(g=>g.id===id))throw Error('Duplicate group ID.');
  unlocked(project,(state.groups??[]).filter(g=>g.placements.some(member=>members.has(member))).flatMap(g=>g.placements));
  const groups=(state.groups??[]).map(g=>({...g,placements:g.placements.filter(member=>!members.has(member))})).filter(g=>g.placements.length>=2);
  groups.push({id,name,placements:rows.map(p=>p.id)});
  return withAuthoring(project,{...state,groups});
}
export function ungroupSelection(project,ids) {
  const members=new Set(selectionIds(project,ids)),state=metadata(project),groups=state.groups??[];
  const removed=groups.filter(g=>g.placements.some(id=>members.has(id)));
  unlocked(project,[...members,...removed.flatMap(g=>g.placements)]);
  if(!removed.length)return project;
  return withAuthoring(project,{...state,groups:groups.filter(g=>!removed.includes(g))});
}
export function setLocked(project,ids,locked) {
  if(typeof locked!=='boolean')throw Error('Invalid lock state.');
  const members=selectionIds(project,ids),state=metadata(project),locks=new Set(state.locked??[]);
  for(const id of members)if(locked)locks.add(id);else locks.delete(id);
  return withAuthoring(project,{...state,locked:project.placements.filter(p=>locks.has(p.id)).map(p=>p.id)});
}
function freshId(idFactory,kind,oldId,used) {
  if(typeof idFactory!=='function')throw Error('An ID factory is required.');
  const id=identifier(idFactory(kind,oldId),`new ${kind} ID`);
  if(used.has(id))throw Error(`Duplicate ${kind} ID. Use a fresh immutable identity.`);
  used.add(id);return id;
}
export function duplicateSelection(project,ids,{idFactory,dx=20,dy=20}={}) {
  const rows=selected(project,ids,{editable:true});number(dx,'X offset');number(dy,'Y offset');
  if(!rows.length)return project;
  if(project.placements.length+rows.length>MAX_PLACEMENTS)throw Error('The placement limit is reached.');
  const used=new Set(project.placements.map(p=>p.id)),copies=new Map();
  const placements=rows.map(p=>{
    const id=freshId(idFactory,'placement',p.id,used);copies.set(p.id,id);
    return {...transformPlacement(p,{x:p.x+dx,y:p.y+dy}),id};
  });
  const state=metadata(project),groups=state.groups??[],groupIds=new Set(groups.map(g=>g.id));
  const newGroups=groups.filter(g=>g.placements.every(id=>copies.has(id))).map(g=>({
    id:freshId(idFactory,'group',g.id,groupIds),name:g.name,placements:g.placements.map(id=>copies.get(id))
  }));
  const next={...project,placements:[...project.placements,...placements]};
  return newGroups.length?withAuthoring(next,{...state,groups:[...groups,...newGroups]}):next;
}
export function pruneAuthoring(project) {
  if(project.authoring===undefined)return project;
  const valid=new Set(project.placements.map(p=>p.id)),state=metadata(project);
  const groups=(state.groups??[]).map(g=>({...g,placements:g.placements.filter(id=>valid.has(id))})).filter(g=>g.placements.length>=2);
  const links=(state.links??[]).filter(link=>valid.has(link.a)&&valid.has(link.b));
  return withAuthoring(project,{...state,groups,locked:(state.locked??[]).filter(id=>valid.has(id)),links});
}
export function removeSelection(project,ids) {
  const rows=selected(project,ids,{editable:true});if(!rows.length)return project;
  const removed=new Set(rows.map(p=>p.id)),placements=project.placements.filter(p=>!removed.has(p.id)),used=new Set(placements.map(p=>p.vinylId));
  return pruneAuthoring({...project,placements,vinyls:project.vinyls.filter(v=>used.has(v.id))});
}
function boundsOf(rows,getBounds) {
  if(!rows.length)throw Error('Select at least one placement.');
  if(typeof getBounds!=='function')throw Error('Artwork bounds are required.');
  let left=Infinity,top=Infinity,right=-Infinity,bottom=-Infinity;
  for(const row of rows) {
    const bounds=getBounds(row.id);
    if(!Array.isArray(bounds)||bounds.length!==4||!bounds.every(v=>typeof v==='number'&&Number.isFinite(v))||bounds[0]>=bounds[2]||bounds[1]>=bounds[3]||bounds[0]<0||bounds[1]<0||bounds[2]>SECTION_SIZE[0]||bounds[3]>SECTION_SIZE[1])throw Error('Invalid artwork bounds.');
    const matrix=placementMatrix(row);
    for(const x of [bounds[0],bounds[2]])for(const y of [bounds[1],bounds[3]]) {
      const [cx,cy]=mapPoint(matrix,x-SECTION_SIZE[0]/2,y-SECTION_SIZE[1]/2);
      number(cx,'transformed bound');number(cy,'transformed bound');
      left=Math.min(left,cx);right=Math.max(right,cx);top=Math.min(top,cy);bottom=Math.max(bottom,cy);
    }
  }
  return {left,top,right,bottom,cx:(left+right)/2,cy:(top+bottom)/2,section:rows[0].section};
}
export function selectionBounds(project,ids,getBounds) {
  return boundsOf(selected(project,ids,{sameSection:true}),getBounds);
}
function changedPlacements(project,changes) {
  if(!changes.size)return project;
  return {...project,placements:project.placements.map(p=>changes.get(p.id)??p)};
}
function tolerantPatch(placement,patch) {
  const limits={x:[-4096,4096],y:[-4096,4096],scaleX:[.01,8],scaleY:[.01,8],rotation:[-3600,3600],skew:[-4,4]};
  for(const [key,[min,max]] of Object.entries(limits))if(Object.hasOwn(patch,key)) {
    const n=patch[key],epsilon=1e-10;
    if(n<min&&n>=min-epsilon)patch[key]=min;
    if(n>max&&n<=max+epsilon)patch[key]=max;
  }
  return transformPlacement(placement,patch);
}
export function transformSelection(project,ids,anchorId,patch,getBounds) {
  const rows=selected(project,ids,{editable:true,sameSection:true}),anchor=rows.find(p=>p.id===anchorId);
  if(!anchor)throw Error('The anchor must be selected.');
  const target=transformPlacement(anchor,patch),dx=target.x-anchor.x,dy=target.y-anchor.y;
  if(rows.length===1)return changedPlacements(project,new Map([[anchor.id,target]]));
  const affine=['scaleX','scaleY','rotation','skew'].some(key=>(target[key]??0)!==(anchor[key]??0));
  if(!affine&&!dx&&!dy&&target.opacity===anchor.opacity&&!Object.hasOwn(patch,'opacity'))return project;
  const changes=new Map();
  if(!affine) {
    for(const p of rows)changes.set(p.id,tolerantPatch(p,{x:p.x+dx,y:p.y+dy,...(Object.hasOwn(patch,'opacity')?{opacity:target.opacity}:{})}));
    return changedPlacements(project,changes);
  }
  // The common affine delta is evaluated against the gesture-start placements.
  const pivot=boundsOf(rows,getBounds),a=placementMatrix(anchor),b=placementMatrix(target),det=a[0]*a[3]-a[1]*a[2];
  if(!Number.isFinite(det)||Math.abs(det)<1e-12)throw Error('Invalid anchor transform.');
  const d=[(b[0]*a[3]-b[2]*a[1])/det,(b[1]*a[3]-b[3]*a[1])/det,
    (b[2]*a[0]-b[0]*a[2])/det,(b[3]*a[0]-b[1]*a[2])/det];
  for(const p of rows) {
    const m=placementMatrix(p),linear=[d[0]*m[0]+d[2]*m[1],d[1]*m[0]+d[3]*m[1],d[0]*m[2]+d[2]*m[3],d[1]*m[2]+d[3]*m[3]];
    const scaleX=Math.hypot(linear[0],linear[1]),scaleY=(linear[0]*linear[3]-linear[1]*linear[2])/scaleX;
    let rotation=Math.atan2(-linear[1],linear[0])*180/Math.PI;
    rotation+=360*Math.round((p.rotation+target.rotation-anchor.rotation-rotation)/360);
    const cx=m[4]-pivot.cx,cy=m[5]-pivot.cy;
    changes.set(p.id,tolerantPatch(p,{
      x:pivot.cx+d[0]*cx+d[2]*cy+dx-SECTION_SIZE[0]/2,
      y:SECTION_SIZE[1]/2-(pivot.cy+d[1]*cx+d[3]*cy-dy),scaleX,scaleY,rotation,
      skew:-(linear[0]*linear[2]+linear[1]*linear[3])/(scaleX*scaleY),
      ...(Object.hasOwn(patch,'opacity')?{opacity:target.opacity}:{})
    }));
  }
  return changedPlacements(project,changes);
}
function alignmentUnits(project,ids,getBounds) {
  const rows=selected(project,ids,{editable:true,sameSection:true}),remaining=new Map(rows.map(p=>[p.id,p])),units=[];
  for(const group of project.authoring?.groups??[])if(group.placements.every(id=>remaining.has(id))) {
    const members=group.placements.map(id=>remaining.get(id));
    group.placements.forEach(id=>remaining.delete(id));units.push({members,bounds:boundsOf(members,getBounds)});
  }
  for(const row of remaining.values())units.push({members:[row],bounds:boundsOf([row],getBounds)});
  return units;
}
function translateUnit(changes,unit,dx,dy) {
  for(const row of unit.members)changes.set(row.id,tolerantPatch(row,{x:row.x+dx,y:row.y-dy}));
}
export function alignSelection(project,ids,mode,getBounds) {
  const modes={left:['left','x'],centerX:['cx','x'],right:['right','x'],top:['top','y'],centerY:['cy','y'],bottom:['bottom','y']};
  if(!Object.hasOwn(modes,mode))throw Error('Invalid alignment mode.');
  const units=alignmentUnits(project,ids,getBounds);if(units.length<2)return project;
  const union=boundsOf(units.flatMap(unit=>unit.members),getBounds),[field,axis]=modes[mode],target=union[field],changes=new Map();
  for(const unit of units)translateUnit(changes,unit,axis==='x'?target-unit.bounds[field]:0,axis==='y'?target-unit.bounds[field]:0);
  return changedPlacements(project,changes);
}
export function distributeSelection(project,ids,axis,getBounds) {
  if(axis!=='x'&&axis!=='y')throw Error('Invalid distribution axis.');
  const units=alignmentUnits(project,ids,getBounds);if(units.length<3)return project;
  const start=axis==='x'?'left':'top',end=axis==='x'?'right':'bottom';
  units.sort((a,b)=>a.bounds[start]-b.bounds[start]);
  const first=units[0].bounds[start],last=units.at(-1).bounds[end];
  const gap=(last-first-units.reduce((sum,unit)=>sum+unit.bounds[end]-unit.bounds[start],0))/(units.length-1),changes=new Map();
  let cursor=first;
  for(const unit of units){const delta=cursor-unit.bounds[start];translateUnit(changes,unit,axis==='x'?delta:0,axis==='y'?delta:0);cursor+=unit.bounds[end]-unit.bounds[start]+gap;}
  return changedPlacements(project,changes);
}
export function snapTranslation(project,ids,{dx,dy,grid=0,tolerance=6}={},getBounds) {
  number(dx,'X offset');number(dy,'Y offset');number(grid,'grid');number(tolerance,'snap tolerance');
  if(grid<0||tolerance<0)throw Error('Grid and snap tolerance must be non-negative.');
  const rows=selected(project,ids,{editable:true,sameSection:true}),bounds=boundsOf(rows,getBounds),chosen=new Set(rows.map(p=>p.id));
  const xTargets=[0,SECTION_SIZE[0]/2,SECTION_SIZE[0]],yTargets=[0,SECTION_SIZE[1]/2,SECTION_SIZE[1]];
  for(const p of project.placements)if(!chosen.has(p.id)&&p.section===bounds.section&&p.visible&&p.opacity>0) {
    const b=boundsOf([p],getBounds);xTargets.push(b.left,b.cx,b.right);yTargets.push(b.top,b.cy,b.bottom);
  }
  const match=(points,targets)=>{
    let best=null;
    for(const point of points)for(const target of targets){const delta=target-point;if(Math.abs(delta)<=tolerance&&(!best||Math.abs(delta)<Math.abs(best.delta)))best={delta,target};}
    // Explicit object/section guides take precedence over the optional grid.
    if(!best&&grid>0)for(const point of points){const target=Math.round(point/grid)*grid,delta=target-point;if(Math.abs(delta)<=tolerance&&(!best||Math.abs(delta)<Math.abs(best.delta)))best={delta,target};}
    return best;
  };
  const x=match([bounds.left+dx,bounds.cx+dx,bounds.right+dx],xTargets),y=match([bounds.top-dy,bounds.cy-dy,bounds.bottom-dy],yTargets);
  return {dx:dx+(x?.delta??0),dy:dy-(y?.delta??0),snappedX:!!x,snappedY:!!y,guideX:x?.target??null,guideY:y?.target??null};
}
const color=value=>{
  if(!Array.isArray(value)||value.length!==4||!value.every(n=>Number.isInteger(n)&&n>=0&&n<=255))throw Error('Invalid RGBA color.');
  return value;
};
export function replaceSelectionColor(project,ids,fromRGBA,toRGBA,{idFactory}={}) {
  color(fromRGBA);color(toRGBA);
  const rows=selected(project,ids,{editable:true}),chosen=new Set(rows.map(p=>p.id)),sources=new Set(rows.map(p=>p.vinylId));
  if(fromRGBA.every((n,i)=>n===toRGBA[i]))return project;
  const matches=shape=>!shape.mask&&!shape.data?.[6]&&shape.color?.length===4&&shape.color.every((n,i)=>n===fromRGBA[i]);
  const used=new Set(project.vinyls.map(v=>v.id)),revisions=new Map(),added=[];
  for(const source of project.vinyls)if(sources.has(source.id)&&source.shapes.some(matches)) {
    const id=freshId(idFactory,'vinyl',source.id,used),shapes=source.shapes.map(shape=>{
      const next=structuredClone(shape);
      if(matches(shape))next.color=[...toRGBA];
      return next;
    });
    revisions.set(source.id,id);added.push({...source,id,shapes});
  }
  if(!added.length)return project;
  const placements=project.placements.map(p=>chosen.has(p.id)&&revisions.has(p.vinylId)?{...p,vinylId:revisions.get(p.vinylId)}:p),active=new Set(placements.map(p=>p.vinylId));
  const vinyls=[...project.vinyls.filter(v=>!revisions.has(v.id)||active.has(v.id)),...added];
  if(vinyls.length>MAX_VINYLS)throw Error('The vinyl source limit is reached.');
  return {...project,placements,vinyls};
}
