"""Generate the v2 Contract documents (catalog/*.json). Measures and dimensions come from analysis_v2 so the Contract and the engine cannot drift."""
from __future__ import annotations
import argparse,pathlib
from common import load,save
from analysis_v2 import MEASURES,DIMENSIONS,AnalyzeRequest,ResolveRequest,RelatedRequest,TERRITORIES,additive
from request_models import Request

VERSION='wwi-data-v1-2026-10-08'
HEAD={'dataset_version':VERSION,'scenario_id':'base'}
REFERENCE_DATE='2016-05-31'

def analysis_measures():
    items=[]
    for mid,s in MEASURES.items():
        money=mid in ('M10','M11')
        items.append({'id':mid,'name':s['name'],'definition':s['definition'],'unit':s['unit'],'currency':'not stated in source' if money else None,
            'grain':'order' if not s['per_line'] else ('invoice line' if money else ('purchase line' if mid=='M05' else 'order line')),
            'date_bases':s['bases'],'default_date_basis':s['bases'][0],'filters':s['filters'],'status_values':s['status'],
            'dimensions':[{'id':d,'additive':(None if d=='none' else (True if d=='month' else additive(mid,d)))} for d in s['dimensions']],
            'not_allowed':s['why_not'],
            'status':'published-with-caveat' if money else 'verified',
            'caveat':{'M10':'Arithmetic reconciles on all 228,265 invoice lines; the source states no currency (Microsoft describes the company as US-based). Excludes tax. Dated by invoice date.',
                      'M11':'Recorded gross line profit, not net profit (no overheads). Currency not stated in source.',
                      'M02':'Stored state at archive end; not historical backlog at a past date.','M05':'Related to items, not allocated to customer orders.',
                      'M13':'Units of unlike products; not money or volume.'}.get(mid),
            'operations':['analyze']+(['metric'] if mid in ('M01','M02','M03','M05') else []),
            'verification':'evidence/analysis_validation.json'})
    items.append({'id':'M04','name':'Stored holdings and reorder level','definition':'Per-item QuantityOnHand, ReorderLevel, TargetStockLevel (undated stored state).','unit':'item units','currency':None,'grain':'stock item',
        'date_bases':['none'],'default_date_basis':'none','filters':['stock_item_id','supplier_id','stock_group_id'],'status_values':['all'],'dimensions':[{'id':'none','additive':None}],
        'not_allowed':{'period':'holdings are undated'},'status':'verified','caveat':'Not available-to-promise.','operations':['metric','related'],'verification':'evidence/metric_validation.json'})
    for mid,name,why in [('M06','Date-based time to pick completion','candidate: date-only start'),('M07','Supplier receipt lateness','rejected: uniformly zero in source'),('M08','Recorded confirmation lateness','candidate: not published'),('M09','Estimated open lines at a past date','candidate approximation; exact history blocked')]:
        items.append({'id':mid,'name':name,'definition':'See catalog/measures.json and reports/measure_verdicts.md','unit':None,'currency':None,'grain':None,'date_bases':[],'default_date_basis':None,'filters':[],'status_values':[],'dimensions':[],
            'not_allowed':{},'status':'rejected' if mid=='M07' else 'candidate','caveat':why,'operations':[],'verification':'reports/measure_verdicts.md'})
    return {**HEAD,'note':'Authoritative measure list for /api/analyze. catalog/measures.json still describes the v1 /api/metric operation unchanged.','items':items}

