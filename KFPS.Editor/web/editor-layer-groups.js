(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.KfpsEditorLayerGroups = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";
  const MAX_DEPTH = 64;
  const freshId = () => `group-${globalThis.crypto.randomUUID()}`;
  function shapePath(shape) {
    const source = shape.editor_group_path ?? (shape.editor_group_id
      ? [{ id: String(shape.editor_group_id), name: String(shape.editor_group_name || "") }] : []);
    if (!Array.isArray(source) || source.length > MAX_DEPTH) throw new Error("The project has invalid or excessively nested groups.");
    const ids = new Set();
    const path = source.map(group => {
      if (!group || typeof group.id !== "string" || !group.id || group.id.length > 256
        || typeof group.name !== "string" || group.name.length > 1024 || ids.has(group.id)) {
        throw new Error("The project has invalid or excessively nested groups.");
      }
      ids.add(group.id);
      return { id: group.id, name: group.name };
    });
    if (shape.editor_group_id && path.at(-1)?.id !== String(shape.editor_group_id)) throw new Error("The project has conflicting group information.");
    return path;
  }
  function objectPath(object) {
    const meta = object?.kloudy || {};
    return meta.group_path || (meta.group_id ? [{ id: String(meta.group_id), name: String(meta.group_name || "") }] : []);
  }
  function fields(path) {
    const last = path.at(-1);
    return {
      editor_group_id: last?.id || null, editor_group_name: last?.name || null,
      ...(path.length > 1 ? { editor_group_path: path.map(group => ({ ...group })) } : {}),
    };
  }
  function applyPath(object, path) {
    Object.assign(object.kloudy, {
      group_id: path.at(-1)?.id || null, group_name: path.at(-1)?.name || null,
      group_path: path.length > 1 ? path.map(group => ({ ...group })) : null,
    });
  }
  function cloneShapes(shapes, { outer = null, allocateGroupId = freshId } = {}) {
    const ids = new Map(), parents = new Map(), names = new Map();
    const copies = shapes.map(source => {
      const shape = JSON.parse(JSON.stringify(source));
      const path = shapePath(source);
      if (path.length + Number(Boolean(outer)) > MAX_DEPTH) throw new Error("The project has invalid or excessively nested groups.");
      let parent = null;
      const mapped = path.map(group => {
        if (parents.has(group.id) && parents.get(group.id) !== parent) throw new Error("The project has conflicting group information.");
        if (names.has(group.id) && names.get(group.id) !== group.name) throw new Error("The project has conflicting group information.");
        parents.set(group.id, parent);
        names.set(group.id, group.name);
        parent = group.id;
        if (!ids.has(group.id)) ids.set(group.id, allocateGroupId());
        return { ...group, id: ids.get(group.id) };
      });
      delete shape.editor_id;
      delete shape.editor_group_path;
      Object.assign(shape, fields(outer ? [{ ...outer }, ...mapped] : mapped));
      return shape;
    });
    return { shapes: copies, groupIds: ids };
  }
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
      const names = new Set(scene.all().flatMap(object=>objectPath(object).map(group=>group.name)).filter(Boolean));
      for (let i=1;i<10000;i++) { const name=tr("Group {0}",i); if(!names.has(name))return name; }
      return tr("Group {0}",Date.now().toString(36));
    }
    return {
      nextName,
      group() {
        const objects=scene.selected();
        if(objects.length<2){view.status(tr("Select two or more layers before creating a group."));return false;}
        const id=freshId(),name=nextName();
        let grouped;
        try { grouped=cloneShapes(objects.map(object=>fields(objectPath(object))),{outer:{id,name}}); }
        catch(error){view.status(tr(error.message));return false;}
        objects.forEach((object,index)=>applyPath(object,shapePath(grouped.shapes[index])));
        scene.expand(id);
        scene.focus?.(id);
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
        const current=scene.groupName(objects[0],ids[0]),generation=edits.generation();
        const name=await requestName(tr("Rename Editor Group"),tr("Group name"),current,
          tr("Groups organize the project only. The exported game JSON remains a flat layer list."));
        if(name===null||!valid(generation,objects)||objects.some(object=>!objectPath(object).some(group=>group.id===ids[0])))return false;
        const cleaned=String(name).trim().slice(0,64)||current;
        objects.forEach(object=>applyPath(object,objectPath(object).map(group=>group.id===ids[0]?{...group,name:cleaned}:group)));
        finish("rename group",tr("Renamed editor group to {0}. Export remains flat.",cleaned));
        return true;
      },
      ungroup() {
        const ids=scene.groupIds(),objects=ids.length?scene.members(ids):scene.selected().filter(object=>object.kloudy?.group_id);
        if(!objects.length){view.status(tr("Select a grouped layer before ungrouping."));return false;}
        for(const object of objects){
          const removed=new Set(ids.length?ids:[object.kloudy.group_id]);
          removed.forEach(id=>scene.expand(id));
          applyPath(object,objectPath(object).filter(group=>!removed.has(group.id)));
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
  return {create,shapePath,objectPath,fields,applyPath,cloneShapes,MAX_DEPTH};
});
