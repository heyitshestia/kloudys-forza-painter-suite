// Theme-owned controls; all document mutations belong to the editor transaction API.
import {t,localizeStatic,errorText} from './i18n.mjs';
export function initializeStudioTools(api) {
  const $=id=>document.getElementById(id), controller=new AbortController(), signal=controller.signal;
  const host=document.createElement('div');host.id='studioTools';
  host.innerHTML=`<details id="selectionTools" open><summary>Selection and groups</summary>
    <p id="multiSelectionCount" role="status">No placements selected</p>
    <div class="qol-row"><button id="selectSection">Select section</button><button id="clearSelection">Clear</button></div>
    <label class="field">Group name<input id="groupName" maxlength="80" placeholder="Sponsor group"></label>
    <div class="qol-row"><button id="groupSelection">Group</button><button id="ungroupSelection">Ungroup</button><button id="lockSelection">Lock</button><button id="unlockSelection">Unlock</button></div>
    <div class="qol-row"><select id="alignment" aria-label="Alignment"><option value="left">Left edges</option><option value="centerX">Horizontal centres</option><option value="right">Right edges</option><option value="top">Top edges</option><option value="centerY">Vertical centres</option><option value="bottom">Bottom edges</option></select><button id="alignSelection">Align</button></div>
    <div class="qol-row"><button id="distributeX">Space horizontally</button><button id="distributeY">Space vertically</button></div>
    <label class="qol-check"><input id="snapGuides" type="checkbox">Snap to centres and artwork</label><p id="snapStatus" role="status"></p>
  </details>
  <details id="symmetryTools"><summary>Linked sides</summary>
    <label class="field">Artwork orientation<select id="mirrorMode"><option value="readable">Readable lettering</option><option value="mirror">Mirrored artwork</option></select></label>
    <div class="qol-row"><button id="createOtherSide">Create other side</button><button id="linkMirror">Link aligned pair</button><button id="applyMirrorMode">Update orientation</button><button id="unlinkMirror">Unlink</button></div><p id="mirrorStatus" role="status"></p>
  </details>
  <details id="colourTools"><summary>Design colours</summary>
    <label class="field">Apply to<select id="colourScope"><option value="selection">Selected placements</option><option value="all">Whole design</option></select></label>
    <div id="colourSwatches" aria-label="Artwork colours"></div>
    <div class="qol-row"><input id="replacementColour" type="color" value="#ff3366" aria-label="Replacement colour"><button id="replaceColour">Replace colour</button></div><p id="colourStatus" role="status"></p>
  </details>
  <details id="sourceEditTools"><summary>Edit source artwork</summary><div class="qol-row"><button id="editSource">Open in 2D editor</button><button id="checkSourceEdit">Check changes</button></div>
    <label class="field">Returned artwork<select id="sourceEditScope"><option value="all">Update all instances</option><option value="selection">Make selected instance independent</option></select></label>
    <div class="qol-row"><button id="applySourceEdit">Apply returned artwork</button><button id="cancelSourceEdit">Cancel edit link</button></div><p id="sourceEditStatus" role="status"></p>
  </details><div id="inspectionToolsHost"></div><div id="recoveryToolsHost"></div><details><summary>Action confirmations</summary><button id="resetConfirmations" type="button" title="Re-enable explanations for colour changes and source editing. Safety warnings are always separate.">Show confirmations again</button></details>`;
  localizeStatic(host);$('authoring').append(host);
  const stack=document.createElement('dialog');stack.id='placementStack';stack.setAttribute('aria-labelledby','placementStackTitle');
  stack.innerHTML='<h2 id="placementStackTitle">Artwork under pointer</h2><div id="placementStackItems"></div><form method="dialog" class="actions"><button>Close</button></form>';
  localizeStatic(stack);document.body.append(stack);
  let disposed=false,colourKey=null,signature='';
  const command=(id,action,args=()=>[])=>$(id).addEventListener('click',()=>Promise.resolve(api.action(action,...args())).catch(error=>api.message(errorText(error),true)),{signal});
  for(const [id,action,args] of [
    ['selectSection','selectSection'],['clearSelection','clearSelection'],['groupSelection','group',()=>[$('groupName').value]],
    ['ungroupSelection','ungroup'],['lockSelection','lock'],['unlockSelection','unlock'],
    ['alignSelection','align',()=>[$('alignment').value]],['distributeX','distribute',()=>['x']],['distributeY','distribute',()=>['y']],
    ['createOtherSide','createOtherSide',()=>[$('mirrorMode').value]],['linkMirror','linkMirror',()=>[$('mirrorMode').value]],['applyMirrorMode','mirrorMode',()=>[$('mirrorMode').value]],['unlinkMirror','unlinkMirror'],
    ['replaceColour','replaceColour',()=>[colourKey,$('replacementColour').value,$('colourScope').value]],
    ['editSource','editSource'],['checkSourceEdit','checkSourceEdit'],['applySourceEdit','applySourceEdit',()=>[$('sourceEditScope').value]],['cancelSourceEdit','cancelSourceEdit'],['resetConfirmations','resetConfirmations']
  ])command(id,action,args);
  $('colourScope').addEventListener('change',()=>{signature='';refresh();},{signal});
  $('snapGuides').title=t('Snap placement centres and artwork edges; hold Ctrl while dragging to bypass');
  $('selectSection').title=t('Select every placement on the current section (Ctrl+A)');
  $('groupSelection').title=t('Group selected placements (Ctrl+G)');$('ungroupSelection').title=t('Ungroup (Ctrl+Shift+G)');
  function refresh() {
    if(disposed)return;
    const state=api.state(),ids=state.selectedIds||[],locked=state.locked||[];
    $('multiSelectionCount').textContent=t`${ids.length} selected`+(locked.length?t` / ${locked.length} locked`:'');
    for(const id of ['groupSelection','alignSelection','distributeX','distributeY'])$(id).disabled=state.busy||ids.length<2||locked.length>0;
    for(const id of ['ungroupSelection','lockSelection','unlockSelection','linkMirror','unlinkMirror','replaceColour','editSource'])$(id).disabled=state.busy||!ids.length;
    $('linkMirror').disabled=state.busy||ids.length!==2||locked.length>0;
    const links=(state.project.authoring?.links||[]).filter(link=>ids.includes(link.a)||ids.includes(link.b));
    $('applyMirrorMode').disabled=state.busy||!links.length||locked.length>0;
    $('unlinkMirror').disabled=state.busy||!links.length;
    $('createOtherSide').disabled=state.busy||ids.length!==1||locked.length>0;
    $('selectSection').disabled=$('clearSelection').disabled=state.busy;
    $('resetConfirmations').disabled=state.busy;
    $('editSource').disabled=state.busy||ids.length!==1||locked.length>0||!state.sourceEditorAvailable||!!state.sourceEditing;
    $('checkSourceEdit').disabled=$('cancelSourceEdit').disabled=state.busy||!state.sourceEditing;
    $('applySourceEdit').disabled=state.busy||!['ready','taken'].includes(state.sourceEditing?.status);
    $('mirrorStatus').textContent=links.length?t`${links.length} linked pair(s): ${[...new Set(links.map(link=>t(link.mode==='mirror-artwork'?'mirrored artwork':'readable lettering')))].join(', ')}`:t('User-aligned pairs. Automatic physical side matching is unverified.');
    const scope=$('colourScope').value,selected=new Set(ids),sourceIds=new Set(state.project.placements.filter(p=>scope==='all'||selected.has(p.id)).map(p=>p.vinylId));
    const next=JSON.stringify([scope,[...sourceIds],state.project.vinyls.map(v=>v.id)]);
    if(next!==signature){
      signature=next;const colours=new Map();
      for(const source of state.project.vinyls)if(sourceIds.has(source.id))for(const shape of source.shapes){
        if(shape.data?.[6]||shape.mask)continue;
        const rgb=shape.color?.slice(0,3);if(!rgb||rgb.length!==3)continue;
        const key=rgb.join(',');colours.set(key,(colours.get(key)||0)+1);
      }
      if(!colours.has(colourKey))colourKey=colours.keys().next().value||null;
      $('colourSwatches').replaceChildren();
      for(const [key,count] of colours){
        const button=document.createElement('button');button.type='button';button.className='colour-swatch';button.dataset.colour=key;
        const colour='#'+key.split(',').map(v=>Number(v).toString(16).padStart(2,'0')).join('');
        button.style.setProperty('--swatch',colour);button.title=t`${colour} / ${count} shapes`;button.setAttribute('aria-label',button.title);
        button.setAttribute('aria-pressed',String(key===colourKey));
        button.addEventListener('click',()=>{colourKey=key;for(const item of $('colourSwatches').children)item.setAttribute('aria-pressed',String(item===button));});
        $('colourSwatches').append(button);
      }
      $('colourStatus').textContent=t`${colours.size} colours`;
    }
    $('replaceColour').disabled=state.busy||!colourKey||locked.length>0;
  }
  return {refresh,host, snapping:()=>!disposed&&$('snapGuides').checked,
    status:(id,text)=>{if(!disposed)$(id).textContent=t(text);},
    showStack(placements){
      if(disposed||!placements.length)return;const items=$('placementStackItems');items.replaceChildren();
      for(const placement of placements){
        const button=api.artworkButton(placement);button.addEventListener('click',()=>{stack.close();api.select(placement.id,{individual:true});},{once:true});items.append(button);
      }
      stack.showModal();items.firstElementChild?.focus();
    },dispose(){disposed=true;controller.abort();if(stack.open)stack.close();host.remove();stack.remove();}};
}
