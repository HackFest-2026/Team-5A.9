// Analysis page (v2): renders exactly what /api/analyze returns. URL hash holds the full request, so a deep link reproduces the view.
(()=>{
const INT_FILTERS=['customer_id','stock_item_id','supplier_id','stock_group_id','order_id','customer_category_id','buying_group_id','state_province_id','salesperson_id'];
const STR_FILTERS=['sales_territory','status'];
const DRILL={customer:'customer_id',customer_category:'customer_category_id',buying_group:'buying_group_id',state_province:'state_province_id',sales_territory:'sales_territory',salesperson:'salesperson_id',stock_item:'stock_item_id',supplier:'supplier_id',stock_group:'stock_group_id'};
const PAGE={customer:'customer',stock_item:'item',supplier:'supplier'};
const NEXT={sales_territory:'customer',customer_category:'customer',buying_group:'customer',state_province:'customer',salesperson:'customer',stock_group:'stock_item',supplier:'stock_item'};
let contract=null,lists={};
const fmt=v=>v===null||v===undefined?'–':(typeof v==='string'&&v.includes('.')?Number(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}):Number(v).toLocaleString('en-US'));
const pct=v=>v===null||v===undefined?'–':(v*100).toFixed(1)+'%';
const h=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function readHash(){
  const q=new URLSearchParams(location.hash.split('?')[1]||'');
  const r={measure_id:q.get('measure_id')||'M01',group_by:q.get('group_by')||'none',scenario_id:q.get('scenario_id')||'base',top_n:Number(q.get('top_n')||10),filters:{}};
  for(const k of ['date_basis','start','end','compare_start','compare_end','sort'])if(q.get(k))r[k]=q.get(k);
  if(!q.has('start')&&!q.has('date_basis')&&(q.get('measure_id')||'M01')!=='M05'){r.start='2016-05-01';r.end='2016-06-01';}
  for(const k of INT_FILTERS)if(q.get(k))r.filters[k]=Number(q.get(k));
  for(const k of STR_FILTERS)if(q.get(k))r.filters[k]=q.get(k);
  return r;
}
function writeHash(r){
  const q=new URLSearchParams();
  for(const k of ['measure_id','date_basis','start','end','compare_start','compare_end','group_by','sort','top_n','scenario_id'])if(r[k]!==undefined&&r[k]!==null&&r[k]!=='')q.set(k,r[k]);
  for(const [k,v] of Object.entries(r.filters||{}))if(v!==null&&v!==undefined&&v!=='')q.set(k,v);
  location.hash='/analysis?'+q.toString();
}
async function post(path,body){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await res.json();if(!res.ok)throw new Error(d.error||'Query failed');return d;}
async function loadContract(){
  if(contract)return;
  contract=await (await fetch('/api/contract')).json();
  for(const t of ['customer_category','buying_group','state_province','sales_territory','salesperson','stock_group','supplier'])lists[t]=await (await fetch('/api/lookup?type='+t)).json();
}
function options(items,selected,blank='All'){return `<option value="">${blank}</option>`+items.map(x=>`<option value="${h(x.id)}" ${String(x.id)===String(selected??'')?'selected':''}>${h(x.name)}</option>`).join('');}
function controls(r){
  const ms=contract.analysis_measures.items.filter(m=>['verified','published-with-caveat'].includes(m.status)&&m.operations.includes('analyze'));
  const m=ms.find(x=>x.id===r.measure_id)||ms[0];
  const dims=m.dimensions.map(d=>d.id),f=r.filters,customerSide=m.filters.includes('customer_id');
  const dimName=id=>(contract.dimensions.items.find(d=>d.id===id)||{name:id}).name;
  return `<section class="filters analysis-controls" aria-label="Analysis request">
   <label>Measure<select id="a-measure">${ms.map(x=>`<option value="${x.id}" ${x.id===m.id?'selected':''}>${h(x.name)}</option>`).join('')}</select></label>
   <label>Break down by<select id="a-group">${dims.map(d=>`<option value="${d}" ${d===r.group_by?'selected':''}>${h(dimName(d))}</option>`).join('')}</select></label>
   <label>Date basis<select id="a-basis">${m.date_bases.map(b=>`<option ${b===(r.date_basis||m.default_date_basis)?'selected':''}>${b}</option>`).join('')}</select></label>
   <label>From<input type="date" id="a-start" value="${r.start||''}"></label><label>To, exclusive<input type="date" id="a-end" value="${r.end||''}"></label>
   <label>Compare with: from<input type="date" id="a-cstart" value="${r.compare_start||''}"></label><label>to, exclusive<input type="date" id="a-cend" value="${r.compare_end||''}"></label>
   ${customerSide?`<label>Territory<select id="a-territory">${options(lists.sales_territory,f.sales_territory)}</select></label>
   <label>Customer category<select id="a-category">${options(lists.customer_category,f.customer_category_id)}</select></label>
   <label>Buying group<select id="a-bgroup">${options(lists.buying_group,f.buying_group_id)}</select></label>
   <label>State<select id="a-state">${options(lists.state_province,f.state_province_id)}</select></label>
   <label>Salesperson<select id="a-sales">${options(lists.salesperson,f.salesperson_id)}</select></label>
   <label>Customer ID<input id="a-customer" type="number" min="1" value="${f.customer_id||''}" placeholder="All"></label>`:''}
   <label>Supplier<select id="a-supplier">${options(lists.supplier,f.supplier_id)}</select></label>
   <label>Stock group<select id="a-sgroup">${options(lists.stock_group,f.stock_group_id)}</select></label>
   <label>Item ID<input id="a-item" type="number" min="1" value="${f.stock_item_id||''}" placeholder="All"></label>
   <label>Top<input id="a-top" type="number" min="1" max="50" value="${r.top_n||10}"></label>
   <button id="a-apply">Apply</button><button id="a-clear" class="secondary">Clear filters</button></section>`;
}
function readControls(){
  const v=id=>{const e=document.getElementById(id);return e?e.value:'';};
  const r={measure_id:v('a-measure'),group_by:v('a-group'),date_basis:v('a-basis'),top_n:Number(v('a-top')||10),scenario_id:(window.wwiState&&window.wwiState.request&&window.wwiState.request.scenario_id)||'base',filters:{}};
  if(v('a-start'))r.start=v('a-start');if(v('a-end'))r.end=v('a-end');if(v('a-cstart'))r.compare_start=v('a-cstart');if(v('a-cend'))r.compare_end=v('a-cend');
  const map=[['a-territory','sales_territory',0],['a-category','customer_category_id',1],['a-bgroup','buying_group_id',1],['a-state','state_province_id',1],['a-sales','salesperson_id',1],['a-customer','customer_id',1],['a-supplier','supplier_id',1],['a-sgroup','stock_group_id',1],['a-item','stock_item_id',1]];
  for(const [id,k,isNum] of map)if(v(id))r.filters[k]=isNum?Number(v(id)):v(id);
  return r;
}
function result(d,r){
  const m=d.measure,unit=h(m.unit),cmp=d.total_baseline!==undefined;
  let html='<div class="cards">';
  if(cmp)html+=`<div class="card"><span>${h(m.name)} · baseline ${h(d.periods.baseline.join(' → '))}</span><strong>${fmt(d.total_baseline)}</strong><span>${unit}</span></div><div class="card"><span>${h(m.name)} · current ${h(d.periods.current.join(' → '))}</span><strong>${fmt(d.total_current)}</strong><span>${unit}</span></div><div class="card"><span>Change</span><strong>${Number(d.change)>0?'+':''}${fmt(d.change)}</strong><span>${d.pct_change===null?'–':d.pct_change+'%'} vs baseline</span></div>`;
  else html+=`<div class="card"><span>${h(m.name)}</span><strong>${fmt(d.total)}</strong><span>${unit}</span></div>`;
  html+='</div>';
  if(d.rows){
    const drill=DRILL[r.group_by],page=PAGE[r.group_by];
    const act=row=>row.key===null?'':(page?`<button class="secondary" onclick="analysisOpen('${page}','${h(row.key)}')">Open</button>`:'')+(drill?`<button class="secondary" onclick="analysisDrill('${drill}','${h(row.key)}')">Drill in</button>`:'')+(r.group_by==='month'?`<button class="secondary" onclick="analysisMonth('${h(row.key)}')">This month</button>`:'');
    const max=Math.max(...d.rows.filter(x=>x.key!==null).map(x=>Math.abs(Number(cmp?x.change:x.value))),1);
    html+=`<section class="panel"><h2>${h(m.name)} by ${h(d.dimension.id.replace('_',' '))}</h2><div class="table-wrap"><table><thead><tr><th>${h(d.dimension.id)}</th>${cmp?'<th>Baseline</th><th>Current</th><th>Change</th><th>Share of change</th>':'<th>Value</th><th>Share</th>'}<th></th><th></th></tr></thead><tbody>`+
      d.rows.map(x=>`<tr><td>${h(x.label)}</td>${cmp?`<td>${fmt(x.baseline)}</td><td>${fmt(x.current)}</td><td>${Number(x.change)>0?'+':''}${fmt(x.change)}</td><td>${pct(x.share_of_change)}</td>`:`<td>${fmt(x.value)}</td><td>${pct(x.share)}</td>`}<td style="min-width:160px"><div class="bar-track"><div class="bar-fill" style="width:${x.key===null?0:Math.abs(Number(cmp?x.change:x.value))/max*100}%;${cmp&&Number(x.change)<0?'background:#c97b5a':''}"></div></div></td><td>${act(x)}</td></tr>`).join('')+
      `</tbody></table></div><p class="caption">${h(d.group_count)} groups in scope.${d.dimension.note?' '+h(d.dimension.note):''}</p></section>`;
  }
  const am=contract.analysis_measures.items.find(x=>x.id===m.id);
  html+=`<p class="caption"><b>Definition:</b> ${h(m.definition)}${am&&am.caveat?' <b>Caveat:</b> '+h(am.caveat):''}</p>`;
  return html;
}
window.analysisDrill=(filter,key)=>{const r=readHash();r.filters[filter]=filter==='sales_territory'?key:Number(key);r.group_by=NEXT[r.group_by]||'none';writeHash(r);};
window.analysisOpen=(page,key)=>{location.hash='/'+page+'/'+key;};
window.analysisMonth=month=>{const r=readHash();const [y,mo]=month.split('-').map(Number);r.start=month+'-01';r.end=new Date(Date.UTC(y,mo,1)).toISOString().slice(0,10);delete r.compare_start;delete r.compare_end;r.group_by='none';writeHash(r);};
window.renderAnalysis=async()=>{
  document.getElementById('title').textContent='Analysis';
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.hash==='#/analysis'));
  const v1=document.querySelector('section.filters:not(.analysis-controls)');if(v1)v1.style.display='none';
  const err=document.getElementById('error'),content=document.getElementById('content'),scope=document.getElementById('scope');
  err.hidden=true;document.getElementById('loading').hidden=false;
  const r=readHash();
  try{
    await loadContract();
    const d=await post('/api/analyze',r);
    const a=d.applied;
    scope.textContent=`${a.scenario_id==='base'?'Base source':'SYNTHETIC fixture'} | ${a.measure_id} | ${a.date_basis}${a.start?` | ${a.start} inclusive to ${a.end} exclusive`:' | all dates'}${a.compare_start?` | baseline ${a.compare_start} to ${a.compare_end}`:''} | group by ${a.group_by} | filters ${JSON.stringify(Object.fromEntries(Object.entries(a.filters).filter(([k,v])=>v!==null&&!(k==='status'&&v==='all'))))}`;
    content.innerHTML=controls(a)+result(d,a);content.dataset.completed='true';
    window.wwiState={route:'analysis',request:a,deep_link:d.deep_link,completed:true,summary:{total:d.total??null,total_baseline:d.total_baseline??null,total_current:d.total_current??null,change:d.change??null,first_row:d.rows?d.rows[0]:null}};
  }catch(e){
    err.textContent=e.message;err.hidden=false;content.dataset.completed='false';
    content.innerHTML=contract?controls(r):'';
    window.wwiState={route:'analysis',request:r,completed:false,error:e.message};
  }finally{document.getElementById('loading').hidden=true;}
  const apply=document.getElementById('a-apply');if(apply)apply.onclick=()=>writeHash(readControls());
  const clear=document.getElementById('a-clear');if(clear)clear.onclick=()=>{const r2=readControls();r2.filters={};writeHash(r2);};
  const ms=document.getElementById('a-measure');if(ms)ms.onchange=()=>{const r2=readControls();delete r2.date_basis;r2.group_by='none';r2.filters={};writeHash(r2);};
};
})();
