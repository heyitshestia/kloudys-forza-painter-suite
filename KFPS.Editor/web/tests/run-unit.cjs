"use strict";
const fs=require("node:fs"),path=require("node:path"),cp=require("node:child_process");
const editor=path.resolve(__dirname,".."),root=path.resolve(editor,"../..");
const manifest=JSON.parse(fs.readFileSync(path.join(root,"KFPS.Editor/manifest.json"),"utf8"));
const commands=manifest.web.filter(item=>item.path.endsWith(".js")).map(item=>["--check",path.join(editor,item.path)]);
commands.push(...fs.readdirSync(__dirname).filter(name=>name.endsWith(".node.js")).sort().map(name=>[path.join(__dirname,name)]));
let failures=0;
for(const args of commands){
  const result=cp.spawnSync(process.execPath,args,{cwd:root,encoding:"utf8",windowsHide:true,timeout:120000});
  process.stdout.write(result.stdout||"");process.stderr.write(result.stderr||"");
  if(result.status!==0){failures++;console.error("FAILED",args.join(" "),result.error||result.status);}
}
console.log(JSON.stringify({syntaxAndSuites:commands.length,failures}));
process.exitCode=failures?1:0;
