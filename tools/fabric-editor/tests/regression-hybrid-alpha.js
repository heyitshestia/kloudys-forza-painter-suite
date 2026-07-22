async (page) => page.evaluate(async () => {
  const opaqueShape = await makeFabricObject({
    type: 1050986,
    type_word: 2410,
    resource_family: "Community_Vinyls_4",
    resource_index: 10,
    color: [255, 255, 255, 255],
    data: [0, 0, 1, 1, 0, 0, 0],
  });
  const gradientShape = await makeFabricObject({
    type: 1048777,
    type_word: 201,
    resource_family: "Gradient_Shapes",
    resource_index: 1,
    color: [255, 255, 255, 255],
    data: [0, 0, 1, 1, 0, 0, 0],
  });
  const opaqueMesh = hybridMeshForObject(opaqueShape);
  const gradientMesh = hybridMeshForObject(gradientShape);
  if (!opaqueMesh || !gradientMesh) throw new Error("Hybrid regression resources did not produce meshes.");
  if (opaqueMesh.usesVertexAlpha) throw new Error("Opaque community resource incorrectly enabled vertex alpha.");
  if (!gradientMesh.usesVertexAlpha) throw new Error("Gradient resource did not enable vertex alpha.");
  return {
    opaqueUsesVertexAlpha: opaqueMesh.usesVertexAlpha,
    gradientUsesVertexAlpha: gradientMesh.usesVertexAlpha,
  };
})
