export const WHEEL_CORNERS = Object.freeze(['front_left', 'front_right', 'rear_left', 'rear_right']);

export function placeholderWheelSpecs(assembly) {
  if (assembly?.format !== 'kfps_fh6_local_vehicle_assembly_v1') return [];
  const result = [];
  for (const corner of WHEEL_CORNERS) {
    const center = assembly.wheel_centers?.[corner];
    const dimensions = assembly.wheel_dimensions?.[corner] ?? assembly;
    const {tire_radius: radius, tire_width: width, rim_radius: rimRadius} = dimensions;
    if (!Array.isArray(center) || center.length !== 3
      || center.some(value => typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > 10)
      || [radius, width, rimRadius].some(value => typeof value !== 'number' || !Number.isFinite(value) || value <= 0)
      || radius > 2 || width > 1 || rimRadius >= radius) return [];
    result.push({corner, center: [...center], radius, width, rimRadius,
      nominalSize: dimensions.nominal_size ?? null});
  }
  return result;
}

export function placeholderFloorY(assembly, fallback) {
  const wheels = placeholderWheelSpecs(assembly);
  return wheels.length === 4 ? Math.min(...wheels.map(wheel => wheel.center[1] - wheel.radius)) : fallback;
}
