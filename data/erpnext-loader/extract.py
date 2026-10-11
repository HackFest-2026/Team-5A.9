"""Extract WWI (raw Parquet + synthetic fixture) into ERPNext-shaped JSONL, one file per load stage.

Runs on the host. Output goes to build/; load_in_container.py reads it inside the ERPNext backend container.
Every record keeps its WWI ID in a custom field so ERPNext can be reconciled against the WWI answer key.
"""
from __future__ import annotations
import argparse,json,pathlib
import duckdb

ROOT=pathlib.Path(__file__).resolve().parent
PKG=ROOT.parent/'wwi-package-v2-2026-10-08'
CO='WWI'                       # company abbreviation (warehouse/account suffix)
WH=f'Stores - {CO}'

def item_code(i):return f'WWI-{i}'
def outer_uom(unit,outer,qpo):
    # WWI sometimes uses the same package name for unit and outer (e.g. Each/Each) while a pack holds several units
    if outer!=unit:return outer
    return unit if qpo==1 else f'{outer} outer of {int(qpo)}'

def run(out):
    c=duckdb.connect();R=lambda t:f"read_parquet('{PKG}/data/raw/{t}.parquet')";S=lambda t:f"read_parquet('{PKG}/data/synthetic/no_incoming_v1/{t}.parquet')"
    rows=lambda sql:[dict(zip([d[0] for d in cur.description],r)) for cur in [c.execute(sql)] for r in cur.fetchall()]
    out.mkdir(parents=True,exist_ok=True);counts={}
    def dump(name,recs):
        with open(out/f'{name}.jsonl','w',encoding='utf-8') as f:
            for r in recs:f.write(json.dumps(r,default=str,ensure_ascii=False)+'\n')
        counts[name]=len(recs)

    # ---------- masters ----------
    pk=rows(f"SELECT PackageTypeID AS id,TRIM(PackageTypeName) AS pname FROM {R('Warehouse.PackageTypes')}");pkname={p['id']:p['pname'] for p in pk}
    derived=rows(f"SELECT DISTINCT OuterPackageID,QuantityPerOuter FROM {R('Warehouse.StockItems')} WHERE UnitPackageID=OuterPackageID AND QuantityPerOuter<>1")
    dump('01_uom',[{'doctype':'UOM','uom_name':p['pname'],'must_be_whole_number':1} for p in pk]+
         [{'doctype':'UOM','uom_name':f"{pkname[d['OuterPackageID']]} outer of {int(d['QuantityPerOuter'])}",'must_be_whole_number':1} for d in derived])
    dump('02_customer_group',[{'doctype':'Customer Group','customer_group_name':r['CustomerCategoryName'],'parent_customer_group':'All Customer Groups','is_group':0}
        for r in rows(f"SELECT CustomerCategoryName FROM {R('Sales.CustomerCategories')} ORDER BY CustomerCategoryID")])
    terr=rows(f"SELECT DISTINCT SalesTerritory FROM {R('Application.StateProvinces')} WHERE SalesTerritory IS NOT NULL ORDER BY 1")
    states=rows(f"SELECT StateProvinceID,StateProvinceName,StateProvinceCode,SalesTerritory FROM {R('Application.StateProvinces')} ORDER BY StateProvinceID")
    dump('03_territory',[{'doctype':'Territory','territory_name':f"{t['SalesTerritory']} (territory)",'parent_territory':'All Territories','is_group':1} for t in terr]+
         [{'doctype':'Territory','territory_name':s['StateProvinceName'].strip(),'parent_territory':f"{s['SalesTerritory']} (territory)",'is_group':0,'wwi_state_province_id':s['StateProvinceID']} for s in states])
    dump('04_sales_person',[{'doctype':'Sales Person','sales_person_name':p['FullName'],'parent_sales_person':'Sales Team','is_group':0,'enabled':1,'wwi_person_id':p['PersonID']}
        for p in rows(f"SELECT PersonID,FullName FROM {R('Application.People')} WHERE IsSalesperson ORDER BY PersonID")])
    dump('05_supplier',[{'doctype':'Supplier','supplier_name':s['SupplierName'],'supplier_group':'All Supplier Groups','wwi_supplier_id':s['SupplierID']}
        for s in rows(f"SELECT SupplierID,SupplierName FROM {R('Purchasing.Suppliers')} ORDER BY SupplierID")])
    sg=rows(f"SELECT StockGroupID,StockGroupName FROM {R('Warehouse.StockGroups')} ORDER BY StockGroupID");sgname={g['StockGroupID']:g['StockGroupName'] for g in sg}
    dump('06_item_group',[{'doctype':'Item Group','item_group_name':g['StockGroupName'],'parent_item_group':'All Item Groups','is_group':0} for g in sg])
    dump('07_customer',[{'doctype':'Customer','customer_name':r['CustomerName'].strip(),'customer_type':'Company' if r['BuyingGroupID'] else 'Individual','customer_group':r['CustomerCategoryName'],
        'territory':r['StateProvinceName'].strip(),'wwi_customer_id':r['CustomerID'],'wwi_buying_group':r['BuyingGroupName'],'wwi_bill_to_customer_id':r['BillToCustomerID']}
        for r in rows(f"""SELECT c.CustomerID,c.CustomerName,c.BillToCustomerID,c.BuyingGroupID,cat.CustomerCategoryName,bg.BuyingGroupName,sp.StateProvinceName
            FROM {R('Sales.Customers')} c JOIN {R('Sales.CustomerCategories')} cat USING(CustomerCategoryID) LEFT JOIN {R('Sales.BuyingGroups')} bg USING(BuyingGroupID)
            JOIN {R('Application.Cities')} ci ON ci.CityID=c.DeliveryCityID JOIN {R('Application.StateProvinces')} sp ON sp.StateProvinceID=ci.StateProvinceID ORDER BY c.CustomerID""")])
    groups={}
    for r in rows(f"SELECT StockItemID,StockGroupID FROM {R('Warehouse.StockItemStockGroups')} ORDER BY StockItemID,StockGroupID"):groups.setdefault(r['StockItemID'],[]).append(sgname[r['StockGroupID']])
    def item_rec(r,synthetic=False):
        unit=pkname[r['UnitPackageID']];outer=outer_uom(unit,pkname[r['OuterPackageID']],r['QuantityPerOuter'])
        uoms=[{'uom':unit,'conversion_factor':1}]+([{'uom':outer,'conversion_factor':r['QuantityPerOuter']}] if outer!=unit else [])
        return {'doctype':'Item','item_code':item_code(r['StockItemID']),'item_name':r['StockItemName'][:140],'description':r['StockItemName'],
            'item_group':(groups.get(r['StockItemID']) or ['All Item Groups'])[0],'stock_uom':unit,'uoms':uoms,'purchase_uom':outer,'is_stock_item':1,
            'standard_rate':float(r['UnitPrice']),'valuation_rate':float(r['LastCostPrice'] or 0),
            'item_defaults':[{'company':'Wide World Importers','default_warehouse':WH,'default_supplier':r['SupplierName']}],
            'reorder_levels':[{'warehouse':WH,'warehouse_reorder_level':float(r['ReorderLevel']),'warehouse_reorder_qty':float(max(r['TargetStockLevel']-r['ReorderLevel'],1)),'material_request_type':'Purchase'}],
            'taxes':[{'item_tax_template':f"WWI Tax {int(r['TaxRate'])}% - {CO}"}],
            'wwi_stock_item_id':r['StockItemID'],'wwi_quantity_per_outer':r['QuantityPerOuter'],'wwi_stock_groups':', '.join(groups.get(r['StockItemID'],[])),'wwi_is_synthetic':int(synthetic)}
    itq=lambda src:f"""SELECT s.*,h.ReorderLevel,h.TargetStockLevel,h.LastCostPrice,h.QuantityOnHand,su.SupplierName FROM {src('Warehouse.StockItems' if src==R else 'Warehouse_StockItems')} s
        JOIN {src('Warehouse.StockItemHoldings' if src==R else 'Warehouse_StockItemHoldings')} h USING(StockItemID) JOIN {R('Purchasing.Suppliers')} su ON su.SupplierID=s.SupplierID ORDER BY StockItemID"""
    items=rows(itq(R));syn_items=rows(itq(S))
    dump('08_item',[item_rec(r) for r in items]+[item_rec(r,True) for r in syn_items])

    # ---------- opening stock: back-solved so that the period's flows end at WWI holdings ----------
    rec={r['StockItemID']:r['u'] for r in rows(f"SELECT l.StockItemID,SUM(l.ReceivedOuters*s.QuantityPerOuter) u FROM {R('Purchasing.PurchaseOrderLines')} l JOIN {R('Warehouse.StockItems')} s USING(StockItemID) GROUP BY 1")}
    sold={r['StockItemID']:r['u'] for r in rows(f"SELECT StockItemID,SUM(Quantity) u FROM {R('Sales.InvoiceLines')} GROUP BY 1")}
    opening=[];closing=[]
    for r in items:
        o=r['QuantityOnHand']-rec.get(r['StockItemID'],0)+sold.get(r['StockItemID'],0)
        if o>0:opening.append({'item_code':item_code(r['StockItemID']),'warehouse':WH,'qty':float(o),'valuation_rate':float(r['LastCostPrice'] or 0.01)})
        closing.append({'item_code':item_code(r['StockItemID']),'warehouse':WH,'qty':float(r['QuantityOnHand']),'valuation_rate':float(r['LastCostPrice'] or 0.01)})
    for r in syn_items:closing.append({'item_code':item_code(r['StockItemID']),'warehouse':WH,'qty':float(r['QuantityOnHand']),'valuation_rate':float(r['LastCostPrice'] or 0.01)})
    dump('09_opening_stock',[{'doctype':'Stock Reconciliation','purpose':'Opening Stock','posting_date':'2012-12-31','posting_time':'23:00:00','set_posting_time':1,'items':opening,
        'wwi_note':'Back-solved: WWI holdings minus received plus invoiced units; items whose back-solve is negative start at 0 (WWI simulated flows are inconsistent).'}])

    # ---------- transactions ----------
    po_lines={}
    for l in rows(f"SELECT l.*,s.QuantityPerOuter,s.OuterPackageID,s.UnitPackageID FROM {R('Purchasing.PurchaseOrderLines')} l JOIN {R('Warehouse.StockItems')} s USING(StockItemID) ORDER BY PurchaseOrderLineID"):l['OuterUOM']=outer_uom(pkname[l['UnitPackageID']],pkname[l['OuterPackageID']],l['QuantityPerOuter']);po_lines.setdefault(l['PurchaseOrderID'],[]).append(l)
    sup={s['SupplierID']:s['SupplierName'] for s in rows(f"SELECT SupplierID,SupplierName FROM {R('Purchasing.Suppliers')}")}
    pos=[];prs=[]
    for p in rows(f"SELECT * FROM {R('Purchasing.PurchaseOrders')} ORDER BY OrderDate,PurchaseOrderID"):
        ls=po_lines.get(p['PurchaseOrderID'],[])
        pos.append({'doctype':'Purchase Order','supplier':sup[p['SupplierID']],'transaction_date':p['OrderDate'],'schedule_date':p['ExpectedDeliveryDate'],'set_warehouse':WH,
            'wwi_purchase_order_id':p['PurchaseOrderID'],'wwi_is_finalized':int(p['IsOrderFinalized']),
            'items':[{'item_code':item_code(l['StockItemID']),'qty':float(l['OrderedOuters']),'uom':l['OuterUOM'],'conversion_factor':float(l['QuantityPerOuter']),
                'rate':float(l['ExpectedUnitPricePerOuter'] or 0),'schedule_date':p['ExpectedDeliveryDate'],'warehouse':WH,'wwi_purchase_order_line_id':l['PurchaseOrderLineID']} for l in ls]})
        bydate={}
        for l in ls:
            if l['ReceivedOuters']>0:bydate.setdefault(l['LastReceiptDate'],[]).append(l)
        for d,dl in sorted(bydate.items()):
            prs.append({'doctype':'Purchase Receipt','supplier':sup[p['SupplierID']],'posting_date':d,'posting_time':'08:00:00','set_posting_time':1,'set_warehouse':WH,'wwi_purchase_order_id':p['PurchaseOrderID'],
                'items':[{'item_code':item_code(l['StockItemID']),'qty':float(l['ReceivedOuters']),'uom':l['OuterUOM'],'conversion_factor':float(l['QuantityPerOuter']),
                    'rate':float(l['ExpectedUnitPricePerOuter'] or 0),'warehouse':WH,'wwi_purchase_order_line_id':l['PurchaseOrderLineID']} for l in dl]})
    dump('10_purchase_order',pos);dump('11_purchase_receipt',prs)

    cust={r['CustomerID']:r['CustomerName'].strip() for r in rows(f"SELECT CustomerID,CustomerName FROM {R('Sales.Customers')}")}
    sp={r['PersonID']:r['FullName'] for r in rows(f"SELECT PersonID,FullName FROM {R('Application.People')} WHERE IsSalesperson")}
    tax={r['StockItemID']:int(r['TaxRate']) for r in items+syn_items}
    def so_records(orders_sql,lines_sql,synthetic=False):
        lines={}
        for l in rows(lines_sql):lines.setdefault(l['OrderID'],[]).append(l)
        return [{'doctype':'Sales Order','customer':cust[o['CustomerID']],'transaction_date':o['OrderDate'],'delivery_date':o['ExpectedDeliveryDate'],'set_warehouse':WH,
            'sales_team':[{'sales_person':sp[o['SalespersonPersonID']],'allocated_percentage':100}],'po_no':o['CustomerPurchaseOrderNumber'],
            'wwi_order_id':o['OrderID'],'wwi_backorder_order_id':o['BackorderOrderID'],'wwi_is_synthetic':int(synthetic),
            'items':[{'item_code':item_code(l['StockItemID']),'qty':float(l['Quantity']),'rate':float(l['UnitPrice']),'delivery_date':o['ExpectedDeliveryDate'],'warehouse':WH,
                'item_tax_template':f"WWI Tax {int(l['TaxRate'])}% - {CO}",'wwi_order_line_id':l['OrderLineID'],'wwi_picked_quantity':float(l['PickedQuantity'])} for l in lines[o['OrderID']]]}
            for o in rows(orders_sql)]
    dump('12_sales_order',so_records(f"SELECT * FROM {R('Sales.Orders')} ORDER BY OrderDate,OrderID",f"SELECT * FROM {R('Sales.OrderLines')} ORDER BY OrderLineID"))
    inv_lines={}
    for l in rows(f"SELECT * FROM {R('Sales.InvoiceLines')} ORDER BY InvoiceLineID"):inv_lines.setdefault(l['InvoiceID'],[]).append(l)
    dump('13_sales_invoice',[{'doctype':'Sales Invoice','customer':cust[i['CustomerID']],'posting_date':i['InvoiceDate'],'posting_time':'17:00:00','set_posting_time':1,'update_stock':1,'set_warehouse':WH,
        'sales_team':[{'sales_person':sp[i['SalespersonPersonID']],'allocated_percentage':100}],'wwi_invoice_id':i['InvoiceID'],'wwi_order_id':i['OrderID'],
        'items':[{'item_code':item_code(l['StockItemID']),'qty':float(l['Quantity']),'rate':float(l['UnitPrice']),'warehouse':WH,'item_tax_template':f"WWI Tax {int(l['TaxRate'])}% - {CO}",
            'wwi_invoice_line_id':l['InvoiceLineID'],'wwi_line_profit':float(l['LineProfit']),'wwi_tax_amount':float(l['TaxAmount'])} for l in inv_lines[i['InvoiceID']]]}
        for i in rows(f"SELECT * FROM {R('Sales.Invoices')} ORDER BY InvoiceDate,InvoiceID")])
    dump('14_closing_stock',[{'doctype':'Stock Reconciliation','purpose':'Stock Reconciliation','posting_date':'2016-05-31','posting_time':'23:59:00','set_posting_time':1,'items':closing,
        'wwi_note':'Sets every item to WWI StockItemHoldings.QuantityOnHand (stored state at archive end), correcting simulated-flow inconsistencies.'}])
    dump('15_synthetic_sales_order',so_records(f"SELECT * FROM {S('Sales_Orders')}",f"SELECT * FROM {S('Sales_OrderLines')}",True))
    (out/'counts.json').write_text(json.dumps(counts,indent=1));print(json.dumps(counts,indent=1))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',default=str(ROOT/'build'));a=ap.parse_args();run(pathlib.Path(a.out))
