from __future__ import annotations
import argparse,pathlib,time
from common import save,load,sha,db
def build(package):
    import duckdb,pyarrow.parquet as pq
    package=pathlib.Path(package).resolve();start=time.perf_counter();m=load(package/'manifest.json')
    c=db(package,readonly=False)
    for s in ['raw','analytics','synthetic']:c.execute(f'CREATE SCHEMA IF NOT EXISTS {s}')
    for f in m['files']:
        name=f['table'].replace('.','_');p=package/f['path']
        if sha(p)!=f['sha256']:raise ValueError('Raw checksum mismatch: '+f['path'])
        c.execute(f'CREATE OR REPLACE TABLE raw."{name}" AS SELECT * FROM read_parquet(?)',[str(p)])
    for table in ['Sales_Orders','Sales_OrderLines','Warehouse_StockItems','Warehouse_StockItemHoldings']:
        files=sorted((package/'data/synthetic').glob('*/'+table+'.parquet')) if (package/'data/synthetic').exists() else []
        if files:c.execute(f'CREATE OR REPLACE TABLE synthetic."{table}" AS SELECT * FROM read_parquet(?)',[[str(f) for f in files]])
        else:c.execute(f'CREATE OR REPLACE TABLE synthetic."{table}" AS SELECT *,CAST(NULL AS VARCHAR) ScenarioID,CAST(NULL AS BOOLEAN) IsSynthetic FROM raw."{table}" WHERE FALSE')
    c.execute("""CREATE OR REPLACE VIEW analytics.orders AS SELECT *, 'base' ScenarioID, FALSE IsSynthetic FROM raw.Sales_Orders UNION ALL BY NAME SELECT * FROM synthetic.Sales_Orders""")
    c.execute("""CREATE OR REPLACE VIEW analytics.lines AS SELECT *, 'base' ScenarioID,FALSE IsSynthetic FROM raw.Sales_OrderLines UNION ALL BY NAME SELECT * FROM synthetic.Sales_OrderLines""")
    c.execute("""CREATE OR REPLACE VIEW analytics.items AS SELECT *,'base' ScenarioID,FALSE IsSynthetic FROM raw.Warehouse_StockItems UNION ALL BY NAME SELECT * FROM synthetic.Warehouse_StockItems""")
    c.execute("""CREATE OR REPLACE VIEW analytics.holdings AS SELECT *,'base' ScenarioID,FALSE IsSynthetic FROM raw.Warehouse_StockItemHoldings UNION ALL BY NAME SELECT * FROM synthetic.Warehouse_StockItemHoldings""")
    c.execute("""CREATE OR REPLACE VIEW analytics.order_lines AS SELECT o.ScenarioID,o.IsSynthetic,o.OrderID,o.CustomerID,o.OrderDate,o.ExpectedDeliveryDate,o.PickingCompletedWhen OrderPickingCompletedWhen,o.BackorderOrderID,l.OrderLineID,l.StockItemID,l.Quantity,l.PickedQuantity,l.PickingCompletedWhen LinePickingCompletedWhen,GREATEST(CAST(l.Quantity AS BIGINT)-l.PickedQuantity,0) UnpickedUnits,l.PackageTypeID,l.UnitPrice FROM analytics.orders o JOIN analytics.lines l ON l.OrderID=o.OrderID AND l.ScenarioID=o.ScenarioID""")
    c.execute("""CREATE OR REPLACE VIEW analytics.incoming AS SELECT 'base' ScenarioID,FALSE IsSynthetic,p.PurchaseOrderID,l.PurchaseOrderLineID,l.StockItemID,p.SupplierID,p.OrderDate PurchaseOrderDate,p.ExpectedDeliveryDate,l.OrderedOuters,l.ReceivedOuters,s.QuantityPerOuter,(CAST(l.OrderedOuters AS BIGINT)-l.ReceivedOuters)*s.QuantityPerOuter IncomingUnits FROM raw.Purchasing_PurchaseOrders p JOIN raw.Purchasing_PurchaseOrderLines l USING(PurchaseOrderID) JOIN raw.Warehouse_StockItems s USING(StockItemID) WHERE NOT p.IsOrderFinalized AND NOT l.IsOrderLineFinalized AND l.OrderedOuters>l.ReceivedOuters""")
    c.execute("""CREATE OR REPLACE TABLE analytics.calendar AS SELECT CAST(d AS DATE) AS "Date",strftime(d,'%Y-%m') AS "Month" FROM generate_series(DATE '2013-01-01',DATE '2016-06-20',INTERVAL 1 DAY) t(d)""")
    c.execute('CHECKPOINT');c.close();save(package/'evidence/build.json',{'status':'pass','seconds':time.perf_counter()-start,'database_bytes':(package/'data/wwi.duckdb').stat().st_size,'raw_transport_bytes':sum((package/f['path']).stat().st_size for f in m['files']),'paths':'materialized tables; Parquet needed only for explicit rebuild; no absolute-path data views'})
    print('Local database built',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);a=p.parse_args();build(a.package)
