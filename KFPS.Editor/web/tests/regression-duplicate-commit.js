async page => {
  return await page.evaluate(async () => {
    const results = [];
    const shape = i => ({type:1048677,data:[(i%20)*12,Math.floor(i/20)*12,.1,.1,0,0,0],color:[80,150,220,255]});
    document.querySelectorAll("dialog[open]").forEach(dialog=>dialog.close());
    documentDirty=false; await startBlankCanvas();
    await loadPayload({shapes:Array.from({length:300},(_,i)=>shape(i))});
    const original = vinylObjects()[0];
    canvas.setActiveObject(original);
    const initialIndex = editorHistory.index;
    const previousRevision = editorRecovery.revision;
    const refresh = refreshLayers;
    let failed = false;
    refreshLayers = (...args) => { if (!failed) { failed=true; throw Error("Injected duplicate list-refresh failure"); } return refresh(...args); };
    try { await duplicateSelected(); } finally { refreshLayers = refresh; }
    if (vinylObjects().length!==301 || editorHistory.index!==initialIndex+1 || editorRecovery.revision<=previousRevision)
      throw Error(`Duplicate must be committed despite UI refresh failure: layers=${vinylObjects().length}, history=${editorHistory.index-initialIndex}, recovery=${editorRecovery.revision-previousRevision}`);
    await flushPendingAutosave();
    if (!editorRecovery.status.serverOk) throw Error("Duplicate did not reach app-folder recovery");
    results.push({case:"UI failure after commit", passed:true, layers:301});
    document.querySelectorAll("dialog[open]").forEach(dialog=>dialog.close());
    await undo();
    if(vinylObjects().length!==300) throw Error("One undo did not remove exactly the duplicate");
    await redo();
    if(vinylObjects().length!==301) throw Error("Redo did not restore duplicate");
    results.push({case:"single undo/redo",passed:true});
    const before = JSON.stringify(snapshotShapes());
    const index = editorHistory.index;
    canvas.setActiveObject(styledActiveSelection(vinylObjects().slice(0,3)));
    const add = canvas.add;
    let installs=0;
    canvas.add=function(...objects) { if(objects.some(o=>o.kloudy) && ++installs===2) throw Error("Injected partial installation"); return add.apply(this,objects); };
    try { await duplicateSelected(); } finally { canvas.add=add; }
    if(JSON.stringify(snapshotShapes())!==before || editorHistory.index!==index) throw Error("Failed installation changed committed artwork");
    document.querySelectorAll("dialog[open]").forEach(dialog=>dialog.close());
    results.push({case:"partial installation rollback",passed:true});
    return results;
  });
}
