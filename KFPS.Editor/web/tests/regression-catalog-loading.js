async page => {
  const result = await page.evaluate(async () => {
    const realFetch = window.fetch;
    const before = JSON.stringify(editorCatalog.names);
    let requests = 0;
    try {
      window.fetch = async (url, options) => {
        if (String(url).endsWith('shape-names.json')) return new Response(JSON.stringify({ families: { Primitives: { 1: 'Partial metadata' } } }));
        if (String(url).endsWith('shape-words.json')) return new Response('invalid JSON');
        if (String(url).endsWith('/Community_Vinyls_4/39')) {
          requests += 1;
          return new Response(JSON.stringify({ Vertices: [{ X: 0, Y: 0 }, { X: 1, Y: 0 }, { X: 0, Y: 1 }], Indices: [0, 1, 2] }));
        }
        return realFetch(url, options);
      };
      await loadShapeNames();
      const resolved = { family: 'Community_Vinyls_4', index: 39, typeCode: editorCatalog.resourceToTypeCode('Community_Vinyls_4', 39) };
      const [path, outline, payload] = await Promise.all([
        editorCatalog.loadResourcePathForResolved(resolved), editorCatalog.loadResourceOutlinePathForResolved(resolved), editorCatalog.loadResourcePayloadForResolved(resolved),
      ]);
      return { metadataUnchanged: before === JSON.stringify(editorCatalog.names), requests, path, outline, vertices: payload.Vertices.length };
    } finally {
      window.fetch = realFetch;
      await loadShapeNames();
    }
  });
  if (!result.metadataUnchanged || result.requests !== 1) throw Error(JSON.stringify(result));
  return result;
}
