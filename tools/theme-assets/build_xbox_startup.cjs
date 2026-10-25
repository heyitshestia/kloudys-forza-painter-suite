// Original offline-rendered visuals. Only the supplied audio is reused.
const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const {spawn}=require('node:child_process');
const {once}=require('node:events');
const {createHash}=require('node:crypto');
const {chromium}=require('playwright');
const ROOT=path.resolve(__dirname,'../..');
const [source,ffmpeg,out]=process.argv.slice(2,5).map(p=>p&&path.resolve(p));
const preview=process.argv.includes('--preview');
if(!source||!ffmpeg||!out)throw Error('Usage: node build_xbox_startup.cjs source.mp4 ffmpeg.exe output-directory');
const sourceHash=createHash('sha256').update(fs.readFileSync(source)).digest('hex');
if(sourceHash!=='a0e81ed471e300b948c759575eb1a51c40a58c18ff0b74c24fa2461c21a71e7c')throw Error('Unreviewed soundtrack source: inspect its duration and audio cues before rendering.');
fs.mkdirSync(out,{recursive:true});
const temp=path.join(out,'tmp');fs.mkdirSync(temp,{recursive:true});process.env.TEMP=temp;process.env.TMP=temp;
async function run(args){
 const p=spawn(ffmpeg,['-hide_banner','-nostdin','-y',...args],{windowsHide:true});
 let log='';p.stderr.on('data',b=>log+=b);const [code]=await once(p,'close');
 fs.appendFileSync(path.join(out,'encode.log'),log);
 if(code)throw Error(`FFmpeg exited ${code}`);
}
const server=http.createServer((req,res)=>{
 const file=path.resolve(ROOT,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
 if(!file.startsWith(ROOT+path.sep)){res.writeHead(403).end();return;}
 fs.readFile(file,(e,data)=>{if(e){res.writeHead(404).end();return;}
 res.setHeader('Content-Type',file.endsWith('.html')?'text/html':'text/javascript');res.end(data);});
});
(async()=>{
 server.listen(0,'127.0.0.1');await once(server,'listening');
 let browser,encoder;
 try{
  browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-background-networking']});
  const page=await browser.newPage({viewport:{width:1280,height:720}});
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(`http://127.0.0.1:${server.address().port}/tools/theme-assets/xbox-startup.html`);
  await page.waitForFunction(()=>window.ready);
  const samples=[];
  for(const t of [.5,1.5,2.5,3.5,4.2,4.5,4.7,5.0,5.3,5.8,8,10.8]){
   const bytes=Buffer.from(await page.evaluate(t=>window.renderFrame(t),t),'base64');
   fs.writeFileSync(path.join(out,`frame-${t.toFixed(2)}.png`),bytes);
   samples.push(await page.evaluate(()=>window.motionSnapshot()));
  }
  fs.writeFileSync(path.join(out,'motion-samples.json'),JSON.stringify(samples,null,2));
  if(preview){if(errors.length)throw Error(errors.join('\n'));console.log('Preview keyframes rendered.');return;}
  const silent=path.join(out,'authored-silent.mp4');
  encoder=spawn(ffmpeg,['-hide_banner','-nostdin','-y','-f','image2pipe','-framerate','60','-i','pipe:0','-c:v','libx264','-threads','2','-crf','17','-pix_fmt','yuv420p',silent],{windowsHide:true});
  let log='';encoder.stderr.on('data',b=>log+=b);
  const completed=once(encoder,'close');
  for(let i=0;i<704;i++){
   const t=i/60;
   const bytes=Buffer.from(await page.evaluate(t=>window.renderFrame(t),t),'base64');
   if(!encoder.stdin.write(bytes))await once(encoder.stdin,'drain');
   if(i%60===0)console.log(`Authored frame ${i}/704`);
  }
  encoder.stdin.end();const [code]=await completed;fs.appendFileSync(path.join(out,'encode.log'),log);
  if(code||errors.length)throw Error(`Render failed: ${code}; ${errors}`);
  await run(['-i',silent,'-i',source,'-map','0:v:0','-map','1:a:0','-c:v','copy',
   '-c:a','copy','-movflags','+faststart','-t','11.733333',path.join(out,'startup.mp4')]);
  const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
  fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({sourceSha256:hash(source),outputSha256:hash(path.join(out,'startup.mp4')),width:1280,height:720,fps:60,frames:704,duration:11.733333,sourceVideoFramesUsed:0,visuals:'Original procedural geometry, shaders, lighting, camera and KFPS wordmark',audio:'Original stream copied without re-encoding',renderer:'Three.js offline, SwiftShader, H.264 CPU encoding',redistribution:'Visuals authored for KFPS; supplied soundtrack clearance pending',errors},null,2));
 }finally{if(encoder&&encoder.exitCode===null){encoder.stdin.destroy();encoder.kill();}if(browser)await browser.close();server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;server.close();});
