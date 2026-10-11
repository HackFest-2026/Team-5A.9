// Chart builder: pick a measure, a breakdown, a period and a chart type; see it drawn from the governed /api/analyze result; save it.
// A saved chart is a REQUEST (measure, breakdown, dates, type), never a copy of data: every time it is drawn the figures are computed
// again from the source data, so a chart can never disagree with the Analysis page. Definitions live in the workspace store.
(()=>{
const TYPES=[['bar','Bars'],['hbar','Horizontal bars'],['line','Line'],['pie','Pie']];
const PALETTE=['#1d7a8c','#d69e2e','#5b6fb5','#2f9e6f','#b4382d','#8a6fb5','#4aa3c4','#9a7b4f'];
const C1='#1d7a8c',C2='#a9bcc8';
let contract=null,editId=null,def=null,last=null,timer=null,seq=0,loadedFor=null;
const q=s=>document.querySelector(s);
const fmtN=v=>v===null||v===undefined?'–':Number(v).toLocaleString('en-US',{maximumFractionDigits:2});
const cut=(s,n)=>{s=String(s??'');return s.length>n?s.slice(0,n-1)+'…':s;};

async function loadContract(){if(!contract)contract=await (await fetch('/api/contract')).json();return contract;}
const measures=()=>contract.analysis_measures.items.filter(m=>['verified','published-with-caveat'].includes(m.status)&&m.operations.includes('analyze'));
const measure=id=>measures().find(m=>m.id===id)||measures()[0];
const dimName=id=>(contract.dimensions.items.find(d=>d.id===id)||{name:id}).name;
const dim=(m,id)=>m.dimensions.find(d=>d.id===id);

function blank(){return{title:'',measure_id:'M01',group_by:'sales_territory',date_basis:null,start:'2016-05-01',end:'2016-06-01',compare_start:null,compare_end:null,chart_type:'bar',top_n:10,sort:null};}
function normalise(d){   // make a definition valid for its measure; returns notes about what was adjusted
  const m=measure(d.measure_id);d.measure_id=m.id;
  if(!dim(m,d.group_by))d.group_by=m.dimensions.find(x=>x.id!=='none')?m.dimensions.find(x=>x.id!=='none').id:'none';
  if(!m.date_bases.includes(d.date_basis))d.date_basis=m.default_date_basis;
  if(d.group_by==='month')d.compare_start=d.compare_end=null;
  if(d.group_by==='none')d.chart_type='number';
  else{
    if(d.chart_type==='number')d.chart_type=d.group_by==='month'?'line':'bar';
    if(d.chart_type==='line'&&d.group_by!=='month')d.chart_type='bar';
    if(d.chart_type==='pie'&&(!dim(m,d.group_by).additive||d.compare_start))d.chart_type='bar';
    if(d.group_by==='month'&&d.chart_type!=='line'&&d.chart_type!=='bar')d.chart_type='line';
  }
  d.top_n=Math.min(50,Math.max(1,Number(d.top_n)||10));
  return d;
}
function request(d){
  const r={measure_id:d.measure_id,group_by:d.group_by,scenario_id:'base',top_n:d.top_n||10,filters:{}};
  if(d.date_basis)r.date_basis=d.date_basis;
  if(d.start){r.start=d.start;r.end=d.end;}
  if(d.compare_start){r.compare_start=d.compare_start;r.compare_end=d.compare_end;}
  r.sort=d.sort||(d.group_by==='month'?'label_asc':'value_desc');
  return r;
}
async function analyze(r){
  const res=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(r)});
  const d=await res.json();if(!res.ok)throw new Error(d.error||'The query failed');return d;
}
function period(d){
  const one=(a,b)=>{if(!a)return 'all dates';const s=new Date(a+'T00:00:00Z'),e=new Date(b+'T00:00:00Z'),nx=new Date(Date.UTC(s.getUTCFullYear(),s.getUTCMonth()+1,1));
    return (s.getUTCDate()===1&&e.getTime()===nx.getTime())?s.toLocaleString('en-GB',{month:'long',year:'numeric',timeZone:'UTC'}):`${a} to ${b}`;};
  return one(d.start,d.end)+(d.compare_start?' vs '+one(d.compare_start,d.compare_end):'');
}
function subtitle(d){const m=measure(d.measure_id);return `${m.name} · ${d.group_by==='none'?'total':'by '+dimName(d.group_by).toLowerCase()} · ${period(d)}`;}

