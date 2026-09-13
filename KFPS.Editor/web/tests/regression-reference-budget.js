async page => {
  page.setDefaultTimeout(180000);
  return page.evaluate(async () => {
    const prefix = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8" fill="red"/><!--');
    const suffix = encodeURIComponent('--></svg>');
    const makeUrl = bytes => prefix + 'x'.repeat(bytes - prefix.length - suffix.length) + suffix;
    const outcomes = [];
    await clearAutosave();
    editorReference.removeOverlay();
    for (const delta of [-1, 0, 1]) {
      const bytes = EDITOR_REFERENCE_MAX_BYTES + delta;
      const previous = editorReference.image;
      let rejected = false;
      try { await editorReference.loadOverlayImageFromUrl(makeUrl(bytes), `budget-${delta}.svg`); }
      catch (error) {
        rejected = true;
        if (!String(error.message).includes(`${EDITOR_REFERENCE_MAX_BYTES / (1024 * 1024)} MiB`)) throw error;
      }
      if (delta <= 0 && (rejected || editorReference.source.dataUrl.length !== bytes)) throw new Error('Valid reference boundary was rejected');
      if (delta > 0 && (!rejected || editorReference.image !== previous)) throw new Error('Over-budget reference replaced existing image');
      if (editorReference.readOverlayPixel(0, 0)[0] !== 255 || editorReference.readOverlayPixel(0, 0)[1] !== 0) throw new Error('Reference pixels changed at boundary');
      outcomes.push({ bytes, accepted: !rejected });
    }
    editorReference.removeOverlay();
    await clearAutosave();
    documentDirty = false;
    return outcomes;
  });
}
