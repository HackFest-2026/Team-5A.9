"""v2 build step: run after build_local.py. Adds analysis views and the entity name index.

Only adds objects in schema analytics; raw/synthetic tables and v1 views are untouched.
"""
from __future__ import annotations
import argparse,pathlib,re,time
from common import save,db

CUSTOMER_DIM="""CREATE OR REPLACE VIEW analytics.customer_dim AS
SELECT c.CustomerID,c.CustomerName,c.BillToCustomerID,c.CustomerCategoryID,cat.CustomerCategoryName,
       c.BuyingGroupID,bg.BuyingGroupName,c.DeliveryCityID,ci.CityName DeliveryCityName,
       sp.StateProvinceID,sp.StateProvinceCode,sp.StateProvinceName,sp.SalesTerritory
FROM raw.Sales_Customers c
LEFT JOIN raw.Sales_CustomerCategories cat ON cat.CustomerCategoryID=c.CustomerCategoryID
LEFT JOIN raw.Sales_BuyingGroups bg ON bg.BuyingGroupID=c.BuyingGroupID
LEFT JOIN raw.Application_Cities ci ON ci.CityID=c.DeliveryCityID
LEFT JOIN raw.Application_StateProvinces sp ON sp.StateProvinceID=ci.StateProvinceID"""

# Order lines with current customer attributes, salesperson and the item's nominated supplier.
ORDER_LINES_V2="""CREATE OR REPLACE VIEW analytics.order_lines_v2 AS
SELECT l.*,o.SalespersonPersonID,p.FullName SalespersonName,
       cd.CustomerName,cd.CustomerCategoryID,cd.CustomerCategoryName,cd.BuyingGroupID,cd.BuyingGroupName,
       cd.StateProvinceID,cd.StateProvinceName,cd.SalesTerritory,
       s.StockItemName,s.SupplierID,su.SupplierName
FROM analytics.order_lines l
JOIN analytics.orders o ON o.OrderID=l.OrderID AND o.ScenarioID=l.ScenarioID
LEFT JOIN raw.Application_People p ON p.PersonID=o.SalespersonPersonID
LEFT JOIN analytics.customer_dim cd ON cd.CustomerID=l.CustomerID
LEFT JOIN analytics.items s ON s.StockItemID=l.StockItemID AND s.ScenarioID=l.ScenarioID
LEFT JOIN raw.Purchasing_Suppliers su ON su.SupplierID=s.SupplierID"""

INVOICE_LINES_V2="""CREATE OR REPLACE VIEW analytics.invoice_lines_v2 AS
SELECT 'base' ScenarioID,FALSE IsSynthetic,i.InvoiceID,il.InvoiceLineID,i.InvoiceDate,i.OrderID,i.CustomerID,
       i.SalespersonPersonID,p.FullName SalespersonName,il.StockItemID,s.StockItemName,s.SupplierID,su.SupplierName,
       il.Quantity,il.ExtendedPrice-il.TaxAmount SalesExTax,il.LineProfit,il.TaxAmount,il.ExtendedPrice,
       cd.CustomerName,cd.CustomerCategoryID,cd.CustomerCategoryName,cd.BuyingGroupID,cd.BuyingGroupName,
       cd.StateProvinceID,cd.StateProvinceName,cd.SalesTerritory
FROM raw.Sales_Invoices i
JOIN raw.Sales_InvoiceLines il ON il.InvoiceID=i.InvoiceID
LEFT JOIN raw.Application_People p ON p.PersonID=i.SalespersonPersonID
LEFT JOIN raw.Warehouse_StockItems s ON s.StockItemID=il.StockItemID
LEFT JOIN raw.Purchasing_Suppliers su ON su.SupplierID=s.SupplierID
LEFT JOIN analytics.customer_dim cd ON cd.CustomerID=i.CustomerID"""

# Same predicate as v1 analytics.incoming; adds names. SupplierID here is the purchase order's actual supplier.
INCOMING_V2="""CREATE OR REPLACE VIEW analytics.incoming_v2 AS
SELECT i.*,s.StockItemName,su.SupplierName FROM analytics.incoming i
JOIN raw.Warehouse_StockItems s ON s.StockItemID=i.StockItemID
JOIN raw.Purchasing_Suppliers su ON su.SupplierID=i.SupplierID"""