/* ---------- drawing (plain SVG, no library) ---------- */
function seriesOf(data){
  const cmp=data.rows&&data.rows.length&&data.rows[0].current!==undefined;
  return {cmp,rows:(data.rows||[]).map(r=>({label:r.label??r.key,v:Number(cmp?r.current:r.value),b:cmp?Number(r.baseline):null,share:r.share}))};
}
function niceMax(v){if(v<=0)return 1;const p=Math.pow(10,Math.floor(Math.log10(v))),n=v/p;return(n<=1?1:n<=2?2:n<=5?5:10)*p;}
function legend(cmp,d){return cmp?`<g font-size="13" fill="#34495a"><rect x="560" y="10" width="12" height="12" fill="${C1}"/><text x="578" y="21">${esc(period({start:d.start,end:d.end}))}</text><rect x="560" y="30" width="12" height="12" fill="${C2}"/><text x="578" y="41">${esc(period({start:d.compare_start,end:d.compare_end}))}</text></g>`:'';}
function drawBars(rows,cmp,d,horizontal){
  const W=760,H=horizontal?Math.max(260,60+rows.length*(cmp?44:32)):340;
  const max=niceMax(Math.max(...rows.flatMap(r=>[r.v,r.b||0]),1));
  let out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(d.title||subtitle(d))}" class="cb-svg">`;
  if(horizontal){
    const L=190,R=70,T=cmp?58:20,rowH=cmp?44:32,pw=W-L-R;
    rows.forEach((r,i)=>{const y=T+i*rowH,w1=r.v/max*pw,w2=(r.b||0)/max*pw;
      out+=`<text x="${L-10}" y="${y+(cmp?16:19)}" text-anchor="end" font-size="13" fill="#27465c">${esc(cut(r.label,26))}<title>${esc(r.label)}</title></text>`;
      out+=`<rect x="${L}" y="${y+4}" width="${Math.max(w1,1)}" height="${cmp?15:20}" fill="${C1}" rx="2"><title>${esc(r.label)}: ${fmtN(r.v)}</title></rect><text x="${L+w1+6}" y="${y+(cmp?16:19)}" font-size="12.5" fill="#27465c">${fmtN(r.v)}</text>`;
      if(cmp)out+=`<rect x="${L}" y="${y+22}" width="${Math.max(w2,1)}" height="14" fill="${C2}" rx="2"><title>${esc(r.label)} (baseline): ${fmtN(r.b)}</title></rect><text x="${L+w2+6}" y="${y+34}" font-size="12" fill="#6b7e8f">${fmtN(r.b)}</text>`;});
    out+=`<line x1="${L}" y1="${T-4}" x2="${L}" y2="${H-8}" stroke="#cfdbe2"/>`;
  }else{
    const L=64,R=20,T=cmp?58:24,B=88,pw=W-L-R,ph=H-T-B,slot=pw/rows.length,bw=Math.min(cmp?28:46,slot/(cmp?2.4:1.5));
    for(let i=0;i<=4;i++){const y=T+ph-ph*i/4;out+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="#e8eef2"/><text x="${L-8}" y="${y+4}" text-anchor="end" font-size="12" fill="#6b7e8f">${fmtN(max*i/4)}</text>`;}
    rows.forEach((r,i)=>{const cx=L+slot*i+slot/2,h1=r.v/max*ph,h2=(r.b||0)/max*ph,x1=cmp?cx-bw-1:cx-bw/2;
      out+=`<rect x="${x1}" y="${T+ph-h1}" width="${bw}" height="${Math.max(h1,1)}" fill="${C1}" rx="2"><title>${esc(r.label)}: ${fmtN(r.v)}</title></rect>`;
      if(rows.length<=12)out+=`<text x="${x1+bw/2}" y="${T+ph-h1-5}" text-anchor="middle" font-size="12" fill="#27465c">${fmtN(r.v)}</text>`;
      if(cmp)out+=`<rect x="${cx+1}" y="${T+ph-h2}" width="${bw}" height="${Math.max(h2,1)}" fill="${C2}" rx="2"><title>${esc(r.label)} (baseline): ${fmtN(r.b)}</title></rect>`;
      out+=`<text transform="translate(${cx},${T+ph+14}) rotate(${rows.length>6?-35:0})" text-anchor="${rows.length>6?'end':'middle'}" font-size="12.5" fill="#27465c">${esc(cut(r.label,rows.length>6?18:22))}</text>`;});
    out+=`<line x1="${L}" y1="${T+ph}" x2="${W-R}" y2="${T+ph}" stroke="#9fb3c0"/>`;
  }
  return out+legend(cmp,d)+'</svg>';
}
function drawLine(rows,cmp,d){
  const W=760,H=340,L=64,R=24,T=28,B=62,pw=W-L-R,ph=H-T-B,max=niceMax(Math.max(...rows.map(r=>r.v),1)),n=rows.length;
  const x=i=>L+(n===1?pw/2:pw*i/(n-1)),y=v=>T+ph-v/max*ph;
  let out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(d.title||subtitle(d))}" class="cb-svg">`;
  for(let i=0;i<=4;i++){const yy=T+ph-ph*i/4;out+=`<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" stroke="#e8eef2"/><text x="${L-8}" y="${yy+4}" text-anchor="end" font-size="12" fill="#6b7e8f">${fmtN(max*i/4)}</text>`;}
  out+=`<polyline fill="none" stroke="${C1}" stroke-width="2.5" points="${rows.map((r,i)=>x(i)+','+y(r.v)).join(' ')}"/>`;
  const step=Math.ceil(n/14);
  rows.forEach((r,i)=>{out+=`<circle cx="${x(i)}" cy="${y(r.v)}" r="3.5" fill="${C1}"><title>${esc(r.label)}: ${fmtN(r.v)}</title></circle>`;
    if(i%step===0||i===n-1)out+=`<text transform="translate(${x(i)},${T+ph+16}) rotate(-35)" text-anchor="end" font-size="12" fill="#27465c">${esc(r.label)}</text>`;});
  return out+`<line x1="${L}" y1="${T+ph}" x2="${W-R}" y2="${T+ph}" stroke="#9fb3c0"/></svg>`;
}
function drawPie(rows,d){
  const W=760,H=320,cx=190,cy=160,R=120,r0=64,tot=rows.reduce((a,r)=>a+r.v,0)||1;
  let out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(d.title||subtitle(d))}" class="cb-svg">`,a=-Math.PI/2;
  rows.forEach((r,i)=>{const f=r.v/tot,b=a+f*2*Math.PI,big=f>0.5?1:0,col=PALETTE[i%PALETTE.length];
    const p=(rad,ang)=>`${cx+rad*Math.cos(ang)},${cy+rad*Math.sin(ang)}`;
    out+=f>=0.9999?`<circle cx="${cx}" cy="${cy}" r="${(R+r0)/2}" fill="none" stroke="${col}" stroke-width="${R-r0}"><title>${esc(r.label)}: ${fmtN(r.v)}</title></circle>`
      :`<path d="M${p(R,a)} A${R},${R} 0 ${big} 1 ${p(R,b)} L${p(r0,b)} A${r0},${r0} 0 ${big} 0 ${p(r0,a)} Z" fill="${col}" stroke="#fff" stroke-width="1.5"><title>${esc(r.label)}: ${fmtN(r.v)} (${(f*100).toFixed(1)}%)</title></path>`;
    a=b;});
  out+=`<text x="${cx}" y="${cy-2}" text-anchor="middle" font-size="22" font-weight="700" fill="#10263a">${fmtN(tot)}</text><text x="${cx}" y="${cy+18}" text-anchor="middle" font-size="12.5" fill="#6b7e8f">shown</text>`;
  rows.forEach((r,i)=>{const y=40+i*28;out+=`<rect x="360" y="${y-11}" width="14" height="14" fill="${PALETTE[i%PALETTE.length]}" rx="3"/><text x="382" y="${y}" font-size="13.5" fill="#27465c">${esc(cut(r.label,30))}</text><text x="740" y="${y}" text-anchor="end" font-size="13.5" fill="#27465c">${fmtN(r.v)} · ${(r.v/tot*100).toFixed(1)}%</text>`;});
  return out+'</svg>';
}
function drawNumber(data,d){
  const m=measure(d.measure_id),cmp=data.total_current!==undefined;
  const big=cmp?data.total_current:data.total;
  return `<div class="cb-number"><span>${esc(m.name)} · ${esc(period(d))}</span><strong>${fmtN(big)}</strong><em>${esc(m.unit||'')}</em>${cmp?`<p>${fmtN(data.total_baseline)} before · <b class="${data.change>=0?'up':'down'}">${data.change>0?'+':''}${fmtN(data.change)}${data.pct_change!=null?` (${data.pct_change>0?'+':''}${data.pct_change}%)`:''}</b></p>`:''}</div>`;
}
function draw(d,data){
  if(d.chart_type==='number')return drawNumber(data,d);
  const {cmp,rows}=seriesOf(data);
  if(!rows.length)return '<div class="empty">No rows for this request.</div>';
  if(d.chart_type==='line')return drawLine(rows,cmp,d);
  if(d.chart_type==='pie')return drawPie(rows.slice(0,8),d);
  return drawBars(rows,cmp,d,d.chart_type==='hbar');
}
function summary(d,data){
  const m=measure(d.measure_id),cmp=data.total_current!==undefined,t=cmp?data.total_current:data.total;
  let s=`Total ${fmtN(t)} ${m.unit||''}`;
  if(cmp)s+=` (${data.change>0?'+':''}${fmtN(data.change)} against ${fmtN(data.total_baseline)})`;
  if(data.group_count&&data.rows&&data.group_count>data.rows.length)s+=` · showing the top ${data.rows.length} of ${data.group_count} groups`;
  if(m.caveat)s+=` · Caveat: ${m.caveat}`;
  return s;
}
function csv(d,data){
  const {cmp,rows}=seriesOf(data),esc2=v=>`"${String(v).replace(/"/g,'""')}"`;
  return [[ 'label',cmp?'current':'value',...(cmp?['baseline']:[])].join(','),...rows.map(r=>[esc2(r.label),r.v,...(cmp?[r.b]:[])].join(','))].join('\n');
}

