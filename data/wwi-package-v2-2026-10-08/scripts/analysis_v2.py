"""v2 operations for multi-step agent work: analyze (breakdown + period comparison), resolve (name -> ID), related (entity hops).

Allowlisted SQL fragments only; callers never supply SQL or identifiers. Definitions follow docs/V2_SPEC.md.
"""
from __future__ import annotations
import datetime,difflib,re
from decimal import Decimal
from typing import Literal
from urllib.parse import urlencode
from pydantic import BaseModel,ConfigDict,Field,model_validator
from common import db,query
from build_v2 import norm,singular

VERSION='wwi-data-v1-2026-10-08'
TERRITORIES=['Far West','Great Lakes','Mideast','New England','Plains','Rocky Mountain','Southeast','Southwest','External']
MeasureID=Literal['M01','M02','M03','M13','M05','M10','M11']
Dimension=Literal['none','month','customer','customer_category','buying_group','state_province','sales_territory','salesperson','stock_item','supplier','stock_group']
Sort=Literal['value_desc','value_asc','label_asc','label_desc','change_desc','change_asc','abs_change_desc']

class AnalyzeFilters(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    customer_id:int|None=None
    stock_item_id:int|None=None
    supplier_id:int|None=None
    stock_group_id:int|None=None
    order_id:int|None=None
    order_line_id:int|None=None
    purchase_order_id:int|None=None
    purchase_line_id:int|None=None
    customer_category_id:int|None=None
    buying_group_id:int|None=None
    state_province_id:int|None=None
    sales_territory:Literal['Far West','Great Lakes','Mideast','New England','Plains','Rocky Mountain','Southeast','Southwest','External']|None=None
    salesperson_id:int|None=None
    status:Literal['all','quantity-not-yet-picked','picking-incomplete','picking-complete','incoming']='all'

class AnalyzeRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    dataset_version:Literal['wwi-data-v1-2026-10-08']=VERSION
    scenario_id:Literal['base','no_incoming_v1']='base'
    measure_id:MeasureID
    date_basis:Literal['order_date','invoice_date','purchase_order_date','expected_delivery_date','none']|None=None
    start:datetime.date|None=None
    end:datetime.date|None=None
    compare_start:datetime.date|None=None
    compare_end:datetime.date|None=None
    group_by:Dimension='none'
    filters:AnalyzeFilters=Field(default_factory=AnalyzeFilters)
    sort:Sort|None=None
    top_n:int=Field(default=10,ge=1,le=50)
    @model_validator(mode='after')
    def check(self):
        spec=MEASURES[self.measure_id]
        if self.date_basis is None:self.date_basis=spec['bases'][0]
        if self.date_basis not in spec['bases']:raise ValueError(f"{self.measure_id} accepts date_basis {spec['bases']}, not {self.date_basis}.")
        for a,b,label in [(self.start,self.end,'start/end'),(self.compare_start,self.compare_end,'compare_start/compare_end')]:
            if (a is None)!=(b is None):raise ValueError(f'Supply both {label} (inclusive start, exclusive end).')
            if a is not None and not datetime.date(2013,1,1)<=a<b<=datetime.date(2016,6,21):raise ValueError(f'{label} outside the 2013-01-01..2016-06-21 archive, or empty.')
        if self.compare_start and not self.start:raise ValueError('A comparison needs the current period (start/end) as well as the baseline (compare_start/compare_end).')
        if self.date_basis=='none' and (self.start or self.compare_start):raise ValueError('date_basis none is undated; remove the period or choose a purchasing date basis.')
        if self.group_by=='month' and self.date_basis=='none':raise ValueError('group_by month needs a dated basis.')
        if self.group_by=='month' and self.compare_start:raise ValueError('Months differ between periods; compare totals, or use one wider period grouped by month.')
        if self.group_by not in spec['dimensions']:raise ValueError(f"{self.measure_id} cannot be broken down by {self.group_by}: {spec['why_not'].get(self.group_by,'not applicable')}")
        f=self.filters
        for k,v in f.model_dump().items():
            if isinstance(v,int) and not isinstance(v,bool) and v<=0:raise ValueError('Entity IDs must be positive integers.')
            if v is not None and k!='status' and k not in spec['filters']:raise ValueError(f"Filter {k} does not apply to {self.measure_id}: {spec['why_not'].get(k,'not applicable to this measure')}")
        if f.status not in spec['status']:raise ValueError(f"status {f.status} is invalid for {self.measure_id}; allowed {spec['status']}.")
        if self.measure_id in ('M10','M11') and self.scenario_id!='base':raise ValueError('The synthetic fixture has no invoices; money measures are base-only.')
        if self.sort is None:self.sort='abs_change_desc' if self.compare_start else 'value_desc'
        if self.sort.startswith(('change','abs_change')) and not self.compare_start:raise ValueError('Change sorts need a comparison period.')
        return self

CUSTOMER_FILTERS=['customer_id','customer_category_id','buying_group_id','state_province_id','sales_territory','salesperson_id','order_id']
ITEM_FILTERS=['stock_item_id','supplier_id','stock_group_id']
CUSTOMER_DIMS=['customer','customer_category','buying_group','state_province','sales_territory','salesperson']
ORDER_STATUS=['all','quantity-not-yet-picked','picking-incomplete','picking-complete']
NOT_ALLOCATED='purchasing is related to items, not allocated to customers or sales orders'
ORDER_SPEC=dict(source='analytics.order_lines_v2',bases=['order_date'],date_col={'order_date':'OrderDate'},
                filters=CUSTOMER_FILTERS+['order_line_id']+ITEM_FILTERS,status=ORDER_STATUS,
                dimensions=['none','month']+CUSTOMER_DIMS+['stock_item','supplier','stock_group'],
                why_not={'purchase_order_id':'sales orders are not allocated to purchase orders','purchase_line_id':'sales orders are not allocated to purchase orders'})
MEASURES={
 'M01':dict(ORDER_SPEC,name='Orders created',unit='orders',value='COUNT(DISTINCT x.OrderID)',per_line=False,definition='Distinct orders created in the period (includes backorders).'),
 'M02':dict(ORDER_SPEC,name='Stored unpicked units',unit='item units',value='SUM(x.UnpickedUnits)',per_line=True,definition='Sum over order lines of max(Quantity - PickedQuantity, 0), stored state; not historical backlog.'),
 'M03':dict(ORDER_SPEC,name='Orders with unpicked quantities',unit='orders',value='COUNT(DISTINCT CASE WHEN x.UnpickedUnits>0 THEN x.OrderID END)',per_line=False,definition='Distinct orders with at least one line still unpicked.'),
 'M13':dict(ORDER_SPEC,name='Ordered units',unit='item units',value='SUM(x.Quantity)',per_line=True,definition='Sum of ordered quantity over order lines; units of unlike products, not money.'),
 'M05':dict(source='analytics.incoming_v2',bases=['none','purchase_order_date','expected_delivery_date'],date_col={'purchase_order_date':'PurchaseOrderDate','expected_delivery_date':'ExpectedDeliveryDate'},
            filters=['purchase_order_id','purchase_line_id']+ITEM_FILTERS,status=['all','incoming'],dimensions=['none','month','stock_item','supplier','stock_group'],
            why_not={**{k:NOT_ALLOCATED for k in CUSTOMER_FILTERS+CUSTOMER_DIMS+['order_line_id']}},
            name='Related incoming units',unit='item units',value='SUM(x.IncomingUnits)',per_line=True,definition='Unreceived outers x units per outer on open purchase lines (header and line not finalized). Related by item, not allocated.'),
}
INVOICE_SPEC=dict(source='analytics.invoice_lines_v2',bases=['invoice_date'],date_col={'invoice_date':'InvoiceDate'},filters=CUSTOMER_FILTERS+ITEM_FILTERS,status=['all'],
                  dimensions=['none','month']+CUSTOMER_DIMS+['stock_item','supplier','stock_group'],per_line=True,unit='sample amount (currency not stated in source)',
                  why_not={'order_line_id':'invoice lines are not linked to order lines','purchase_order_id':'invoices are not linked to purchasing','purchase_line_id':'invoices are not linked to purchasing'})
MEASURES['M10']=dict(INVOICE_SPEC,name='Invoiced sales excluding tax',value='SUM(x.SalesExTax)',definition='Sum of ExtendedPrice - TaxAmount over invoice lines dated in the period. Currency not stated in the source (US-based company).')
MEASURES['M11']=dict(INVOICE_SPEC,name='Recorded gross line profit',value='SUM(x.LineProfit)',definition='Sum of recorded LineProfit over invoice lines. Gross line profit, not net profit; currency not stated in the source.')

DIMENSIONS={
 'month':dict(key=None,label=None,additive=True,name='Month'),
 'customer':dict(key='x.CustomerID',label='x.CustomerName',additive=True,name='Customer'),
 'customer_category':dict(key='x.CustomerCategoryID',label='x.CustomerCategoryName',additive=True,name='Customer category (current)'),
 'buying_group':dict(key='x.BuyingGroupID',label="COALESCE(x.BuyingGroupName,'No buying group')",additive=True,name='Buying group (current)'),
 'state_province':dict(key='x.StateProvinceID',label='x.StateProvinceName',additive=True,name='Delivery state (current)'),
 'sales_territory':dict(key='x.SalesTerritory',label='x.SalesTerritory',additive=True,name='Sales territory (current)'),
 'salesperson':dict(key='x.SalespersonPersonID',label='x.SalespersonName',additive=True,name='Salesperson'),
 'stock_item':dict(key='x.StockItemID',label='x.StockItemName',additive=None,name='Stock item'),
 'supplier':dict(key='x.SupplierID',label='x.SupplierName',additive=None,name='Supplier'),
 'stock_group':dict(key='g.StockGroupID',label='sg.StockGroupName',additive=False,name='Stock group (items can be in several groups)'),
}
FILTER_SQL={'customer_id':'x.CustomerID','stock_item_id':'x.StockItemID','supplier_id':'x.SupplierID','order_id':'x.OrderID','order_line_id':'x.OrderLineID',
            'purchase_order_id':'x.PurchaseOrderID','purchase_line_id':'x.PurchaseOrderLineID','customer_category_id':'x.CustomerCategoryID',
            'buying_group_id':'x.BuyingGroupID','state_province_id':'x.StateProvinceID','sales_territory':'x.SalesTerritory','salesperson_id':'x.SalespersonPersonID'}

def additive(mid,dim):
    d=DIMENSIONS[dim]
    if d['additive'] is None:return MEASURES[mid]['per_line']
    return d['additive']

def where_clause(r,start,end):
    spec=MEASURES[r.measure_id];terms=['x.ScenarioID=?'];params=[r.scenario_id]
    if start is not None:
        col=spec['date_col'][r.date_basis];terms+=[f'x.{col}>=?',f'x.{col}<?'];params+=[start,end]
    f=r.filters
    for k,col in FILTER_SQL.items():
        v=getattr(f,k)
        if v is not None:terms.append(f'{col}=?');params.append(v)
    if f.stock_group_id is not None:
        terms.append('EXISTS(SELECT 1 FROM raw.Warehouse_StockItemStockGroups b WHERE b.StockItemID=x.StockItemID AND b.StockGroupID=?)');params.append(f.stock_group_id)
    if f.status=='quantity-not-yet-picked':terms.append('x.UnpickedUnits>0')
    elif f.status=='picking-incomplete':terms.append('x.OrderPickingCompletedWhen IS NULL')
    elif f.status=='picking-complete':terms.append('x.OrderPickingCompletedWhen IS NOT NULL')
    return ' AND '.join(terms),params

def run_period(c,r,start,end):
    spec=MEASURES[r.measure_id];where,params=where_clause(r,start,end)
    total=query(c,f"SELECT {spec['value']} FROM {spec['source']} x WHERE {where}",params)[1][0][0] or 0
    if r.group_by=='none':return total,{}
    if r.group_by=='month':
        col=spec['date_col'][r.date_basis];key=label=f"strftime(x.{col},'%Y-%m')";join=''
    else:
        d=DIMENSIONS[r.group_by];key,label=d['key'],d['label']
        join=' JOIN raw.Warehouse_StockItemStockGroups g ON g.StockItemID=x.StockItemID JOIN raw.Warehouse_StockGroups sg ON sg.StockGroupID=g.StockGroupID' if r.group_by=='stock_group' else ''
    _,rows=query(c,f"SELECT {key} AS k,{label} AS l,{spec['value']} AS v FROM {spec['source']} x{join} WHERE {where} GROUP BY 1,2",params)
    return total,{k:(l,v or 0) for k,l,v in rows}

def num(v):
    if isinstance(v,Decimal):return format(v.quantize(Decimal('0.01')),'f')
    return int(v)
def ratio(a,b):
    return None if not b else round(float(Decimal(a)/Decimal(b)),4)

def deep_link(r):
    q={'measure_id':r.measure_id,'date_basis':r.date_basis,'group_by':r.group_by,'sort':r.sort,'top_n':r.top_n,'scenario_id':r.scenario_id}
    for k in ['start','end','compare_start','compare_end']:
        if getattr(r,k):q[k]=getattr(r,k).isoformat()
    q.update({k:v for k,v in r.filters.model_dump().items() if v is not None and not (k=='status' and v=='all')})
    return '#/analysis?'+urlencode(q)

def tie(k):
    # Tie-break on the key: numbers numerically, text alphabetically, missing last.
    return (2,'') if k is None else ((0,k,'') if isinstance(k,(int,float)) else (1,0,str(k)))
def sort_rows(rows,sort,value_key):
    keyfn={'value_desc':lambda x:(-Decimal(str(x[value_key])),tie(x['key'])),'value_asc':lambda x:(Decimal(str(x[value_key])),tie(x['key'])),
           'label_asc':lambda x:(str(x['label']).casefold(),tie(x['key'])),'label_desc':lambda x:(str(x['label']).casefold(),tie(x['key'])),
           'change_desc':lambda x:(-Decimal(str(x['change'])),tie(x['key'])),'change_asc':lambda x:(Decimal(str(x['change'])),tie(x['key'])),
           'abs_change_desc':lambda x:(-abs(Decimal(str(x['change']))),tie(x['key']))}[sort]
    rows.sort(key=keyfn,reverse=(sort=='label_desc'))
    return rows

def analyze(package,body):
    r=AnalyzeRequest.model_validate(body) if isinstance(body,dict) else body
    spec=MEASURES[r.measure_id];add=None if r.group_by=='none' else additive(r.measure_id,r.group_by)
    out={'dataset_version':r.dataset_version,'scenario_id':r.scenario_id,
         'measure':{'id':r.measure_id,'name':spec['name'],'unit':spec['unit'],'definition':spec['definition']},
         'dimension':{'id':r.group_by,'additive':add,'note':None if add in (None,True) else 'Groups overlap: one order/item can appear in several groups, so rows must not be summed.'},
         'applied':r.model_dump(mode='json'),'deep_link':deep_link(r),'completed':True}
    c=db(package)
    try:
        total,groups=run_period(c,r,r.start,r.end)
        if r.compare_start:
            base_total,base_groups=run_period(c,r,r.compare_start,r.compare_end)
    finally:c.close()
    if not r.compare_start:
        out['total']=num(total)
        if r.group_by!='none':
            rows=[{'key':k,'label':l,'value':num(v),'share':ratio(v,total) if add else None} for k,(l,v) in groups.items()]
            rows=sort_rows(rows,r.sort,'value');top=rows[:r.top_n]
            if add and len(rows)>r.top_n:
                rest=total-sum(Decimal(str(x['value'])) for x in top) if isinstance(total,Decimal) else total-sum(x['value'] for x in top)
                top.append({'key':None,'label':f'All others ({len(rows)-r.top_n} groups)','value':num(rest),'share':ratio(rest,total),'is_other':True})
            out['rows']=top;out['group_count']=len(rows)
        return out
    change=total-base_total
    out.update({'total_baseline':num(base_total),'total_current':num(total),'change':num(change),'pct_change':None if not base_total else round(float(Decimal(change)/Decimal(base_total)*100),2),
                'periods':{'baseline':[r.compare_start.isoformat(),r.compare_end.isoformat()],'current':[r.start.isoformat(),r.end.isoformat()]}})
    if r.group_by!='none':
        zero=Decimal('0') if isinstance(total,Decimal) else 0;rows=[]
        for k in set(groups)|set(base_groups):
            label=(groups.get(k) or base_groups.get(k))[0];cur=groups.get(k,(label,zero))[1];base=base_groups.get(k,(label,zero))[1];ch=cur-base
            rows.append({'key':k,'label':label,'baseline':num(base),'current':num(cur),'change':num(ch),'share_of_change':ratio(ch,change) if add else None})
        rows=sort_rows(rows,r.sort,'current');top=rows[:r.top_n]
        if add and len(rows)>r.top_n:
            sb=sum(Decimal(str(x['baseline'])) for x in top);sc=sum(Decimal(str(x['current'])) for x in top)
            rb=Decimal(str(num(base_total)))-sb;rc=Decimal(str(num(total)))-sc
            fix=(lambda v:num(v) if isinstance(total,Decimal) else int(v))
            top.append({'key':None,'label':f'All others ({len(rows)-r.top_n} groups)','baseline':fix(rb),'current':fix(rc),'change':fix(rc-rb),'share_of_change':ratio(rc-rb,change),'is_other':True})
        out['rows']=top;out['group_count']=len(rows)
    return out

# ---------------- resolve ----------------
ENTITY_TYPES=['customer','stock_item','supplier','customer_category','buying_group','stock_group','state_province','sales_territory','salesperson']
class ResolveRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str=Field(min_length=1,max_length=200)
    types:list[Literal['customer','stock_item','supplier','customer_category','buying_group','stock_group','state_province','sales_territory','salesperson']]|None=None
    limit:int=Field(default=5,ge=1,le=25)
_INDEX={}
def index(package):
    key=str(package)
    if key not in _INDEX:
        c=db(package);_,rows=query(c,'SELECT entity_type,entity_id,name,alias,detail FROM analytics.entity_index');c.close();_INDEX[key]=rows
    return _INDEX[key]
def typed_id(etype,eid):return eid if etype=='sales_territory' else int(eid)
def resolve(package,body):
    r=ResolveRequest.model_validate(body) if isinstance(body,dict) else body
    q=norm(r.text);q=' '.join(singular(w) for w in q.split());qt=set(q.split());best={}
    if not q:raise ValueError('Nothing to resolve after normalisation.')
    for etype,eid,name,alias,detail in index(package):
        if r.types and etype not in r.types:continue
        at=alias.split()
        if alias==q:score,kind=1.0,('exact' if norm(name)==q or ' '.join(singular(w) for w in norm(name).split())==q else 'alias')
        elif qt and qt<=set(at):score,kind=0.85+0.1*len(qt)/len(at),'token'
        elif alias.startswith(q) and len(q)>=3:score,kind=0.8,'prefix'
        else:
            s=difflib.SequenceMatcher(None,q,alias).ratio()
            if s<0.72:continue
            score,kind=round(0.75*s,4),'fuzzy'
        k=(etype,eid)
        if k not in best or score>best[k]['score']:
            best[k]={'type':etype,'id':typed_id(etype,eid),'name':name,'detail':detail,'score':round(score,4),'match':kind}
    cands=sorted(best.values(),key=lambda x:(-x['score'],x['type'],str(x['id'])))
    strong=[x for x in cands if x['match'] in ('exact','alias')]
    phrase=[x for x in cands if x['match']=='token' and x['type'] not in {s['type'] for s in strong}] if len(qt)>=2 else []
    if len(strong)==1 and not phrase:status='unique'
    elif len(strong)>=2 or (strong and phrase):status='ambiguous'
    elif cands and cands[0]['score']>=0.8 and (len(cands)==1 or cands[0]['score']-cands[1]['score']>=0.08):status='unique'
    elif cands:status='ambiguous'
    else:status='none'
    out={'text':r.text,'status':status,'candidates':cands[:r.limit],'candidate_count':len(cands)}
    if status=='ambiguous':out['ask']='Several records match "'+r.text+'". Ask the user which one they mean; do not pick for them.'
    if status=='none':out['ask']='No record matches "'+r.text+'". Ask the user to rephrase or give an ID.'
    return out

# ---------------- related ----------------
class RelatedRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    entity_type:Literal['customer','order','stock_item','supplier','purchase_order','salesperson']
    entity_id:int=Field(gt=0)
    scenario_id:Literal['base','no_incoming_v1']='base'
def rows(c,sql,params):
    cols,data=query(c,sql,params);return [dict(zip(cols,[num(v) if isinstance(v,Decimal) else v for v in row])) for row in data]
def suggest(label,op,request,link=None):return {'label':label,'operation':op,'request':request,'deep_link':link}
def related(package,body):
    r=RelatedRequest.model_validate(body) if isinstance(body,dict) else body
    t,i,s=r.entity_type,r.entity_id,r.scenario_id;c=db(package);out={'entity_type':t,'entity_id':i,'scenario_id':s,'scope':'stored sample state; all dates unless stated'}
    try:
        if t=='stock_item':
            item=rows(c,"SELECT s.StockItemID,s.StockItemName,s.SupplierID,su.SupplierName,s.QuantityPerOuter,up.PackageTypeName UnitPackage,op.PackageTypeName OuterPackage,s.IsSynthetic FROM analytics.items s LEFT JOIN raw.Purchasing_Suppliers su ON su.SupplierID=s.SupplierID LEFT JOIN raw.Warehouse_PackageTypes up ON up.PackageTypeID=s.UnitPackageID LEFT JOIN raw.Warehouse_PackageTypes op ON op.PackageTypeID=s.OuterPackageID WHERE s.StockItemID=? AND s.ScenarioID=?",[i,s])
            if not item:raise ValueError(f'No stock item {i} in scenario {s}.')
            out['entity']=item[0]
            out['stock_groups']=rows(c,"SELECT g.StockGroupID,sg.StockGroupName FROM raw.Warehouse_StockItemStockGroups g JOIN raw.Warehouse_StockGroups sg USING(StockGroupID) WHERE g.StockItemID=? ORDER BY 1",[i])
            out['holdings']=rows(c,"SELECT QuantityOnHand,ReorderLevel,TargetStockLevel FROM analytics.holdings WHERE StockItemID=? AND ScenarioID=?",[i,s])
            out['unpicked_demand']=rows(c,"SELECT COALESCE(SUM(UnpickedUnits),0) units,COUNT(*) FILTER (WHERE UnpickedUnits>0) lines,COUNT(DISTINCT CASE WHEN UnpickedUnits>0 THEN OrderID END) orders FROM analytics.order_lines WHERE StockItemID=? AND ScenarioID=?",[i,s])[0]
            out['top_waiting_customers']=rows(c,"SELECT CustomerID,CustomerName,SUM(UnpickedUnits) unpicked_units FROM analytics.order_lines_v2 WHERE StockItemID=? AND ScenarioID=? AND UnpickedUnits>0 GROUP BY 1,2 ORDER BY 3 DESC,1 LIMIT 5",[i,s])
            out['incoming']=rows(c,"SELECT PurchaseOrderID,PurchaseOrderLineID,SupplierID,SupplierName,ExpectedDeliveryDate,OrderedOuters,ReceivedOuters,QuantityPerOuter,IncomingUnits FROM analytics.incoming_v2 WHERE StockItemID=? AND ScenarioID=? ORDER BY PurchaseOrderID",[i,s])
            sup=out['entity']['SupplierID']
            out['next_steps']=[suggest('Which customers wait for this item','analyze',{'measure_id':'M02','group_by':'customer','filters':{'stock_item_id':i},'scenario_id':s}),
                suggest('Incoming purchase lines for this item','records',{'id':'purchase_lines','date_basis':'none','filters':{'stock_item_id':i,'status':'incoming'}},f'#/item/{i}'),
                suggest('Nominated supplier','related',{'entity_type':'supplier','entity_id':sup},f'#/supplier/{sup}'),
                suggest('Monthly ordered units for this item','analyze',{'measure_id':'M13','group_by':'month','start':'2016-01-01','end':'2016-06-01','filters':{'stock_item_id':i},'scenario_id':s})]
        elif t=='customer':
            cust=rows(c,"SELECT * FROM analytics.customer_dim WHERE CustomerID=?",[i])
            if not cust:raise ValueError(f'No customer {i}.')
            out['entity']=cust[0]
            out['orders']=rows(c,"SELECT COUNT(DISTINCT OrderID) all_orders,COUNT(DISTINCT OrderID) FILTER (WHERE OrderDate>='2016-05-01') may_2016_orders,MAX(OrderDate) last_order_date,COALESCE(SUM(UnpickedUnits),0) unpicked_units,COUNT(DISTINCT CASE WHEN UnpickedUnits>0 THEN OrderID END) orders_with_unpicked FROM analytics.order_lines_v2 WHERE CustomerID=? AND ScenarioID=?",[i,s])[0]
            out['top_unpicked_items']=rows(c,"SELECT StockItemID,StockItemName,SUM(UnpickedUnits) unpicked_units FROM analytics.order_lines_v2 WHERE CustomerID=? AND ScenarioID=? AND UnpickedUnits>0 GROUP BY 1,2 ORDER BY 3 DESC,1 LIMIT 5",[i,s])
            out['recent_orders']=rows(c,"SELECT DISTINCT OrderID,OrderDate,SalespersonName,OrderPickingCompletedWhen FROM analytics.order_lines_v2 WHERE CustomerID=? AND ScenarioID=? ORDER BY OrderDate DESC,OrderID DESC LIMIT 5",[i,s])
            out['invoiced']=rows(c,"SELECT COUNT(DISTINCT InvoiceID) invoices,COALESCE(SUM(SalesExTax),0) sales_ex_tax,COALESCE(SUM(LineProfit),0) gross_line_profit FROM analytics.invoice_lines_v2 WHERE CustomerID=?",[i])[0]
            out['invoiced']['unit']='sample amount (currency not stated in source)'
            out['next_steps']=[suggest('Orders created per month','analyze',{'measure_id':'M01','group_by':'month','start':'2016-01-01','end':'2016-06-01','filters':{'customer_id':i}}),
                suggest('Unpicked units by item','analyze',{'measure_id':'M02','group_by':'stock_item','filters':{'customer_id':i}}),
                suggest('Customer page','navigate',None,f'#/customer/{i}')]
        elif t=='order':
            head=rows(c,"SELECT DISTINCT OrderID,CustomerID,CustomerName,SalespersonPersonID,SalespersonName,OrderDate,ExpectedDeliveryDate,OrderPickingCompletedWhen,BackorderOrderID,IsSynthetic FROM analytics.order_lines_v2 WHERE OrderID=? AND ScenarioID=?",[i,s])
            if not head:raise ValueError(f'No order {i} in scenario {s}.')
            out['entity']=head[0]
            out['lines']=rows(c,"SELECT OrderLineID,StockItemID,StockItemName,Quantity,PickedQuantity,UnpickedUnits,LinePickingCompletedWhen FROM analytics.order_lines_v2 WHERE OrderID=? AND ScenarioID=? ORDER BY OrderLineID",[i,s])
            out['backorder_of']=rows(c,"SELECT OrderID FROM analytics.orders WHERE BackorderOrderID=? AND ScenarioID=?",[i,s])
            out['invoices']=rows(c,"SELECT DISTINCT InvoiceID,InvoiceDate FROM analytics.invoice_lines_v2 WHERE OrderID=? ORDER BY 1",[i])
            out['meaning']='BackorderOrderID points from the original order to the new order created for its undersupplied quantity.'
            out['next_steps']=[suggest('Customer','related',{'entity_type':'customer','entity_id':head[0]['CustomerID']},f"#/customer/{head[0]['CustomerID']}")]+[suggest(f"Item {l['StockItemID']}",'related',{'entity_type':'stock_item','entity_id':l['StockItemID'],'scenario_id':s},f"#/item/{l['StockItemID']}") for l in out['lines'][:3]]
        elif t=='supplier':
            sup=rows(c,"SELECT SupplierID,SupplierName,SupplierCategoryID,PaymentDays,WebsiteURL FROM raw.Purchasing_Suppliers WHERE SupplierID=?",[i])
            if not sup:raise ValueError(f'No supplier {i}.')
            out['entity']=sup[0]
            out['items']=rows(c,"SELECT COUNT(*) items FROM raw.Warehouse_StockItems WHERE SupplierID=?",[i])[0]
            out['unpicked_demand_on_its_items']=rows(c,"SELECT COALESCE(SUM(UnpickedUnits),0) units,COUNT(DISTINCT CASE WHEN UnpickedUnits>0 THEN OrderID END) orders FROM analytics.order_lines_v2 WHERE SupplierID=? AND ScenarioID='base'",[i])[0]
            out['top_items_by_unpicked']=rows(c,"SELECT StockItemID,StockItemName,SUM(UnpickedUnits) unpicked_units FROM analytics.order_lines_v2 WHERE SupplierID=? AND ScenarioID='base' AND UnpickedUnits>0 GROUP BY 1,2 ORDER BY 3 DESC,1 LIMIT 5",[i])
            out['incoming']=rows(c,"SELECT COUNT(DISTINCT PurchaseOrderID) open_purchase_orders,COALESCE(SUM(IncomingUnits),0) incoming_units FROM analytics.incoming_v2 WHERE SupplierID=?",[i])[0]
            out['note']='Demand uses the item\'s nominated supplier; incoming uses the purchase order\'s actual supplier. Related by item, not allocated.'
            out['next_steps']=[suggest('Unpicked units by item for this supplier','analyze',{'measure_id':'M02','group_by':'stock_item','filters':{'supplier_id':i}}),
                suggest('Incoming units by item for this supplier','analyze',{'measure_id':'M05','group_by':'stock_item','filters':{'supplier_id':i}}),suggest('Supplier page','navigate',None,f'#/supplier/{i}')]
        elif t=='purchase_order':
            po=rows(c,"SELECT p.PurchaseOrderID,p.SupplierID,su.SupplierName,p.OrderDate,p.ExpectedDeliveryDate,p.IsOrderFinalized FROM raw.Purchasing_PurchaseOrders p JOIN raw.Purchasing_Suppliers su USING(SupplierID) WHERE p.PurchaseOrderID=?",[i])
            if not po:raise ValueError(f'No purchase order {i}.')
            out['entity']=po[0]
            out['lines']=rows(c,"SELECT l.PurchaseOrderLineID,l.StockItemID,s.StockItemName,l.OrderedOuters,l.ReceivedOuters,s.QuantityPerOuter,(CAST(l.OrderedOuters AS BIGINT)-l.ReceivedOuters)*s.QuantityPerOuter remaining_units,l.IsOrderLineFinalized FROM raw.Purchasing_PurchaseOrderLines l JOIN raw.Warehouse_StockItems s USING(StockItemID) WHERE l.PurchaseOrderID=? ORDER BY 1",[i])
            out['next_steps']=[suggest('Purchase page','navigate',None,f'#/purchase/{i}'),suggest('Supplier','related',{'entity_type':'supplier','entity_id':po[0]['SupplierID']},f"#/supplier/{po[0]['SupplierID']}")]
        elif t=='salesperson':
            p=rows(c,"SELECT PersonID,FullName,PreferredName FROM raw.Application_People WHERE PersonID=? AND IsSalesperson",[i])
            if not p:raise ValueError(f'No salesperson {i}.')
            out['entity']=p[0]
            out['orders']=rows(c,"SELECT COUNT(DISTINCT OrderID) all_orders,COUNT(DISTINCT OrderID) FILTER (WHERE OrderDate>='2016-04-01' AND OrderDate<'2016-05-01') april_2016,COUNT(DISTINCT OrderID) FILTER (WHERE OrderDate>='2016-05-01' AND OrderDate<'2016-06-01') may_2016,COUNT(DISTINCT CustomerID) customers FROM analytics.order_lines_v2 WHERE SalespersonPersonID=? AND ScenarioID='base'",[i])[0]
            out['next_steps']=[suggest('Orders by territory, May vs April 2016','analyze',{'measure_id':'M01','group_by':'sales_territory','start':'2016-05-01','end':'2016-06-01','compare_start':'2016-04-01','compare_end':'2016-05-01','filters':{'salesperson_id':i}})]
    finally:c.close()
    return out