def dimensions():
    paths={'month':'strftime(date basis column, %Y-%m)','customer':'Orders/Invoices.CustomerID -> Customers','customer_category':'Customer -> CustomerCategories (current)',
           'buying_group':'Customer -> BuyingGroups (current; NULL = "No buying group")','state_province':'Customer.DeliveryCityID -> Cities -> StateProvinces (current)',
           'sales_territory':'Customer delivery state -> StateProvinces.SalesTerritory (current)','salesperson':'Orders/Invoices.SalespersonPersonID -> People',
           'stock_item':'line StockItemID -> StockItems','supplier':"item's nominated supplier (orders/invoices); purchase order's actual supplier (incoming)",
           'stock_group':'StockItemStockGroups bridge (many-to-many)'}
    items=[{'id':'none','name':'No breakdown','path':None,'additive':None,'measures':list(MEASURES),'resolve_type':None,'filter':None}]
    fil={'customer':'customer_id','customer_category':'customer_category_id','buying_group':'buying_group_id','state_province':'state_province_id','sales_territory':'sales_territory','salesperson':'salesperson_id','stock_item':'stock_item_id','supplier':'supplier_id','stock_group':'stock_group_id','month':None}
    for d,v in DIMENSIONS.items():
        items.append({'id':d,'name':v['name'],'path':paths[d],'additive':v['additive'],'additive_rule':'per measure: additive for line-level sums, overlapping for distinct-order counts' if v['additive'] is None else None,
                      'measures':[m for m,s in MEASURES.items() if d in s['dimensions']],'resolve_type':None if d=='month' else d,'filter':fil[d],
                      'drill_down':f'take a row key and set filter {fil[d]} to drill in' if fil[d] else 'take a row month and set start/end to that month'})
    return {**HEAD,'note':'Customer attributes are current stored values, not values at order time.','items':items}

def T(term,synonyms,status,maps_to=None,note=None,ask=None,reply=None):
    return {'term':term,'synonyms':synonyms,'status':status,'maps_to':maps_to,'note':note,'clarify_question':ask,'unsupported_reply':reply}