/* ---------- the page ---------- */
async function chartsPage(){
  await loadContract();
  $('#scope').textContent='Charts are drawn from the same governed query as the Analysis page. A saved chart stores the request, not the numbers.';
  if(!def||loadedFor!==editId){
    if(editId){try{const rec=await window.wsApi('get?id='+editId);def={...blank(),...rec.data};def._version=rec.version;}catch(e){editId=null;def=blank();}}
    else def=blank();
    loadedFor=editId;
  }
  normalise(def);
  return `<div class="cb"><section class="panel cb-form"><h2>${editId?'Edit chart':'New chart'}</h2><div id="cb-controls"></div></section>
    <section class="panel cb-preview"><h2 id="cb-title">Preview</h2><p class="caption" id="cb-sub"></p><div id="cb-canvas" class="cb-canvas">Loading…</div><p id="cb-sum" class="cb-sum"></p>
      <p id="cb-err" class="ws-err" role="alert" hidden></p><div class="actions" id="cb-actions"></div>
      <details class="cb-data"><summary>Data behind the chart</summary><div id="cb-table"></div></details></section></div>
    <section class="panel"><h2>My charts</h2><p class="caption">Saved in your workspace. Each one is recomputed from the source data when shown.</p><div id="cb-gallery" class="cb-gallery"><span class="ws-muted">Loading…</span></div></section>`;
}
function controlsHTML(){
  const d=def,m=measure(d.measure_id),dims=m.dimensions;
  const opt=(v,t,sel)=>`<option value="${esc(v)}"${String(v)===String(sel)?' selected':''}>${esc(t)}</option>`;
  const types=d.group_by==='none'?[['number','Number']]:TYPES.filter(([t])=>!(t==='line'&&d.group_by!=='month')&&!(t==='pie'&&(!dim(m,d.group_by).additive||d.compare_start)));
  return `<div class="ws-field"><label for="cb-t">Title</label><input id="cb-t" type="text" maxlength="80" value="${esc(d.title)}" placeholder="e.g. Orders by territory, May 2016"></div>
  <div class="ws-field"><label for="cb-m">Measure</label><select id="cb-m">${measures().map(x=>opt(x.id,x.name,d.measure_id)).join('')}</select><small class="ws-muted">${esc(m.definition||'')}</small></div>
  <div class="ws-field"><label for="cb-g">Break down by</label><select id="cb-g">${dims.map(x=>opt(x.id,dimName(x.id),d.group_by)).join('')}</select></div>
  ${m.date_bases.length>1?`<div class="ws-field"><label for="cb-b">Date basis</label><select id="cb-b">${m.date_bases.map(b=>opt(b,b.replace(/_/g,' '),d.date_basis)).join('')}</select></div>`:''}
  <div class="cb-row"><div class="ws-field"><label for="cb-s">From</label><input id="cb-s" type="date" value="${d.start||''}"></div><div class="ws-field"><label for="cb-e">To (not included)</label><input id="cb-e" type="date" value="${d.end||''}"></div></div>
  ${d.group_by==='month'?'':`<div class="cb-row"><div class="ws-field"><label for="cb-cs">Compare with: from</label><input id="cb-cs" type="date" value="${d.compare_start||''}"></div><div class="ws-field"><label for="cb-ce">to (not included)</label><input id="cb-ce" type="date" value="${d.compare_end||''}"></div></div>`}
  <div class="cb-row"><div class="ws-field"><label>Chart type</label><div class="cb-seg" id="cb-type">${types.map(([t,l])=>`<button type="button" data-t="${t}" class="${t===d.chart_type?'on':''}">${l}</button>`).join('')}</div></div>
  ${d.group_by==='none'?'':`<div class="ws-field"><label for="cb-n">Top</label><input id="cb-n" type="number" min="1" max="50" value="${d.top_n}"></div>`}</div>`;
}
function readControls(){
  const v=id=>{const e=document.getElementById(id);return e?e.value:null;};
  const prev={...def};
  def.title=v('cb-t')??def.title;def.measure_id=v('cb-m')||def.measure_id;def.group_by=v('cb-g')||def.group_by;
  if(document.getElementById('cb-b'))def.date_basis=v('cb-b');
  def.start=v('cb-s')||null;def.end=v('cb-e')||null;
  if(document.getElementById('cb-cs')){def.compare_start=v('cb-cs')||null;def.compare_end=v('cb-ce')||null;}
  if(document.getElementById('cb-n'))def.top_n=Number(v('cb-n'))||10;
  if(def.group_by!==prev.group_by){if(def.group_by==='month')def.chart_type='line';else if(prev.group_by==='month'&&def.chart_type==='line')def.chart_type='bar';else if(prev.group_by==='none')def.chart_type='bar';}
  if(def.measure_id!==prev.measure_id){def.date_basis=null;def.group_by=measure(def.measure_id).dimensions.some(x=>x.id===prev.group_by)?prev.group_by:def.group_by;}
  normalise(def);
}
function showControls(){const c=q('#cb-controls');if(c)c.innerHTML=controlsHTML();}
function schedule(rebuild){clearTimeout(timer);timer=setTimeout(()=>{if(!q('#cb-controls'))return;readControls();if(rebuild)showControls();preview();},350);}
async function preview(){
  const my=++seq,canvas=q('#cb-canvas');if(!canvas)return;
  q('#cb-title').textContent=def.title||'Preview';q('#cb-sub').textContent=subtitle(def);q('#cb-err').hidden=true;
  try{
    const data=await analyze(request(def));if(my!==seq||!q('#cb-canvas'))return;
    last=data;canvas.innerHTML=draw(def,data);q('#cb-sum').textContent=summary(def,data);
    const {cmp,rows}=seriesOf(data);
    q('#cb-table').innerHTML=rows.length?`<div class="table-wrap"><table><thead><tr><th>${esc(dimName(def.group_by))}</th><th>${cmp?'Current':'Value'}</th>${cmp?'<th>Baseline</th>':''}</tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.label)}</td><td>${fmtN(r.v)}</td>${cmp?`<td>${fmtN(r.b)}</td>`:''}</tr>`).join('')}</tbody></table></div>`:'<p class="ws-muted">This chart is a single number.</p>';
    q('#cb-actions').innerHTML=`<button type="button" id="cb-save">${editId?'Save changes':'Save chart'}</button>${editId?'<button type="button" class="secondary" id="cb-new">New chart</button>':''}<a class="cb-link" href="${esc(data.deep_link||'#/analysis')}">Open in Analysis</a><button type="button" class="secondary" id="cb-csv">Download CSV</button>`;
  }catch(e){if(my!==seq||!q('#cb-canvas'))return;canvas.innerHTML='<div class="empty">Nothing to draw yet.</div>';q('#cb-err').textContent=e.message;q('#cb-err').hidden=false;q('#cb-actions').innerHTML='';last=null;}
}
async function save(){
  if(!q('#cb-controls'))return;
  readControls();if(!def.title.trim()){q('#cb-err').textContent='Give the chart a title first.';q('#cb-err').hidden=false;q('#cb-t').focus();return;}
  const data={title:def.title,measure_id:def.measure_id,group_by:def.group_by,date_basis:def.date_basis,start:def.start,end:def.end,compare_start:def.compare_start,compare_end:def.compare_end,chart_type:def.chart_type,top_n:def.top_n,sort:def.sort};
  try{
    const rec=editId?await window.wsApi('update',{id:editId,data,version:def._version}):await window.wsApi('create',{kind:'chart',data});
    editId=rec.id;def._version=rec.version;loadedFor=editId;window.wsToast('Chart saved to your workspace.');await gallery();showControls();preview();
  }catch(e){q('#cb-err').textContent=e.message;q('#cb-err').hidden=false;}
}
async function gallery(){
  const box=q('#cb-gallery');if(!box)return;
  const recs=(await window.wsApi('list?kind=chart')).records.filter(r=>r.ref_id===null);
  if(!recs.length){box.innerHTML='<span class="ws-muted">No saved charts yet. Build one above and choose Save chart.</span>';return;}
  box.innerHTML=recs.map(r=>`<article class="cb-card" data-id="${r.id}"><header><b>${esc(r.data.title)}</b><small>${esc(subtitle(r.data))}</small></header><div class="cb-mini" id="cb-mini-${r.id}"><span class="ws-muted">Loading…</span></div><footer><button type="button" data-act="edit" data-id="${r.id}">Edit</button><button type="button" class="secondary" data-act="open" data-id="${r.id}">Analysis</button><button type="button" class="danger-soft" data-act="del" data-id="${r.id}" data-name="${esc(r.data.title)}">Delete</button></footer></article>`).join('');
  for(const r of recs){const el=document.getElementById('cb-mini-'+r.id);if(!el)continue;
    try{const d=normalise({...blank(),...r.data}),data=await analyze(request(d));el.innerHTML=draw(d,data);el.dataset.link=data.deep_link||'';}catch(e){el.innerHTML=`<span class="ws-muted">${esc(e.message)}</span>`;}}
}
async function init(){
  if(!q('#cb-controls'))return;
  showControls();preview();gallery();
  const c=q('#cb-controls');
  c.addEventListener('input',e=>{if(e.target.id==='cb-t'){def.title=e.target.value;q('#cb-title').textContent=def.title||'Preview';return;}if(e.target.id==='cb-n'||e.target.type==='date')schedule(false);});
  c.addEventListener('change',e=>{if(e.target.tagName==='SELECT')schedule(true);else if(e.target.type==='date'){readControls();showControls();preview();}});
  c.addEventListener('click',e=>{const b=e.target.closest('#cb-type button');if(b){readControls();def.chart_type=b.dataset.t;normalise(def);showControls();preview();}});
  q('.cb').addEventListener('click',e=>{
    if(e.target.id==='cb-save')save();
    else if(e.target.id==='cb-new')window.cbNew();
    else if(e.target.id==='cb-csv'&&last){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv(def,last)],{type:'text/csv'}));a.download=(def.title||'chart').replace(/[^\w-]+/g,'_')+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);}
  });
  q('#cb-gallery').addEventListener('click',e=>{
    const b=e.target.closest('button[data-act]');if(!b)return;const id=Number(b.dataset.id);
    if(b.dataset.act==='edit'){editId=id;def=null;render();window.scrollTo({top:0,behavior:'smooth'});}
    else if(b.dataset.act==='open'){const l=(document.getElementById('cb-mini-'+id)||{}).dataset;if(l&&l.link)location.hash=l.link.slice(1);}
    else if(b.dataset.act==='del'){window.wsDelete(id,b.dataset.name);}
  });
}
window.cbNew=()=>{editId=null;def=null;loadedFor=null;render();};
window.cbEdit=id=>{editId=Number(id);def=null;if((location.hash.slice(2)||'').split('?')[0]==='charts')render();else location.hash='#/charts';};
window.addEventListener('hashchange',()=>{if((location.hash.slice(2)||'').split('?')[0]!=='charts'){editId=null;def=null;loadedFor=null;}});
window.browsePages=window.browsePages||{};window.browsePages.charts=chartsPage;
const prevAfter=window.afterRender;
window.afterRender=async(view,id)=>{if(view==='charts'){try{await init();}catch(e){}}else if(prevAfter)return prevAfter(view,id);};
})();
