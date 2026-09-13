async page => page.evaluate(async () => {
  const cases=[
    ['delete','refreshLayers',()=>deleteSelected()],
    ['add','refreshLayers',()=>addShape('Primitives',30)],
    ['color','updateSelectionPanel',()=>applyEditorColor([210,80,90,128])],
    ['group','refreshLayers',()=>groupSelectedLayers()],
    ['ungroup','refreshLayers',()=>ungroupSelectedLayers(),true],
    ['hide group','refreshLayers',()=>toggleSelectedGroupVisibility(),true],
    ['lock group','refreshLayers',()=>toggleSelectedGroupLock(),true],
    ['mask','updateSelectionPanel',()=>toggleSelectedMaskLayers()],
    ['order','refreshLayers',()=>moveSelected(1)],
    ['front','refreshLayers',()=>moveSelectedToEdge(true)],
    ['flip','updateSelectionPanel',()=>flipSelected('x')],
    ['align','updateSelectionPanel',()=>alignSelected('left')],
    ['distribute','updateSelectionPanel',()=>distributeSelected('x')],
    ['quarter turn','updateSelectionPanel',()=>rotateSelectedQuarter(1)],
  ];
  const results=[];
  for(const [name,hook,action,grouped]of cases){
    await loadPayload({shapes:Array.from({length:300},(_,i)=>({type:1048677,
      data:[i%20*23+(i===1?5:0),Math.floor(i/20)*25+(i%3)*3,.1,.12,0,0,0],color:[80,120,220,255],
      ...(grouped&&i<3?{editor_group_id:'group-fixture',editor_group_name:'Fixture'}:{})}))});
    canvas.setActiveObject(styledActiveSelection(vinylObjects().slice(0,3)));
    const before=JSON.stringify(snapshotShapes()),index=editorHistory.index,revision=editorRecovery.revision;
    const originals=new Map([hook,'refreshLayers','updateSelectionPanel'].map(key=>[key,window[key]]));let injected=false;
    originals.forEach((original,key)=>{window[key]=(...args)=>{if(!injected&&JSON.stringify(snapshotShapes())!==before){injected=true;throw Error('Injected '+name+' refresh failure');}return original(...args);};});
    try{await action();}catch(_){}finally{originals.forEach((original,key)=>{window[key]=original;});}
    document.querySelectorAll('dialog[open]').forEach(d=>d.close());
    if(!injected||editorHistory.index!==index+1||editorRecovery.revision<=revision)
      throw Error(`${name}: edit escaped history/recovery or test did not inject; index=${editorHistory.index}, injected=${injected}`);
    if(JSON.stringify(snapshotShapes())!==JSON.stringify(currentHistoryState().shapes))throw Error(name+': committed history differs from scene');
    await flushPendingAutosave();
    if(!editorRecovery.status.serverOk)throw Error(name+': recovery not confirmed');
    await undo();
    if(JSON.stringify(snapshotShapes())!==before)throw Error(name+': exact undo failed');
    results.push({name,refreshFailureCommitted:true,oneUndo:true,recovery:true});
  }
  return results;
})
