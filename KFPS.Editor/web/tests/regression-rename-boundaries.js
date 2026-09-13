async page => page.evaluate(async()=>{
  const results=[];
  for(const group of [false,true]){
    await loadPayload({shapes:Array.from({length:group?3:1},(_,i)=>({type:1048677,data:[i*30,0,1,1,0,0,0],color:[90,130,200,255],shape_name:'Original',
      ...(group?{editor_group_id:'rename-group',editor_group_name:'Original group'}:{})}))});
    canvas.setActiveObject(vinylObjects()[0]);
    const old=vinylObjects()[0],identity=o=>[o.kloudy.name,o.kloudy.group_id,o.kloudy.group_name];
    const original=JSON.stringify(identity(old)),prompt=requestTextInput;let release;
    requestTextInput=()=>new Promise(resolve=>{release=resolve;});
    try{
      const rename=group?renameSelectedGroup():renameSelectedLayer();
      documentDirty=false;await startBlankCanvas();release('Late rename');await rename;
      if(JSON.stringify(identity(old))!==original||vinylObjects().length||editorHistory.index!==0)throw Error('Late rename crossed document replacement');
    }finally{requestTextInput=prompt;}
    results.push({group,staleRenameIgnored:true});
  }
  return results;
})
