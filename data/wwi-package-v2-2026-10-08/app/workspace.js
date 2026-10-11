// Workspace: create, edit and delete records without touching the source data.
// Every change goes through a review step, is saved to a separate store (/api/ws/*), is logged, and can be undone (deletes are soft,
// edits can be reverted to the source values). Analytics read only the source, so nothing here moves a reported figure.
(()=>{
const WH={'Content-Type':'application/json','X-Sapience-Write':'1'};
const ENT={customer:'customer',supplier:'supplier',item:'stock_item'};
const LISTS={customers:'customer',items:'item',suppliers:'supplier'};
const PLURAL={customer:'customers',item:'items',supplier:'suppliers',order:'orders'};
let SCHEMA=null;const LOOK={};let tab='records',showDeleted=false,kindFilter='';
const q=s=>document.querySelector(s);

async function wapi(path,body){
  const r=await fetch('/api/ws/'+path,body?{method:'POST',headers:WH,body:JSON.stringify(body)}:{cache:'no-store'});
  const d=await r.json().catch(()=>({error:'Unexpected response'}));
  if(!r.ok)throw new Error(d.error||'Request failed');return d;
}
async function schema(){if(!SCHEMA)SCHEMA=await wapi('schema');return SCHEMA;}
async function lookup(type){if(!LOOK[type]){const r=await fetch('/api/lookup?type='+type);LOOK[type]=await r.json();}return LOOK[type];}
const nm=(type,id)=>((LOOK[type]||[]).find(x=>Number(x.id)===Number(id))||{}).name;

/* ---------- small helpers ---------- */
function toast(msg,bad){const t=document.createElement('div');t.className='ws-toast'+(bad?' bad':'');t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),3800);}
function when(ts){return new Date(ts*1000).toLocaleString('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});}
function val(v){return v===null||v===undefined||v===''?'—':String(v);}
async function refreshCount(){try{const c=await wapi('counts');const n=Object.values(c).reduce((a,b)=>a+b,0);const el=q('#ws-count');if(el){el.textContent=n||'';el.hidden=!n;}}catch(e){}}

/* ---------- the modal ---------- */
const modal=document.createElement('div');modal.id='ws-modal';modal.hidden=true;
modal.innerHTML='<div class="ws-card" role="dialog" aria-modal="true"><div class="ws-head"><div><b id="ws-title"></b><small id="ws-sub"></small></div><button type="button" id="ws-x" aria-label="Close">&times;</button></div><div id="ws-body"></div></div>';
document.body.appendChild(modal);
const body=()=>q('#ws-body');
function closeModal(){modal.hidden=true;body().innerHTML='';}
q('#ws-x').onclick=closeModal;
modal.addEventListener('mousedown',e=>{if(e.target===modal)closeModal();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden){e.stopPropagation();closeModal();}},true);
function openModal(title,sub){q('#ws-title').textContent=title;q('#ws-sub').textContent=sub||'';modal.hidden=false;}

/* ---------- form fields ---------- */
function pickerHTML(name,type,cur,label){
  return `<div class="ws-pick" data-name="${name}" data-ent="${type}"><input type="hidden" name="${name}" value="${esc(cur??'')}"><div class="ws-picked">${cur?`<b>${esc(label||('#'+cur))}</b> <span class="ws-id">#${esc(cur)}</span> <button type="button" class="ws-link" data-act="unpick">change</button>`:'<span class="ws-muted">Nothing chosen</span>'}</div><div class="ws-find"${cur?' hidden':''}><input type="search" placeholder="Type part of a name" autocomplete="off"><button type="button" class="secondary" data-act="find">Search</button></div><div class="chips ws-res"></div></div>`;
}
function fieldHTML(f,v,labels){
  const id='wsf-'+f.name,req=f.required?' <span class="ws-req" title="Required">*</span>':'';
  let input='';
  if(f.type==='text'){const long=f.limit>200;input=long?`<textarea id="${id}" name="${f.name}" rows="3" maxlength="${f.limit}">${esc(v??'')}</textarea>`:`<input id="${id}" name="${f.name}" type="text" maxlength="${f.limit}" value="${esc(v??'')}">`;}
  else if(f.type==='int')input=`<input id="${id}" name="${f.name}" type="number" min="0" step="1" value="${esc(v??'')}">`;
  else if(f.type==='date')input=`<input id="${id}" name="${f.name}" type="date" value="${esc(v??'')}">`;
  else if(f.type.startsWith('select:')){const t=f.type.split(':')[1],opts=LOOK[t]||[];input=`<select id="${id}" name="${f.name}"><option value="">— none —</option>${opts.map(o=>`<option value="${o.id}"${Number(o.id)===Number(v)?' selected':''}>${esc(o.name)}</option>`).join('')}</select>`;}
  else if(f.type.startsWith('ref:'))input=pickerHTML(f.name,f.type.split(':')[1],v,labels&&labels[f.name]);
  return `<div class="ws-field"><label for="${id}">${esc(f.label)}${req}</label>${input}</div>`;
}
function lineHTML(l,i){
  return `<tr data-i="${i}"><td>${pickerHTML('item_id','stock_item',l.item_id,l.item_name)}</td><td><input class="ws-qty" type="number" min="1" max="100000" step="1" value="${esc(l.qty??1)}" aria-label="Quantity"></td><td><button type="button" class="ws-x" data-act="rmline" aria-label="Remove line">&times;</button></td></tr>`;
}
function readForm(sch){
  const out={};
  sch.fields.forEach(f=>{const el=body().querySelector(`[name="${f.name}"]`);if(el)out[f.name]=el.value===''?null:el.value;});
  if(sch.has_lines){out.lines=[...body().querySelectorAll('.ws-lines tbody tr')].map(tr=>{
    const p=tr.querySelector('.ws-pick');return{item_id:p.querySelector('input[type=hidden]').value||null,item_name:(p.querySelector('.ws-picked b')||{}).textContent||'',qty:tr.querySelector('.ws-qty').value};});}
  return out;
}

/* ---------- create / edit flow ---------- */
// ctx: {kind, mode:'create'|'edit-source'|'update', ref_id?, rec?, preset?}
async function openForm(ctx){
  const S=(await schema())[ctx.kind];
  await Promise.all(S.fields.filter(f=>f.type.startsWith('select:')).map(f=>lookup(f.type.split(':')[1])));
  let cur={},labels={},title='',sub='';
  if(ctx.mode==='create'){cur={...(ctx.preset||{})};title='New '+S.label.toLowerCase();sub='Saved to your workspace. The source data is not changed.';}
  else if(ctx.mode==='update'){cur={...ctx.rec.data};title='Edit '+S.label.toLowerCase();sub='Workspace record #'+ctx.rec.id;}
  else{
    const src=(await wapi('source?kind='+ctx.kind+'&ref_id='+ctx.ref_id)).values;
    const ov=(await wapi('list?kind='+ctx.kind+'&ref_id='+ctx.ref_id)).records[0];
    ctx.source=src;cur={...src,...(ov&&!ov.deleted?ov.data:{}),...(ctx.typed||{})};ctx.prior=ov;title='Edit '+S.label.toLowerCase()+' '+ctx.ref_id;sub='Saved as a workspace edit; the source row stays as it is.';
  }
  // names for chosen references
  for(const f of S.fields)if(f.type.startsWith('ref:')&&cur[f.name])labels[f.name]=await refName(f.type.split(':')[1],cur[f.name]);
  if(ctx.kind==='order')for(const l of cur.lines||[])if(!l.item_name)l.item_name=await refName('stock_item',l.item_id);
  openModal(title,sub);
  body().innerHTML=`<form id="ws-form" novalidate>
    ${S.fields.map(f=>fieldHTML(f,cur[f.name],labels)).join('')}
    ${S.has_lines?`<div class="ws-field"><label>Order lines <span class="ws-req">*</span></label><table class="ws-lines"><thead><tr><th>Item</th><th>Qty</th><th></th></tr></thead><tbody>${(cur.lines&&cur.lines.length?cur.lines:[{qty:1}]).map(lineHTML).join('')}</tbody></table><button type="button" class="secondary" data-act="addline">+ Add line</button></div>`:''}
    <p class="ws-err" id="ws-err" role="alert" hidden></p>
    <div class="ws-actions"><button type="button" class="secondary" data-act="cancel">Cancel</button><button type="submit">Review changes</button></div></form>`;
  const form=q('#ws-form');
  form.onsubmit=e=>{e.preventDefault();review(ctx,S,cur,labels);};
  form.onclick=e=>formClick(e,S);
  const first=form.querySelector('input:not([type=hidden]),select,textarea');if(first)first.focus();
}
async function refName(ent,id){
  try{const r=await fetch('/api/records',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:PLURAL[{customer:'customer',supplier:'supplier',stock_item:'item'}[ent]],dataset_version:'wwi-data-v1-2026-10-08',scenario_id:'base',date_basis:'none',filters:{[{customer:'customer_id',supplier:'supplier_id',stock_item:'stock_item_id'}[ent]]:Number(id)},limit:1,offset:0})});
    const d=await r.json();const row=d.rows&&d.rows[0];return row?(row.CustomerName||row.SupplierName||row.StockItemName):'#'+id;}catch(e){return '#'+id;}
}
async function formClick(e,S){
  const b=e.target.closest('[data-act]');if(!b)return;const act=b.dataset.act;
  if(act==='cancel')return closeModal();
  if(act==='addline'){const tb=body().querySelector('.ws-lines tbody');if(tb.rows.length>=S.max_lines)return;tb.insertAdjacentHTML('beforeend',lineHTML({qty:1},tb.rows.length));}
  if(act==='rmline'){const tb=body().querySelector('.ws-lines tbody');if(tb.rows.length>1)b.closest('tr').remove();}
  const pick=b.closest('.ws-pick');if(!pick)return;
  if(act==='unpick'){pick.querySelector('input[type=hidden]').value='';pick.querySelector('.ws-picked').innerHTML='<span class="ws-muted">Nothing chosen</span>';pick.querySelector('.ws-find').hidden=false;}
  if(act==='find'){
    const text=pick.querySelector('.ws-find input').value.trim(),out=pick.querySelector('.ws-res');if(!text)return;out.textContent='Searching…';
    try{const r=await fetch('/api/resolve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,types:[pick.dataset.ent],limit:8})});const d=await r.json();if(!r.ok)throw new Error(d.error);
      out.innerHTML=(d.candidates||[]).length?d.candidates.map(c=>`<button type="button" data-act="choose" data-id="${c.id}" data-name="${esc(c.name)}">${esc(c.name)}${c.detail?' · '+esc(c.detail):''}</button>`).join(''):'<span class="ws-muted">No match. Try a shorter part of the name.</span>';}
    catch(err){out.textContent=err.message;}
  }
  if(act==='choose'){pick.querySelector('input[type=hidden]').value=b.dataset.id;pick.querySelector('.ws-picked').innerHTML=`<b>${esc(b.dataset.name)}</b> <span class="ws-id">#${esc(b.dataset.id)}</span> <button type="button" class="ws-link" data-act="unpick">change</button>`;pick.querySelector('.ws-find').hidden=true;pick.querySelector('.ws-res').innerHTML='';}
}
document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.closest&&e.target.closest('.ws-find input')){e.preventDefault();e.target.closest('.ws-find').querySelector('[data-act=find]').click();}});