def glossary():
    items=[
     T('orders created',['orders','order count','new orders','orders placed','order volume','how many orders'],'mapped',{'measure_id':'M01'}),
     T('unpicked units',['not yet picked','still to pick','waiting to be picked','outstanding units','unfulfilled quantity','units left to pick'],'mapped',{'measure_id':'M02'},'Stored state at archive end, not historical backlog.'),
     T('orders with unpicked quantities',['orders waiting','orders not fully picked','orders with outstanding items'],'mapped',{'measure_id':'M03'}),
     T('ordered units',['units ordered','quantity ordered','demand units','volume ordered'],'mapped',{'measure_id':'M13'},'Counts of unlike products.'),
     T('incoming units',['incoming','on order from suppliers','inbound','due in','supply pipeline','expected supply'],'mapped',{'measure_id':'M05'},'Related by item, not allocated to a customer order.'),
     T('sales',['revenue','turnover','invoiced','billed','sales value','takings'],'mapped',{'measure_id':'M10'},'Invoiced sales excluding tax; currency not stated in source; dated by invoice date.'),
     T('profit',['gross profit','margin earned','line profit'],'mapped',{'measure_id':'M11'},'Recorded gross line profit, not net profit.'),
     T('stock on hand',['inventory','holdings','stock level','how much stock'],'mapped',{'operation':'metric','measure_id':'M04'},'Undated stored state; not available-to-promise.'),
     T('below reorder level',['needs reordering','low stock'],'mapped',{'operation':'metric','measure_id':'M04','compare':'QuantityOnHand < ReorderLevel'}),
     T('backorder',['back order','backordered'],'mapped',{'operation':'related','entity_type':'order'},'Orders.BackorderOrderID points from the original order to the new order created for its undersupplied quantity.'),
     T('territory',['region','area','sales region'],'mapped',{'group_by':'sales_territory','filter':'sales_territory','values':TERRITORIES}),
     T('state',['US state','province','delivery state'],'mapped',{'group_by':'state_province','filter':'state_province_id'}),
     T('customer category',['segment','customer type','channel','kind of customer'],'mapped',{'group_by':'customer_category','filter':'customer_category_id'}),
     T('buying group',['customer group','chain','franchise group'],'mapped',{'group_by':'buying_group','filter':'buying_group_id'}),
     T('salesperson',['rep','sales rep','account manager','seller'],'mapped',{'group_by':'salesperson','filter':'salesperson_id'}),
     T('item',['product','SKU','stock item','article'],'mapped',{'group_by':'stock_item','filter':'stock_item_id'}),
     T('supplier',['vendor','manufacturer'],'mapped',{'group_by':'supplier','filter':'supplier_id'}),
     T('stock group',['product group','product line','product type'],'mapped',{'group_by':'stock_group','filter':'stock_group_id'},'Items can be in several groups: group totals overlap and must not be summed.'),
     T('this month',['current month','month to date'],'mapped',{'start':'2016-05-01','end':'2016-06-01'},f'Reference date is the archive end, {REFERENCE_DATE}.'),
     T('last month',['previous month','prior month'],'mapped',{'start':'2016-04-01','end':'2016-05-01'},f'Relative to reference date {REFERENCE_DATE}.'),
     T('this year',['year to date','YTD'],'mapped',{'start':'2016-01-01','end':'2016-06-01'},'2016 data ends 31 May.'),
     T('last year',['previous year','2015'],'mapped',{'start':'2015-01-01','end':'2016-01-01'}),
     T('open orders',['pending orders','outstanding orders','backlog'],'ambiguous',None,'Could mean orders with unpicked quantities (M03), orders whose picking is incomplete (status picking-incomplete), or a historical backlog (not available).',
       'By "open orders", do you mean orders that still have units to pick, or orders whose picking is not marked complete?'),
     T('category',['categories'],'ambiguous',None,'Customer category and product stock group are different things.','Do you mean customer category (e.g. Novelty Shop) or product group (e.g. Mugs)?'),
     T('top customers',['best customers','biggest customers'],'ambiguous',None,'Ranking needs a measure.','Top by number of orders, units ordered, or invoiced sales?'),
     T('performance',['how are we doing','results'],'ambiguous',None,None,'Which measure: orders, units, unpicked units, incoming supply, or invoiced sales?'),
     T('late deliveries',['delayed orders','on-time delivery','delivery performance'],'unsupported',None,'Confirmation lateness (M08) is an unpublished candidate; supplier receipt lateness (M07) is uniformly zero in the source.',None,
       'Delivery performance is not a published measure in this data. I can show orders created, unpicked units, or expected delivery dates for specific orders.'),
     T('why / root cause',['why did','what caused','because of','blame'],'unsupported',None,'The source records no reasons.',None,
       'The data has no recorded reasons, so I can show where a change is concentrated (territory, customer, item) but not prove its cause.'),
     T('forecast',['predict','next month','projection'],'unsupported',None,None,None,'Forecasting is not supported; I can show the historical trend by month.'),
     T('net profit',['bottom line','profit after costs','margin after overheads'],'unsupported',None,'Only recorded gross line profit exists.',None,'Net profit is not available; I can show recorded gross line profit (M11).'),
     T('historical backlog',['backlog at the end of April','open orders on a past date'],'unsupported',None,'Exact past-state quantities are not recorded (M09 is an approximation candidate).',None,
       'The data stores the current state only, so I cannot give exact backlog at a past date.'),
     T('allocation',['which purchase order covers this order','available to promise','ATP'],'unsupported',None,'Purchasing is related to items, not allocated to sales orders.',None,
       'Incoming supply is linked by item, not reserved for particular orders; I can show both side by side.'),
     T('currency',['dollars','USD','rupees','convert'],'unsupported',None,'Currency is not stated in the source.',None,'Amounts are sample amounts; the source does not state a currency.'),
     T('change data',['create a case','update order','cancel','send email'],'unsupported',None,'The app is read-only.',None,'This app is read-only; I can only look up and analyse.'),
    ]
    return {**HEAD,'reference_date':REFERENCE_DATE,'time_rules':'Relative dates are resolved against the archive end date; always state the resolved dates in the answer.','items':items}

