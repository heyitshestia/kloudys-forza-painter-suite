import {t,number} from './i18n.mjs';
export const CONFIRMATION_KEYS=Object.freeze(['colour.selection.v1','colour.all.v1','source.open.v1','source.apply.selection.v1','source.apply.all.v1']);

export function validatePreferences(value) {
  if(!value||value.version!==1||!Array.isArray(value.skipped)||value.skipped.length>CONFIRMATION_KEYS.length
      ||new Set(value.skipped).size!==value.skipped.length||value.skipped.some(key=>!CONFIRMATION_KEYS.includes(key)))throw Error('Invalid action confirmation preferences.');
  return [...value.skipped];
}

const count=n=>n===1?t`${n} placement`:t`${n} placements`;
const unchanged=()=>t('Original JSON files and your saved project file are not overwritten. Undo restores the previous artwork.');
function linkedIds(project,ids) {
  const affected=new Set(ids);
  for(const link of project.authoring?.links||[])if(affected.has(link.a)||affected.has(link.b)){affected.add(link.a);affected.add(link.b);}
  return affected;
}

export function confirmationSpec(action,{project,next,selectedIds=[],sourceEdit,scope='selection',from,to}={}) {
  if(action==='colour'){
    const affected=next.placements.filter(p=>project.placements.find(old=>old.id===p.id)?.vinylId!==p.vinylId);
    if(!affected.length)return null;
    const linked=scope!=='all'&&affected.some(p=>!selectedIds.includes(p.id));
    return {key:`colour.${scope==='all'?'all':'selection'}.v1`,title:t(scope==='all'?'Replace colour across this design?':'Replace colour in the selection?'),acceptLabel:t('Replace colour'),paragraphs:[
      t`Replace ${from} with ${to} in ${t(scope==='all'?'the whole current design':'the selected artwork')}. This changes ${count(affected.length)}; opacity and masks stay unchanged.`,
      ...(linked?[t('Linked counterparts will also change. Unlink the pair first if you want to change only one side.')]:[]),
      ...(scope==='all'?[]:[t('Other unlinked copies keep their current colours.')]),unchanged()]};
  }
  if(action==='source.open'){
    const placement=project.placements.find(p=>p.id===selectedIds[0]),source=project.vinyls.find(v=>v.id===placement?.vinylId);
    if(!source)return null;
    return {key:'source.open.v1',title:t('Open this artwork in the 2D editor?'),acceptLabel:t('Open editor'),paragraphs:[
      t`Open "${source.name}" (${number(source.shapes.length)} shapes) in a separate editor window, using your selected native or Chrome editor setting.`,
      t('This does not change your livery. Edit the shapes, choose Return to Studio, then explicitly apply the result here. You can choose all instances or an independent instance when applying.'),
      t('Your current placement, original JSON and saved files remain unchanged. Closing the edit link does not close the separate editor.')]};
  }
  if(action==='source.apply'){
    const direct=scope==='all'?project.placements.filter(p=>p.vinylId===sourceEdit.vinylId).map(p=>p.id):[sourceEdit.placementId];
    const affected=linkedIds(project,direct),linked=affected.size>direct.length;
    return {key:`source.apply.${scope==='all'?'all':'selection'}.v1`,title:t(scope==='all'?'Update all instances of this artwork?':'Make this instance independent?'),acceptLabel:t('Apply artwork'),paragraphs:[
      scope==='all'?t`Replace every instance of this source in the current design. This updates ${count(affected.size)}, including any linked counterparts.`:
        t`Give the originally edited placement its own updated source. This updates ${count(affected.size)}. Other unlinked copies keep the old artwork.`,
      ...(linked?[t('Its linked counterpart will also update. Unlink the pair first to edit only one side.')]:[]),
      t('Placement position, scale, rotation and skew stay unchanged.'),unchanged()]};
  }
  throw Error('Unknown confirmation action.');
}