function showError(msg){const el=q('#ws-err');if(el){el.textContent=msg;el.hidden=false;}}
function displayVal(f,v,labels){
  if(v===null||v===undefined||v==='')return '—';
  if(f.type.startsWith('select:')){return nm(f.type.split(':')[1],v)||('#'+v);}
  if(f.type.startsWith('ref:'))return (labels&&labels[f.name])?`${labels[f.name]} (#${v})`:'#'+v;
  return String(v);
}
async function review(ctx,S,before,labels){
  const data=readForm(S);const rows=[];
  const newLabels={...labels};
  for(const f of S.fields)if(f.type.startsWith('ref:')&&data[f.name]&&Number(data[f.name])!==Number(before[f.name]))newLabels[f.name]=await refName(f.type.split(':')[1],data[f.name]);
  S.fields.forEach(f=>{const a=data[f.name]===undefined?null:data[f.name],b=before[f.name]===undefined?null:before[f.name];
    const same=String(a??'')===String(b??'');if(ctx.mode==='create'||!same)rows.push([f.label,ctx.mode==='create'?null:displayVal(f,b,labels),displayVal(f,a,newLabels),same]);});
  let linesHTML='';
  if(S.has_lines){const L=(data.lines||[]).filter(l=>l.item_id);linesHTML=`<h4 class="ws-h">Lines (${L.length})</h4><table class="ws-diff"><thead><tr><th>Item</th><th>Qty</th></tr></thead><tbody>${L.map(l=>`<tr><td>${esc(l.item_name||'#'+l.item_id)} <span class="ws-id">#${esc(l.item_id)}</span></td><td>${esc(l.qty)}</td></tr>`).join('')}</tbody></table>`;}
  if(ctx.mode!=='create'&&!rows.length&&!S.has_lines){showError('Nothing has changed yet.');return;}
  body().innerHTML=`<p class="ws-note">Check what will be saved. Nothing is written until you confirm.</p>
  <table class="ws-diff"><thead><tr><th>Field</th>${ctx.mode==='create'?'':'<th>Now</th>'}<th>${ctx.mode==='create'?'Value':'After'}</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r[0])}</td>${ctx.mode==='create'?'':`<td class="ws-old">${esc(r[1])}</td>`}<td><b>${esc(r[2])}</b></td></tr>`).join('')}</tbody></table>${linesHTML}
  <p class="ws-err" id="ws-err" role="alert" hidden></p>
  <div class="ws-actions"><button type="button" class="secondary" id="ws-back">Back</button><button type="button" id="ws-save">Confirm and save</button></div>`;
  q('#ws-back').onclick=()=>openFormAgain(ctx,data);
  q('#ws-save').onclick=async()=>{
    const btn=q('#ws-save');btn.disabled=true;btn.textContent='Saving…';
    try{
      let res;
      if(ctx.mode==='create')res=await wapi('create',{kind:ctx.kind,data});
      else if(ctx.mode==='update')res=await wapi('update',{id:ctx.rec.id,data,version:ctx.rec.version});
      else res=await wapi('edit',{kind:ctx.kind,ref_id:ctx.ref_id,data});
      closeModal();toast(res.unchanged?'No difference from the source, nothing saved.':(ctx.mode==='create'?'Saved to your workspace.':'Change saved.'));
      afterWrite();
    }catch(err){btn.disabled=false;btn.textContent='Confirm and save';showError(err.message);}
  };
}
function openFormAgain(ctx,data){   // back from review: reopen the form with what was typed
  if(ctx.mode==='create')ctx.preset=data;else if(ctx.mode==='update')ctx.rec={...ctx.rec,data};else ctx.typed=data;
  openForm(ctx);
}
function afterWrite(){refreshCount();if(typeof render==='function')render();}

/* ---------- delete / restore / revert ---------- */
function confirmBox(title,text,okLabel,danger,fn){
  openModal(title,'');body().innerHTML=`<p class="ws-note">${esc(text)}</p><p class="ws-err" id="ws-err" role="alert" hidden></p><div class="ws-actions"><button type="button" class="secondary" id="ws-no">Cancel</button><button type="button" id="ws-yes" class="${danger?'danger':''}">${esc(okLabel)}</button></div>`;
  q('#ws-no').onclick=closeModal;
  q('#ws-yes').onclick=async()=>{const b=q('#ws-yes');b.disabled=true;try{await fn();closeModal();afterWrite();}catch(e){b.disabled=false;showError(e.message);}};
}
window.wsDelete=(id,label)=>confirmBox('Delete this record?',`“${label}” will be hidden from your workspace. You can restore it later; the audit log keeps a copy.`,'Delete',true,async()=>{await wapi('delete',{id});toast('Deleted. You can restore it from the workspace page.');});
window.wsDeleteBtn=b=>window.wsDelete(Number(b.dataset.del),b.dataset.name);
window.wsRestore=async id=>{try{await wapi('restore',{id});toast('Restored.');afterWrite();}catch(e){toast(e.message,true);}};
window.wsRevert=(kind,ref)=>confirmBox('Revert to source values?','Your workspace edit for this record will be removed and the source values will show again.','Revert',false,async()=>{const src=(await wapi('source?kind='+kind+'&ref_id='+ref)).values;await wapi('edit',{kind,ref_id:ref,data:src});toast('Reverted to the source values.');});
window.wsNew=(kind,preset)=>openForm({kind,mode:'create',preset});
window.wsEditSource=(kind,ref)=>openForm({kind,mode:'edit-source',ref_id:Number(ref)});
window.wsApi=wapi;window.wsToast=toast;
window.wsEdit=async id=>{try{const rec=await wapi('get?id='+id);if(rec.kind==='chart')return window.cbEdit(rec.id);rec.ref_id!==null?openForm({kind:rec.kind,mode:'edit-source',ref_id:rec.ref_id}):openForm({kind:rec.kind,mode:'update',rec});}catch(e){toast(e.message,true);}};

/* ---------- list rendering ---------- */
function summary(r,S){
  const d=r.data;
  if(r.kind==='chart')return `${esc(d.measure_id)} · ${esc(d.group_by)} · ${esc(d.chart_type)} chart`;
  if(r.kind==='order')return `${esc(d.lines.length)} line${d.lines.length>1?'s':''} · ${esc(d.lines.reduce((a,l)=>a+l.qty,0))} units · customer #${esc(d.customer_id)}${d.expected_delivery?' · due '+esc(d.expected_delivery):''}`;
  return Object.entries(d).filter(([k,v])=>v!==null&&k!=='name').map(([k,v])=>{const f=S.fields.find(x=>x.name===k);return `${esc(f?f.label:k)}: ${esc(v)}`;}).join(' · ')||'<span class="ws-muted">no other fields</span>';
}
function recName(r){if(r.kind==='chart')return r.data.title;return r.kind==='order'?'Draft order for customer #'+r.data.customer_id:(r.data.name||('#'+r.ref_id));}
function recRow(r,sc){
  const S=sc[r.kind],edit=r.ref_id!==null;
  return `<tr class="${r.deleted?'ws-del':''}"><td><span class="ws-tag ${edit?'edit':'new'}">${edit?'Edit':'New'}</span> ${esc(S.label)}</td><td>${esc(recName(r))}${edit?` <span class="ws-id">source #${esc(r.ref_id)}</span>`:` <span class="ws-id">ws-${r.id}</span>`}</td><td class="ws-sum">${summary(r,S)}</td><td>${esc(when(r.updated))}</td><td class="ws-ops">${r.deleted?`<button type="button" onclick="wsRestore(${r.id})">Restore</button>`:`<button type="button" onclick="wsEdit(${r.id})">Edit</button>${edit?`<button type="button" class="danger-soft" onclick="wsRevert('${r.kind}',${r.ref_id})">Revert</button>`:`<button type="button" class="danger-soft" data-del="${r.id}" data-name="${esc(recName(r))}" onclick="wsDeleteBtn(this)">Delete</button>`}`}</td></tr>`;
}
window.wsTab=t=>{tab=t;render();};
window.wsFilter=(k,d)=>{kindFilter=k;showDeleted=d;render();};
async function workspacePage(){
  const sc=await schema();$('#scope').textContent='Your workspace · changes are stored apart from the source data and are not included in any analytics figure.';
  const toolbar=`<div class="ws-bar"><div class="ws-new">${['customer','supplier','item','order'].map(k=>`<button type="button" onclick="wsNew('${k}')">+ ${esc(sc[k].label)}</button>`).join('')}</div></div>`;
  const tabs=`<div class="ws-tabs"><button type="button" class="${tab==='records'?'on':''}" onclick="wsTab('records')">Records</button><button type="button" class="${tab==='activity'?'on':''}" onclick="wsTab('activity')">Activity log</button></div>`;
  let main='';
  if(tab==='records'){
    const recs=(await wapi('list'+(showDeleted?'?deleted=1':''))).records.filter(r=>!kindFilter||r.kind===kindFilter);
    const filt=`<div class="ws-filter"><label>Show <select onchange="wsFilter(this.value,${showDeleted})"><option value="">All records</option>${Object.keys(sc).map(k=>`<option value="${k}"${kindFilter===k?' selected':''}>${esc(sc[k].label)}s</option>`).join('')}</select></label><label class="ws-check"><input type="checkbox" ${showDeleted?'checked':''} onchange="wsFilter('${kindFilter}',this.checked)"> include deleted</label></div>`;
    main=filt+(recs.length?`<div class="table-wrap"><table><thead><tr><th>Type</th><th>Record</th><th>Details</th><th>Updated</th><th></th></tr></thead><tbody>${recs.map(r=>recRow(r,sc)).join('')}</tbody></table></div>`:`<div class="empty">Nothing here yet. Use the buttons above to add a record, or open a customer, item or supplier and choose “Edit”.</div>`);
  }else{
    const a=(await wapi('audit?limit=100')).audit;
    main=a.length?`<div class="table-wrap"><table><thead><tr><th>When</th><th>Action</th><th>Record</th><th>Before</th><th>After</th></tr></thead><tbody>${a.map(x=>`<tr><td>${esc(when(x.ts))}</td><td><span class="ws-tag ${x.action}">${esc(x.action)}</span></td><td>${esc(sc[x.kind]?sc[x.kind].label:x.kind)} ${x.ref_id!==null?'<span class="ws-id">source #'+esc(x.ref_id)+'</span>':'<span class="ws-id">ws-'+esc(x.rec_id)+'</span>'}</td><td class="ws-sum">${x.before?esc(JSON.stringify(x.before).slice(0,160)):'—'}</td><td class="ws-sum">${x.after?esc(JSON.stringify(x.after).slice(0,160)):'—'}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">No activity yet.</div>';
  }
  return panel('Workspace',toolbar+tabs+main,'Created records and edits live in a separate store. Deletes are soft and can be undone. Every change is logged.');
}
window.browsePages=window.browsePages||{};window.browsePages.workspace=workspacePage;

