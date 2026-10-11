// In-app assistant: a side panel that sends questions to the Sapience agent service and acts on the app with the answer
// (it opens the matching page with the filters set, then shows the figures, the page link and the actions it took).
// Each answer carries a LEDGER: the eight steps the agent went through and the facts it was allowed to use. Steps 07 and 08 are
// completed here in the browser: open the page, then compare what the page itself shows with the figures in the answer.
(()=>{
const AGENT=(window.AGENT_URL||`${location.protocol}//${location.hostname}:8018`).replace(/\/$/,'');
const CHIPS=[
  'How did orders in May 2016 compare with April, by territory?',
  'Which states inside Great Lakes moved?',
  'Which items have the most unpicked units in May 2016?',
  'Show the top 5 customers by orders in April 2016'
];
const $$=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let sid=null,busy=false,online=false;const ledgers=[],proposals=[];
try{sid=sessionStorage.getItem('sap_sid');}catch(e){}

const root=document.createElement('div');
root.innerHTML=`
<section id="sap-panel" role="dialog" aria-label="Sapience assistant" hidden>
  <div class="sap-head">
    <div class="sap-title"><span class="sap-badge">S</span><div><b>Sapience Assistant</b><small id="sap-status">Checking connection…</small></div></div>
    <div class="sap-head-btns"><button type="button" id="sap-new" title="Start a new conversation" aria-label="New conversation">New</button><button type="button" id="sap-close" aria-label="Close assistant">&times;</button></div>
  </div>
  <div id="sap-msgs" aria-live="polite"></div>
  <div id="sap-chips" class="sap-chips"></div>
  <form id="sap-form"><textarea id="sap-input" rows="2" maxlength="600" placeholder="Ask about orders, items, customers or suppliers…" aria-label="Your question"></textarea><button type="submit" id="sap-send">Send</button></form>
  <p class="sap-foot">Answers come from the source WWI data (your workspace edits are not included). Every figure is checked against a tool result before it is shown.</p>
</section>
<div id="sap-modal" hidden><div class="sap-modal-card" role="dialog" aria-modal="true" aria-label="How the assistant got this answer">
  <div class="sap-modal-head"><div><b>How the assistant got this answer</b><small>The real steps for this question, with the page and values used at each one</small></div><button type="button" id="sap-modal-close" aria-label="Close">&times;</button></div>
  <div id="sap-modal-body"></div>
</div></div>`;
[...root.children].forEach(c=>document.body.appendChild(c));
const panel=$$('#sap-panel'),msgs=$$('#sap-msgs'),input=$$('#sap-input'),statusEl=$$('#sap-status'),modal=$$('#sap-modal');

function add(cls,html){const d=document.createElement('div');d.className='sap-msg '+cls;d.innerHTML=html;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;return d;}
function paragraphs(t){return String(t||'').split(/\n{1,}/).filter(Boolean).map(p=>`<p>${esc(p)}</p>`).join('');}
function welcome(){
  msgs.innerHTML='';
  add('bot',`<p>Hi, I'm the Sapience assistant. Ask a question about Wide World Importers and I'll find the answer and open the matching page for you.</p><p class="sap-muted">I can compare periods, group by territory, state, customer or item, and follow up on what we just discussed.</p>`);
  $$('#sap-chips').innerHTML=CHIPS.map(c=>`<button type="button" class="sap-chip">${esc(c)}</button>`).join('');
}
async function health(){
  try{const r=await fetch(AGENT+'/health',{cache:'no-store'});const h=await r.json();online=!!h.ok&&h.data_api;
    statusEl.textContent=online?`Online · ${h.model}`:'Data service unreachable';statusEl.className=online?'ok':'bad';}
  catch(e){online=false;statusEl.textContent='Assistant offline';statusEl.className='bad';}
}
function open(){panel.hidden=false;document.body.classList.add('sap-open');health();setTimeout(()=>input.focus(),50);}
function close(){panel.hidden=true;document.body.classList.remove('sap-open');}
window.toggleAssistant=()=>panel.hidden?open():close();

/* ---------- the journey: the real steps taken for this question ---------- */
const WHO={you:'You',model:'Language model',code:'Code check',tool:'Data API',browser:'This page'};
const NN=n=>String(n).padStart(2,'0');
function cellHTML(s){
  const t=s.t==null?'':` · ${s.t}s`;
  return `<button type="button" class="jy-cell st-${s.status} who-${s.who}" data-n="${s.n}" title="${esc(s.note||'Show the details of this step')}"><span class="jy-n">${NN(s.n)}</span><b class="jy-t">${esc(s.title)}</b><span class="jy-d">${esc(s.detail||'')}</span><span class="jy-who">${WHO[s.who]}${t}</span></button>`;
}
function journeyHTML(L){
  const S=L.trail,N=S.length,grid=`style="grid-template-columns:repeat(${N},minmax(122px,1fr))"`;
  const top=S.map(s=>s.n%2?cellHTML(s):'<div></div>').join('');
  const bot=S.map(s=>s.n%2?'<div></div>':cellHTML(s)).join('');
  const reached=s=>s&&(s.status==='done'||s.status==='ask');
  const line=S.map((s,i)=>{
    const left=i===0?'solid':(reached(s)?'solid':'dash');
    const right=i===N-1?'dash':(reached(S[i+1])?'solid':'dash');
    return `<div class="jy-pt st-${s.status} who-${s.who}" data-l="${left}" data-r="${right}"><i></i></div>`;
  }).join('');
  return `<div class="jy" style="min-width:${N*122}px"><div class="jy-row" ${grid}>${top}</div><div class="jy-line" ${grid}>${line}</div><div class="jy-row" ${grid}>${bot}</div></div>`;
}
function pathHTML(L){
  const seq=[];
  L.trail.forEach(s=>{if(['you','tool','browser'].includes(s.who)&&s.where&&s.status!=='pending'){const w=s.who==='browser'&&s.n&&!s.where.startsWith('#')?s.where:s.where;if(seq[seq.length-1]!==w)seq.push(w);}});
  if(!seq.length)return'';
  return `<div class="jy-path"><span class="jy-path-l">Where it went</span>${seq.map((w,i)=>`${i?'<i class="jy-arrow">→</i>':''}<span class="jy-loc${w.startsWith('#')?' page':w.startsWith('POST')?' api':''}">${esc(w)}</span>`).join('')}</div>`;
}
function logHTML(L){
  return `<ol class="jy-log">${L.trail.map(s=>`<li id="jy-log-${s.n}" class="st-${s.status}"><details${s.who==='tool'||s.status==='failed'?' open':''}><summary><span class="jy-num">${NN(s.n)}</span><span class="jy-chip who-${s.who}">${WHO[s.who]}</span><b>${esc(s.title)}</b>${s.detail?`<span class="jy-sum"> — ${esc(s.detail)}</span>`:''}<span class="jy-time">${s.t==null?'':s.t+' s'}</span></summary>${s.where?`<p class="jy-where">${esc(s.where)}</p>`:''}${s.note?`<p class="sap-muted">${esc(s.note)}</p>`:''}${s.kv&&s.kv.length?`<table class="jy-kv"><tbody>${s.kv.map(([k,v])=>`<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</tbody></table>`:''}</details></li>`).join('')}</ol>`;
}
function factsHTML(L){
  if(!L.facts||!L.facts.length)return'<p class="sap-muted">No numeric facts were recorded for this answer.</p>';
  return `<table class="jy-facts"><thead><tr><th>Ledger entry</th><th>Value</th><th>Where it came from</th></tr></thead><tbody>${L.facts.map(f=>`<tr><td>${esc(f.label)}</td><td><b>${esc(f.value)}</b></td><td><span class="jy-by ${f.by}">${f.by==='code'?'computed by code':'tool result'}</span> ${esc(f.source)}</td></tr>`).join('')}</tbody></table>`;
}
function modalHTML(L){
  return `${L.question?`<p class="jy-q">Question: <b>“${esc(L.question)}”</b>${L.followed_up?' <span class="sap-muted">(a follow-up)</span>':''}</p>`:''}
  <div class="jy-wrap">${journeyHTML(L)}</div>
  <div class="jy-legend">${['you','model','code','tool','browser'].map(w=>`<span><i class="jy-chip who-${w}">${WHO[w]}</i></span>`).join('')}<span><i class="lg"></i>done</span><span><i class="lg dash"></i>waiting or not reached</span><span><i class="lg bad"></i>failed</span></div>
  ${pathHTML(L)}
  <h3 class="jy-h">Step by step</h3><p class="sap-muted">Click a step above to jump to it. Each step lists the exact values used.</p>${logHTML(L)}
  <h3 class="jy-h">The ledger</h3>
  <p class="sap-muted">Only values in this list may appear in the answer. Differences and percentages are computed by code, never by the model.</p>${factsHTML(L)}`;
}
function miniHTML(L){return L.trail.map(s=>`<i class="mini st-${s.status} who-${s.who}" title="${esc(NN(s.n)+' '+s.title+(s.detail?': '+s.detail:''))}"></i>`).join('');}
let openIdx=null;
function refreshLedger(idx){
  const el=msgs.querySelector(`.sap-journey[data-i="${idx}"] .mini-strip`);if(el)el.innerHTML=miniHTML(ledgers[idx]);
  if(openIdx===idx&&!modal.hidden){const body=$$('#sap-modal-body'),keep=body.scrollTop,open=[...body.querySelectorAll('.jy-log details')].map(d=>d.open);body.innerHTML=modalHTML(ledgers[idx]);body.querySelectorAll('.jy-log details').forEach((d,i)=>{if(open[i]!==undefined)d.open=open[i];});body.scrollTop=keep;}
}
function showJourney(idx){openIdx=idx;$$('#sap-modal-body').innerHTML=modalHTML(ledgers[idx]);modal.hidden=false;}
function setItem(idx,item,patch){Object.assign(item,patch);refreshLedger(idx);}

/* ---------- the last steps only the browser can do: open the page, read it, compare it with the answer ---------- */
const same=(a,b)=>Number(a)===Number(b);
async function openAndConfirm(idx,link,base){
  const L=ledgers[idx],B=L.trail.filter(s=>s.who==='browser');
  if(!link||!link.startsWith('#/')||B.length<3){if(link&&link.startsWith('#/'))location.hash=link.slice(1);return;}
  const [o,r,c]=B,rcv=Date.now(),el=()=>Math.round(((base||0)+(Date.now()-rcv)/1000)*10)/10;
  const want=(L.expect&&L.expect.request)||{},path=link.slice(2).split('?')[0];
  location.hash=link.slice(1);
  await sleep(200);
  let ready=false;const t0=Date.now();
  while(Date.now()-t0<30000){
    const done=$$('#content')&&$$('#content').dataset.completed==='true',bad=$$('#error')&&!$$('#error').hidden;
    const here=(location.hash.slice(2)||'').split('?')[0]===path;
    if(here&&(done||bad)){
      if(path==='analysis'&&L.expect){const w=window.wwiState;
        if(w&&w.route==='analysis'&&w.completed&&w.request&&['start','end','compare_start','compare_end','group_by'].every(k=>(w.request[k]||null)===(want[k]||null)||(k==='group_by'&&!w.request[k]&&want[k]==='none'))&&w.summary){ready=true;break;}}
      else{ready=true;break;}
    }
    await sleep(250);
  }
  const loadS=Math.round((Date.now()-t0)/100)/10,heading=($$('#title')||{}).textContent||path,active=document.querySelector('nav a.active'),scope=(($$('#scope')||{}).textContent||'').trim();
  if(!ready){
    setItem(idx,o,{status:'failed',title:'Open the page',detail:'#/'+path+' did not load',where:'#/'+path,t:el(),kv:[['Link',link],['Waited','30 s']]});
    setItem(idx,r,{status:'skipped',detail:'Page not loaded'});setItem(idx,c,{status:'skipped',detail:'Nothing to compare'});return;
  }
  const rows=document.querySelectorAll('#content tbody tr').length,panels=[...document.querySelectorAll('#content h2')].map(h=>h.textContent).slice(0,5).join(' · '),err=$$('#error')&&!$$('#error').hidden?$$('#error').textContent:'';
  setItem(idx,o,{status:err?'failed':'done',title:`Opened the ${heading} page`,detail:'#/'+path,where:'#/'+path,t:el(),
    kv:[['Page heading',heading],['Sidebar item',active?active.textContent.trim():null],['Address',location.hash],['Loaded in',loadS+' s']],note:'The assistant sets the page address; the app itself then loads the view and applies the filters.'});
  const sm=window.wwiState&&window.wwiState.summary;
  setItem(idx,r,{status:err?'failed':'done',title:'Read the page',detail:err?_s(err):(path==='analysis'&&sm&&sm.total_current!=null?`${Number(sm.total_current).toLocaleString('en-US')} vs ${Number(sm.total_baseline).toLocaleString('en-US')}`:path==='analysis'&&sm&&sm.total!=null?`Total ${Number(sm.total).toLocaleString('en-US')}`:`${heading} · ${rows} table row${rows===1?'':'s'}`),where:'#/'+path,t:el(),
    kv:[['Scope line shown on the page',scope],['Sections on the page',panels],['Table rows visible',rows],['Figures on the page',sm?(sm.total_current!=null?`now ${sm.total_current}, before ${sm.total_baseline}, change ${sm.change}`:(sm.total!=null?`total ${sm.total}`:null)):null],['Error shown',err||null]],note:'What the page itself displays after it has loaded, read from the page, not from the assistant.'});
  if(err){setItem(idx,c,{status:'failed',detail:'Page shows an error',t:el()});return;}
  if(!L.expect||!sm){setItem(idx,c,{status:'done',title:'Confirm the page loaded',detail:'Loaded without errors',t:el(),kv:[['Result','The page loaded and showed no error']],note:'This kind of answer has no single figure to compare with the page.'});return;}
  const E=L.expect,single=E.total!=null&&E.total_current==null,fmt=v=>Number(v).toLocaleString('en-US'),sg=v=>(v>0?'+':'')+v;
  const ok=single?same(sm.total,E.total):(same(sm.total_current,E.total_current)&&same(sm.total_baseline,E.total_baseline)&&same(sm.change,E.change));
  const pageTxt=single?fmt(sm.total):`${fmt(sm.total_current)} against ${fmt(sm.total_baseline)} (${sg(sm.change)})`,ansTxt=single?fmt(E.total):`${fmt(E.total_current)} against ${fmt(E.total_baseline)} (${sg(E.change)})`;
  setItem(idx,c,ok?{status:'done',title:'Compared with the answer',detail:'Same figures',t:el(),kv:[['Page shows',pageTxt],['Answer used',ansTxt],['Result','match']],note:'Two separate routes to the same numbers: the data API (answer) and the app view (page).'}
              :{status:'failed',title:'Compared with the answer',detail:'Page differs',t:el(),kv:[['Page shows',pageTxt],['Answer used',ansTxt],['Result','different']]});
}
function _s(x){x=String(x||'');return x.length>90?x.slice(0,89)+'…':x;}

async function ask(q){
  if(busy||!q.trim())return;
  busy=true;$$('#sap-send').disabled=true;$$('#sap-chips').innerHTML='';
  add('user',`<p>${esc(q)}</p>`);input.value='';
  const work=add('bot sap-work',`<span class="sap-dots"><i></i><i></i><i></i></span> Working on it… <span id="sap-t">0</span>s`);
  const t0=Date.now(),tick=setInterval(()=>{const e=$$('#sap-t');if(e)e.textContent=Math.round((Date.now()-t0)/1000);},500);
  try{
    const r=await fetch(AGENT+'/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,session_id:sid})});
    const d=await r.json();work.remove();
    if(d.session_id){sid=d.session_id;try{sessionStorage.setItem('sap_sid',sid);}catch(e){}}
    render(d,r.ok);
  }catch(e){work.remove();add('bot sap-err',`<p>I couldn't reach the assistant service. Check that it is running, then try again.</p>`);}
  finally{clearInterval(tick);busy=false;$$('#sap-send').disabled=false;input.focus();}
}
function render(d,ok){
  const kind=!ok||d.status==='error'?'sap-err':d.status==='answered'?'':d.status==='clarify'?'sap-ask':'sap-note';
  let h=paragraphs(d.text);
  (d.notes||[]).forEach(n=>{h+=`<p class="sap-muted">${esc(n)}</p>`;});
  let idx=null;
  if(d.ledger){idx=ledgers.push(d.ledger)-1;h+=`<button type="button" class="sap-journey" data-i="${idx}"><span class="mini-strip">${miniHTML(d.ledger)}</span><span>See how I got this answer</span></button>`;}
  let pidx=null;
  if(d.proposal){pidx=proposals.push(d.proposal)-1;h+=`<div class="sap-propose" data-p="${pidx}"><b>Save this as a chart?</b><small>It is stored as a request and redrawn from the data each time. Nothing is saved until you press Save.</small><input class="sap-ptitle" maxlength="80" value="${esc(d.proposal.title)}" aria-label="Chart title"><div class="sap-pbtns"><button type="button" class="sap-psave">Save chart</button><span class="sap-pmsg"></span></div></div>`;}
  if(d.deep_link){h+=`<button type="button" class="sap-link" data-link="${esc(d.deep_link)}">Open this view in the app</button>`;}
  if((d.actions||[]).length){h+=`<details><summary>What I did (${d.actions.length} step${d.actions.length>1?'s':''})</summary><ul>${d.actions.map(a=>`<li>${esc(a)}</li>`).join('')}</ul></details>`;}
  if(d.latency!==undefined&&ok&&d.status!=='error'){h+=`<p class="sap-meta">${esc(d.status)} · ${d.latency}s · ${d.llm_calls} model call${d.llm_calls===1?'':'s'}</p>`;}
  add('bot '+kind,h);
  if(ok&&d.status==='answered'&&d.deep_link){
    if(idx!==null)openAndConfirm(idx,d.deep_link,d.latency);else location.hash=d.deep_link.slice(1);
  }
}
async function savePropose(box){
  const p=proposals[Number(box.dataset.p)],msg=box.querySelector('.sap-pmsg'),btn=box.querySelector('.sap-psave');
  const title=box.querySelector('.sap-ptitle').value.trim();
  if(!title){msg.textContent='Give the chart a title.';return;}
  btn.disabled=true;msg.textContent='Saving…';
  try{
    const r=await fetch('/api/ws/create',{method:'POST',headers:{'Content-Type':'application/json','X-Sapience-Write':'1'},body:JSON.stringify({kind:'chart',data:{...p,title}})});
    const d=await r.json();if(!r.ok)throw new Error(d.error||'Could not save');
    box.classList.add('saved');msg.innerHTML=`Saved. <a href="#/charts">Open in the Chart builder</a>`;btn.hidden=true;
  }catch(e){msg.textContent=e.message;btn.disabled=false;}
}
panel.addEventListener('click',e=>{
  const sv=e.target.closest('.sap-psave');if(sv){savePropose(sv.closest('.sap-propose'));return;}
  const c=e.target.closest('.sap-chip');if(c){ask(c.textContent);return;}
  const j=e.target.closest('.sap-journey');if(j){showJourney(Number(j.dataset.i));return;}
  const o=e.target.closest('.sap-link');if(o){const link=o.dataset.link;location.hash=link.slice(1);}
});
function closeModal(){modal.hidden=true;openIdx=null;}
$$('#sap-modal-close').onclick=closeModal;
modal.addEventListener('click',e=>{if(e.target===modal){closeModal();return;}const c=e.target.closest('.jy-cell');if(c){const li=$$('#jy-log-'+c.dataset.n);if(li){const d=li.querySelector('details');if(d)d.open=true;li.scrollIntoView({behavior:'smooth',block:'center'});li.classList.add('flash');setTimeout(()=>li.classList.remove('flash'),1400);}}});
$$('#sap-form').addEventListener('submit',e=>{e.preventDefault();ask(input.value);});
input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask(input.value);}});
$$('#sap-close').onclick=close;
$$('#sap-new').onclick=async()=>{try{if(sid)await fetch(AGENT+'/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sid})});}catch(e){}sid=null;try{sessionStorage.removeItem('sap_sid');}catch(e){}welcome();};
document.addEventListener('keydown',e=>{if(e.key==='Escape'){if(!modal.hidden)closeModal();else if(!panel.hidden)close();}});
const btn=$$('#ask-open');if(btn)btn.onclick=window.toggleAssistant;
window.sapienceAsk=ask;   // used by tests and by the VACP bridge
window.sapienceLedgers=ledgers;
welcome();
})();
