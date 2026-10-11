"""Compare ERPNext's measures (erp_measures.json, produced inside the container) with the independent WWI oracle.

Usage (host): python reconcile.py --erp build/erp_measures.json
Writes evidence/reconciliation.json and prints a pass/fail summary.
"""
from __future__ import annotations
import argparse,json,pathlib,sys
from decimal import Decimal
ROOT=pathlib.Path(__file__).resolve().parent;PKG=ROOT.parent/'wwi-package-v2-2026-10-08'
sys.path.insert(0,str(PKG/'scripts'))
from oracle_v2 import Oracle   # independent implementation over raw Parquet (never imports the engine)
import duckdb

def main(erp_path):
    e=json.load(open(erp_path));o=Oracle(PKG);checks=[]
    def check(name,got,exp,tol=0.0,note=None):
        ok=(abs(float(got)-float(exp))<=tol) if isinstance(exp,(int,float,Decimal,str)) and not isinstance(exp,dict) else got==exp
        checks.append({'check':name,'pass':bool(ok),'erpnext':got,'wwi_oracle':exp,'note':note});return ok
    full={'start':'2013-01-01','end':'2016-06-01'}
    def by_month(mid):
        r=o.analyze({'measure_id':mid,'group_by':'month','top_n':50,**full})
        return {row['key']:row['value'] for row in r['rows'] if not str(row['label']).startswith('All others')}
    for mid,key,tol in [('M01','M01_by_month',0),('M13','M13_by_month',0),('M10','M10_by_month',0.005)]:
        w=by_month(mid);g=e[key];bad=[m for m in w if abs(float(g.get(m,0))-float(w[m]))>tol]
        check(f'{mid} monthly ({len(w)} months)',len(bad),0,note=f'months differing: {bad[:6]}')
        check(f'{mid} total',round(sum(float(v) for v in g.values()),2),round(sum(float(v) for v in w.values()),2),tol*len(w)+0.001)
    c=duckdb.connect();R=lambda t:f"read_parquet('{PKG}/data/raw/{t}.parquet')"
    hold={f'WWI-{i}':q for i,q in c.execute(f"SELECT StockItemID,QuantityOnHand FROM {R('Warehouse.StockItemHoldings')}").fetchall()}
    hold['WWI-1227']=20
    bad=[k for k,v in hold.items() if abs(e['M04_on_hand'].get(k,0)-v)>0.0001]
    check('M04 stock on hand per item (228 items)',len(bad),0,note=f'differing: {bad[:6]}')
    for mid,key in [('M02','M02_by_item'),('M05','M05_by_item')]:
        r=o.analyze({'measure_id':mid,'group_by':'stock_item','top_n':50,**({'date_basis':'none'} if mid=='M05' else {})})
        total=o.analyze({'measure_id':mid,**({'date_basis':'none'} if mid=='M05' else {})})['total']
        g={k:v for k,v in e[key].items() if k!='WWI-1227' and abs(v)>1e-9}
        check(f'{mid} total (all history, real data)',round(sum(g.values())),int(total))
        top={f"WWI-{row['key']}":row['value'] for row in r['rows'] if row.get('key') is not None and not row.get('is_other') and not str(row['label']).startswith('All others')}
        bad=[k for k,v in top.items() if abs(g.get(k,0)-v)>0.0001]
        check(f'{mid} per item (top {len(top)})',len(bad),0,note=f'differing: {bad[:6]}')
    ta=e['territory_apr_may'];gl=ta.get('Great Lakes (territory)',[0,0])
    check('Story: May vs April orders +96',sum(v[1] for v in ta.values())-sum(v[0] for v in ta.values()),96)
    check('Story: Great Lakes +65',gl[1]-gl[0],65)
    i80=e['item80'];check('Story: item 80 on hand',i80['actual_qty'],20);check('Story: item 80 on order (units)',i80['ordered_qty'],21972)
    syn=e['synthetic'];check('Synthetic: one flagged sales order for WWI-1227, 120 to deliver, 20 on hand, 0 on order',
        [(s['item_code'],float(s['qty']),float(s['delivered_qty']),float(s['actual_qty'] or 0),float(s['ordered_qty'] or 0)) for s in syn],[('WWI-1227',120.0,0.0,20.0,0.0)])
    check('Counts: sales orders',e['counts']['Sales Order'],73596,note='73,595 WWI + 1 synthetic')
    check('Counts: sales invoices',e['counts']['Sales Invoice'],70510)
    check('Counts: purchase orders',e['counts']['Purchase Order'],2074)
    check('Counts: purchase receipts',e['counts']['Purchase Receipt'],2072)
    wtax=float(c.execute(f"SELECT SUM(TaxAmount) FROM {R('Sales.InvoiceLines')}").fetchone()[0])
    checks.append({'check':'Tax total (informational)','pass':None,'erpnext':e['tax_total'],'wwi_oracle':wtax,'note':'ERPNext rounds tax per invoice, WWI per line; cents differ by design'})
    checks.append({'check':'M11 recorded profit','pass':None,'note':'Not comparable: ERPNext recomputes profit from stock valuation; WWI LineProfit is kept in Sales Invoice Item.wwi_line_profit'})
    failed=[x for x in checks if x['pass'] is False]
    (ROOT/'evidence').mkdir(exist_ok=True)
    json.dump({'status':'pass' if not failed else 'fail','checks':checks,'masters':e['masters'],'counts':e['counts']},open(ROOT/'evidence/reconciliation.json','w'),indent=1,default=str)
    for x in checks:print('PASS' if x['pass'] else ('INFO' if x['pass'] is None else 'FAIL'),x['check'],'' if x['pass'] else f"erp={x.get('erpnext')} wwi={x.get('wwi_oracle')} {x.get('note') or ''}")
    print(f"{len(checks)-len(failed)-sum(1 for x in checks if x['pass'] is None)} passed, {len(failed)} failed")

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--erp',default=str(ROOT/'build/erp_measures.json'));main(ap.parse_args().erp)
