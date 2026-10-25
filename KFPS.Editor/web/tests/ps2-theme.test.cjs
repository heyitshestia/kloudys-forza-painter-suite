'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
(async () => {
  const {PALETTES, COLOR_KEYS, normalizeTheme} = await import(pathToFileURL(path.resolve(__dirname, '../../../tools/livery-studio/src/web/theme-adapter.mjs')));
  const theme = normalizeTheme({id:'builtin:ps2'});
  assert.equal(theme.name, 'Original PS2');
  assert.equal(theme.base, 'builtin:ps2');
  assert.equal(theme.colorScheme, 'dark');
  assert.equal(COLOR_KEYS.length, 33);
  assert.deepEqual(Object.keys(PALETTES['builtin:ps2']).sort(), [...COLOR_KEYS].sort());
  const custom = normalizeTheme({...theme,id:'custom-ps2',values:{...theme.values,'--accent':'#ffd177'}});
  assert.deepEqual(normalizeTheme(JSON.parse(JSON.stringify(custom))), custom);
  assert.equal(custom.values['--accent'], '#ffd177');
  assert.equal(normalizeTheme({id:'ps2',base:'dark'}).base, 'dark');
  const lum = color => color.slice(1).match(/../g).map(c=>parseInt(c,16)/255).map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4).reduce((s,c,i)=>s+c*[.2126,.7152,.0722][i],0);
  let minimum=Infinity;
  for(const fg of ['--text','--muted','--soft','--accent','--accent2','--warn','--danger']) {
    for(const bg of ['--shell','--panel','--panel2','--panel3','--dialog-header']) {
      const a=lum(theme.values[fg]),b=lum(theme.values[bg]),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
      assert.ok(ratio>=4.5,fg+'/'+bg+': '+ratio);
      minimum=Math.min(minimum,ratio);
    }
  }
  console.log(JSON.stringify({theme:theme.name,keys:33,minimumTextContrast:minimum,customRoundtrip:true,legacyIdPreserved:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
