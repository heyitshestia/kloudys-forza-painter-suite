import { CONFIRMATION_KEYS, validatePreferences } from './confirmation-policy.mjs';
import {t,localizeStatic,errorText} from './i18n.mjs';

export function initializeActionConfirmations({message,request}={}) {
  const dialog=document.createElement('dialog');dialog.id='actionConfirmation';dialog.setAttribute('aria-labelledby','actionConfirmationTitle');dialog.setAttribute('aria-describedby','actionConfirmationBody');
  dialog.innerHTML='<h2 id="actionConfirmationTitle"></h2><div id="actionConfirmationBody"></div><label class="qol-check"><input id="skipActionConfirmation" type="checkbox">Don\'t show again for this action and scope</label><p id="actionConfirmationStatus" role="status"></p><div class="actions"><button id="cancelActionConfirmation" type="button">Cancel</button><button id="acceptActionConfirmation" type="button"></button></div>';
  localizeStatic(dialog);document.body.append(dialog);
  const $=id=>dialog.querySelector('#'+id),controllers=new Set();
  let disposed=false,pending=null;
  const api=request||async function(value){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);controllers.add(controller);
    try{
      const response=await fetch('./api/confirmations',{signal:controller.signal,...(value===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)})});
      if(!response.ok)throw Error('Action preferences could not be saved or loaded.');
      const result=await response.json();validatePreferences(result);return result;
    }finally{clearTimeout(timer);controllers.delete(controller);}
  };
  function finish(accepted){
    const token=pending;if(!token)return;pending=null;
    if(dialog.open)dialog.close();
    token.resolve(!disposed&&accepted);
    queueMicrotask(()=>{if(!disposed&&token.focus?.isConnected&&!token.focus.disabled)token.focus.focus({preventScroll:true});});
  }
  $('cancelActionConfirmation').addEventListener('click',()=>{if(!pending?.accepting)finish(false);});
  dialog.addEventListener('cancel',event=>{event.preventDefault();if(!pending?.accepting)finish(false);});
  dialog.addEventListener('close',()=>{if(!pending?.accepting)finish(false);});
  dialog.addEventListener('keydown',event=>{
    event.stopPropagation();
    if(event.isComposing||event.keyCode===229||event.altKey||event.getModifierState?.('AltGraph'))return;
    if(event.repeat&&event.key==='Enter'||(event.ctrlKey||event.metaKey)&&['KeyS','KeyZ','KeyY','KeyD','KeyG'].includes(event.code))event.preventDefault();
  });
  const guard=event=>{
    if(!pending||(event.target?.nodeType&&dialog.contains(event.target)))return;
    if(event.isComposing||event.keyCode===229){event.stopImmediatePropagation();return;}
    event.preventDefault();event.stopImmediatePropagation();
    if(event.key==='Escape'&&!pending.accepting)finish(false);
  };
  window.addEventListener('keydown',guard,{capture:true});
  $('acceptActionConfirmation').addEventListener('click',async()=>{
    const token=pending;if(!token||token.loading||token.accepting)return;
    token.accepting=true;$('acceptActionConfirmation').disabled=$('cancelActionConfirmation').disabled=true;
    if($('skipActionConfirmation').checked){
      try{validatePreferences(await api({action:token.spec.key,skip:true}));}
      catch{
        if(disposed||pending!==token)return;
        token.accepting=false;$('skipActionConfirmation').checked=false;
        $('actionConfirmationStatus').textContent=t('Could not remember this choice. You can continue without remembering it, or cancel.');
        $('acceptActionConfirmation').disabled=$('cancelActionConfirmation').disabled=false;
        $('cancelActionConfirmation').focus({preventScroll:true});return;
      }
    }
    if(!disposed&&pending===token)finish(true);
  });
  return {
    confirm(spec){
      if(disposed||pending||!spec)return Promise.resolve(false);
      if(!CONFIRMATION_KEYS.includes(spec.key))return Promise.reject(Error('Unknown confirmation preference.'));
      return new Promise(resolve=>{
        const token={resolve,spec,focus:document.activeElement,loading:true,accepting:false};pending=token;
        void(async()=>{
          let skipped=[],warning='';
          try{skipped=validatePreferences(await api());}catch{warning=t('Preferences could not be read. Please confirm this action.');}
          if(disposed||pending!==token)return;
          if(skipped.includes(spec.key)){finish(true);return;}
          $('actionConfirmationTitle').textContent=spec.title;$('actionConfirmationBody').replaceChildren();
          for(const text of spec.paragraphs){const p=document.createElement('p');p.textContent=text;$('actionConfirmationBody').append(p);}
          $('acceptActionConfirmation').textContent=spec.acceptLabel;$('skipActionConfirmation').checked=false;
          $('actionConfirmationStatus').textContent=warning;
          $('acceptActionConfirmation').disabled=$('cancelActionConfirmation').disabled=false;token.loading=false;
          dialog.showModal();$('cancelActionConfirmation').focus({preventScroll:true});
        })().catch(error=>{message?.(errorText(error),true);finish(false);});
      });
    },
    async reset(){
      if(disposed||pending)return;
      validatePreferences(await api({reset:true}));
      if(!disposed)message?.(t('Action confirmations are enabled again.'));
    },
    dispose(){if(disposed)return;disposed=true;finish(false);for(const controller of controllers)controller.abort();window.removeEventListener('keydown',guard,{capture:true});dialog.remove();},
  };
}
