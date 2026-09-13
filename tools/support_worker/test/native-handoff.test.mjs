import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomBytes,randomUUID} from 'node:crypto';
import {nativeHandoff} from '../public/native-handoff.mjs';
import {MAX_PACKAGE_BYTES} from '../public/private-logs.mjs';

const meta=(data,extra={})=>({id:randomUUID(),size:data.length,mode:'package',sha256:createHash('sha256').update(data).digest('hex'),...extra});
const settle=async(receiver,id)=>{
  for(let i=0;i<200&&receiver.status(id).state==='checking';i++)await new Promise(resolve=>setTimeout(resolve,5));
  return receiver.status(id);
};
test('native transfer accepts the full 9 MiB allowance without a URL or upload',async()=>{
  const data=randomBytes(MAX_PACKAGE_BYTES), metadata=meta(data),accepted=[];
  const receiver=nativeHandoff({current:()=>false,accept:async(file,options)=>accepted.push({data:Buffer.from(await file.arrayBuffer()),options})});
  receiver.begin(metadata);
  for(let offset=0,index=0;offset<data.length;offset+=196608,index++)receiver.chunk(index,data.subarray(offset,offset+196608).toString('base64'));
  assert.equal(accepted.length,0);receiver.finish();
  assert.equal((await settle(receiver,metadata.id)).state,'ready');
  assert.deepEqual(accepted[0].data,data);assert.equal(accepted[0].options.expectedId,metadata.id);
});
test('invalid limits, sequences, excess bytes and incomplete transfers fail closed',()=>{
  const data=Buffer.from('test'),metadata=meta(data);
  const receiver=nativeHandoff({current:()=>false,accept:()=>assert.fail('Must not accept')});
  for(const change of [{size:MAX_PACKAGE_BYTES+1},{size:0},{mode:'path'},{sha256:'bad'},{id:'../x'},{mode:'json',size:50000}])assert.throws(()=>receiver.begin({...metadata,...change}));
  receiver.begin(metadata);assert.throws(()=>receiver.chunk(1,data.toString('base64')));
  assert.throws(()=>receiver.chunk(0,Buffer.from('extra').toString('base64')));
  assert.throws(()=>receiver.chunk(0,'!!!!'));
  assert.throws(()=>receiver.finish());
});
test('checksum mismatch and validation rejection never report success',async()=>{
  for(const badHash of [true,false]) {
    let accepted=0;const data=Buffer.from('test'),metadata=meta(data,badHash?{sha256:'0'.repeat(64)}:{});
    const receiver=nativeHandoff({current:()=>false,accept:()=>{accepted++;throw Error('Invalid report');}});
    receiver.begin(metadata);receiver.chunk(0,data.toString('base64'));receiver.finish();
    assert.equal((await settle(receiver,metadata.id)).state,'error');assert.equal(accepted,badHash?0:1);
  }
});
test('expired transfers are discarded and replaced reports cannot complete late',async()=>{
  let time=0,accepted=0;const data=Buffer.from('test'),metadata=meta(data);
  const receiver=nativeHandoff({now:()=>time,current:()=>false,accept:()=>accepted++});
  receiver.begin(metadata);time=60001;assert.throws(()=>receiver.chunk(0,data.toString('base64')));
  receiver.begin(metadata);receiver.chunk(0,data.toString('base64'));receiver.finish();receiver.begin(meta(data));
  await new Promise(resolve=>setTimeout(resolve,20));assert.equal(accepted,0);
});
test('already-restored reports need no duplicate transfer',()=>{
  const id=randomUUID(),receiver=nativeHandoff({current:value=>value===id,accept:()=>assert.fail()});
  assert.equal(receiver.status(id).state,'ready');assert.equal(receiver.status(randomUUID()).state,'idle');
});
