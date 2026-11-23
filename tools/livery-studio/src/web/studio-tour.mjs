import {t} from './i18n.mjs';

export const studioTourSteps=Object.freeze([
  ["car","#chooseCar","Pick your car","Just exploring? Choose any car. To export a full livery, start in Garage > Packages and open your own package for that car in Studio. It supplies the template, not a design you have to keep."],
  ["import","#importVinyl","Place your first vinyl","Pick a section, like Left or Top, then choose Add vinyl. Want the same artwork twice? Select its source and choose Place vinyl again."],
  ["transform","#surfaceModes","Line it up","Orbit to see the other side. To change the vinyl instead of the camera, select it and use Move, Scale or Rotate. Apply keeps the edit; Cancel puts it back."],
  ["inspection","#inspectionToolsHost","Check an edge or seam","In View, use Paintability and Frame section to see where the artwork lands. The preview helps you line things up; check tricky edges on the car in FH6."],
  ["parts","#componentPanel","Try parts without changing the car","Preview a wing or kit here. Save your project to keep the fit, then restore the stock preview to export artwork. Fit the parts in FH6; Studio keeps the template paint."],
  ["save","#saveProject","Keep an editable copy","Use Save project before exporting. Open project brings back your sources, placements and parts so you can keep editing. Saving a project does not put it in the game."],
  ["export","#liveryExportActions","Choose what to take with you","For the whole car, choose Export livery package and give it a name. For just one side, use Export section instead. No need to unpack or rebuild a ZIP."],
  ["install","#viewport","Take it into FH6","Close FH6. In Garage > Packages, choose Add Package, open your .kfpslivery and select Install in FH6 Save. Then start FH6 and load the new entry from My Designs."],
].map(([id,selector,title,body])=>Object.freeze({id,selector,title,body})));

