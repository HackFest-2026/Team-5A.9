// Browse pages: entry points to the record pages (customer, order, item, supplier, purchase order) that were previously reachable
// only from links inside tables. Uses the same read-only /api/records and /api/resolve endpoints as the rest of the app.
(()=>{
const FULL={start:'2013-01-01',end:'2016-06-01'};
const META={
  overview:'Order volume, fulfilment status and the orders behind them.',
  fulfilment:'Quantities still to pick, by item and by picking status.',
  supply:'Incoming purchasing and stored holdings against reorder levels.',
  analysis:'Compare any measure across periods, grouped by a dimension.',
  customers:'Every customer. Search by name, or open a customer to see their orders.',
  orders:'Every order from 2013 to May 2016. Open one to see its lines and any backorder.',
  items:'Every stock item with its holdings and reorder level.',
  suppliers:'Every supplier. Open one to see related incoming purchasing.',
  purchases:'Every purchase order line, with ordered and received quantities.',
  charts:'Build a chart from any measure, breakdown and period, then save it.',
  workspace:'Records you created or edited. Kept apart from the source data and from every analytics figure.'
};
window.setSubtitle=view=>{$('#subtitle').textContent=META[view]||'Source records with their context.';};
const KIND={customers:'customer',items:'stock_item',suppliers:'supplier'};
const ROUTE={customer:'customer/',stock_item:'item/',supplier:'supplier/'};
const CFG={
  customers:{kind:'records:customers',title:'Customers',columns:['CustomerID','CustomerName','CustomerCategoryID','BuyingGroupID'],find:'Find a customer by name',caption:'Customer category and buying group are shown as IDs.'},
  items:{kind:'records:items',title:'Stock items',columns:['StockItemID','StockItemName','SupplierID','QuantityOnHand','ReorderLevel','TargetStockLevel','QuantityPerOuter'],find:'Find an item by name',caption:'Holdings are stored quantities, not a dated inventory snapshot.'},
  suppliers:{kind:'records:suppliers',title:'Suppliers',columns:['SupplierID','SupplierName','SupplierCategoryID'],find:'Find a supplier by name',caption:'Open a supplier to see its incoming purchase lines.'},
  orders:{kind:'records:orders',title:'Orders',dated:true,columns:['OrderID','CustomerID','CustomerName','OrderDate','ExpectedDeliveryDate','OrderPickingCompletedWhen','BackorderOrderID'],idbox:{label:'Open order by ID',route:'order/'},caption:'All order creation dates, January 2013 to May 2016.'},
  purchases:{kind:'records:purchase_lines',title:'Purchase order lines',columns:['PurchaseOrderID','PurchaseOrderLineID','StockItemID','SupplierName','PurchaseOrderDate','ExpectedDeliveryDate','OrderedOuters','ReceivedOuters','ArithmeticRemainingUnits'],idbox:{label:'Open purchase order by ID',route:'purchase/'},caption:'Quantities are in outers as stored; the last column converts the remainder to item units.'}
};
function searchBar(view,cfg){
  if(cfg.find)return`<form class="search-row" onsubmit="browseFind('${view}');return false"><label>${esc(cfg.find)}<input id="bf" type="search" placeholder="Type part of a name" autocomplete="off"></label><button type="submit">Search</button></form><div id="bf-out" class="chips" aria-live="polite"></div>`;
  if(cfg.idbox)return`<form class="search-row" onsubmit="return browseOpen('${cfg.idbox.route}')"><label>${esc(cfg.idbox.label)}<input id="bf" type="number" min="1" placeholder="ID"></label><button type="submit">Open</button></form>`;
  return'';
}
window.browseOpen=route=>{const v=Number($('#bf').value);if(v>0)go(route+v);return false;};
window.browseFind=async view=>{
  const text=$('#bf').value.trim(),out=$('#bf-out');if(!text){out.innerHTML='';return false;}
  out.textContent='Searching…';
  try{
    const res=await fetch('/api/resolve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,types:[KIND[view]],limit:12})});
    const d=await res.json();if(!res.ok)throw new Error(d.error||'Search failed');
    out.innerHTML=d.candidates&&d.candidates.length?d.candidates.map(c=>`<button type="button" onclick="go('${ROUTE[c.type]}${c.id}')">${esc(c.name)}${c.detail?' · '+esc(c.detail):''}</button>`).join(''):'<span class="caption">No match. Try a shorter part of the name.</span>';
  }catch(e){out.textContent=e.message;}
  return false;
};
window.browsePages=window.browsePages||{};
Object.keys(CFG).forEach(view=>{
  const cfg=CFG[view],kind=cfg.kind.split(':')[1];
  window.browsePages[view]=async()=>{
    const base=cfg.dated?{...req('order_date',{},false),start:FULL.start,end:FULL.end}:req('none',{},false);
    const rec=await api('records',kind,{...base,offset:state.offset});
    $('#scope').textContent=`${state.scenario_id==='base'?'Base source data':'SYNTHETIC fixture'} · ${num(rec.total_rows)} records · 50 per page.`;
    return (window.wsToolbar?wsToolbar(view):'')+searchBar(view,cfg)+panel(cfg.title,table(rec,kind,cfg.columns),cfg.caption);
  };
});
})();
