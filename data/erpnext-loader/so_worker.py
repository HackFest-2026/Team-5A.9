"""Extra parallel worker for the sales_orders stage: loads records lo<i<=hi of 12_sales_order. Idempotent (skips existing WWI orders),
so it can overlap with the main loader, which later skips what these workers did. Runs INSIDE the backend container.
Usage: python wwi_load/so_worker.py LO HI"""
import sys,time,traceback
sys.path.insert(0,'wwi_load')
import load_in_container as L
def insert_named(rec):
    # explicit name (SO-WWI-<id>) bypasses the shared naming-series counter, which serialises parallel workers
    if L.existing(rec):return
    for attempt in range(4):
        try:
            d=L.frappe.get_doc(rec);d.flags.ignore_permissions=True;d.insert(set_name=f"SO-WWI-{rec['wwi_order_id']}");d.submit();return
        except (L.frappe.QueryDeadlockError,L.frappe.DoesNotExistError):
            L.frappe.db.rollback()
            if attempt==3:raise
            time.sleep(0.5*(attempt+1))
lo,hi=int(sys.argv[1]),int(sys.argv[2]);name=f'so_worker_{lo}_{hi}'
L.LIMIT=0;L.connect();i=ok=fail=0;t0=time.time()
for rec in L.jsonl('12_sales_order'):
    i+=1
    if i<=lo:continue
    if i>hi:break
    rec['taxes']=L.tax_row();rec['ignore_pricing_rule']=1
    try:insert_named(rec);ok+=1
    except Exception:L.frappe.db.rollback();fail+=1;L.log_failure(name,rec['wwi_order_id'],traceback.format_exc())
    L.frappe.db.commit()
    if i%200==0:print(f'{name} {i} ok={ok} fail={fail} {(ok+fail)/(time.time()-t0):.1f}/s',flush=True)
L.frappe.db.commit();print(f'{name} DONE ok={ok} fail={fail}',flush=True);L.frappe.destroy()
