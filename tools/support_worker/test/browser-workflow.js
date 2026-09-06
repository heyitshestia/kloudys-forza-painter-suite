// Playwright CLI run-code scenario. Identity and delivery are mocked; no Discord post is sent.
async (page) => {
  const origin = 'https://kfps-support-staging.hestia-cummings.workers.dev';
  const checks = [], posts = [];
  const assert = (value, name) => { if (!value) throw new Error(name); checks.push(name); };
  const draft = {schema:'kfps-support-report/1', id:'dadffddc-abcd-4567-89ab-abcdef123456', created_at:'2026-09-06T12:00:00Z', source:'kfps', feature:'Editor', title:'Synthetic browser test', description:'Synthetic error from KFPS.', technical:{app:{version:'3.1.60'}, hardware:{platform:'Windows 11',memory_bytes:17179869184,gpus:[{name:'Synthetic GPU',driver_version:'test'}]}, artwork:{shapes:['MUST NOT SURVIVE']}, logs:[{source:'app',text:'Password: MUST NOT SURVIVE\nError while rendering'}]}};
  const delivered = {id:draft.id,status:'delivered',message:'Synthetic delivery acknowledged.',public_url:'https://discord.com/channels/1546144079778283552/999999999999999999'};
  await page.route('**/api/config', route => route.fulfill({json:{enabled:true,join_url:'https://discord.gg/XT8dG8bDKy'}}));
  await page.route('**/api/session', route => route.fulfill({json:{authenticated:true,name:'Synthetic Tester',csrf:'synthetic-csrf'}}));
  await page.route('**/api/reports/*', route => route.fulfill({json:delivered}));
  await page.route('**/api/reports', async route => {posts.push(route.request().postDataJSON()); await page.waitForTimeout(250); await route.fulfill({json:delivered});});
  try {
    // The desktop handoff starts in a separate document, not a same-page hash jump.
    await page.goto('about:blank');
    const encoded = await page.evaluate(value => btoa(JSON.stringify(value)), draft);
    await page.goto(origin+'/#draft='+encoded);
    await page.getByRole('button',{name:'Send report',exact:true}).waitFor({state:'visible'});
    assert(!page.url().includes('#'),'private fragment removed');
    assert(!(await page.locator('header').textContent()).includes('DIRTY testing'),'public form has no testing label');
    const visibility = page.getByRole('note',{name:'Who can see your report'});
    assert(await visibility.isVisible()&&(await visibility.textContent()).includes('publicly visible in the KFPS Support Discord server'),'public Discord visibility disclosed');
    assert((await visibility.textContent()).includes('visible only to Kloudy and authorized KFPS support staff'),'private technical recipients disclosed');
    assert((await visibility.textContent()).includes('created specifically for reporting and resolving KFPS issues'),'dedicated support server explained');
    assert(await visibility.getByRole('link',{name:'Join the support server'}).getAttribute('href')==='https://discord.gg/XT8dG8bDKy','permanent server invitation provided');
    assert(await page.getByRole('textbox',{name:'What happened? Required'}).inputValue()===draft.description,'description autofilled');
    assert(await page.getByRole('combobox',{name:'Affected area'}).inputValue()==='Editor','feature autofilled');
    const title = page.locator('#title');
    const titleToggle = page.locator('summary').filter({hasText:/^Post title$/});
    assert(await title.isVisible(),'post title expanded by default');
    assert(await title.inputValue()===draft.title,'post title autofilled');
    await title.fill('Edited synthetic title');
    await titleToggle.click();
    assert(!await title.isVisible(),'post title can be collapsed');
    await titleToggle.press('Enter');
    assert(await title.isVisible()&&await title.inputValue()==='Edited synthetic title','keyboard expansion preserves title');
    const context=await page.locator('#technical').textContent();
    assert(context.includes('Synthetic GPU')&&!context.includes('MUST NOT SURVIVE'),'shared privacy allowlist used before review');
    assert(posts.length===0,'no automatic submission on opening');
    await page.getByRole('textbox',{name:'What happened? Required'}).fill('Synthetic test: moving a shape becomes slow.');
    await page.reload();
    assert((await page.getByRole('textbox',{name:'What happened? Required'}).inputValue()).includes('moving a shape'),'draft survives refresh and sign-in style navigation');
    assert(await title.isVisible()&&await title.inputValue()==='Edited synthetic title','post title remains available after reload');
    for(const [width,height] of [[390,844],[1280,900]]) {
      await page.setViewportSize({width,height});
      assert(await title.isVisible()&&await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`expanded form fits at ${width}`);
      const noteBounds=await visibility.boundingBox(), featureBounds=await page.locator('#feature').boundingBox();
      assert(noteBounds&&featureBounds&&noteBounds.y+noteBounds.height<=featureBounds.y,`visibility notice above fields at ${width}`);
    }
    await page.getByRole('checkbox',{name:'Include technical details privately for staff'}).uncheck();
    await page.getByRole('button',{name:'Send report',exact:true}).dblclick();
    await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    assert(posts.length===1,'double click sends once');
    assert(Object.keys(posts[0].technical).length===0,'technical exclusion respected in submitted body');
    assert(posts[0].id===draft.id,'stable report identity');
    assert(posts[0].title==='Edited synthetic title','edited post title submitted');
    await page.reload();
    await page.getByRole('heading',{name:'Report sent',exact:true}).waitFor();
    assert(posts.length===1,'receipt reload does not repost');
    for(const [width,height] of [[390,844],[1280,900]]) {
      await page.setViewportSize({width,height});
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`no horizontal overflow at ${width}`);
    }
    return {checks,posted_to_discord:false,intercepted_submissions:posts.length};
  } finally {
    await page.unroute('**/api/config'); await page.unroute('**/api/session');
    await page.unroute('**/api/reports/*'); await page.unroute('**/api/reports');
    await page.evaluate(()=>sessionStorage.removeItem('kfps-support-draft-v1'));
    await page.goto(origin);
  }
}
