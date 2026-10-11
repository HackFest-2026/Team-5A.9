from __future__ import annotations
import argparse,pathlib,datetime
from common import save,load,db,sha
def make(package,scenario):
    import pyarrow as pa,pyarrow.parquet as pq
    p=pathlib.Path(package).resolve()
    if scenario!='no_incoming_v1':raise ValueError('Exactly one scenario is supported')
    if load(p/'manifest.json').get('p1_status')!='pass':raise ValueError('P1 acceptance required before P2 fixture')
    c=db(p);base=p/'data/raw';out=p/'data/synthetic'/scenario;out.mkdir(parents=True,exist_ok=True)
    ids={'stock_item_id':c.execute('SELECT MAX(StockItemID)+1000 FROM raw.Warehouse_StockItems').fetchone()[0],'order_id':c.execute('SELECT MAX(OrderID)+1000 FROM raw.Sales_Orders').fetchone()[0],'order_line_id':c.execute('SELECT MAX(OrderLineID)+1000 FROM raw.Sales_OrderLines').fetchone()[0]}
    sources={t:pq.read_table(base/(t+'.parquet')).to_pylist() for t in ['Warehouse.StockItems','Warehouse.StockItemHoldings','Sales.Orders','Sales.OrderLines']}
    rows={t:next(r for r in rr if r[{'Warehouse.StockItems':'StockItemID','Warehouse.StockItemHoldings':'StockItemID','Sales.Orders':'OrderID','Sales.OrderLines':'OrderLineID'}[t]]=={'Warehouse.StockItems':80,'Warehouse.StockItemHoldings':80,'Sales.Orders':73595,'Sales.OrderLines':231360}[t]) for t,rr in sources.items()}
    rows['Warehouse.StockItems'].update(StockItemID=ids['stock_item_id'],StockItemName='SYNTHETIC investigation item — no incoming supply')
    rows['Warehouse.StockItemHoldings'].update(StockItemID=ids['stock_item_id'],QuantityOnHand=20,BinLocation='SYNTHETIC',ReorderLevel=5,TargetStockLevel=20)
    rows['Sales.Orders'].update(OrderID=ids['order_id'],BackorderOrderID=None,OrderDate=datetime.date(2016,5,31),ExpectedDeliveryDate=datetime.date(2016,6,1),PickingCompletedWhen=None,Comments='SYNTHETIC fixture; not a source order')
    rows['Sales.OrderLines'].update(OrderID=ids['order_id'],OrderLineID=ids['order_line_id'],StockItemID=ids['stock_item_id'],Quantity=120,PickedQuantity=0,PickingCompletedWhen=None,Description='SYNTHETIC no-incoming branch')
    for t,row in rows.items():
        schema=pq.read_schema(base/(t+'.parquet'));schema=schema.append(pa.field('ScenarioID',pa.string())).append(pa.field('IsSynthetic',pa.bool_()));row.update(ScenarioID=scenario,IsSynthetic=True);pq.write_table(pa.Table.from_pylist([row],schema=schema),out/(t.replace('.','_')+'.parquet'),compression='zstd')
    save(out/'scenario.json',{'scenario_id':scenario,'version':'1.0.0','seed':0,'synthetic':True,**ids,'linked_source_ids':{'customer_id':11,'supplier_id':4,'unit_package_id':7,'outer_package_id':6},'expected':{'unpicked_units':120,'stored_holdings_units':20,'qualifying_incoming_pos':0},'scope':'fixture business records only; verified source customer/supplier/package lookups reused; base charts unchanged','prohibited_inference':'no supplier-delay reason, customer allocation or physical fulfillment guarantee'})
    c.close();print('Scenario created',ids,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--scenario',required=True);a=p.parse_args();make(a.package,a.scenario)
