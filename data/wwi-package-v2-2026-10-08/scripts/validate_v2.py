"""v2 checks: parity with v1, breakdown/compare arithmetic, raw cross-checks for new dimensions,
name resolution, entity hops, rejected combinations, Contract integrity, and (with --url) HTTP behaviour."""
from __future__ import annotations
import argparse,json,pathlib,time,urllib.request,urllib.error
from decimal import Decimal
from common import load,save
from engine import execute_metric
from analysis_v2 import analyze,resolve,related,MEASURES,DIMENSIONS,additive

def validate(package,url=None):
    import duckdb,jsonschema
    p=pathlib.Path(package).resolve();checks=[];started=time.perf_counter()
    def check(name,got,expected):
        ok=got==expected;checks.append({'check':name,'pass':ok,'got':got,'expected':expected})
        if not ok:print('FAIL',name,'got',got,'expected',expected,flush=True)
    A=lambda **k:analyze(p,k)
    # 1. parity with the v1 metric engine (unchanged code path)
    periods=[(None,None),('2016-05-01','2016-06-01'),('2016-04-01','2016-05-01'),('2015-01-01','2016-01-01'),('2013-01-01','2013-02-01')]
    fsets=[{},{'customer_id':11},{'stock_item_id':193},{'supplier_id':7},{'stock_group_id':1},{'status':'picking-incomplete'},{'status':'quantity-not-yet-picked'},{'customer_id':404,'supplier_id':4}]
    for mid in ['M01','M02','M03']:
        for s,e in periods:
            for f in fsets:
                v1=execute_metric(p,mid,{'date_basis':'order_date','start':s,'end':e,'filters':f})['rows'][0]['value']
                check(f'parity_{mid}_{s}_{json.dumps(f)}',A(measure_id=mid,start=s,end=e,filters=f)['total'],v1)
    for basis,s,e in [('none',None,None),('purchase_order_date','2016-01-01','2016-06-01'),('expected_delivery_date','2016-05-01','2016-07-01'.replace('07-01','06-21'))]:
        for f in [{},{'stock_item_id':80},{'supplier_id':4},{'purchase_order_id':2073}]:
            v1=execute_metric(p,'M05',{'date_basis':basis,'start':s,'end':e,'filters':f})['rows'][0]['value']
            check(f'parity_M05_{basis}_{json.dumps(f)}',A(measure_id='M05',date_basis=basis,start=s,end=e,filters=f)['total'],v1)
    # 2. arithmetic: additive breakdowns sum to total, compare changes sum to change
    for mid,spec in MEASURES.items():
        per=({'date_basis':'none'} if mid=='M05' else {'start':'2016-01-01','end':'2016-06-01'})
        for dim in spec['dimensions']:
            if dim=='none' or (dim=='month' and mid=='M05'):continue
            r=A(measure_id=mid,group_by=dim,top_n=5,**per);dec=isinstance(r['total'],str)
            total=Decimal(r['total']) if dec else r['total']
            if additive(mid,dim):
                rows_sum=sum((Decimal(x['value']) if dec else x['value']) for x in r['rows'])
                check(f'additive_{mid}_{dim}',rows_sum,total)
            else:
                check(f'overlap_share_null_{mid}_{dim}',all(x['share'] is None for x in r['rows']),True)
        if mid!='M05':
            for dim in ['none','sales_territory','customer_category','salesperson']:
                if dim not in spec['dimensions']:continue
                r=A(measure_id=mid,group_by=dim,start='2016-05-01',end='2016-06-01',compare_start='2016-04-01',compare_end='2016-05-01',top_n=3)
                dec=isinstance(r['change'],str);conv=(lambda v:Decimal(v)) if dec else (lambda v:v)
                check(f'compare_change_{mid}_{dim}',conv(r['total_current'])-conv(r['total_baseline']),conv(r['change']))
                if dim!='none':check(f'compare_rows_sum_{mid}_{dim}',sum(conv(x['change']) for x in r['rows']),conv(r['change']))
    # 3. independent raw-Parquet cross-checks for the new dimensions and money (own SQL, no analytics views)
    c=duckdb.connect();R=lambda t:f"read_parquet('{p}/data/raw/{t}.parquet')"
    geo=f"{R('Sales.Customers')} cu JOIN {R('Application.Cities')} ci ON ci.CityID=cu.DeliveryCityID JOIN {R('Application.StateProvinces')} sp ON sp.StateProvinceID=ci.StateProvinceID"
    raw=dict(c.execute(f"SELECT sp.SalesTerritory,COUNT(*) FROM {R('Sales.Orders')} o JOIN {geo} ON cu.CustomerID=o.CustomerID WHERE o.OrderDate>='2016-05-01' AND o.OrderDate<'2016-06-01' GROUP BY 1").fetchall())
    eng={x['key']:x['value'] for x in A(measure_id='M01',group_by='sales_territory',start='2016-05-01',end='2016-06-01',top_n=50)['rows']}
    check('raw_territory_may_orders',eng,raw)
    raw=dict(c.execute(f"SELECT o.SalespersonPersonID,COUNT(*) FROM {R('Sales.Orders')} o WHERE o.OrderDate>='2016-04-01' AND o.OrderDate<'2016-05-01' GROUP BY 1").fetchall())
    eng={x['key']:x['value'] for x in A(measure_id='M01',group_by='salesperson',start='2016-04-01',end='2016-05-01',top_n=50)['rows']}
    check('raw_salesperson_april_orders',eng,raw)
    raw={k:format(v,'f') for k,v in c.execute(f"SELECT strftime(i.InvoiceDate,'%Y-%m'),SUM(l.ExtendedPrice-l.TaxAmount) FROM {R('Sales.Invoices')} i JOIN {R('Sales.InvoiceLines')} l USING(InvoiceID) WHERE i.InvoiceDate>='2015-01-01' AND i.InvoiceDate<'2016-06-01' GROUP BY 1").fetchall()}
    eng={x['key']:x['value'] for x in A(measure_id='M10',group_by='month',start='2015-01-01',end='2016-06-01',top_n=50)['rows']}
    check('raw_monthly_invoiced_sales',eng,raw)
    check('raw_total_invoiced_sales',A(measure_id='M10')['total'],format(c.execute(f"SELECT SUM(ExtendedPrice-TaxAmount) FROM {R('Sales.InvoiceLines')}").fetchone()[0],'f'))
    check('raw_total_line_profit',A(measure_id='M11')['total'],format(c.execute(f"SELECT SUM(LineProfit) FROM {R('Sales.InvoiceLines')}").fetchone()[0],'f'))
    raw=dict(c.execute(f"SELECT cu.CustomerCategoryID,SUM(GREATEST(l.Quantity-l.PickedQuantity,0)) FROM {R('Sales.OrderLines')} l JOIN {R('Sales.Orders')} o USING(OrderID) JOIN {R('Sales.Customers')} cu ON cu.CustomerID=o.CustomerID GROUP BY 1 HAVING SUM(GREATEST(l.Quantity-l.PickedQuantity,0))>0").fetchall())
    eng={x['key']:x['value'] for x in A(measure_id='M02',group_by='customer_category',top_n=50)['rows'] if x['value']>0}
    check('raw_category_unpicked',eng,raw)
    raw=c.execute(f"SELECT SUM(l.Quantity) FROM {R('Sales.OrderLines')} l JOIN {R('Sales.Orders')} o USING(OrderID) JOIN {geo} ON cu.CustomerID=o.CustomerID WHERE sp.StateProvinceName='California' AND o.OrderDate>='2016-01-01' AND o.OrderDate<'2016-06-01'").fetchone()[0]
    check('raw_california_ordered_units',A(measure_id='M13',start='2016-01-01',end='2016-06-01',filters={'state_province_id':5})['total'],int(raw))
    raw=c.execute(f"SELECT COUNT(DISTINCT o.OrderID) FROM {R('Sales.Orders')} o JOIN {R('Sales.Customers')} cu USING(CustomerID) WHERE cu.BuyingGroupID IS NULL AND o.OrderDate>='2016-05-01' AND o.OrderDate<'2016-06-01'").fetchone()[0]
    rows={x['label']:x['value'] for x in A(measure_id='M01',group_by='buying_group',start='2016-05-01',end='2016-06-01')['rows']}
    check('raw_no_buying_group_may',rows.get('No buying group'),raw)
    # 4. name resolution
    for text,types,status,top in [('litware',None,'unique',('supplier',7)),('Litware, Inc.',None,'unique',('supplier',7)),('Hudson',None,'ambiguous',None),('tailspin toys',None,'ambiguous',None),
        ('tailspin toys',['buying_group'],'unique',('buying_group',1)),('great lakes',None,'unique',('sales_territory','Great Lakes')),('CA',['state_province'],'unique',('state_province',5)),
        ('novelty shops',None,'unique',('customer_category',3)),('Kayla Woodcock',None,'unique',('salesperson',2)),('fabrikam',None,'unique',('supplier',4)),('qwxzv',None,'none',None),
        ('mugs',['stock_group'],'unique',('stock_group',3)),('Tailspin Toys (Head Office)',None,'unique',('customer',1))]:
        r=resolve(p,{'text':text,**({'types':types} if types else {})})
        check(f'resolve_status_{text}_{types}',r['status'],status)
        if top:check(f'resolve_top_{text}_{types}',(r['candidates'][0]['type'],r['candidates'][0]['id']),top)
    # 5. entity hops
    it=related(p,{'entity_type':'stock_item','entity_id':80})
    check('related_item80_supplier',it['entity']['SupplierID'],4);check('related_item80_incoming',sum(x['IncomingUnits'] for x in it['incoming']),21972)
    check('related_item80_unpicked',it['unpicked_demand']['units'],execute_metric(p,'M02',{'date_basis':'order_date','filters':{'stock_item_id':80}})['rows'][0]['value'])
    o=related(p,{'entity_type':'order','entity_id':73573});check('related_order_backorder',o['entity']['BackorderOrderID'],73595)
    o=related(p,{'entity_type':'order','entity_id':73595});check('related_backorder_of',[x['OrderID'] for x in o['backorder_of']],[73573])
    fx=related(p,{'entity_type':'stock_item','entity_id':1227,'scenario_id':'no_incoming_v1'})
    check('related_fixture',(fx['unpicked_demand']['units'],fx['holdings'][0]['QuantityOnHand'],len(fx['incoming']),fx['entity']['IsSynthetic']),(120,20,0,True))
    check('related_supplier7_items',related(p,{'entity_type':'supplier','entity_id':7})['items']['items'],c.execute(f"SELECT COUNT(*) FROM {R('Warehouse.StockItems')} WHERE SupplierID=7").fetchone()[0])
    # 6. rejected combinations (must raise, never silently ignore)
    bad=[{'measure_id':'M05','group_by':'customer'},{'measure_id':'M05','filters':{'sales_territory':'Plains'}},{'measure_id':'M01','filters':{'purchase_order_id':2073}},
         {'measure_id':'M10','date_basis':'order_date'},{'measure_id':'M10','filters':{'status':'picking-incomplete'}},{'measure_id':'M10','scenario_id':'no_incoming_v1'},
         {'measure_id':'M01','start':'2016-05-01','end':'2016-06-01','compare_start':'2016-04-01','compare_end':'2016-05-01','group_by':'month'},
         {'measure_id':'M01','compare_start':'2016-04-01','compare_end':'2016-05-01'},{'measure_id':'M01','start':'2016-05-01'},{'measure_id':'M01','filters':{'sales_territory':'Atlantis'}},
         {'measure_id':'M01','filters':{'colour':'red'}},{'measure_id':'M01','sort':'change_desc'},{'measure_id':'M04'},{'measure_id':'M01','top_n':51},{'measure_id':'M05','date_basis':'none','start':'2016-01-01','end':'2016-02-01'},
         {'measure_id':'M01','start':'2012-01-01','end':'2012-02-01'},{'measure_id':'M01','filters':{'customer_id':-3}}]
    for b in bad:
        try:analyze(p,b);check(f'rejected_{json.dumps(b)}','accepted','rejected')
        except ValueError:check(f'rejected_{json.dumps(b)}','rejected','rejected')
    # 7. Contract integrity
    cat=lambda n:load(p/'catalog'/f'{n}.json')
    am={m['id']:m for m in cat('analysis_measures')['items']}
    check('contract_measures_match_engine',sorted(k for k,v in am.items() if 'analyze' in v['operations']),sorted(MEASURES))
    dims={d['id'] for d in cat('dimensions')['items']}
    check('contract_dimensions_match_engine',dims,{'none',*DIMENSIONS})
    gl=cat('glossary')['items'];bad_terms=[]
    for t in gl:
        m=t['maps_to'] or {}
        if m.get('measure_id') and m['measure_id'] not in am:bad_terms.append(t['term'])
        if m.get('group_by') and m['group_by'] not in dims:bad_terms.append(t['term'])
        if t['status']=='ambiguous' and not t['clarify_question']:bad_terms.append(t['term'])
        if t['status']=='unsupported' and not t['unsupported_reply']:bad_terms.append(t['term'])
    check('contract_glossary_targets',bad_terms,[])
    g=cat('graph');ents={e['id'] for e in g['entities']}
    check('contract_graph_endpoints',[r for r in g['relationships'] if r['from'] not in ents or r['to'] not in ents],[])
    ops={o['name'] for o in cat('operations')['items']}
    check('contract_playbook_operations',sorted({s['operation'] for pb in cat('playbooks')['items'] for s in pb['steps']}-ops),[])
    for o in cat('operations')['items']:
        if o['input_schema']:jsonschema.Draft202012Validator.check_schema(o['input_schema'])
    check('contract_operation_schemas_valid',True,True)
    filters={f['id'] for f in cat('filters')['items']}
    check('contract_filters_cover_engine',sorted({k for s in MEASURES.values() for k in s['filters']}-filters),[])
    # 8. HTTP
    if url:
        def call(path,body=None):
            req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=60) as r:return r.status,json.load(r)
            except urllib.error.HTTPError as e:return e.code,json.load(e)
        s,d=call('/api/analyze',{'measure_id':'M01','start':'2016-05-01','end':'2016-06-01'});check('http_analyze',(s,d['total']),(200,2047))
        s,d=call('/api/analyze',{'measure_id':'M05','group_by':'customer'});check('http_analyze_invalid',(s,d['completed']),(422,False))
        s,d=call('/api/analyze',{'measure_id':'M07'});check('http_analyze_unpublished',s,422)
        s,d=call('/api/resolve',{'text':'litware'});check('http_resolve',(s,d['candidates'][0]['id']),(200,7))
        s,d=call('/api/related',{'entity_type':'order','entity_id':73573});check('http_related',(s,d['entity']['BackorderOrderID']),(200,73595))
        s,d=call('/api/related',{'entity_type':'order','entity_id':999999});check('http_related_missing',s,422)
        s,d=call('/api/contract');check('http_contract_docs',sorted(d),sorted(['analysis_measures','charts','contract_version','dimensions','filters','glossary','graph','measures','operations','playbooks','views','widgets']))
        s,d=call('/api/lookup?type=salesperson');check('http_lookup',(s,len(d)),(200,10))
        s,d=call('/api/lookup?type=customer');check('http_lookup_refuses_large',s,422)
        s,d=call('/api/metric',{'id':'M02','start':'2016-05-01','end':'2016-06-01'});check('http_v1_metric_unchanged',(s,d['rows'][0]['value']),(200,17710))
        s,d=call('/api/capabilities');check('http_v1_money_hidden',bool({'M10','M11'}&{m['id'] for m in d['measures']['items']}),False)
    failures=[x for x in checks if not x['pass']]
    save(p/'evidence/analysis_validation.json',{'status':'pass' if not failures else 'fail','checks':len(checks),'failures':failures,'results':checks,'seconds':time.perf_counter()-started,
        'scope':'engine parity with v1, arithmetic invariants, raw-Parquet cross-checks, resolution, hops, rejections, Contract integrity'+(', HTTP' if url else ''),'agent_success':'not-measured'})
    print(f"v2 validation {'passed' if not failures else 'FAILED'}: {len(checks)-len(failures)}/{len(checks)}",flush=True)
    if failures:raise SystemExit(1)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--url');a=ap.parse_args();validate(a.package,a.url)