LEGAL=re.compile(r',?\s*\b(inc|ltd|llc|corporation|corp|company|co)\.?$',re.I)
def norm(text):
    text=str(text).casefold().replace('&',' and ')
    text=re.sub(r'[^\w\s]',' ',text)
    return ' '.join(text.split())
def singular(word):
    return word[:-1] if len(word)>3 and word.endswith('s') and not word.endswith('ss') else word

def entity_rows(c):
    rows=[]
    def add(etype,eid,name,aliases=(),detail=None):
        names={norm(name)}|{norm(a) for a in aliases if a}
        names|={' '.join(singular(w) for w in n.split()) for n in list(names)}
        for alias in sorted(n for n in names if n):
            rows.append((etype,str(eid),name,alias,detail))
    for cid,name,city,state in c.execute("SELECT CustomerID,CustomerName,DeliveryCityName,StateProvinceCode FROM analytics.customer_dim").fetchall():
        aliases=[re.sub(r'[()]',' ',name)]
        add('customer',cid,name,aliases,f'{city}, {state}')
    for iid,name in c.execute("SELECT StockItemID,StockItemName FROM raw.Warehouse_StockItems").fetchall():
        add('stock_item',iid,name)
    for sid,name in c.execute("SELECT SupplierID,SupplierName FROM raw.Purchasing_Suppliers").fetchall():
        add('supplier',sid,name,[LEGAL.sub('',name)])
    for kid,name in c.execute("SELECT CustomerCategoryID,CustomerCategoryName FROM raw.Sales_CustomerCategories").fetchall():
        add('customer_category',kid,name)
    for bid,name in c.execute("SELECT BuyingGroupID,BuyingGroupName FROM raw.Sales_BuyingGroups").fetchall():
        add('buying_group',bid,name)
    for gid,name in c.execute("SELECT StockGroupID,StockGroupName FROM raw.Warehouse_StockGroups").fetchall():
        add('stock_group',gid,name)
    for pid,name,code,terr in c.execute("SELECT StateProvinceID,StateProvinceName,StateProvinceCode,SalesTerritory FROM raw.Application_StateProvinces").fetchall():
        add('state_province',pid,name,[code],terr)
    for (terr,) in c.execute("SELECT DISTINCT SalesTerritory FROM raw.Application_StateProvinces WHERE SalesTerritory IS NOT NULL").fetchall():
        add('sales_territory',terr,terr,[terr+' territory',terr+' region'])
    for pid,name,pref in c.execute("SELECT PersonID,FullName,PreferredName FROM raw.Application_People WHERE IsSalesperson").fetchall():
        add('salesperson',pid,name,[pref],'salesperson')
    return rows

def build(package):
    package=pathlib.Path(package).resolve();start=time.perf_counter();c=db(package,readonly=False)
    for sql in [CUSTOMER_DIM,ORDER_LINES_V2,INVOICE_LINES_V2,INCOMING_V2]:c.execute(sql)
    rows=entity_rows(c)
    c.execute('CREATE OR REPLACE TABLE analytics.entity_index(entity_type VARCHAR,entity_id VARCHAR,name VARCHAR,alias VARCHAR,detail VARCHAR)')
    c.connection.executemany('INSERT INTO analytics.entity_index VALUES (?,?,?,?,?)',rows)
    counts=dict(c.execute('SELECT entity_type,COUNT(DISTINCT entity_id) FROM analytics.entity_index GROUP BY 1 ORDER BY 1').fetchall())
    c.execute('CHECKPOINT');c.close()
    save(package/'evidence/build_v2.json',{'status':'pass','seconds':time.perf_counter()-start,'views':['analytics.customer_dim','analytics.order_lines_v2','analytics.invoice_lines_v2','analytics.incoming_v2'],'entity_index_rows':len(rows),'entities_by_type':counts})
    print('v2 analysis views and entity index built',counts,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);a=p.parse_args();build(a.package)
