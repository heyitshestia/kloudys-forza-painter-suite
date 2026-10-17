async (page, options = {}) => {
  page.setDefaultTimeout(20000);
  const checks = [];
  const check = (ok, message) => { if (!ok) throw Error(message); };
  for (const language of options.toolbarLanguages || ['en', 'ko']) {
    await page.evaluate(async language => {
      KfpsEditorPreferences.setItem(KfpsI18n.KEY, language);
      await KfpsEditorPreferences.flush(); await flushPendingAutosave();
    }, language);
    await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready);
    await page.evaluate(async () => {
      document.querySelectorAll('dialog[open]').forEach(d => d.close());
      await loadPayload({ shapes: Array.from({ length: 955 }, (_, i) => ({
        type: 1048677, color: [50, 140, 200, 255], data: [i % 30 * 10, Math.floor(i / 30) * 10, .1, .1, 0, 0, 0],
        editor_id: `toolbar-${i}`, ...(i < 2 ? { editor_group_id: 'toolbar-group', editor_group_name: 'Toolbar group' } : {})
      })) });
      selectObjects([vinylObjects()[3], vinylObjects()[4]], 'test');
      setDockVisible(true); setLayersCollapsed(false);
    });
    for (const theme of options.toolbarThemes || ['pastel', 'dark', 'blackout', 'whiteout']) {
      await page.evaluate(theme => editorTheme.applyEditorTheme(theme, { persist: false }), theme);
      for (const size of options.toolbarViewports || [{width:3840,height:2160}, {width:2560,height:1440}, {width:1760,height:1040}, {width:1280,height:800}, {width:900,height:640}]) {
        await page.setViewportSize(size);
        for (const zoom of [1, 1.25, 1.5, 2]) {
          await page.evaluate(zoom => {
            document.documentElement.style.zoom = String(zoom);
            document.querySelector('.editorShell').style.setProperty('--editor-layer-height', '0px');
            document.getElementById('layersPane').scrollTop = 0;
          }, zoom);
          await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          const geometry = await page.locator('#layersPane > .smallTools').evaluate(bar => {
            const r = bar.getBoundingClientRect();
            const buttons = [...bar.children].filter(b => b.tagName === 'BUTTON' && b.getBoundingClientRect().height);
            return {toolbarHeight:bar.clientHeight, content:bar.scrollHeight, count:buttons.length,
              paneHeight:bar.parentElement.clientHeight,
              clipped:buttons.filter(b => { const q=b.getBoundingClientRect(); return q.top < r.top-1 || q.bottom > r.bottom+1; }).map(b=>b.id)};
          });
          check(geometry.count >= 7 && geometry.content <= geometry.toolbarHeight + 1 && !geometry.clipped.length,
            `Toolbar clipped ${JSON.stringify({language,theme,...size,zoom,...geometry})}`);
          check(Math.abs(geometry.paneHeight - (size.height <= 700 ? 135 : 270)) <= 1,
            `Test did not reach the minimum panel height: ${JSON.stringify(geometry)}`);
          if (zoom === 1) {
            await page.locator('#groupActions').click();
            check(await page.locator('#layerGroupActions').isVisible(), 'Group menu did not open');
            await page.keyboard.press('Escape');
          }
          for (const id of ['bringFront','groupSelected','renameSelectedLayer']) {
            const button = page.locator('#'+id);
            if (!await button.isVisible()) continue;
            await button.scrollIntoViewIfNeeded();
            check(await button.evaluate(b => {
              const r=b.getBoundingClientRect();
              return [0.15,0.5,0.85].every(f => {
                const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height*f);
                return b.contains(hit);
              });
            }), `Button hit area clipped: ${id}/${language}/${theme}/${size.width}/${zoom}`);
          }
          checks.push({language,theme,...size,zoom,...geometry});
          if (size.width === 1760 && zoom === 1) {
            await page.locator('#layersPane').evaluate(p => {p.scrollTop=0;});
            await page.screenshot({path:path.join(output, `toolbar-${language}-${theme}.png`)});
          }
        }
      }
    }
    await page.evaluate(async () => {
      document.documentElement.style.zoom='';
      document.querySelector('.editorShell').style.removeProperty('--editor-layer-height');
      await flushPendingAutosave();
    });
    await page.locator('#saveProjectAs').click();
    await page.locator('#textPromptInput').fill(`Toolbar regression ${language}`);
    await page.locator('#textPromptInput').press('Enter');
    await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  }
  await page.setViewportSize({width:1760,height:1040});
  return {checks, passed:true};
}
