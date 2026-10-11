"""Scoped comparison: ERPNext (loaded through the cut date) vs WWI raw Parquet, with every expected value derived from the raw files as of the cut date.
Usage: python reconcile_feb2016.py [--cut 2016-02-24]   (needs build/erp_measures.json from erp_measures.py)"""
import argparse,json,pathlib,duckdb
ROOT=pathlib.Path(__file__).resolve().parent;RAW=ROOT.parent/'wwi-package-v2-2026-10-08/data/raw'
ap=argparse.ArgumentParser();ap.add_argument('--cut',default='2016-02-24');ap.add_argument('--erp',default=str(ROOT/'build/erp_measures.json'));a=ap.parse_args()
e=json.load(open(a.erp));cut=a.cut;c=duckdb.connect();R=lambda t:f"read_parquet('{RAW}/{t}.parquet')"
res=[]
def chk(name,ok,erp,exp,note=''):res.append(ok);print('PASS' if ok else 'FAIL',name,'' if ok else f'erp={erp} expected={exp} {note}')
q=lambda s:c.execute(s).fetchall()
# invoices through the cut
inv=q(f"select count(*) from {R('Sales.Invoices')} where InvoiceDate<='{cut}'")[0][0]
last=q(f"select count(*) from {R('Sales.Invoices')} where InvoiceDate='{cut}'")[0][0]
chk(f'Sales invoices through {cut} ({last} invoices dated on the cut day)',e['counts']['Sales Invoice']==inv,e['counts']['Sales Invoice'],inv)
prs=q(f"select count(*) from (select PurchaseOrderID,LastReceiptDate from {R('Purchasing.PurchaseOrderLines')} where ReceivedOuters>0 and LastReceiptDate<='{cut}' group by 1,2)")[0][0]
chk('Purchase receipts through the cut',e['counts']['Purchase Receipt']==prs,e['counts']['Purchase Receipt'],prs)
chk('Sales orders (all, + 1 synthetic)',e['counts']['Sales Order']==73596,e['counts']['Sales Order'],73596)
chk('Purchase orders (all)',e['counts']['Purchase Order']==2074,e['counts']['Purchase Order'],2074)
# M10 monthly, net of tax
w={m:float(v) for m,v in q(f"select strftime(i.InvoiceDate,'%Y-%m'),sum(l.ExtendedPrice-l.TaxAmount) from {R('Sales.InvoiceLines')} l join {R('Sales.Invoices')} i using(InvoiceID) where i.InvoiceDate<='{cut}' group by 1")}
bad={m:(round(e['M10_by_month'].get(m,0),2),round(v,2)) for m,v in w.items() if abs(e['M10_by_month'].get(m,0)-v)>0.005}
chk(f'M10 invoiced sales before tax, {len(w)} months',not bad,len(bad),0,f'months differing (erp,wwi): {bad}')
tot_e=sum(e['M10_by_month'].values());tot_w=sum(w.values());chk('M10 total through the cut',abs(tot_e-tot_w)<0.01*len(w),round(tot_e,2),round(tot_w,2),f'diff {tot_e-tot_w:.2f}')
# M02 units still to pick at the cut = history total + units invoiced after the cut
base={k:v for k,v in q(f"select StockItemID,sum(Quantity-PickedQuantity) from {R('Sales.OrderLines')} group by 1")}
after={k:float(v) for k,v in q(f"select l.StockItemID,sum(l.Quantity) from {R('Sales.InvoiceLines')} l join {R('Sales.Invoices')} i using(InvoiceID) where i.InvoiceDate>'{cut}' group by 1")}
exp02={f'WWI-{k}':float(base.get(k,0))+after.get(k,0) for k in set(base)|set(after)}
got02={k:v for k,v in e['M02_by_item'].items() if k!='WWI-1227' and abs(v)>1e-9}
bad=[k for k in set(exp02)|set(got02) if abs(exp02.get(k,0)-got02.get(k,0))>0.0001 and abs(exp02.get(k,0))>1e-9 or abs(got02.get(k,0))>1e-9 and abs(exp02.get(k,0)-got02.get(k,0))>0.0001]
chk('M02 units still to pick at the cut, per item',not bad,len(bad),0,f'differing items: {bad[:6]} total erp={sum(got02.values()):.0f} expected={sum(exp02.values()):.0f}')
# M05 units on order at the cut
rows=q(f"select StockItemID,(OrderedOuters-ReceivedOuters)*QuantityPerOuter open_now, ReceivedOuters*QuantityPerOuter rec, LastReceiptDate, IsOrderLineFinalized, OrderedOuters>ReceivedOuters gt, p.IsOrderFinalized from {R('Purchasing.PurchaseOrderLines')} l join {R('Purchasing.PurchaseOrders')} p using(PurchaseOrderID) join (select StockItemID,QuantityPerOuter from {R('Warehouse.StockItems')}) s using(StockItemID)")
exp05={}
for sid,op,rec,lrd,lf,gt,pf in rows:
    v=0
    if gt and not lf and not pf:v+=float(op)
    if rec and lrd and str(lrd)>cut:v+=float(rec)
    if v:exp05[f'WWI-{sid}']=exp05.get(f'WWI-{sid}',0)+v
got05={k:v for k,v in e['M05_by_item'].items() if k!='WWI-1227' and abs(v)>1e-9}
bad=[k for k in set(exp05)|set(got05) if abs(exp05.get(k,0)-got05.get(k,0))>0.0001]
chk('M05 units on order at the cut, per item',not bad,len(bad),0,f'differing items: {bad[:6]} total erp={sum(got05.values()):.0f} expected={sum(exp05.values()):.0f}')
print(f'\n{sum(res)} passed, {len(res)-sum(res)} failed (cut {cut})')