def graph():
    E=lambda id,table,key,label,route,resolve,note=None:{'id':id,'table':table,'key':key,'label':label,'detail_route':route,'resolve_type':resolve,'related_operation':id if id in ('customer','order','stock_item','supplier','purchase_order','salesperson') else None,'note':note}
    entities=[E('customer','Sales.Customers','CustomerID','CustomerName','#/customer/{id}','customer'),E('order','Sales.Orders','OrderID','OrderID','#/order/{id}',None),
      E('order_line','Sales.OrderLines','OrderLineID','OrderLineID','#/order-line/{id}',None),E('stock_item','Warehouse.StockItems','StockItemID','StockItemName','#/item/{id}','stock_item'),
      E('supplier','Purchasing.Suppliers','SupplierID','SupplierName','#/supplier/{id}','supplier'),E('purchase_order','Purchasing.PurchaseOrders','PurchaseOrderID','PurchaseOrderID','#/purchase/{id}',None),
      E('purchase_line','Purchasing.PurchaseOrderLines','PurchaseOrderLineID','PurchaseOrderLineID','#/purchase-line/{id}',None),E('holdings','Warehouse.StockItemHoldings','StockItemID','StockItemID','#/item/{id}',None,'one row per item; undated'),
      E('invoice','Sales.Invoices','InvoiceID','InvoiceID',None,None,'no invoice page; use analyze M10/M11'),E('salesperson','Application.People (IsSalesperson)','PersonID','FullName',None,'salesperson'),
      E('customer_category','Sales.CustomerCategories','CustomerCategoryID','CustomerCategoryName',None,'customer_category'),E('buying_group','Sales.BuyingGroups','BuyingGroupID','BuyingGroupName',None,'buying_group'),
      E('state_province','Application.StateProvinces','StateProvinceID','StateProvinceName',None,'state_province'),E('sales_territory','Application.StateProvinces.SalesTerritory','SalesTerritory','SalesTerritory',None,'sales_territory'),
      E('stock_group','Warehouse.StockGroups','StockGroupID','StockGroupName',None,'stock_group')]
    R=lambda f,t,join,card,meaning:{'from':f,'to':t,'join':join,'cardinality':card,'meaning':meaning}
    rels=[R('customer','order','Orders.CustomerID','1:n','orders placed by the customer'),R('order','order_line','OrderLines.OrderID','1:n','lines of the order'),
      R('order_line','stock_item','OrderLines.StockItemID','n:1','item ordered'),R('order','salesperson','Orders.SalespersonPersonID','n:1','salesperson on the order'),
      R('order','order','Orders.BackorderOrderID','1:0..1','original order -> new backorder created for its undersupplied quantity'),
      R('order','invoice','Invoices.OrderID','1:0..1','observed one invoice per order in this extract'),R('stock_item','supplier','StockItems.SupplierID','n:1','nominated supplier of the item'),
      R('stock_item','stock_group','StockItemStockGroups','n:m','product groups (overlapping)'),R('stock_item','holdings','StockItemHoldings.StockItemID','1:1','stored stock on hand and reorder level'),
      R('stock_item','purchase_line','PurchaseOrderLines.StockItemID','1:n','related purchasing for the item; NOT allocated to sales orders'),
      R('purchase_order','purchase_line','PurchaseOrderLines.PurchaseOrderID','1:n','lines of the purchase order'),R('purchase_order','supplier','PurchaseOrders.SupplierID','n:1','actual supplier of the purchase order'),
      R('customer','customer_category','Customers.CustomerCategoryID','n:1','current category'),R('customer','buying_group','Customers.BuyingGroupID','n:0..1','current buying group'),
      R('customer','state_province','Customers.DeliveryCityID -> Cities.StateProvinceID','n:1','current delivery state'),R('state_province','sales_territory','StateProvinces.SalesTerritory','n:1','territory of the state'),
      R('customer','customer','Customers.BillToCustomerID','n:1','bill-to account (head office)')]
    return {**HEAD,'entities':entities,'relationships':rels,'traps':['Purchasing is never allocated to customer orders: relate by item only.','Item supplier (nominated) can differ from purchase order supplier (actual).','Purchase quantities are in outers (e.g. cartons): multiply by QuantityPerOuter for units.','Order counts by item/supplier/stock group overlap.','Customer attributes are current, not as at order time.']}

