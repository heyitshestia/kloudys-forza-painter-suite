"use strict";
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../editor.js'),'utf8');
const extract=(name,next)=>source.slice(source.indexOf(`function ${name}(`),source.indexOf(`function ${next}(`));
const context={interactiveVinylTarget:t=>t,isActiveSelectionObject:()=>false,
  fabric:{controlsUtils:{skewHandlerX:()=> 'skew',scalingEqually:()=> 'scale',scalingX:()=> 'x',scalingY:()=> 'y',wrapWithFireEvent:(_name,fn)=>fn}}};
vm.createContext(context);
vm.runInContext(extract('centeredHandleResize','editorCornerTransformHandler')+
  extract('editorCornerTransformHandler','transformCornerFromPointer')+
  extract('editorSideScaleHandler','roundedRectPath'),context);
for(const enabled of [false,true])for(const alt of [false,true]) {
  const object={centeredScaling:false,canvas:{centeredScaling:enabled}};
  assert.equal(context.centeredHandleResize(object,{altKey:alt}),enabled!==alt);
  assert.equal(context.centeredHandleResize(object,{altKey:alt},'skewX'),alt);
}
for(const handler of [context.editorCornerTransformHandler,context.editorSideScaleHandler('x'),context.editorSideScaleHandler('y')]) {
  assert.equal(handler({buttons:0},{},0,0),false,'Unpressed hover must not access or transform a target');
  assert.notEqual(handler({buttons:1},{target:{}},0,0),false);
  assert.notEqual(handler({type:'touchmove'},{target:{}},0,0),false);
}
assert.equal(context.editorCornerTransformHandler({buttons:1,shiftKey:true},{target:{}},0,0),'skew');
console.log('Centered resize: modifier truth table, unchanged Shift, hover guard and touch/fallback compatibility passed');
