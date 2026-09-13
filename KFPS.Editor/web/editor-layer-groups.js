(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorLayerGroups = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  function create({ scene, edits, view, tr, requestName }) {
    const valid = (generation, objects) => generation === edits.generation() && objects.every(scene.attached);
    function finish(reason, message, render = false) {
      edits.commit(reason);
      try {
        if (render) view.render();
        view.refresh(); view.selection(); view.status(message);
      } catch (error) { view.failed(error); }
    }
    function nextName() {
      const names = new Set(scene.all().map(object=>object.kloudy?.group_name).filter(Boolean));
      for (let i=1;i<10000;i++) { const name=tr("Group {0}",i); if(!names.has(name))return name; }
      return tr("Group {0}",Date.now().toString(36));
    }
    return {
      nextName,
      group() {
        const objects=scene.selected();
        if(objects.length<2){view.status(tr("Select two or more layers before creating a group."));return false;}
        const id=`group-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`,name=nextName();
        for(const object of objects)Object.assign(object.kloudy,{group_id:id,group_name:name});
        scene.expand(id);
        finish("group layers",tr("{0}: grouped {1} layer(s). Export remains flat.",name,objects.length));
        return true;
      },
      async renameLayer() {
        const objects=scene.selected();
        if(objects.length!==1){view.status(tr("Select exactly one layer before renaming it."));return false;}
        const object=objects[0],generation=edits.generation();
        const current=object.kloudy?.name||scene.typeLabel(object.kloudy?.type||0);
        const name=await requestName(tr("Rename Layer"),tr("Layer name"),current,
          tr("This name is for project organization and does not change the native shape used in game."));
        if(name===null||!valid(generation,objects))return false;
        const cleaned=String(name).trim().slice(0,64)||current;
        object.kloudy.name=cleaned;
        finish("rename layer",tr("Renamed layer to {0}.",cleaned));
        return true;
      },
      async renameGroup() {
        const ids=scene.groupIds();
        if(!ids.length){view.status(tr("Select a grouped layer before renaming a group."));return false;}
        if(ids.length>1){view.status(tr("Select one editor group before renaming."));return false;}
        const objects=scene.members(ids);
        if(!objects.length){view.status(tr("Selected group has no editable layers."));return false;}
        const current=scene.groupName(objects[0]),generation=edits.generation();
        const name=await requestName(tr("Rename Editor Group"),tr("Group name"),current,
          tr("Groups organize the project only. The exported game JSON remains a flat layer list."));
        if(name===null||!valid(generation,objects)||objects.some(object=>object.kloudy.group_id!==ids[0]))return false;
        const cleaned=String(name).trim().slice(0,64)||current;
        objects.forEach(object=>{object.kloudy.group_name=cleaned;});
        finish("rename group",tr("Renamed editor group to {0}. Export remains flat.",cleaned));
        return true;
      },
      ungroup() {
        const ids=scene.groupIds(),objects=ids.length?scene.members(ids):scene.selected().filter(object=>object.kloudy?.group_id);
        if(!objects.length){view.status(tr("Select a grouped layer before ungrouping."));return false;}
        for(const object of objects){
          if(object.kloudy.group_id)scene.expand(object.kloudy.group_id);
          Object.assign(object.kloudy,{group_id:null,group_name:null});
        }
        finish("ungroup layers",tr("Removed editor grouping from {0} layer(s).",objects.length));
        return true;
      },
      toggleVisibility() {
        const objects=scene.selectedMembers();
        if(!objects.length){view.status(tr("Select a grouped layer before hiding/showing a group."));return false;}
        const hide=objects.some(object=>object.visible!==false);
        objects.forEach(object=>{object.visible=!hide;});
        finish(hide?"hide group":"show group",tr("{0} {1} layer(s) in selected group.",hide?tr("Hid"):tr("Showed"),objects.length),true);
        return true;
      },
      toggleLock() {
        const objects=scene.selectedMembers();
        if(!objects.length){view.status(tr("Select a grouped layer before locking/unlocking a group."));return false;}
        const lock=objects.some(object=>!object.kloudy?.locked);
        objects.forEach(object=>scene.lock(object,lock));
        finish(lock?"lock group":"unlock group",tr("{0} {1} layer(s) in selected group.",lock?tr("Locked"):tr("Unlocked"),objects.length),true);
        return true;
      },
    };
  }
  return {create};
});
