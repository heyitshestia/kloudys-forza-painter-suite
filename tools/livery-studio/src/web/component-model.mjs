// Pure component/coverage rules. Parent-upgrade IDs are evidence, not a guessed
// compatibility graph; the viewer never infers relationships from ID values.
const integer = value => typeof value === 'number' && Number.isSafeInteger(value) ? value : null;
const flag = value => typeof value === 'boolean' ? value : null;

export function componentCatalog(values, fitment) {
  const groups = new Map(), duplicates = [];
  for (const value of Array.isArray(values) ? values : []) {
    const partType = typeof value?.part_type === 'string' ? value.part_type.trim() : '';
    const id = integer(value?.id);
    if (!partType || id === null) continue;
    if (!groups.has(partType)) groups.set(partType, []);
    const options = groups.get(partType);
    if (options.some(option => option.id === id)) { duplicates.push({part_type: partType, id}); continue; }
    options.push({
      part_type: partType, part_type_value: integer(value.part_type_value), id,
      level: integer(value.level), stock: value.stock === true,
      car_body_id: integer(value.car_body_id), parent_is_stock: flag(value.parent_is_stock),
      baseline: value.baseline === true,
      available: value.supported === false || value.available === false ? false : flag(value.supported ?? value.available),
      empty: flag(value.empty), declared_instance_count: integer(value.declared_instance_count),
      reason: [typeof value.reason === 'string' ? value.reason : '', ...(Array.isArray(value.issues) ? value.issues.filter(issue => typeof issue === 'string') : [])].filter(Boolean).join(' '),
    });
  }
  for (const options of groups.values()) {
    options.sort((a, b) => Number(b.stock) - Number(a.stock) || (a.level ?? 0) - (b.level ?? 0) || a.id - b.id);
  }
  const bodyParents=new Map();
  if(typeof fitment?.source==='string'&&fitment.source.trim()&&Array.isArray(fitment.parent_map)) {
    const ambiguous=new Set();
    for(const row of fitment.parent_map) {
      const parent=integer(row?.parent_upgrade_id),body=integer(row?.body_option_id);
      if(parent===null||body===null||!groups.get('CarBody')?.some(option=>option.id===body))continue;
      if(bodyParents.has(parent)&&bodyParents.get(parent)!==body)ambiguous.add(parent);
      bodyParents.set(parent,body);
    }
    for(const parent of ambiguous)bodyParents.delete(parent);
  }
  return {groups, duplicates, bodyParents, fitmentSource:fitment?.source||''};
}

export function initialComponentSelection(catalog) {
  const selection = new Map();
  for (const [partType, options] of catalog.groups) {
    const baseline = options.filter(option => option.baseline && option.available !== false);
    const stock = options.filter(option => option.stock && option.available !== false);
    selection.set(partType, baseline.length === 1 ? baseline[0].id : stock.length === 1 ? stock[0].id : null);
  }
  reconcileBodySelection(catalog, selection);
  return selection;
}

export function selectComponent(catalog, selection, partType, id) {
  const options = catalog.groups.get(partType);
  if (!options || (id !== null && !options.some(option => option.id === id && option.available !== false && componentCompatibility(option,catalog,selection) !== false))) return false;
  selection.set(partType, id);
  if (partType === 'CarBody') reconcileBodySelection(catalog, selection);
  return true;
}

export function componentMeshVisible(metadata, selection) {
  const ids = Array.isArray(metadata?.kfps_part_option_ids)
    ? metadata.kfps_part_option_ids.filter(value => integer(value) !== null) : [];
  // Untagged meshes include unconditional shared geometry and legacy stock GLBs.
  if (!ids.length) return true;
  const selected = selection.get(String(metadata?.kfps_part_type || ''));
  if (selection.has(String(metadata?.kfps_part_type || '')) && selected === null) return false;
  return integer(selected) !== null ? ids.includes(selected) : metadata.kfps_stock_part === true;
}

export function componentLabel(option) {
  const kind = option.stock ? 'Stock' : option.level !== null ? `Level ${option.level}` : 'Option';
  return `${kind} (ID ${option.id})${option.empty === true ? ' - empty' : ''}${option.available === false ? ' - unavailable' : ''}`;
}

export function parentEvidence(option, catalog) {
  const id = option.car_body_id;
  const matches = [];
  if (id !== null) {
    for (const [partType, options] of catalog.groups) {
      if (partType !== option.part_type && options.some(candidate => candidate.id === id)) matches.push(partType);
    }
  }
  return {id, parent_is_stock: option.parent_is_stock, matching_part_types: matches, verified: false,
    mapped_body_option:catalog.bodyParents.get(id)??null,mapping_source:catalog.bodyParents.has(id)?catalog.fitmentSource:''};
}

