"""Load specific sales invoices that the main stock_flow stage missed. Runs INSIDE the backend container.
Usage: python wwi_load/load_missing_invoices.py ID [ID ...]   (same Sales Order linking as stock_flow; idempotent)"""
import sys,time,traceback
sys.path.insert(0,'wwi_load')
import load_in_container as L
L.LIMIT=0;L.connect();want={int(x) for x in sys.argv[1:]}
so_items={}
for r in L.frappe.db.sql("select i.name,i.parent,i.item_code,i.wwi_picked_quantity,s.wwi_order_id from `tabSales Order Item` i join `tabSales Order` s on s.name=i.parent where s.docstatus=1 order by i.idx",as_dict=True):
    so_items.setdefault((r.wwi_order_id,r.item_code),[]).append(r)
recs=sorted([r for r in L.jsonl('13_sales_invoice') if r['wwi_invoice_id'] in want],key=lambda r:(r['posting_date'],r['posting_time']))
print(len(recs),'invoices to load',flush=True)
for rec in recs:
    t=time.time()
    try:
        rec['taxes']=L.tax_row();rec['ignore_pricing_rule']=1;out=[]
        for it in rec['items']:
            rows=so_items.get((rec['wwi_order_id'],it['item_code']),[]);remaining=it['qty']
            for r in rows:
                take=min(remaining,(r.wwi_picked_quantity or 0)-(r.get('_used') or 0))
                if take<=0:continue
                r['_used']=(r.get('_used') or 0)+take;remaining-=take
                out.append({**it,'qty':take,'sales_order':r.parent,'so_detail':r.name})
                if remaining<=0:break
            if remaining>0:out.append({**it,'qty':remaining})
        rec['items']=out;n=L.insert(rec,True);L.frappe.db.commit();print('OK',rec['wwi_invoice_id'],rec['posting_date'],n,f'{time.time()-t:.1f}s',flush=True)
    except Exception:
        L.frappe.db.rollback();print('FAIL',rec['wwi_invoice_id'],traceback.format_exc()[-600:],flush=True)
L.frappe.destroy();print('DONE',flush=True)
