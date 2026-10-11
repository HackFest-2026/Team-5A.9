"""Runs INSIDE the ERPNext backend container: computes our measures from ERPNext's own tables and writes wwi_load/erp_measures.json."""
import json,frappe
frappe.init(site='frontend',sites_path='.');frappe.connect()
q=lambda sql:frappe.db.sql(sql)
REAL="so.wwi_is_synthetic=0"
out={
 'M01_by_month':{m:int(n) for m,n in q(f"select date_format(so.transaction_date,'%Y-%m'),count(*) from `tabSales Order` so where so.docstatus=1 and {REAL} group by 1")},
 'M13_by_month':{m:float(n) for m,n in q(f"select date_format(so.transaction_date,'%Y-%m'),sum(i.stock_qty) from `tabSales Order Item` i join `tabSales Order` so on so.name=i.parent where so.docstatus=1 and {REAL} group by 1")},
 'M10_by_month':{m:float(n) for m,n in q("select date_format(posting_date,'%Y-%m'),sum(net_total) from `tabSales Invoice` where docstatus=1 group by 1")},
 'tax_total':float(q("select sum(total_taxes_and_charges) from `tabSales Invoice` where docstatus=1")[0][0] or 0),
 'M04_on_hand':{c:float(n) for c,n in q("select item_code,actual_qty from tabBin")},
 'M02_by_item':{c:float(n) for c,n in q(f"select i.item_code,sum(i.stock_qty-i.delivered_qty*i.conversion_factor) from `tabSales Order Item` i join `tabSales Order` so on so.name=i.parent where so.docstatus=1 and {REAL} and so.status not in ('Closed') group by 1")},
 'M05_by_item':{c:float(n) for c,n in q("select i.item_code,sum((i.qty-i.received_qty)*i.conversion_factor) from `tabPurchase Order Item` i join `tabPurchase Order` po on po.name=i.parent where po.docstatus=1 and po.status not in ('Closed','Completed') and i.qty>i.received_qty group by 1")},
 'territory_apr_may':{t:[int(a),int(b)] for t,a,b in q(f"""select tp.parent_territory,
     sum(so.transaction_date between '2016-04-01' and '2016-04-30'),sum(so.transaction_date between '2016-05-01' and '2016-05-31')
     from `tabSales Order` so join tabCustomer c on c.name=so.customer join tabTerritory tp on tp.name=c.territory where so.docstatus=1 and {REAL} group by 1""")},
 'counts':{dt:int(q(f"select count(*) from `tab{dt}` where docstatus=1")[0][0]) for dt in ['Sales Order','Sales Invoice','Purchase Order','Purchase Receipt','Stock Reconciliation']},
 'masters':{dt:int(q(f"select count(*) from `tab{dt}`")[0][0]) for dt in ['Customer','Item','Supplier','Sales Person','Territory','Customer Group','Item Group']},
 'synthetic':[dict(r) for r in frappe.db.sql("""select so.name,so.customer,so.transaction_date,so.status,i.item_code,i.qty,i.delivered_qty,b.actual_qty,b.ordered_qty
     from `tabSales Order` so join `tabSales Order Item` i on i.parent=so.name left join tabBin b on b.item_code=i.item_code where so.wwi_is_synthetic=1""",as_dict=True)],
 'item80':dict(frappe.db.sql("""select b.actual_qty,b.reserved_qty,b.ordered_qty,b.projected_qty from tabBin b where b.item_code='WWI-80'""",as_dict=True)[0]),
}
json.dump(out,open('wwi_load/erp_measures.json','w'),default=str,indent=1);print('measures written',out['counts'])
frappe.destroy()
