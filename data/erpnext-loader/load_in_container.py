"""Load extracted WWI JSONL into ERPNext. Runs INSIDE the backend container:

  docker exec wwi-erpnext-backend-1 bash -c "cd /home/frappe/frappe-bench/sites && ../env/bin/python wwi_load/load_in_container.py <stage> [--limit N]"

Stages (run in this order): setup, masters, opening, purchase_orders, sales_orders, stock_flow, closing, synthetic, all.
Every stage is resumable: progress is checkpointed in wwi_load/state/<stage>.json and failures are logged with their WWI IDs.
"""
from __future__ import annotations
import argparse,json,os,sys,time,traceback
HERE=os.path.dirname(os.path.abspath(__file__));BUILD=os.path.join(HERE,'build');STATE=os.path.join(HERE,'state');os.makedirs(STATE,exist_ok=True)
SITE='frontend';COMPANY='Wide World Importers';ABBR='WWI';WH=f'Stores - {ABBR}';TAX_ACCOUNT=f'WWI Sales Tax - {ABBR}'

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def connect():
    frappe.init(site=SITE,sites_path='.');frappe.connect();frappe.set_user('Administrator')
    frappe.flags.mute_emails=True

def jsonl(name):
    with open(os.path.join(BUILD,name+'.jsonl'),encoding='utf-8') as f:
        for line in f:yield json.loads(line)

def log_failure(stage,key,err):
    with open(os.path.join(STATE,f'{stage}.failures.jsonl'),'a') as f:f.write(json.dumps({'key':key,'error':err[-2000:]})+'\n')