def S(n,op,request,use):return {'step':n,'operation':op,'request':request,'use_output':use}
def playbooks():
    cmp={'start':'{current_start}','end':'{current_end}','compare_start':'{baseline_start}','compare_end':'{baseline_end}'}
    items=[
     {'id':'explain_change','question_pattern':'Why did <measure> go up/down between two periods?','answer_style':'Descriptive: where the change is concentrated; never claim a cause.','steps':[
        S(1,'analyze',{'measure_id':'{measure}',**cmp},'total_baseline, total_current, change, pct_change'),
        S(2,'analyze',{'measure_id':'{measure}',**cmp,'group_by':'sales_territory'},'largest share_of_change row -> {top_group}; repeat with customer_category and salesperson to see which dimension concentrates the change'),
        S(3,'analyze',{'measure_id':'{measure}',**cmp,'group_by':'customer','filters':{'sales_territory':'{top_group}'}},'top contributing customers inside the group'),
        S(4,'related',{'entity_type':'customer','entity_id':'{top_customer}'},'context for the top customer'),
        S(5,'navigate',{'deep_link':'from step 2 or 3'},'show the evidence page')]},
     {'id':'unpicked_triage','question_pattern':'Which items hold up fulfilment and is supply coming?','answer_style':'Compare demand, stock and incoming in the same unit (item units).','steps':[
        S(1,'analyze',{'measure_id':'M02','group_by':'stock_item','top_n':5,'start':'{period_start}','end':'{period_end}'},'top item -> {item}'),
        S(2,'related',{'entity_type':'stock_item','entity_id':'{item}'},'holdings, unpicked_demand (all dates), incoming lines (outers x QuantityPerOuter)'),
        S(3,'related',{'entity_type':'supplier','entity_id':'{item_supplier}'},'supplier context'),
        S(4,'navigate',{'deep_link':'#/item/{item}'},'show item evidence')]},
     {'id':'supplier_exposure','question_pattern':'How exposed are we to supplier <name>?','answer_style':'Demand on its items vs incoming from it; related by item, not allocated.','steps':[
        S(1,'resolve',{'text':'{supplier_name}','types':['supplier']},'unique -> {supplier}; ambiguous -> ask'),
        S(2,'related',{'entity_type':'supplier','entity_id':'{supplier}'},'summary'),
        S(3,'analyze',{'measure_id':'M02','group_by':'stock_item','filters':{'supplier_id':'{supplier}'}},'demand by item'),
        S(4,'analyze',{'measure_id':'M05','group_by':'stock_item','filters':{'supplier_id':'{supplier}'}},'incoming by item')]},
     {'id':'customer_review','question_pattern':'How is customer <name> doing?','answer_style':'Orders trend, unpicked items, invoiced sales with caveat.','steps':[
        S(1,'resolve',{'text':'{customer_name}','types':['customer','buying_group']},'unique -> {customer}; ambiguous (e.g. a buying group name) -> ask which'),
        S(2,'related',{'entity_type':'customer','entity_id':'{customer}'},'summary'),
        S(3,'analyze',{'measure_id':'M01','group_by':'month','start':'2016-01-01','end':'2016-06-01','filters':{'customer_id':'{customer}'}},'trend'),
        S(4,'analyze',{'measure_id':'M02','group_by':'stock_item','filters':{'customer_id':'{customer}'}},'what they wait for')]},
     {'id':'segment_comparison','question_pattern':'Compare <segment A> with <segment B> on <measure>.','answer_style':'Same measure, unit, period and filters on both sides.','steps':[
        S(1,'analyze',{'measure_id':'{measure}','group_by':'{dimension}','start':'{period_start}','end':'{period_end}','top_n':50},'read both rows; state shares'),
        S(2,'analyze',{'measure_id':'{measure}','group_by':'month','start':'{period_start}','end':'{period_end}','filters':{'{dimension_filter}':'{segment_a}'}},'trend for A; repeat for B')]},
     {'id':'order_trace','question_pattern':'What happened to order <id>?','answer_style':'Lines, picking, backorder chain, invoice.','steps':[
        S(1,'related',{'entity_type':'order','entity_id':'{order}'},'lines, BackorderOrderID, backorder_of, invoices'),
        S(2,'related',{'entity_type':'order','entity_id':'{BackorderOrderID}'},'follow the backorder if present'),
        S(3,'related',{'entity_type':'stock_item','entity_id':'{unpicked_item}'},'supply for the unpicked item')]},
     {'id':'money_summary','question_pattern':'What were sales and profit?','answer_style':'Always state: excludes tax, invoice date basis, currency not stated, gross line profit not net.','steps':[
        S(1,'analyze',{'measure_id':'M10','group_by':'month','start':'{period_start}','end':'{period_end}'},'sales trend'),
        S(2,'analyze',{'measure_id':'M11','group_by':'month','start':'{period_start}','end':'{period_end}'},'profit trend'),
        S(3,'analyze',{'measure_id':'M10','group_by':'customer_category','start':'{period_start}','end':'{period_end}'},'mix')]},
     {'id':'no_supply_branch','question_pattern':'Which demand has no incoming supply? (synthetic fixture)','answer_style':'Label SYNTHETIC; no reason for missing supply exists.','steps':[
        S(1,'related',{'entity_type':'stock_item','entity_id':1227,'scenario_id':'no_incoming_v1'},'unpicked 120, holdings 20, no incoming lines')]},
    ]
    return {**HEAD,'rules':['Carry period, filters and selected entities between steps unless the user replaces them.','Resolve names before filtering; ask when resolve returns ambiguous.','Stop and report when a step returns completed=false; never continue with stale numbers.','Every figure in the answer must come from a step output or code arithmetic over step outputs.'],'items':items}