/* ---------- toolbars and panels on the existing pages ---------- */
window.wsToolbar=view=>{
  const k=LISTS[view]||(view==='orders'?'order':null);if(!k)return'';
  const label={customer:'customer',item:'stock item',supplier:'supplier',order:'draft order'}[k];
  return `<div class="ws-inline"><button type="button" onclick="wsNew('${k}')">+ New ${label}</button><span class="ws-muted">Saved to your workspace; the source records below are unchanged.</span></div>`;
};
async function listExtras(view){
  const kind=LISTS[view]||(view==='orders'?'order':null);if(!kind)return;
  const sc=await schema(),recs=(await wapi('list?kind='+kind)).records;
  const adds=recs.filter(r=>r.ref_id===null),edits=recs.filter(r=>r.ref_id!==null);
  // mark edited rows in the source table
  const byRef=new Map(edits.map(r=>[String(r.ref_id),r]));
  document.querySelectorAll('#content table tbody tr').forEach(tr=>{const id=(tr.cells[0]||{}).textContent;const r=byRef.get(String(id).trim());if(r){tr.classList.add('ws-edited');const c=tr.cells[1];if(c&&!c.querySelector('.ws-tag'))c.insertAdjacentHTML('beforeend',' <span class="ws-tag edit" title="Edited in your workspace">edited</span>');}});
  if(adds.length){
    const html=panel(`Added in your workspace (${adds.length})`,`<div class="table-wrap"><table><thead><tr><th>Type</th><th>Record</th><th>Details</th><th>Updated</th><th></th></tr></thead><tbody>${adds.map(r=>recRow(r,sc)).join('')}</tbody></table></div>`,'Not part of the source data and not counted in analytics.');
    const c=q('#content');c.insertAdjacentHTML('afterbegin',html);
  }
}
async function detailPanel(view,id){
  const kind={customer:'customer',item:'item',supplier:'supplier'}[view];if(!kind||!id)return;
  const sc=await schema(),S=sc[kind];
  const ov=(await wapi('list?kind='+kind+'&ref_id='+id)).records[0];
  let inner;
  if(ov&&!ov.deleted){
    const src=(await wapi('source?kind='+kind+'&ref_id='+id)).values;await Promise.all(S.fields.filter(f=>f.type.startsWith('select:')).map(f=>lookup(f.type.split(':')[1])));
    inner=`<table class="ws-diff"><thead><tr><th>Field</th><th>Source</th><th>Workspace value</th></tr></thead><tbody>${Object.entries(ov.data).map(([k,v])=>{const f=S.fields.find(x=>x.name===k)||{name:k,label:k,type:'text'};return `<tr><td>${esc(f.label)}</td><td class="ws-old">${esc(src[k]===undefined?'—':displayVal(f,src[k]))}</td><td><b>${esc(displayVal(f,v))}</b></td></tr>`;}).join('')}</tbody></table>`;
  }else inner='<p class="ws-muted">No workspace edits. The values below are the source values.</p>';
  const extra=kind==='customer'?`<button type="button" class="secondary" onclick="wsNew('order',{customer_id:${Number(id)}})">New draft order</button>`:'';
  const html=`<section class="panel ws-panel"><h2>Workspace <span class="ws-tag ${ov&&!ov.deleted?'edit':'new'}">${ov&&!ov.deleted?'edited':'no edits'}</span></h2>${inner}<div class="actions"><button type="button" onclick="wsEditSource('${kind}',${Number(id)})">Edit this ${esc(S.label.toLowerCase())}</button>${ov&&!ov.deleted?`<button type="button" class="secondary" onclick="wsRevert('${kind}',${Number(id)})">Revert to source</button>`:''}${extra}</div><p class="caption">Edits are saved to your workspace and logged. The source record and all analytics stay unchanged.</p></section>`;
  q('#content').insertAdjacentHTML('afterbegin',html);
}
window.afterRender=async(view,id)=>{
  try{ if(LISTS[view]||view==='orders')await listExtras(view); else await detailPanel(view,id);}catch(e){}
  refreshCount();
};
refreshCount();
})();