class Checkpoint:
    def __init__(self,stage):self.path=os.path.join(STATE,f'{stage}.json');self.done=json.load(open(self.path)).get('done',0) if os.path.exists(self.path) else 0
    def save(self,done,extra=None):json.dump({'done':done,'utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**(extra or {})},open(self.path,'w'))

# ---------------- setup ----------------
CUSTOM={
 'Customer':[('wwi_customer_id','Int',1),('wwi_buying_group','Data',0),('wwi_bill_to_customer_id','Int',0)],
 'Territory':[('wwi_state_province_id','Int',0)],'Sales Person':[('wwi_person_id','Int',0)],'Supplier':[('wwi_supplier_id','Int',1)],
 'Item':[('wwi_stock_item_id','Int',1),('wwi_quantity_per_outer','Int',0),('wwi_stock_groups','Small Text',0),('wwi_is_synthetic','Check',1)],
 'Purchase Order':[('wwi_purchase_order_id','Int',1),('wwi_is_finalized','Check',0)],'Purchase Order Item':[('wwi_purchase_order_line_id','Int',1)],
 'Purchase Receipt':[('wwi_purchase_order_id','Int',1)],'Purchase Receipt Item':[('wwi_purchase_order_line_id','Int',1)],
 'Sales Order':[('wwi_order_id','Int',1),('wwi_backorder_order_id','Int',0),('wwi_is_synthetic','Check',1)],
 'Sales Order Item':[('wwi_order_line_id','Int',1),('wwi_picked_quantity','Float',0)],
 'Sales Invoice':[('wwi_invoice_id','Int',1),('wwi_order_id','Int',1)],
 'Sales Invoice Item':[('wwi_invoice_line_id','Int',1),('wwi_line_profit','Currency',0),('wwi_tax_amount','Currency',0)],
 'Stock Reconciliation':[('wwi_note','Small Text',0)],
}
def setup():
    if not frappe.db.get_single_value('System Settings','setup_complete'):
        from frappe.desk.page.setup_wizard.setup_wizard import setup_complete
        setup_complete({'language':'English','country':'United States','timezone':'America/Los_Angeles','currency':'USD','company_name':COMPANY,'company_abbr':ABBR,
            'chart_of_accounts':'Standard','fy_start_date':'2013-01-01','fy_end_date':'2013-12-31','setup_demo':0,'domains':['Distribution'],
            'full_name':'WWI Loader','email':'loader@wwi.local','password':'wwi-loader-change-me'})
        frappe.db.commit()
    for y in range(2012,2017):
        if not frappe.db.exists('Fiscal Year',str(y)):
            frappe.get_doc({'doctype':'Fiscal Year','year':str(y),'year_start_date':f'{y}-01-01','year_end_date':f'{y}-12-31'}).insert()
    create_custom_fields({dt:[{'fieldname':f,'label':f.replace('wwi_','WWI ').replace('_',' ').title(),'fieldtype':t,'search_index':i,'insert_after':None,'read_only':0,'no_copy':1}
        for f,t,i in fs] for dt,fs in CUSTOM.items()},update=True)
    frappe.db.set_single_value('Stock Settings','allow_negative_stock',1)
    frappe.db.set_single_value('Stock Settings','auto_indent',0)
    frappe.db.set_single_value('Global Defaults','disable_rounded_total',1)
    frappe.db.set_single_value('Selling Settings','so_required','No')
    frappe.db.set_value('Company',COMPANY,'enable_perpetual_inventory',0)
    if not frappe.db.exists('Account',TAX_ACCOUNT):
        frappe.get_doc({'doctype':'Account','account_name':'WWI Sales Tax','parent_account':f'Duties and Taxes - {ABBR}','company':COMPANY,'account_type':'Tax','tax_rate':15}).insert()
    for rate in (15,10):
        if not frappe.db.exists('Item Tax Template',f'WWI Tax {rate}% - {ABBR}'):
            frappe.get_doc({'doctype':'Item Tax Template','title':f'WWI Tax {rate}%','company':COMPANY,'taxes':[{'tax_type':TAX_ACCOUNT,'tax_rate':rate}]}).insert()
    frappe.db.set_single_value('Selling Settings','allow_against_multiple_purchase_orders',1)
    frappe.db.commit();print('setup done',flush=True)

def bins():
    from erpnext.stock.utils import get_or_make_bin
    for (code,) in frappe.db.sql("select name from tabItem where is_stock_item=1"):get_or_make_bin(code,WH)
    frappe.db.commit();print('bins ready:',frappe.db.count('Bin'),flush=True)

# ---------------- generic insert ----------------
KEYS={'Purchase Order':['wwi_purchase_order_id'],'Sales Order':['wwi_order_id'],'Sales Invoice':['wwi_invoice_id'],
      'Purchase Receipt':['wwi_purchase_order_id','posting_date'],'Stock Reconciliation':['purpose','posting_date']}
def existing(rec):
    """Idempotency: a record whose WWI key is already submitted is skipped, so any stage can be re-run from the start."""
    k=KEYS.get(rec['doctype'])
    if not k:return None
    return frappe.db.get_value(rec['doctype'],{**{f:rec[f] for f in k},'docstatus':1},'name')

def insert(rec,submit):
    found=existing(rec)
    if found:return found
    for attempt in range(4):
        try:
            d=frappe.get_doc(rec);d.flags.ignore_permissions=True
            d.insert(set_name=None)
            if submit:d.submit()
            return d.name
        except (frappe.QueryDeadlockError,frappe.DoesNotExistError):
            frappe.db.rollback()
            if attempt==3:raise
            time.sleep(0.5*(attempt+1))

def run_simple(stage,files,submit,key):
    cp=Checkpoint(stage);i=0;t0=time.time();ok=fail=0
    for name in files:
        for rec in jsonl(name):
            i+=1
            if i<=cp.done:continue
            try:insert(rec,submit);ok+=1
            except Exception:
                frappe.db.rollback();fail+=1;log_failure(stage,rec.get(key) or rec.get('doctype'),traceback.format_exc())
            if i%100==0:frappe.db.commit();cp.save(i,{'ok':ok,'fail':fail});print(f'{stage} {i} ok={ok} fail={fail} {i/(time.time()-t0+1e-9):.1f}/s',flush=True)
            if LIMIT and ok+fail>=LIMIT:frappe.db.commit();cp.save(i,{'ok':ok,'fail':fail});return
    frappe.db.commit();cp.save(i,{'ok':ok,'fail':fail,'finished':True});print(f'{stage} finished: {i} records, ok={ok} fail={fail}',flush=True)

def masters():
    for f in ['01_uom','02_customer_group','03_territory','04_sales_person','05_supplier','06_item_group','07_customer','08_item']:
        recs=list(jsonl(f));n=0
        for r in recs:
            key={'UOM':'uom_name','Customer Group':'customer_group_name','Territory':'territory_name','Sales Person':'sales_person_name','Supplier':'supplier_name','Item Group':'item_group_name','Customer':'customer_name','Item':'item_code'}[r['doctype']]
            if frappe.db.exists(r['doctype'],r[key]):continue
            try:insert(r,False);n+=1
            except Exception:frappe.db.rollback();log_failure('masters',f"{r['doctype']}:{r[key]}",traceback.format_exc())
        frappe.db.commit();print(f'masters {f}: inserted {n} of {len(recs)}',flush=True)

def tax_row():return [{'charge_type':'On Net Total','account_head':TAX_ACCOUNT,'description':'Sales tax (item-wise rates)','rate':0}]

def purchase_orders():
    run_simple('purchase_orders',['10_purchase_order'],True,'wwi_purchase_order_id')

def sales_orders():
    def gen():
        for r in jsonl('12_sales_order'):r['taxes']=tax_row();r['ignore_pricing_rule']=1;yield r
    stage='sales_orders';cp=Checkpoint(stage);i=0;ok=fail=0;t0=time.time()
    for rec in gen():
        i+=1
        if i<=cp.done:continue
        try:insert(rec,True);ok+=1
        except Exception:frappe.db.rollback();fail+=1;log_failure(stage,rec['wwi_order_id'],traceback.format_exc())
        if i%200==0:frappe.db.commit();cp.save(i,{'ok':ok,'fail':fail});print(f'{stage} {i} ok={ok} fail={fail} {i/(time.time()-t0):.1f}/s',flush=True)
        if LIMIT and ok+fail>=LIMIT:break
    frappe.db.commit();cp.save(i,{'ok':ok,'fail':fail,'finished':not LIMIT});print(f'{stage}: {i} ok={ok} fail={fail}',flush=True)

def stock_flow():
    """Purchase receipts and sales invoices merged in date order, so ERPNext never has to repost back-dated stock."""
    prs=[(r['posting_date'],r['posting_time'],'PR',r) for r in jsonl('11_purchase_receipt')]
    sis=[(r['posting_date'],r['posting_time'],'SI',r) for r in jsonl('13_sales_invoice')]
    flow=sorted(prs+sis,key=lambda x:(x[0],x[1],x[2]))
    po_item={r.wwi_purchase_order_line_id:(r.parent,r.name) for r in frappe.db.sql("select name,parent,wwi_purchase_order_line_id from `tabPurchase Order Item` where docstatus=1",as_dict=True)}
    so_items={}
    for r in frappe.db.sql("select i.name,i.parent,i.item_code,i.wwi_picked_quantity,s.wwi_order_id from `tabSales Order Item` i join `tabSales Order` s on s.name=i.parent where s.docstatus=1 order by i.idx",as_dict=True):
        so_items.setdefault((r.wwi_order_id,r.item_code),[]).append(r)
    stage='stock_flow';cp=Checkpoint(stage);i=0;ok=fail=0;t0=time.time()
    for date,_,kind,rec in flow:
        i+=1
        if i<=cp.done:continue
        try:
            if kind=='PR':
                for it in rec['items']:
                    po,po_row=po_item[it['wwi_purchase_order_line_id']];it['purchase_order']=po;it['purchase_order_item']=po_row
            else:
                rec['taxes']=tax_row();rec['ignore_pricing_rule']=1;out=[]
                for it in rec['items']:
                    rows=so_items.get((rec['wwi_order_id'],it['item_code']),[]);remaining=it['qty']
                    for r in rows:
                        take=min(remaining,(r.wwi_picked_quantity or 0)-(r.get('_used') or 0))
                        if take<=0:continue
                        r['_used']=(r.get('_used') or 0)+take;remaining-=take
                        out.append({**it,'qty':take,'sales_order':r.parent,'so_detail':r.name})
                        if remaining<=0:break
                    if remaining>0:out.append({**it,'qty':remaining})
                rec['items']=out
            insert(rec,True);ok+=1
        except Exception:frappe.db.rollback();fail+=1;log_failure(stage,f"{kind}:{rec.get('wwi_invoice_id') or rec.get('wwi_purchase_order_id')}",traceback.format_exc())
        if i%200==0:frappe.db.commit();cp.save(i,{'ok':ok,'fail':fail,'date':date});print(f'{stage} {i}/{len(flow)} {date} ok={ok} fail={fail} {i/(time.time()-t0):.1f}/s',flush=True)
        if LIMIT and ok+fail>=LIMIT:break
    frappe.db.commit();cp.save(i,{'ok':ok,'fail':fail,'finished':i>=len(flow)});print(f'{stage}: {i}/{len(flow)} ok={ok} fail={fail}',flush=True)

def close_unfinalized_check():
    """WWI finalized POs are all fully received, so no PO needs closing; this reports that the open ones match WWI."""
    print('open POs:',frappe.db.sql("select count(*) from `tabPurchase Order` where docstatus=1 and per_received<100")[0][0],flush=True)

STAGES={'setup':setup,'masters':masters,'bins':bins,'opening':lambda:run_simple('opening',['09_opening_stock'],True,'doctype'),'purchase_orders':purchase_orders,
        'sales_orders':sales_orders,'stock_flow':stock_flow,'closing':lambda:run_simple('closing',['14_closing_stock'],True,'doctype'),
        'synthetic':lambda:run_simple('synthetic',['15_synthetic_sales_order'],True,'wwi_order_id'),'check':close_unfinalized_check}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=list(STAGES)+['all']);ap.add_argument('--limit',type=int,default=0);a=ap.parse_args()
    LIMIT=a.limit;connect()
    try:
        for s in (list(STAGES) if a.stage=='all' else [a.stage]):
            t=time.time();STAGES[s]();print(f'== {s} took {time.time()-t:.0f}s',flush=True)
    finally:frappe.destroy()
