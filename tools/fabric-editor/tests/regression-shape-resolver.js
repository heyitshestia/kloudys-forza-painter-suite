async (page) => page.evaluate(async () => {
  const cases = [
    { code: 1051503, family: "Upper_Letters_7", index: 27 },
    { code: 1051512, family: "Upper_Letters_7", index: 36 },
    { code: 1051516, family: "Upper_Letters_7", index: 40 },
  ];
  const resolved = cases.map((expected) => ({
    expected,
    actual: typeCodeToResource(expected.code),
  }));
  const mismatches = resolved.filter(({ expected, actual }) => (
    !actual || actual.family !== expected.family || actual.index !== expected.index
  ));
  if (mismatches.length) {
    throw new Error(`Upper-letter resource resolution failed: ${JSON.stringify(mismatches)}`);
  }

  const objects = await Promise.all(cases.map((entry) => makeFabricObject({
    type: entry.code,
    data: [0, 0, 1, 1, 0, 0, 0],
    color: [255, 255, 255, 255],
    mask: false,
  })));
  const missing = objects.filter((object) => !object || !object.kloudy);
  if (missing.length) throw new Error(`${missing.length} valid upper-letter resource(s) failed to load.`);
  const upperFamilySlots = shapeCountForFamily("Upper_Letters_7");
  if (upperFamilySlots !== 40) {
    throw new Error(`Expected 40 upper-letter slots in the shape browser, received ${upperFamilySlots}.`);
  }

  return {
    resolved: resolved.map(({ actual }) => `${actual.family}:${actual.index}`),
    loadedObjects: objects.length,
    upperFamilySlots,
  };
})