// A native modal owns focus and stacking; highlighted controls never change z-index.
export function initializeStudioTour({panels,canStart=()=>true,message=()=>{},icon=()=>{},onClose=()=>{}}={}){
  const trigger=document.getElementById('showStudioTour');
  if(!trigger||document.getElementById('studioTour'))throw Error('Studio tour is already mounted or unavailable.');
  const lifetime=new AbortController(),dialog=document.createElement('dialog');
  dialog.id='studioTour';dialog.setAttribute('aria-labelledby','studioTourTitle');
  dialog.setAttribute('aria-describedby','studioTourText');
  dialog.innerHTML='<div class="studio-tour-spotlight" aria-hidden="true"></div><section class="studio-tour-card"><div class="studio-tour-copy" aria-live="polite" aria-atomic="true"><p id="studioTourProgress"></p><h2 id="studioTourTitle"></h2><p id="studioTourText"></p></div><div class="studio-tour-actions"><button type="button" data-tour-close></button><span class="studio-tour-navigation"><button type="button" data-tour-back data-icon="ArrowLeft"></button><button type="button" data-tour-next></button></span></div></section>';
  const card=dialog.querySelector('.studio-tour-card'),spotlight=dialog.querySelector('.studio-tour-spotlight');
  const back=dialog.querySelector('[data-tour-back]'),next=dialog.querySelector('[data-tour-next]'),closeButton=dialog.querySelector('[data-tour-close]');
  closeButton.textContent=t('Close tour');back.textContent=t('Previous step');icon(back);
  document.body.append(dialog);
  let index=0,target=null,view=null,originalFocus=null,scroll=[],details=[],events=null,observer=null,frame=0,disposed=false;
  const isOpen=()=>dialog.open;
  function position(){
    frame=0;if(!dialog.open)return;
    const viewport=window.visualViewport;
    const left=viewport?.offsetLeft||0,top=viewport?.offsetTop||0;
    const width=viewport?.width||innerWidth,height=viewport?.height||innerHeight;
    card.style.maxHeight=`${Math.max(1,height-24)}px`;
    card.style.width=`${Math.max(1,Math.min(380,width-24))}px`;
    const bounds=target?.isConnected?target.getBoundingClientRect():null;
    const r=bounds&&{left:Math.max(left+6,bounds.left-5),top:Math.max(top+6,bounds.top-5),
      right:Math.min(left+width-6,bounds.right+5),bottom:Math.min(top+height-6,bounds.bottom+5)};
    const visible=r&&bounds.width>0&&bounds.height>0&&r.right>r.left&&r.bottom>r.top;
    spotlight.hidden=!visible;dialog.classList.toggle('without-target',!visible);
    if(visible)Object.assign(spotlight.style,{left:`${r.left}px`,top:`${r.top}px`,width:`${r.right-r.left}px`,height:`${r.bottom-r.top}px`});
    const w=card.offsetWidth,h=card.offsetHeight,gap=16;
    let x=left+width-w-12,y=top+height-h-12;
    if(visible){
      const options=[[r.right+gap,r.top],[r.left-w-gap,r.top],[r.left,r.bottom+gap],[r.left,r.top-h-gap]];
      const fits=([a,b])=>a>=left+12&&a+w<=left+width-12&&b>=top+12&&b+h<=top+height-12;
      const choice=options.find(fits);
      if(choice)[x,y]=choice;
      else{
        // In short/narrow windows preserve as much of the highlighted control as
        // possible, rather than always covering the bottom-right of the screen.
        const overlap=([a,b])=>Math.max(0,Math.min(a+w,r.right)-Math.max(a,r.left))*
          Math.max(0,Math.min(b+h,r.bottom)-Math.max(b,r.top));
        const corners=[[x,y],[x,top+12],[left+12,y],[left+12,top+12]];
        [x,y]=corners.reduce((best,point)=>overlap(point)<overlap(best)?point:best);
      }
    }
    x=Math.max(left+12,Math.min(x,left+width-w-12));y=Math.max(top+12,Math.min(y,top+height-h-12));
    Object.assign(card.style,{left:`${x}px`,top:`${y}px`});
  }
  function schedule(){if(dialog.open&&!frame)frame=requestAnimationFrame(position);}
  function showStep(){
    if(frame)cancelAnimationFrame(frame);frame=0;
    const step=studioTourSteps[index];
    dialog.dataset.step=step.id;
    dialog.querySelector('#studioTourProgress').textContent=t('Step {0} of {1}',index+1,studioTourSteps.length);
    dialog.querySelector('#studioTourTitle').textContent=t(step.title);
    dialog.querySelector('#studioTourText').textContent=t(step.body);
    card.scrollTop=0;
    back.disabled=index===0;next.textContent=t(index===studioTourSteps.length-1?'Done':'Next');
    if(back.disabled&&document.activeElement===back)next.focus({preventScroll:true});
    observer?.disconnect();target=document.querySelector(step.selector);
    if(target){
      panels?.reveal(target,{force:true,persist:false});
      for(let node=target;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
      target.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
      observer?.observe(target);
    }
    observer?.observe(card);position();schedule();
  }
  function restore(){
    if(!events)return;
    events.abort();events=null;observer?.disconnect();observer=null;
    if(frame)cancelAnimationFrame(frame);frame=0;
    panels?.restoreView(view);
    for(const [node,open] of details)if(node.isConnected)node.open=open;
    for(const [node,x,y] of scroll)if(node.isConnected)node.scrollTo({left:x,top:y,behavior:'instant'});
    if(originalFocus?.isConnected&&!originalFocus.disabled)originalFocus.focus({preventScroll:true});
    target=view=originalFocus=null;scroll=[];details=[];
    onClose();
  }
  function close(){if(dialog.open)dialog.close();restore();}
  function open(){
    if(disposed||dialog.open)return false;
    if(!canStart()||document.querySelector('dialog[open]')){
      message('Finish or cancel the current edit or operation before starting the tour.');return false;
    }
    originalFocus=document.activeElement;view=panels?.captureView();
    const containers=new Set([document.scrollingElement]);
    for(const step of studioTourSteps)for(let node=document.querySelector(step.selector);node;node=node.parentElement)containers.add(node);
    scroll=[...containers]
      .filter(node=>node&&node!==dialog&&!dialog.contains(node)&&(node.scrollHeight>node.clientHeight||node.scrollWidth>node.clientWidth))
      .map(node=>[node,node.scrollLeft,node.scrollTop]);
    details=[...document.querySelectorAll('details')].map(node=>[node,node.open]);
    events=new AbortController();const signal=events.signal;
    observer=new ResizeObserver(schedule);
    window.addEventListener('resize',schedule,{signal});
    window.addEventListener('scroll',schedule,{capture:true,signal});
    window.visualViewport?.addEventListener('resize',schedule,{signal});
    window.visualViewport?.addEventListener('scroll',schedule,{signal});
    try{dialog.showModal();index=0;showStep();next.focus({preventScroll:true});return true;}
    catch(error){close();throw error;}
  }
  // Do not commit a numeric draft by blurring it before the admission check.
  trigger.addEventListener('pointerdown',event=>{if(!canStart())event.preventDefault();},{signal:lifetime.signal});
  trigger.addEventListener('click',open,{signal:lifetime.signal});
  closeButton.addEventListener('click',close,{signal:lifetime.signal});
  back.addEventListener('click',()=>{if(index>0){index--;showStep();}},{signal:lifetime.signal});
  next.addEventListener('click',()=>{if(index===studioTourSteps.length-1)close();else{index++;showStep();}},{signal:lifetime.signal});
  dialog.addEventListener('cancel',event=>{event.preventDefault();close();},{signal:lifetime.signal});
  dialog.addEventListener('keydown',event=>{
    // Keep document shortcuts and browser Save from escaping the tour's focus.
    event.stopPropagation();
    if(event.isComposing||event.keyCode===229){event.preventDefault();return;}
    if((event.ctrlKey||event.metaKey)&&!event.altKey&&['KeyS','KeyZ','KeyY','KeyD','KeyG'].includes(event.code)){
      event.preventDefault();return;
    }
    if(event.key!=='Tab')return;
    const controls=[closeButton,back,next].filter(button=>!button.disabled);
    if(event.shiftKey&&document.activeElement===controls[0]){
      event.preventDefault();controls.at(-1).focus();
    }else if(!event.shiftKey&&document.activeElement===controls.at(-1)){
      event.preventDefault();controls[0].focus();
    }
  },{signal:lifetime.signal});
  dialog.addEventListener('close',()=>{if(!dialog.open)restore();},{signal:lifetime.signal});
  function dispose(){if(disposed)return;disposed=true;close();lifetime.abort();dialog.remove();trigger.disabled=true;}
  window.addEventListener('pagehide',dispose,{once:true,signal:lifetime.signal});
  trigger.disabled=false;
  return {open,close,isOpen,dispose};
}
