// Observe one edit link. Artwork replacement remains an explicit Studio action.
const statusKeys=Object.freeze({
  launching:'Opening source editor...',
  editing:'Editing source artwork.',
  ready:'Returned artwork ready to apply.',
  taken:'Artwork received. Apply has not completed.',
  cancelled:'Edit link cancelled. Your current artwork is unchanged.',
  failed:'Source edit failed.',
  expired:'Source edit expired. Start a new edit from Studio.',
  stale:'Source edit is out of date. Start a new edit from Studio.',
  applying:'Applying returned artwork...',
  applied:'Applied. Undo restores the previous artwork.',
  'apply-failed':'Could not apply returned artwork.',
});
// Local apply states are presentation only, never source-job protocol values.
export const sourceEditStatusKey=status=>Object.hasOwn(statusKeys,status)?statusKeys[status]:'Source edit status unavailable.';

export function createSourceEditMonitor({read,update,onError=()=>{},schedule=setTimeout,cancel=clearTimeout}) {
  const terminal=new Set(['ready','taken','cancelled','failed','expired','stale']);
  const statuses=new Set(['launching','editing',...terminal]);
  let job=null,epoch=0,timer=null,pending=null,failures=0;
  const clear=()=>{if(timer!==null)cancel(timer);timer=null;};
  function stop(){epoch++;clear();job=null;pending=null;failures=0;}
  function queue(){
    clear();
    if(job&&!terminal.has(job.status)&&failures<5)
      timer=schedule(()=>{timer=null;void check();},Math.min(15000,2000*2**failures));
  }
  async function check(){
    clear();if(!job||pending)return;
    const current=job,generation=epoch,request={};pending=request;
    try{
      const value=await read(current);
      if(generation!==epoch||job!==current)return;
      if(!value||!statuses.has(value.status))throw Error('Invalid source edit status.');
      failures=0;update(current,value);
    }catch(error){
      if(generation===epoch&&job===current&&++failures===5)onError(current,error);
    }finally{
      if(pending===request){pending=null;queue();}
    }
  }
  return {start(value){stop();job=value;queue();},check,stop};
}
