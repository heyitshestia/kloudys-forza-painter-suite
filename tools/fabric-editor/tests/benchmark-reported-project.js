async page => {
  const fixturePath = process.env.KFPS_EDITOR_PROJECT_FIXTURE;
  if (!fixturePath) throw new Error("Set KFPS_EDITOR_PROJECT_FIXTURE to a private test project; never commit the artwork.");
  const content = fs.readFileSync(fixturePath, "utf8");
  const expectedCount = JSON.parse(content).shapes.length;
  await page.setViewportSize({width: 1600, height: 1000});
  const cdp = await page.context().newCDPSession(page);
  await page.evaluate(async content => {
    await loadProjectFile(new File([content], "reported-project.fabric-project.json", {type:"application/json"}));
    window.reportMetrics = null;
    new PerformanceObserver(list => {
      if (reportMetrics) reportMetrics.tasks.push(...list.getEntries().map(e => e.duration));
    }).observe({entryTypes:["longtask"]});
    let last = performance.now();
    function frame(now) { if (reportMetrics) reportMetrics.frames.push(now-last); last=now; requestAnimationFrame(frame); }
    requestAnimationFrame(frame);
  }, content);
  await page.screenshot({path:path.join(output, "reported-project-loaded.png")});
  const results = [];
  for (const [opacity, throttle] of [[0,1],[.6,1],[1,1],[.6,4]]) {
    const fixture = await page.evaluate(opacity => {
      overlayImage.set({opacity});
      $("overlayOpacity").value = Math.round(opacity*100);
      const object = vinylObjects().filter(o => o.kloudy.resource_index === 36)
        .sort((a,b) => b.getScaledWidth()*b.getScaledHeight()-a.getScaledWidth()*a.getScaledHeight())[0] || vinylObjects().at(-1);
      window.reportObject = object;
      const center = object.getCenterPoint();
      const zoom = Math.min(2, 400/Math.max(object.getScaledWidth(),object.getScaledHeight()));
      canvas.setViewportTransform([zoom,0,0,zoom,canvas.width/2-center.x*zoom,canvas.height/2-center.y*zoom]);
      selectObjects([object], "reported project test");
      canvas.renderAll();
      return {layers:vinylObjects().length, reference:[overlayImage.width,overlayImage.height], opacity,
        slot:object.kloudy.resource_index, angle:object.angle, zoom, paths:object.path?.length};
    }, opacity);
    await page.waitForTimeout(500);
    await cdp.send("Emulation.setCPUThrottlingRate", {rate:throttle});
    await cdp.send("Profiler.enable"); await cdp.send("Profiler.start");
    await page.evaluate(() => { reportMetrics = {frames:[],tasks:[]}; });
    for (let repeat=0;repeat<5;repeat++) {
      const points = await page.evaluate(() => {
        const object=reportObject; object.setCoords();
        const rect=canvas.upperCanvasEl.getBoundingClientRect();
        const p = point => ({x:point.x+rect.left,y:point.y+rect.top});
        return {center:p(fabric.util.transformPoint(object.getCenterPoint(),canvas.viewportTransform)), rotate:p(object.oCoords.mtr), scale:p(object.oCoords.mr)};
      });
      const c=points.center, r=points.rotate, dx=r.x-c.x, dy=r.y-c.y;
      await page.mouse.move(r.x,r.y); await page.mouse.down();
      for(let i=1;i<=10;i++) {
        const a=i/10*.3*(repeat%2?-1:1);
        await page.mouse.move(c.x+dx*Math.cos(a)-dy*Math.sin(a),c.y+dx*Math.sin(a)+dy*Math.cos(a));
      }
      await page.mouse.up();
      const resize = await page.evaluate(() => {reportObject.setCoords(); const r=canvas.upperCanvasEl.getBoundingClientRect(),p=reportObject.oCoords.mr;return {x:p.x+r.left,y:p.y+r.top};});
      await page.mouse.move(resize.x,resize.y); await page.mouse.down();
      await page.mouse.move(resize.x+8,resize.y+4,{steps:5}); await page.mouse.up();
      await page.mouse.move(c.x,c.y);
      await page.mouse.down({button:"right"}); await page.mouse.move(c.x+24,c.y+12,{steps:8}); await page.mouse.up({button:"right"});
      for (const delta of [-200,200]) {await page.mouse.wheel(0,delta); await page.waitForTimeout(70);}
      await page.waitForTimeout(200);
    }
    const metrics = await page.evaluate(() => {
      const result=reportMetrics; reportMetrics=null;
      const frames=result.frames.slice(1).sort((a,b)=>a-b); delete result.frames;
      return {...result,frameP95:frames[Math.floor(frames.length*.95)],frameMax:Math.max(...frames),
        angle:reportObject.angle,layers:vinylObjects().length,hybridDisabled:hybridDisabledReason};
    });
    const {profile}=await cdp.send("Profiler.stop");
    const nodes=new Map(profile.nodes.map(n=>[n.id,n])); const counts=new Map();
    for(let i=0;i<(profile.samples||[]).length;i++) {
      const f=nodes.get(profile.samples[i]).callFrame, name=`${f.functionName||"anonymous"} ${f.url.split("/").pop()}:${f.lineNumber+1}`;
      counts.set(name,(counts.get(name)||0)+(profile.timeDeltas[i]||0)/1000);
    }
    await cdp.send("Emulation.setCPUThrottlingRate", {rate:1});
    if(metrics.layers!==expectedCount || Math.abs(metrics.angle-fixture.angle)<1) throw new Error("Reported project gestures did not transform the expected artwork");
    results.push({fixture,throttle,...metrics,topCpu:[...counts].sort((a,b)=>b[1]-a[1]).slice(0,15)});
    await page.screenshot({path:path.join(output, `reported-project-opacity-${opacity}-cpu-${throttle}.png`)});
  }
  const recovery=await page.evaluate(async()=>{await flushPendingAutosave();return autosaveStatus;});
  await cdp.detach();
  return {results,recovery};
}
