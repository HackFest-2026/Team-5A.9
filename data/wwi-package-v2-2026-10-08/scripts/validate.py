from __future__ import annotations
import argparse,pathlib,datetime,decimal,collections,csv,time
from common import save,load,sha,db,query,csvwrite
def validate(package):
    import pyarrow as pa,pyarrow.parquet as pq
    package=pathlib.Path(package).resolve();start=time.perf_counter();m=load(package/'manifest.json');c=db(package);failures=[];checks=[]
    def check(name,ok,evidence):
        checks.append({'name':name,'pass':bool(ok),'evidence':evidence})
        if not ok:failures.append(name)
    tables={};schemas={}
    for f in m['files']:
        path=package/f['path'];t=pq.read_table(path);tables[f['table']]=t.to_pylist();schemas[f['table']]=t.schema
        count=c.execute(f'SELECT COUNT(*) FROM raw."{f["table"].replace(".","_")}"').fetchone()[0]
        check('file_'+f['table'],sha(path)==f['sha256'] and len(t)==f['rows']==count,{'parquet':len(t),'local':count,'source_export':f['rows']})
        check('schema_'+f['table'],[{'name':x.name,'type':str(x.type),'nullable':x.nullable} for x in t.schema]==f['columns'],str(t.schema))
        for col in t.column_names:
            if col.endswith('__100ns'):check('ticks_'+f['table']+'.'+col,all(x is None or 0<=x<=9 for x in t[col].to_pylist()),'residual 100ns range')
    keys=load(package/'schema/keys.json');grouped=collections.defaultdict(list)
    for k in keys:
        t=k['SchemaName']+'.'+k['TableName']
        if t in tables:grouped[(t,k['KeyName'])].append(k)
    for (t,name),ks in grouped.items():
        fields=[x['ColumnName'] for x in sorted(ks,key=lambda x:x['KeyOrdinal'])];vals=[tuple(r[x] for x in fields) for r in tables[t]]
        check('key_'+name,len(set(vals))==len(vals),{'rows':len(vals),'distinct':len(set(vals)),'fields':fields})
    fk=load(package/'schema/relationships.json');groups=collections.defaultdict(list);excluded=[]
    for f in fk:groups[f['Name']].append(f)
    for name,fs in groups.items():
        f=fs[0];child=f['ChildSchema']+'.'+f['ChildTable'];parent=f['ParentSchema']+'.'+f['ParentTable']
        if child not in tables:continue
        if parent not in tables:excluded.append({'name':name,'parent':parent});continue
        parents={tuple(r[x['ParentColumn']] for x in fs) for r in tables[parent]};orphans=0
        for r in tables[child]:
            value=tuple(r[x['ChildColumn']] for x in fs)
            if all(x is not None for x in value) and value not in parents:orphans+=1
        check('fk_'+name,orphans==0,{'orphans':orphans,'source_disabled':f['IsDisabled'],'source_untrusted':f['IsNotTrusted']})
    # Independent Python row oracle: no analytics view, metric query, or shared validator.
    orders={r['OrderID']:r for r in tables['Sales.Orders']};stock={r['StockItemID']:r for r in tables['Warehouse.StockItems']};holds={r['StockItemID']:r for r in tables['Warehouse.StockItemHoldings']};po={r['PurchaseOrderID']:r for r in tables['Purchasing.PurchaseOrders']}
    under=[r for r in tables['Sales.OrderLines'] if r['Quantity']>r['PickedQuantity']];may=[r for r in under if datetime.date(2016,5,1)<=orders[r['OrderID']]['OrderDate']<datetime.date(2016,6,1)]
    incoming=[r for r in tables['Purchasing.PurchaseOrderLines'] if not po[r['PurchaseOrderID']]['IsOrderFinalized'] and not r['IsOrderLineFinalized'] and r['OrderedOuters']>r['ReceivedOuters']]
    independent={'all':{'lines':len(under),'orders':len({r['OrderID'] for r in under}),'units':sum(r['Quantity']-r['PickedQuantity'] for r in under)},'may':{'lines':len(may),'orders':len({r['OrderID'] for r in may}),'units':sum(r['Quantity']-r['PickedQuantity'] for r in may)},'incoming':{'orders':len({r['PurchaseOrderID'] for r in incoming}),'lines':len(incoming),'units':sum((r['OrderedOuters']-r['ReceivedOuters'])*stock[r['StockItemID']]['QuantityPerOuter'] for r in incoming)}}
    for control,key in [('reference_unpicked','all'),('reference_may','may'),('reference_incoming','incoming')]:
        with (package/'evidence/source_controls'/f'{control}.csv').open(encoding='utf-8',newline='') as f:r=next(csv.DictReader(f))
        expected={k.lower():int(v) for k,v in r.items()};check(control,independent[key]==expected,{'source':expected,'independent':independent[key]})
    for key,sql in [('all',"SELECT COUNT(*) lines,COUNT(DISTINCT OrderID) orders,SUM(UnpickedUnits) units FROM analytics.order_lines WHERE ScenarioID='base' AND UnpickedUnits>0"),('may',"SELECT COUNT(*) lines,COUNT(DISTINCT OrderID) orders,SUM(UnpickedUnits) units FROM analytics.order_lines WHERE ScenarioID='base' AND UnpickedUnits>0 AND OrderDate>=DATE '2016-05-01' AND OrderDate<DATE '2016-06-01'"),('incoming',"SELECT COUNT(DISTINCT PurchaseOrderID) orders,COUNT(*) lines,SUM(IncomingUnits) units FROM analytics.incoming WHERE ScenarioID='base'")]:
        cols,rr=query(c,sql);local=dict(zip(cols,rr[0]));check('local_'+key,local==independent[key],{'local':local,'independent':independent[key]})
    # Compare full sorted May contributing rows against source reference evidence.
    localrows=c.execute("SELECT OrderID,OrderLineID,StockItemID,Quantity,PickedQuantity,UnpickedUnits FROM analytics.order_lines WHERE ScenarioID='base' AND OrderDate>=DATE '2016-05-01' AND OrderDate<DATE '2016-06-01' AND UnpickedUnits>0 ORDER BY OrderID,OrderLineID").fetchall()
    with (package/'evidence/source_controls/W2_1.csv').open(encoding='utf-8',newline='') as f:source=[tuple(int(r[x]) for x in ['OrderID','OrderLineID','StockItemID','Quantity','PickedQuantity','UnpickedUnits']) for r in csv.DictReader(f)]
    check('sorted_may_evidence',localrows==source,{'source_rows':len(source),'local_rows':len(localrows)})
    check('demo_values',[(r['Quantity'],r['PickedQuantity']) for r in tables['Sales.OrderLines'] if r['OrderID']==73595 and r['StockItemID']==80]==[(120,0)] and holds[80]['QuantityOnHand']==20 and stock[80]['QuantityPerOuter']==12,{'stock_item_id':80,'holding':holds[80]['QuantityOnHand'],'units_per_outer':stock[80]['QuantityPerOuter']})
    with (package/'evidence/source_controls/W1_0.csv').open(encoding='utf-8',newline='') as f:demo=next(csv.DictReader(f))
    check('current_source_demo',int(demo['QuantityOnHand'])==holds[80]['QuantityOnHand'] and int(demo['QuantityPerOuter'])==stock[80]['QuantityPerOuter'] and demo['StockItemName']==stock[80]['StockItemName'],demo)
    with (package/'evidence/source_controls/W3_0.csv').open(encoding='utf-8',newline='') as f:source_items=list(csv.DictReader(f))
    item_demand=collections.defaultdict(int);item_orders=collections.defaultdict(set);item_supply=collections.defaultdict(int)
    for r in under:item_demand[r['StockItemID']]+=r['Quantity']-r['PickedQuantity'];item_orders[r['StockItemID']].add(r['OrderID'])
    for r in incoming:item_supply[r['StockItemID']]+=(r['OrderedOuters']-r['ReceivedOuters'])*stock[r['StockItemID']]['QuantityPerOuter']
    check('sorted_source_item_evidence',len(source_items)==len(item_demand) and all(int(r['UnpickedUnits'])==item_demand[int(r['StockItemID'])] and int(r['Orders'])==len(item_orders[int(r['StockItemID'])]) and int(r['QuantityOnHand'])==holds[int(r['StockItemID'])]['QuantityOnHand'] and int(r['IncomingUnits'])==item_supply[int(r['StockItemID'])] for r in source_items),{'items':len(source_items),'full_item_values_compared':True})
    dates=[r['OrderDate'] for r in orders.values()];check('date_bounds',str(min(dates))==m['business_date_bounds']['start'] and str(max(dates))==m['business_date_bounds']['end_inclusive'],{'min':min(dates),'max':max(dates)})
    check('backorder_direction',orders[73573]['BackorderOrderID']==73595,{'73573_BackorderOrderID':orders[73573]['BackorderOrderID']})
    # Stock-group multi-membership oracle: existence semantics, independently selected item set.
    bridge=tables.get('Warehouse.StockItemStockGroups',[])
    for gid in sorted({r['StockGroupID'] for r in bridge}):
        ids={r['StockItemID'] for r in bridge if r['StockGroupID']==gid};value=sum(r['Quantity']-r['PickedQuantity'] for r in under if r['StockItemID'] in ids)
        local=c.execute("SELECT COALESCE(SUM(UnpickedUnits),0) FROM analytics.order_lines l WHERE l.ScenarioID='base' AND EXISTS(SELECT 1 FROM raw.Warehouse_StockItemStockGroups b WHERE b.StockItemID=l.StockItemID AND b.StockGroupID=?)",[gid]).fetchone()[0];check('group_semijoin_'+str(gid),value==local,{'independent_units':value,'local_units':local})
    # Meaningful typed transport edge cases; not fictitious business records.
    schema=pa.schema([pa.field('id',pa.int64()),pa.field('text',pa.string()),pa.field('amount',pa.decimal128(38,7)),pa.field('time',pa.timestamp('us')),pa.field('ticks',pa.int8()),pa.field('flag',pa.bool_())])
    edge=[{'id':9223372036854775807,'text':'Unicode: \u65e5\u672c, "quote"\nnewline','amount':decimal.Decimal('12345678901234567890.1234567'),'time':datetime.datetime(9999,12,31,23,59,59,999999),'ticks':9,'flag':True},{'id':0,'text':'','amount':decimal.Decimal('0.0000000'),'time':None,'ticks':None,'flag':False},{'id':None,'text':None,'amount':None,'time':None,'ticks':None,'flag':None}]
    test=pa.Table.from_pylist(edge,schema=schema);path=package/'evidence/type_roundtrip.parquet';pq.write_table(test,path);check('type_edge_roundtrip',pq.read_table(path).equals(test),{'null_vs_empty':True,'unicode_newlines_quotes':True,'decimal_exact':True,'int64_max':True,'year9999_100ns':True})
    scenario=package/'data/synthetic/no_incoming_v1/scenario.json'
    if scenario.exists():
        sc=load(scenario);si=sc['stock_item_id'];oid=sc['order_id'];r=c.execute("SELECT UnpickedUnits FROM analytics.order_lines WHERE ScenarioID=? AND OrderID=? AND StockItemID=?",['no_incoming_v1',oid,si]).fetchall();inc=c.execute("SELECT COUNT(*) FROM analytics.incoming WHERE ScenarioID=? AND StockItemID=?",['no_incoming_v1',si]).fetchone()[0];h=c.execute("SELECT QuantityOnHand FROM analytics.holdings WHERE ScenarioID=? AND StockItemID=?",['no_incoming_v1',si]).fetchone()[0]
        check('synthetic_branch',r==[(120,)] and inc==0 and h==20 and si not in stock and oid not in orders,{'units':r,'incoming':inc,'holdings':h,'ids':sc})
        check('base_isolation',c.execute("SELECT COUNT(*) FROM analytics.orders WHERE ScenarioID='base'").fetchone()[0]==len(orders) and c.execute("SELECT SUM(UnpickedUnits) FROM analytics.order_lines WHERE ScenarioID='base'").fetchone()[0]==independent['all']['units'],independent)
    result={'status':'pass' if not failures else 'fail','checks':checks,'failures':failures,'independent_controls':independent,'out_of_export_scope_fks':excluded,'seconds':time.perf_counter()-start,'source_refresh_required':False};save(package/'evidence/parity.json',result);save(package/'evidence/validation_report.json',result);c.close();print(result['status'],len(checks),'checks',flush=True)
    if failures:raise SystemExit(','.join(failures))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);a=p.parse_args();validate(a.package)
