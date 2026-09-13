import {MAX_PACKAGE_BYTES} from './private-logs.mjs';

// One bounded, one-way transfer from the app into its trusted review page.
// No filesystem bridge, localhost server, or network upload is exposed.
export function nativeHandoff({accept, current, now=()=>Date.now()}) {
  let transfer=null, generation=0;
  const fail=text=>{throw Error(text);};
  const active=()=>{
    if(!transfer||transfer.state!=='receiving')fail('No report transfer is active.');
    if(now()-transfer.started>60000){transfer=null;fail('Report transfer expired. Retry from KFPS.');}
    return transfer;
  };
  return Object.freeze({
    status(id) {
      if(current(id))return {state:'ready',id};
      if(transfer?.id===id)return {state:transfer.state,id,error:transfer.error||''};
      return {state:'idle',id};
    },
    begin(value) {
      if(!value||!/^[a-f0-9-]{36}$/.test(value.id)||!['package','json'].includes(value.mode)
        ||!Number.isSafeInteger(value.size)||value.size<1||value.size>MAX_PACKAGE_BYTES
        ||(value.mode==='json'&&value.size>49152)||!/^[a-f0-9]{64}$/.test(value.sha256))fail('Invalid report transfer.');
      generation++;
      transfer={...value,state:'receiving',parts:[],received:0,started:now(),generation};
      return true;
    },
    chunk(index,encoded) {
      const item=active();
      if(index!==item.parts.length||typeof encoded!=='string'||encoded.length>262144
        ||!encoded.length||encoded.length%4||!/^[A-Za-z0-9+/]*={0,2}$/.test(encoded))fail('Invalid report chunk.');
      const data=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
      if(item.received+data.length>item.size)fail('Report transfer exceeds its declared size.');
      item.parts.push(data);item.received+=data.length;
      return item.received;
    },
    finish() {
      const item=active();
      if(item.received!==item.size)fail('Report transfer is incomplete.');
      item.state='checking';
      (async()=>{
        try {
          const file=new Blob(item.parts);item.parts=[];
          const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer())),x=>x.toString(16).padStart(2,'0')).join('');
          if(digest!==item.sha256)throw Error('Report transfer checksum does not match.');
          if(generation!==item.generation)return;
          await accept(file,{expectedId:item.id,automatic:true});
          if(generation===item.generation)item.state='ready';
        } catch(error) {
          if(generation===item.generation){item.state='error';item.error=error.message;item.parts=[];}
        }
      })();
      return true;
    }
  });
}
