"""Independent row oracle for the declared filter domain; no production predicates shared."""
import argparse,pathlib,datetime,collections,hashlib,json,time
from common import save,load
from engine import execute_metric,execute_chart,records
from request_models import Request
def validate(package):
    import pyarrow.parquet as pq
    p=pathlib.Path(package);started=time.perf_counter();checks=[]
    def rows(t):return pq.read_table(p/'data/raw'/f'{t}.parquet').to_pylist()
    orders={r['OrderID']:r for r in rows('Sales.Orders')};items={r['StockItemID']:r for r in rows('Warehouse.StockItems')};holds={r['StockItemID']:r for r in rows('Warehouse.StockItemHoldings')};lines=rows('Sales.OrderLines');bridge=rows('Warehouse.StockItemStockGroups');pol=rows('Purchasing.PurchaseOrderLines');po={r['PurchaseOrderID']:r for r in rows('Purchasing.PurchaseOrders')}
    def check(name,actual,expected):
        ok=actual==expected;checks.append({'name':name,'pass':ok,'actual':actual,'expected':expected})
        if not ok:raise AssertionError(name)
    cases=[{}, {'start':'2016-04-01','end':'2016-05-01'}, {'start':'2016-05-01','end':'2016-06-01'}, {'start':'2016-05-31','end':'2016-06-01'}, {'start':'2016-06-01','end':'2016-06-02'}, {'filters':{'customer_id':11}}, {'filters':{'customer_id':404}}, {'filters':{'stock_item_id':80}}, {'filters':{'stock_item_id':193}}, {'filters':{'supplier_id':4}}, {'filters':{'supplier_id':7}}, {'filters':{'order_id':73595}}, {'filters':{'stock_item_id':999999}}, {'filters':{'status':'quantity-not-yet-picked'}}, {'filters':{'status':'picking-incomplete'}}, {'filters':{'status':'picking-complete'}}]
    cases += [{'filters':{'stock_group_id':g}} for g in sorted({b['StockGroupID'] for b in bridge})]
    cases += [{'start':'2016-05-01','end':'2016-06-01','filters':{'customer_id':11,'stock_item_id':80,'supplier_id':4}}, {'start':'2016-04-01','end':'2016-05-01','filters':{'stock_group_id':1,'supplier_id':7}}]
    for n,case in enumerate(cases):
        f=case.get('filters',{});selected=[]
        for l in lines:
            o=orders[l['OrderID']]
            if case.get('start') and not datetime.date.fromisoformat(case['start'])<=o['OrderDate']<datetime.date.fromisoformat(case['end']):continue
            if f.get('customer_id') is not None and o['CustomerID']!=f['customer_id']:continue
            if f.get('order_id') is not None and o['OrderID']!=f['order_id']:continue
            if f.get('stock_item_id') is not None and l['StockItemID']!=f['stock_item_id']:continue
            if f.get('supplier_id') is not None and items[l['StockItemID']]['SupplierID']!=f['supplier_id']:continue
            if f.get('stock_group_id') is not None and not any(b['StockItemID']==l['StockItemID'] and b['StockGroupID']==f['stock_group_id'] for b in bridge):continue
            status=f.get('status','all')
            if status=='quantity-not-yet-picked' and l['Quantity']<=l['PickedQuantity']:continue
            if status=='picking-incomplete' and o['PickingCompletedWhen'] is not None:continue
            if status=='picking-complete' and o['PickingCompletedWhen'] is None:continue
            selected.append(l)
        expected={'M01':len({l['OrderID'] for l in selected}),'M02':sum(max(l['Quantity']-l['PickedQuantity'],0) for l in selected),'M03':len({l['OrderID'] for l in selected if l['Quantity']>l['PickedQuantity']})}
        r={'date_basis':'order_date',**case}
        for mid,value in expected.items():check(f'{n}_{mid}',execute_metric(p,mid,r)['rows'][0]['value'],value)
        check(f'{n}_monthly_sum',sum(x['value'] for x in execute_chart(p,'monthly-orders',r)['rows']),expected['M01'])
        check(f'{n}_status_sum',sum(x['value'] for x in execute_chart(p,'picking-status',r)['rows']),expected['M01'])
        check(f'{n}_category_sum',sum(x['value'] for x in execute_metric(p,'M12_orders_category',r)['rows']),expected['M01'])
        top=collections.Counter()
        for l in selected:top[l['StockItemID']]+=max(l['Quantity']-l['PickedQuantity'],0)
        wanted=sorted(((k,v) for k,v in top.items() if v>0),key=lambda x:(-x[1],x[0]))[:20]
        check(f'{n}_top_items',[(x['StockItemID'],x['value']) for x in execute_chart(p,'top-unpicked',r)['rows']],wanted)
        actual=records(p,'orders',{**r,'limit':200});check(f'{n}_record_count',actual['total_rows'],expected['M01'])
    for f in [{},{'stock_item_id':80},{'stock_item_id':193},{'supplier_id':4},{'stock_group_id':1}]:
        wanted=sorted(k for k in holds if (not f.get('stock_item_id') or k==f['stock_item_id']) and (not f.get('supplier_id') or items[k]['SupplierID']==f['supplier_id']) and (not f.get('stock_group_id') or any(b['StockItemID']==k and b['StockGroupID']==f['stock_group_id'] for b in bridge)))[:200]
        actual=execute_metric(p,'M04',{'date_basis':'none','filters':f,'limit':200})['rows'];check('holdings_'+str(f),[(r['StockItemID'],r['QuantityOnHand'],r['ReorderLevel']) for r in actual],[(k,holds[k]['QuantityOnHand'],holds[k]['ReorderLevel']) for k in wanted])
    for basis in ['none','purchase_order_date','expected_delivery_date']:
        for f in [{},{'stock_item_id':80},{'stock_item_id':193},{'supplier_id':4},{'purchase_order_id':2074},{'stock_group_id':1}]:
            r={'date_basis':basis,'filters':f};wanted=0
            if basis!='none':r.update(start='2016-05-01',end='2016-06-01')
            for l in pol:
                o=po[l['PurchaseOrderID']];k=l['StockItemID']
                if o['IsOrderFinalized'] or l['IsOrderLineFinalized'] or l['OrderedOuters']<=l['ReceivedOuters']:continue
                if f.get('stock_item_id') and k!=f['stock_item_id']:continue
                if f.get('supplier_id') and o['SupplierID']!=f['supplier_id']:continue
                if f.get('purchase_order_id') and o['PurchaseOrderID']!=f['purchase_order_id']:continue
                if f.get('stock_group_id') and not any(b['StockItemID']==k and b['StockGroupID']==f['stock_group_id'] for b in bridge):continue
                if basis!='none' and not datetime.date(2016,5,1)<=o['OrderDate' if basis=='purchase_order_date' else 'ExpectedDeliveryDate']<datetime.date(2016,6,1):continue
                wanted+=(l['OrderedOuters']-l['ReceivedOuters'])*items[k]['QuantityPerOuter']
            check('incoming_'+str(r),execute_metric(p,'M05',r)['rows'][0]['value'],wanted)
            check('incoming_chart_'+str(r),sum(x['value'] for x in execute_chart(p,'incoming-supplier',r)['rows']),wanted)
    for basis,col in [('picking_completed_time','PickingCompletedWhen'),('expected_delivery_date','ExpectedDeliveryDate')]:
        wanted=sum(o[col] is not None and datetime.date(2016,4,1)<=(o[col].date() if isinstance(o[col],datetime.datetime) else o[col])<datetime.date(2016,5,1) for o in orders.values())
        check('records_'+basis,records(p,'orders',{'date_basis':basis,'start':'2016-04-01','end':'2016-05-01'})['total_rows'],wanted)
    a=records(p,'orders',{'limit':50});b=records(p,'orders',{'limit':50,'offset':50});check('page_nonoverlap',bool({r['OrderID'] for r in a['rows']}&{r['OrderID'] for r in b['rows']}),False);check('stable_page',records(p,'orders',{'limit':50})['rows'],a['rows'])
    for mid,r in [('M01',{'date_basis':'picking_completed_time'}),('M04',{'date_basis':'order_date'}),('M05',{'date_basis':'none','filters':{'customer_id':11}}),('M01',{'filters':{'purchase_order_id':2073}}),('M10',{}),('M01',{'filters':{'stock_item_id':'80'}}),('M01',{'start':'2016-05-01'}),('M01',{'limit':201}),('M01',{'scenario_id':'unknown'}),('M01',{'filters':{'unknown':1}})]:
        try:execute_metric(p,mid,r);raised=False
        except ValueError:raised=True
        check('rejected_'+mid+str(r),raised,True)
    sc=load(p/'data/synthetic/no_incoming_v1/scenario.json');r={'scenario_id':'no_incoming_v1','filters':{'stock_item_id':sc['stock_item_id']}}
    check('fixture_units',execute_metric(p,'M02',r)['rows'][0]['value'],120);check('fixture_incoming',execute_metric(p,'M05',{**r,'date_basis':'none'})['rows'][0]['value'],0)
    check('base_fixture_absent',execute_metric(p,'M02',{'filters':r['filters']})['rows'][0]['value'],0)
    for entity,field,key in [('order_lines','order_line_id','OrderLineID'),('purchase_lines','purchase_line_id','PurchaseOrderLineID')]:
        source=lines if entity=='order_lines' else pol;rid=source[-1][key];rr=records(p,entity,{'date_basis':'order_date' if entity=='order_lines' else 'none','filters':{field:rid}});check('line_detail_'+entity,[x[key] for x in rr['rows']],[rid])
    check('purchase_header_grain',records(p,'purchase_orders',{'date_basis':'none'})['total_rows'],len(po))
    save(p/'evidence/metric_validation.json',{'status':'pass','checks':len(checks),'seconds':time.perf_counter()-started,'oracle':'independent raw Python row iteration; production SQL and validator not used to calculate expectations','tested_inputs':cases,'results':checks,'all_possible_combinations':'not claimed','percent_zero_denominator':'no percentage widget exposed; comparison contract requires null for zero baseline'})
    print('Independent metric validation passed',len(checks),flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);a=ap.parse_args();validate(a.package)