// GR86's parent-upgrade ID differs from its body model-option ID. Require an
// externally evidenced mapping; equality, suffix arithmetic and stock flags
// cannot establish that relationship.
export function componentCompatibility(option, catalog, selection) {
  if (option.part_type === 'CarBody') return true;
  const required=catalog.bodyParents.get(option.car_body_id);
  if(required===undefined)return null;
  const body=selection.get('CarBody');
  return integer(body) !== null ? body === required : false;
}

function reconcileBodySelection(catalog,selection) {
  for (const [partType,options] of catalog.groups) {
    if(partType==='CarBody')continue;
    const current=options.find(option=>option.id===selection.get(partType));
    if(current && componentCompatibility(current,catalog,selection)!==false)continue;
    const candidates=options.filter(option=>option.available!==false&&componentCompatibility(option,catalog,selection)===true);
    const baseline=candidates.filter(option=>option.baseline),stock=candidates.filter(option=>option.stock);
    const chosen=(baseline.length===1?baseline:stock.length===1?stock:candidates)[0];
    if(chosen)selection.set(partType,chosen.id);
    else if(current && componentCompatibility(current,catalog,selection)===false)selection.set(partType,null);
  }
}

export function validateVehicleParts(value,catalog) {
  if(value===undefined)return initialComponentSelection(catalog);
  if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Invalid vehicle_parts map.');
  const selection=initialComponentSelection(catalog);
  for(const [partType,id] of Object.entries(value)) {
    const options=catalog.groups.get(partType);
    if(!options|| (id!==null&&(integer(id)===null||!options.some(option=>option.id===id&&option.available!==false))))throw Error(`Unavailable component selection: ${partType}.`);
    selection.set(partType,id);
  }
  for(const [partType,id] of selection) {
    const option=catalog.groups.get(partType).find(item=>item.id===id);
    if(option&&componentCompatibility(option,catalog,selection)===false)throw Error(`Component ${partType} is incompatible with the selected body.`);
  }
  return selection;
}

export function inspectNativeUvChannels(geometry, declared = {}, cache = null) {
  const expected = Object.keys(declared || {}).filter(key => /^(0|[1-9][0-9]*)$/.test(key))
    .map(Number).filter(Number.isSafeInteger).sort((a,b) => a-b);
  const cached = cache?.get(geometry);
  if (cached) return {available:[...cached.available], invalid:[...cached.invalid],
    missing:expected.filter(channel => !cached.available.includes(channel))};
  const channels = new Map();
  for (const name of Object.keys(geometry?.attributes || {})) {
    let channel = name === 'uv' ? 0 : /^uv[1-3]$/.test(name) ? Number(name.slice(2)) : null;
    const custom = /^texcoord_(0|[1-9][0-9]*)$/.exec(name);
    if (custom && Number.isSafeInteger(Number(custom[1])) && Number(custom[1]) >= 4) channel = Number(custom[1]);
    if (channel !== null) channels.set(channel, geometry.getAttribute(name));
  }
  const available = [...channels.keys()].sort((a,b) => a-b), invalid = [];
  const position = geometry?.getAttribute('position');
  for (const channel of available) {
    const uv = channels.get(channel);
    if (!uv || !position || !uv.count || uv.count !== position.count || uv.itemSize !== 2) {
      invalid.push(channel); continue;
    }
    for (let index = 0; index < uv.count; index++) {
      if (!Number.isFinite(uv.getX(index)) || !Number.isFinite(uv.getY(index))) {
        invalid.push(channel); break;
      }
    }
  }
  cache?.set(geometry, {available:[...available], invalid:[...invalid]});
  return {available, missing:expected.filter(channel => !channels.has(channel)), invalid};
}

export function inspectUv3(geometry) {
  const uv = geometry?.getAttribute('uv3'), position = geometry?.getAttribute('position');
  if (!uv) return 'missing';
  if (!position || uv.count !== position.count || !uv.count || uv.itemSize < 2) return 'invalid';
  for (let index = 0; index < uv.count; index++) {
    if (!Number.isFinite(uv.getX(index)) || !Number.isFinite(uv.getY(index))) return 'invalid';
  }
  return 'present';
}