def operations():
    def op(name,method,path,purpose,when,schema,returns):return {'name':name,'method':method,'path':path,'purpose':purpose,'when_to_use':when,'input_schema':schema,'returns':returns}
    req=Request.model_json_schema()
    return {**HEAD,'items':[
     op('analyze','POST','/api/analyze','Any published measure, optionally broken down by a dimension and/or compared with a baseline period.','Numbers, rankings, breakdowns, period comparisons.',AnalyzeRequest.model_json_schema(),'total or totals+change, rows, applied, deep_link'),
     op('resolve','POST','/api/resolve','Turn a name the user typed into an entity ID.','Before using any named customer, item, supplier, category, group, state, territory or salesperson as a filter.',ResolveRequest.model_json_schema(),'status unique|ambiguous|none, candidates'),
     op('related','POST','/api/related','Everything linked to one entity, with next-step suggestions.','Drilling from a result row into an entity; multi-hop questions.',RelatedRequest.model_json_schema(),'entity summary, linked records, next_steps'),
     op('metric','POST','/api/metric','v1 verified measures (M01-M05, M12) exactly as the dashboard cards compute them.','Holdings (M04) and checks that a card shows the same value.',{**req,'properties':{'id':{'type':'string'},**req['properties']}},'value rows, applied_filters'),
     op('records','POST','/api/records','Paged source records: orders, order_lines, items, holdings, purchase_orders, purchase_lines, customers, suppliers.','Listing evidence rows.',{**req,'properties':{'id':{'type':'string'},**req['properties']}},'rows, total_rows, has_more, provenance'),
     op('chart','POST','/api/chart','v1 dashboard chart data.','Reading what a dashboard chart shows.',{**req,'properties':{'id':{'type':'string'},**req['properties']}},'rows, caption'),
     op('contract','GET','/api/contract','All Contract documents.','Once per session.',None,'documents'),
     op('navigate','CLIENT','location.hash','Open a page in the app (deep links from analyze/related, or #/item/{id} etc.).','After computing an answer, to show its evidence.',{'type':'object','properties':{'deep_link':{'type':'string'}},'required':['deep_link']},'page renders; then read_app_state'),
     op('read_app_state','CLIENT','window.wwiState','Read what the app actually applied (route, request).','After every navigate: compare with what you intended; mismatch = failure.',None,'state object')]}

