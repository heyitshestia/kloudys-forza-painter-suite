async page => {
  const direct = await page.evaluate(async () => {
    const valid = { type: 1048677, color: [220, 70, 90, 255], data: [75, 50, .25, -.5, 31, .1, 0] };
    const rows = [];
    const malformed = [
      ['empty', { ...valid, data: [] }], ['missing', { ...valid, data: undefined }],
      ['short', { ...valid, data: [1, 2, 3] }], ['null', { ...valid, data: [null, 0, 1, 1] }],
      ['string', { ...valid, data: ['1', 0, 1, 1] }], ['boolean', { ...valid, data: [true, 0, 1, 1] }],
      ['NaN', { ...valid, data: [NaN, 0, 1, 1] }], ['infinity', { ...valid, data: [0, Infinity, 1, 1] }],
      ['range', { ...valid, data: [0, 0, 1e100, 1] }], ['zero scale', { ...valid, data: [0, 0, 0, 1] }],
      ['bad color', { ...valid, color: [0, 0, 300, 255] }], ['null layer', null],
      ['bad mask', { ...valid, data: [0, 0, 1, 1, 0, 0, 7] }],
      ['partial project', { ...valid, data: [1] }],
      ['rotated half-step', { ...valid, data: [0, 0, 5e-7, 1, 359.9, 0, 0] }],
      ['mirrored half-step', { ...valid, data: [0, 0, -5.000000000000001e-7, 1, 359.9, 0, 0] }],
      ['legacy rectangle half-step', { ...valid, type: 2, data: [0, 0, .0000635, 127, 30, 0, 0] }],
      ['legacy ellipse half-step', { ...valid, type: 16, data: [0, 0, .0000315, 63, 30, 0, 0] }],
    ];
    for (const [type, divisor] of [[1048677, 1], [1, 127], [2, 127], [8, 63], [16, 63]]) {
      for (const axis of [2, 3]) for (const sign of [-1, 1]) {
        const data = valid.data.slice();
        data[axis] = sign * 1e-7 * divisor;
        malformed.push([`tiny ${type} axis ${axis} sign ${sign}`, { ...valid, type, data }]);
      }
    }
    for (const [name, broken] of malformed) {
      await loadProjectPayload({ name: 'Protected R3', shapes: [valid] });
      const object = vinylObjects()[0];
      selectObjects([object], 'strict fixture');
      await flushPendingAutosave();
      const before = JSON.stringify(snapshotEditorState()), history = currentHistoryState();
      const selection = canvas.getActiveObject(), identity = documentIdentity, ids = nextEditorObjectId;
      const recovery = JSON.stringify(await readAutosavePayload());
      let rejected = false;
      try { await loadPayload({ shapes: [valid, broken] }, { strict: true, name: 'Bad R3' }); }
      catch (_) { rejected = true; }
      await flushPendingAutosave();
      rows.push({ name, rejected, scene: before === JSON.stringify(snapshotEditorState()),
        object: vinylObjects()[0] === object, history: history === currentHistoryState(),
        selection: selection === canvas.getActiveObject(), identity: identity === documentIdentity,
        ids: ids === nextEditorObjectId, recovery: recovery === JSON.stringify(await readAutosavePayload()) });
    }
    const roundtrips = [];
    for (const [type, divisor] of [[1048677, 1], [1, 127], [2, 127], [8, 63], [16, 63]]) {
      for (const sign of [-1, 1]) {
        await loadProjectPayload({ name: 'Small supported scales', shapes: [valid,
          { ...valid, type, data: [0, 0, sign * 1e-6 * divisor, -sign * 2e-6 * divisor, 30, .1, 0] }] });
        await flushPendingAutosave();
        const saved = await readAutosavePayload();
        const before = JSON.stringify(saved.shapes);
        const reopened = await loadProjectPayload(saved);
        await flushPendingAutosave();
        const after = await readAutosavePayload();
        const recovered = await recoverAutosavePayload(after);
        roundtrips.push({ type, sign, reopened, recovered,
          nonzero: saved.shapes.every(shape => shape.data[2] !== 0 && shape.data[3] !== 0),
          exact: before === JSON.stringify(after.shapes) });
      }
    }
    clearBusy();
    return { rows, roundtrips, passed: rows.every(row => Object.entries(row).every(([key, value]) => key === 'name' || value === true))
      && roundtrips.every(row => row.reopened && row.recovered && row.nonzero && row.exact) };
  });
  fs.writeFileSync(path.join(output, 'strict-geometry.json'), JSON.stringify(direct, null, 2));
  return direct;
}
