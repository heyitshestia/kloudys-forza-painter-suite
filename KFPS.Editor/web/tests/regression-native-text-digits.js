async page => page.evaluate(async () => {
  const results = [];
  for (let font = 1; font <= 11; font++) {
    const glyphs = [..."0123456789"].map(char => ({ char, ...textVinylForzaGlyphResource(char, font) }));
    for (const glyph of glyphs) {
      const expected = glyph.char === "0" ? 36 : 26 + Number(glyph.char);
      if (glyph.index !== expected || glyph.family !== `Upper_Letters_${font}`) throw new Error(`Wrong digit resource: ${font}/${glyph.char}`);
    }
    document.getElementById("textVinylInput").value = "KFPS AaZz 0123456789";
    const selector = document.getElementById("textVinylForzaFont");
    if (selector) selector.value = String(font);
    await generateTextVinylShapes();
    const generated = vinylObjects().filter(o => o.kloudy?.source_format === TEXT_VINYL_SOURCE_FLAG);
    if (generated.length !== 18) throw new Error(`Font ${font} generated ${generated.length} glyphs instead of 18`);
    results.push({ font, digits: glyphs.length, generated: generated.length });
  }
  return { fonts: results.length, digitsResolved: results.reduce((n, r) => n + r.digits, 0) };
})