def build(package):
    p=pathlib.Path(package);c=p/'catalog'
    save(c/'analysis_measures.json',analysis_measures());save(c/'dimensions.json',dimensions());save(c/'glossary.json',glossary());save(c/'graph.json',graph());save(c/'playbooks.json',playbooks());save(c/'operations.json',operations())
    views=load(c/'views.json')
    if not any(v['id']=='analysis' for v in views['items']):
        views['items'].append({'id':'analysis','route':'#/analysis','url_parameters':['scenario_id','measure_id','date_basis','start','end','compare_start','compare_end','group_by','sort','top_n','customer_id','stock_item_id','supplier_id','stock_group_id','order_id','customer_category_id','buying_group_id','state_province_id','sales_territory','salesperson_id','status'],
            'widgets':['analysis-total','analysis-breakdown','analysis-change'],'detail_destinations':['#/customer/{id}','#/item/{id}','#/supplier/{id}','#/order/{id}'],'integration_status':'local companion implementation; renders /api/analyze exactly'})
    views['supported_operations']=sorted(set(views['supported_operations'])|{'analyze','resolve_name','related_entities'});save(c/'views.json',views)
    widgets=load(c/'widgets.json')
    if not any(w['id']=='analysis-total' for w in widgets['items']):
        for wid,typ,unit in [('analysis-total','metric','unit of the selected measure'),('analysis-breakdown','chart','unit of the selected measure'),('analysis-change','table','change in the unit of the selected measure')]:
            widgets['items'].append({'id':wid,'type':typ,'view_id':'analysis','query_id':'analyze','measure_id':None,'display_unit':unit,'filters':['customer_id','stock_item_id','supplier_id','stock_group_id','order_id','customer_category_id','buying_group_id','state_province_id','sales_territory','salesperson_id','status'],
                'record_links':['customer','item','supplier'],'loading':'Loading verified data…','empty':'No matching source records under the applied scope','error':'Display validation/query failure; do not show stale values as completed'})
    save(c/'widgets.json',widgets)
    filters=load(c/'filters.json');have={f['id'] for f in filters['items']}
    for f in filters['items']:
        if 'analysis' not in f['views']:f['views'].append('analysis')
    for fid,etype,lookup in [('customer_category_id','integer','raw.Sales_CustomerCategories.CustomerCategoryID'),('buying_group_id','integer','raw.Sales_BuyingGroups.BuyingGroupID'),('state_province_id','integer','raw.Application_StateProvinces.StateProvinceID'),('sales_territory','enum',None),('salesperson_id','integer','raw.Application_People.PersonID (IsSalesperson)')]:
        if fid not in have:
            filters['items'].append({'id':fid,'views':['analysis'],'field':fid,'date_basis':None,'operators':['eq'],'default':None,'value_type':etype,'valid_enums':TERRITORIES if etype=='enum' else [],'id_lookup':lookup,
                'propagation':'retain until the user replaces it; customer-side filter, rejected for purchasing measures','reset_rule':'new selection replaces previous value; scenario switch clears it'})
    save(c/'filters.json',filters)
    v=load(c/'contract_version.json');v['contract_version']='0.2.0';v['package_version']='2.0.0'
    v['supported_operations']=sorted(set(v['supported_operations'])|{'analyze','resolve_name','related_entities'})
    v['context_propagation'].update({'analysis':'carry measure, period, group_by and filters between turns; a follow-up replaces only what the user changes','names':'resolve names to IDs before filtering; ask when ambiguous','reference_date':REFERENCE_DATE})
    v['documents']=['analysis_measures','dimensions','glossary','graph','playbooks','operations','retrieval/pages.json'];v['money_published']='M10/M11 published with caveat in analysis_measures.json (set status to blocked to withdraw)'
    save(c/'contract_version.json',v);print('Contract v0.2.0 documents written',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);a=ap.parse_args();build(a.package)
