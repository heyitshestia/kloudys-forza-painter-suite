export const BODY_PARTS = Object.freeze(['CarBody','ChassisStiffness','FrontBumper','Hood','RearBumper','RearWing','SideSkirts']);

export function validateGarageBuild(value) {
  if(!value||typeof value!=='object'||Array.isArray(value)||value.version!==1||
    Object.keys(value).sort().join(',')!=='fingerprint,parts,version'||
    typeof value.fingerprint!=='string'||!/^[a-f0-9]{64}$/.test(value.fingerprint)||
    !value.parts||typeof value.parts!=='object'||Array.isArray(value.parts)||
    Object.keys(value.parts).sort().join(',')!==[...BODY_PARTS].sort().join(','))throw Error('The Garage body configuration is invalid. Refresh Garage and retry.');
  for(const [part,id] of Object.entries(value.parts)) {
    if(id!==null&&(!Number.isInteger(id)||id< -1||id>2147483647))throw Error(`Invalid Garage part ID: ${part}.`);
  }
  return {version:1,parts:{...value.parts},fingerprint:value.fingerprint};
}

export function resolveGarageBuild(value,catalog) {
  const build=validateGarageBuild(value),selection={};
  for(const part of BODY_PARTS) {
    const options=catalog.groups.get(part)||[],id=build.parts[part];
    if(!options.length) {
      if(id===null||id<=0)continue;
      throw Error(`The car model does not declare Garage component ${part} (ID ${id}).`);
    }
    if(id===null)throw Error(`Garage is missing ${part}. Refresh Garage before opening this build.`);
    const option=options.find(row=>row.id===id);
    if(!option||option.available!==true||catalog.duplicates.some(row=>row.part_type===part&&row.id===id))throw Error(`Unavailable Garage component: ${part} (ID ${id}). No stock substitute was applied.`);
    selection[part]=id;
  }
  for(const [part,id] of Object.entries(selection)) {
    const option=catalog.groups.get(part).find(row=>row.id===id),required=catalog.bodyParents.get(option.car_body_id);
    if(part!=='CarBody'&&required!==undefined&&required!==selection.CarBody)throw Error(`Garage component ${part} is incompatible with the selected body.`);
  }
  return selection;
}
