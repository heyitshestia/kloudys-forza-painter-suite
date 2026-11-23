'use strict';
(() => {
  const form = document.querySelector('#lookup'), input = form.querySelector('input');
  const clear = document.querySelector('#clear'), count = document.querySelector('#count'), list = document.querySelector('#results');
  const clean = s => s.toLowerCase().normalize('NFKD').replace(/[^a-z0-9]+/g, ' ').trim();
  const entries = [];
  for (const article of document.querySelectorAll('.topic')) {
    const title = article.querySelector('h3').textContent, part = article.dataset.part;
    entries.push({id:article.id,title,part,scope:'',keys:clean(article.dataset.terms),label:clean(title),body:clean(article.textContent)});
    for (const row of article.querySelectorAll('.controls > div')) {
      const name = row.querySelector('dt').textContent;
      entries.push({id:row.id,title:name,part,scope:title,keys:clean(title),label:clean(name),body:clean(row.textContent)});
    }
  }
  function render() {
    const q=clean(input.value), words=q.split(' ');
    clear.hidden=!input.value; list.replaceChildren(); list.hidden=!q; count.textContent='';
    if(!q)return;
    const scored=[];
    for(const e of entries){
      const labels=e.label.split(' '), all=e.label+' '+e.keys+' '+e.body;
      if(!words.every(w=>all.includes(w)))continue;
      const exact=e.title.split(' / ').some(v=>clean(v)===q);
      let score=(exact?140:0)+(e.label.includes(q)?55:0)+(e.keys.includes(q)?22:0)+(e.body.includes(q)?8:0);
      for(const w of words)score+=labels.includes(w)?12:e.label.includes(w)?6:e.keys.includes(w)?4:1;
      scored.push([score,e]);
    }
    scored.sort((a,b)=>b[0]-a[0]);
    const hits=scored.slice(0,12);
    count.textContent=hits.length?(scored.length>12?'Top 12 of '+scored.length+' matches':scored.length+' '+(scored.length===1?'match':'matches')):'No matches. Try a shorter word or use the A–Z index.';
    list.hidden=!hits.length;
    for(const [,e] of hits){const li=document.createElement('li'),a=document.createElement('a'),context=document.createElement('small');a.href='#'+e.id;a.textContent=e.title;context.textContent=e.part+(e.scope?' · '+e.scope:'');li.append(a,context);list.append(li);}
  }
  input.addEventListener('input',render);
  function reset(){input.value='';render();input.focus();}
  clear.addEventListener('click',reset);
  form.addEventListener('submit',event=>{event.preventDefault();const target=list.querySelector('a');if(target)target.click();});
  input.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();reset();}else if(event.key==='ArrowDown'&&!list.hidden){event.preventDefault();list.querySelector('a')?.focus();}});
  if (window.matchMedia('(max-width:650px)').matches) {
    for (const group of document.querySelectorAll('aside nav details')) group.open=false;
  }
  form.hidden=false;
})();
