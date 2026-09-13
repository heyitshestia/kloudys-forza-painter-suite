async page => page.evaluate(async () => {
  const shape=x=>({type:1048677,data:[x,0,1,1,0,0,0],color:[80,120,220,255]});
  await loadPayload({shapes:[shape(0),shape(100),shape(200)]});
  canvas.setActiveObject(vinylObjects()[0]); deleteSelected();
  const before=editorHistory.index;
  const refresh=refreshLayers; let injected=false, error=null;
  refreshLayers=(...args)=>{if(!injected){injected=true;throw Error('Injected history display failure');}return refresh(...args);};
  try{await undo();}catch(err){error=err.message;}finally{refreshLayers=refresh;}
  document.querySelectorAll('dialog[open]').forEach(d=>d.close());
  if(editorHistory.index!==before-1 || vinylObjects().length!==3)
    throw Error(`Undo display failure separated scene/history: layers=${vinylObjects().length}, index=${editorHistory.index}, error=${error}`);
  await flushPendingAutosave();
  const recovery=await readAutosavePayload();
  if(!editorRecovery.status.serverOk||recovery.shapes.length!==3)throw Error('Undo did not reach recovery');
  await redo();
  if(vinylObjects().length!==2)throw Error('Redo after display failure is incorrect');
  vinylObjects().forEach(o=>o.set({left:o.left+20}));pushHistory('rollback fixture');
  const original=JSON.stringify(snapshotShapes()),index=editorHistory.index;
  const apply=applyHistoryShapeToObject;let calls=0,failed=false;
  applyHistoryShapeToObject=(...args)=>{if(++calls===2)throw Error('Injected partial reuse installation');return apply(...args);};
  try{await undo();}catch(_){failed=true;}finally{applyHistoryShapeToObject=apply;}
  if(!failed||JSON.stringify(snapshotShapes())!==original||editorHistory.index!==index||historyLocked)
    throw Error('Failed history installation did not roll back exact geometry/history');
  return {displayFailureCommitted:true,recovery:true,redo:true,partialReuseRollback:true};
})