export function summarizeComponents(catalog, selection, meshes) {
  const groups = [];
  for (const [partType, options] of catalog.groups) {
    const related = meshes.filter(mesh => mesh.part_type === partType);
    groups.push({part_type: partType, selected: selection.get(partType) ?? null, options: options.map(option => {
      const members = related.filter(mesh => mesh.option_ids.includes(option.id));
      const unconditional = related.filter(mesh => !mesh.option_ids.length);
      return {...option, parent: parentEvidence(option, catalog), compatible: componentCompatibility(option,catalog,selection), mesh_count: members.length,
        shared_unconditional_mesh_count: unconditional.length,
        visible_mesh_count: members.filter(mesh => mesh.visible).length,
        missing_uv3: members.filter(mesh => ['paint', 'glass'].includes(mesh.category) && mesh.uv3 !== 'present').length};
    })});
  }
  const surfaces = meshes.filter(mesh => ['paint', 'glass'].includes(mesh.category));
  const missing = surfaces.filter(mesh => mesh.uv3 === 'missing');
  const invalid = surfaces.filter(mesh => mesh.uv3 === 'invalid');
  const unrepresented = groups.flatMap(group => group.options.filter(option => option.mesh_count === 0 && option.empty !== true));
  const channels = {}, missingChannels = [], invalidChannels = [];
  for (const mesh of meshes) {
    for (const channel of mesh.native_uv?.available || []) channels[channel] = (channels[channel] || 0) + 1;
    for (const channel of mesh.native_uv?.missing || []) missingChannels.push({id:mesh.id, channel});
    for (const channel of mesh.native_uv?.invalid || []) invalidChannels.push({id:mesh.id, channel});
  }
  return {
    groups, duplicates: catalog.duplicates, mesh_count: meshes.length,
    visible_mesh_count: meshes.filter(mesh => mesh.visible).length,
    hidden_by_role: meshes.filter(mesh => mesh.category === 'hidden').length,
    hidden_by_source: meshes.filter(mesh => !mesh.source_visible).length,
    hidden_by_selection: meshes.filter(mesh => mesh.source_visible && mesh.category !== 'hidden' && !mesh.selected).length,
    meshes,
    native_uv: {channels, missing:missingChannels, invalid:invalidChannels},
    unmapped_visual_surfaces: meshes.filter(mesh => ['paint','glass'].includes(mesh.unpaintable_surface_role))
      .map(mesh => ({id:mesh.id, name:mesh.name, role:mesh.unpaintable_surface_role, visible:mesh.visible})),
    unrepresented_options: unrepresented.map(option => ({part_type: option.part_type, id: option.id})),
    uv3: {surface_count: surfaces.length, direct: surfaces.length - missing.length - invalid.length,
      missing: missing.length, invalid: invalid.length,
      visible_unmapped: surfaces.filter(mesh => mesh.visible && mesh.uv3 !== 'present').length,
      unmapped_meshes: [...missing, ...invalid].map(mesh => ({id: mesh.id, name: mesh.name, part_type: mesh.part_type, uv3: mesh.uv3, visible: mesh.visible}))},
  };
}

export function fidelityMessages(coverage, runtime, wheels, materials) {
  const declared = runtime?.summary || {}, uv = coverage.uv3;
  const messages = [
    'Game parity unverified. Source decoder not independently verified.',
    `${materials ? 'Source-aware studio materials' : 'Neutral inspection materials'}; ${wheels.native?.instances || 0} native wheel instances; ${wheels.count} placeholder wheels${wheels.visible ? '' : ' (hidden)'}.`,
    `UV3: ${uv.direct}/${uv.surface_count} paint/glass meshes present; ${uv.missing} missing, ${uv.invalid} invalid. ${uv.visible_unmapped} visible surfaces remain neutral/unmapped.`,
    'Guessed world projection is off. UV3 presence alone does not verify game wrapping.',
  ];
  if (materials) messages.push(`${materials.nativeValuesApplied} native parameter applications across ${materials.meshes} mesh instances. ${materials.unresolvedTextures} texture references remain unresolved. Physical shading and parameter colour encoding are approximations, not native shader parity.`);
  if (coverage.unmapped_visual_surfaces?.length) messages.push(`${coverage.unmapped_visual_surfaces.length} body/glass surface(s) retained without supported vinyl mapping in this preview. In-game paintability is unverified.`);
  const count = key => integer(declared[key]);
  if (count('declared_upgrade_options') !== null) {
    messages.push(`Source options: ${count('declared_upgrade_options')} declared, ${count('converted_options') ?? '?'} converted, ${count('unrepresented_options') ?? '?'} unrepresented${count('blocked_options')===null?'':`, ${count('blocked_options')} blocked`}.`);
  } else messages.push('Source component completeness is unknown (coverage not supplied).');
  if (count('uv_integrity_errors') > 0) messages.push(`UV integrity errors: ${count('uv_integrity_errors')}. Source UV equivalence is not established.`);
  if (coverage.unrepresented_options.length) messages.push(`${coverage.unrepresented_options.length} option(s) have no tagged meshes; empty versus missing is not confirmed.`);
  if (coverage.duplicates.length) messages.push('Duplicate option IDs in a component group; selection coverage is ambiguous.');
  if (Array.isArray(runtime?.limitations)) {
    for (const limitation of runtime.limitations) if (typeof limitation === 'string' && limitation.trim()) messages.push(limitation);
  }
  return messages;
}
