"use strict";
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const runner = fs.readFileSync(path.join(__dirname,'run-native-page.cjs'),'utf8');
const guard = runner.slice(runner.indexOf('  const testOptions ='),runner.indexOf('  const browser ='));
const captured = [];
function check(options) {
  return vm.runInNewContext(`(()=>{${guard};return testOptions;})()`, {
    process:{env:{KFPS_TEST_OPTIONS:JSON.stringify(options)}},
    fs:{writeFileSync:(_,data)=>captured.push(JSON.parse(data))},path,output:'private-evidence',
  });
}
for (const preserveStartupNotices of [undefined,false,null,0,'true']) {
  captured.length=0;
  assert.throws(()=>check({customizationRestart:true,preserveStartupNotices}), /preserveStartupNotices/);
  assert.equal(captured.length,0,'Invalid options must not proceed to browser setup');
}
const options={customizationRestart:true,preserveStartupNotices:true,browserHost:true};
check(options);
assert.deepEqual(captured.at(-1).options,options,'Record exact Node options before any browser/dialog setup');
check({});
// Exercise the actual Python early guard without importing Qt or launching a host.
const pythonSource=fs.readFileSync(path.join(__dirname,'run-workflow-chrome.py'),'utf8');
const start=pythonSource.indexOf('test_options = json.loads(');
assert.ok(start>=0,'Chrome host must reject invalid restart configuration before startup');
const pythonGuard=pythonSource.slice(start,pythonSource.indexOf('REFERENCE =',start));
const python=process.env.KFPS_TEST_PYTHON;
assert.ok(python,'Pass explicit existing Python for the CPU-only launcher guard');
const {spawnSync}=require('node:child_process');
for(const input of [{customizationRestart:true},{customizationRestart:true,preserveStartupNotices:false},options,{}]) {
  const result=spawnSync(python,['-I','-B','-c','import argparse,json,os\nparser=argparse.ArgumentParser()\n'+pythonGuard],
    {env:{...process.env,KFPS_TEST_OPTIONS:JSON.stringify(input)},windowsHide:true,encoding:'utf8',timeout:10000});
  assert.equal(result.error,undefined);
  const valid=!input.customizationRestart||input.preserveStartupNotices===true;
  assert.equal(result.status,valid?0:2,result.stderr);
  if(!valid)assert.match(result.stderr,/preserveStartupNotices/);
}
console.log(JSON.stringify({passed:true,nodeInvalidCases:5,nodeValidCases:2,pythonCases:4,browserLaunches:0,productWrites:0}));
