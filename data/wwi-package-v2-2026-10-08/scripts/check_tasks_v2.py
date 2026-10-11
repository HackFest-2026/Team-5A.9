"""Grade the engine against the independent oracle's expected answers in evaluation/v2 (dev, holdout and utterances).

This checks the APP (engine) can produce every expected answer; it is not an agent score."""
from __future__ import annotations
import argparse,json,pathlib
from decimal import Decimal
from common import save
from engine import records
from analysis_v2 import analyze,resolve,related

def same(a,b,tol=None):
    if a is None or b is None:return a is None and b is None
    if isinstance(a,(int,float,str)) and isinstance(b,(int,float,str)):
        try:
            if tol is not None:return abs(float(a)-float(b))<=tol
            return Decimal(str(a))==Decimal(str(b))
        except Exception:return str(a)==str(b)
    return a==b

def check_analyze(p,req,exp):
    got=analyze(p,req);diffs=[]
    for k in ['total','total_baseline','total_current','change','group_count']:
        if k in exp and not same(got.get(k),exp[k]):diffs.append((k,got.get(k),exp[k]))
    if 'pct_change' in exp and not same(got.get('pct_change'),exp['pct_change'],0.006):diffs.append(('pct_change',got.get('pct_change'),exp['pct_change']))
    if 'dimension_additive' in exp and bool(got['dimension']['additive'])!=bool(exp['dimension_additive']):diffs.append(('additive',got['dimension']['additive'],exp['dimension_additive']))
    if 'rows' in exp:
        # The answer key stores the leading rows (plus the "All others" row, if any) and the full count in rows_returned.
        g=got.get('rows',[]);isoth=lambda x:str(x.get('label','')).startswith('All others');top=[x for x in exp['rows'] if not isoth(x)];others=[x for x in exp['rows'] if isoth(x)]
        if 'rows_returned' in exp and len(g)!=exp['rows_returned']:diffs.append(('rows_returned',len(g),exp['rows_returned']))
        if others:
            mine=[x for x in g if x.get('is_other')]
            if not mine:diffs.append(('all_others_row','missing','present'))
            else:
                for k in ['value','baseline','current','change']:
                    if k in others[0] and not same(mine[0].get(k),others[0][k]):diffs.append((f'all_others.{k}',mine[0].get(k),others[0][k]))
        for i,(a,b) in enumerate(zip([x for x in g if not x.get('is_other')],top)):
            for k in ['key','value','baseline','current','change']:
                if k in b and not same(a.get(k),b[k]):diffs.append((f'rows[{i}].{k}',a.get(k),b[k]))
            for k in ['share','share_of_change']:
                if k in b and not same(a.get(k),b[k],0.0006):diffs.append((f'rows[{i}].{k}',a.get(k),b[k]))
    return diffs

def check_related(p,req,exp):
    got=related(p,req);t=req['entity_type'];diffs=[]
    def cmp(name,a,b):
        if not same(a,b):diffs.append((name,a,b))
    if t=='stock_item':
        cmp('supplier',got['entity']['SupplierID'],exp.get('nominated_supplier_id'))
        cmp('per_outer',got['entity']['QuantityPerOuter'],exp.get('quantity_per_outer'))
        if 'holdings' in exp:cmp('on_hand',got['holdings'][0]['QuantityOnHand'],exp['holdings']['quantity_on_hand'])
        if 'unpicked_units_all_history' in exp:cmp('unpicked',got['unpicked_demand']['units'],exp['unpicked_units_all_history'])
        if 'orders_with_unpicked_all_history' in exp:cmp('unpicked_orders',got['unpicked_demand']['orders'],exp['orders_with_unpicked_all_history'])
        if 'incoming_units' in exp:cmp('incoming',sum(x['IncomingUnits'] for x in got['incoming']),exp['incoming_units'])
        if 'incoming_lines' in exp:cmp('incoming_lines',sorted(x['PurchaseOrderLineID'] for x in got['incoming']),sorted(x['purchase_line_id'] for x in exp['incoming_lines']))
    elif t=='supplier':
        cmp('items',got['items']['items'],exp.get('nominated_item_count'))
        cmp('unpicked',got['unpicked_demand_on_its_items']['units'],exp.get('unpicked_units_nominated_items_all_history'))
        cmp('incoming',got['incoming']['incoming_units'],exp.get('incoming_units_on_open_pos'))
    elif t=='customer':
        e=got['entity'];cmp('category',e['CustomerCategoryName'],exp.get('customer_category'));cmp('territory',e['SalesTerritory'],exp.get('sales_territory'))
        cmp('state',e['StateProvinceName'],exp.get('state_province'));cmp('orders',got['orders']['all_orders'],exp.get('orders_all_history'))
        if 'orders_with_unpicked_all_history' in exp:cmp('orders_unpicked',got['orders']['orders_with_unpicked'],exp['orders_with_unpicked_all_history'])
    elif t=='order':
        for k,gk in [('backorder_order_id','BackorderOrderID'),('customer_id','CustomerID')]:
            if k in exp:cmp(k,got['entity'][gk],exp[k])
    return diffs

def check_records(p,req,exp):
    body=dict(req);ident=body.pop('id');got=records(p,ident,body);diffs=[]
    if 'total_rows' in exp and got['total_rows']!=exp['total_rows']:diffs.append(('total_rows',got['total_rows'],exp['total_rows']))
    for k,col in [('order_ids','OrderID'),('purchase_line_ids','PurchaseOrderLineID'),('purchase_order_ids','PurchaseOrderID')]:
        if k in exp:
            ids=sorted({r[col] for r in got['rows']})
            if ids!=sorted(set(exp[k]))[:len(ids)] or (got['total_rows']<=len(got['rows']) and ids!=sorted(set(exp[k]))):diffs.append((k,ids[:12],sorted(set(exp[k]))[:12]))
    return diffs

CLARIFY_NAMES={('V2D14',1):('Tailspin Toys',['customer','buying_group']),('V2D15',1):('Hudson',['salesperson']),('V2H05',1):('Wingtip Toys',['customer','buying_group']),('V2H13',1):('David',['customer'])}
REFUSE_REQUESTS={('V2D28',1):{'measure_id':'M05','group_by':'customer_category'},('V2D29',1):{'measure_id':'M05','filters':{'customer_id':950}},('V2H10',1):{'measure_id':'M05','group_by':'sales_territory'}}

def run(package):
    p=pathlib.Path(package).resolve();results=[]
    def record(where,kind,diffs,err=None):results.append({'where':where,'kind':kind,'pass':not diffs and err is None,'diffs':[list(map(str,d)) for d in diffs],'error':err})
    for fname in ['dev_multistep.jsonl','holdout_multistep.jsonl']:
        for line in open(p/'evaluation/v2'/fname,encoding='utf-8'):
            t=json.loads(line)
            for s in t['steps']:
                where=f"{t['task_id']}.{s['step']}";op=s['expected_operation'];req=s['expected_request'];exp=s['expected_result'] or {}
                try:
                    if op=='analyze':record(where,op,check_analyze(p,req,exp))
                    elif op=='related':record(where,op,check_related(p,req,exp))
                    elif op=='records':record(where,op,check_records(p,req,exp))
                    elif op=='resolve':
                        r=resolve(p,req);d=[]
                        if r['status']!=exp['status']:d.append(('status',r['status'],exp['status']))
                        if exp.get('best') and (r['candidates'][0]['type'],r['candidates'][0]['id'])!=(exp['best']['type'],exp['best']['id']):d.append(('best',r['candidates'][0],exp['best']))
                        record(where,op,d)
                    elif op=='clarify' and (t['task_id'],s['step']) in CLARIFY_NAMES:
                        text,types=CLARIFY_NAMES[(t['task_id'],s['step'])];r=resolve(p,{'text':text,'types':types})
                        record(where,'clarify(resolve ambiguous)',[] if r['status']=='ambiguous' else [('status',r['status'],'ambiguous')])
                    elif op=='refuse' and (t['task_id'],s['step']) in REFUSE_REQUESTS:
                        try:analyze(p,REFUSE_REQUESTS[(t['task_id'],s['step'])]);record(where,'refuse(engine rejects)',[('accepted','accepted','rejected')])
                        except ValueError:record(where,'refuse(engine rejects)',[])
                    else:results.append({'where':where,'kind':op,'pass':None,'note':'agent behaviour only (no engine call to grade)'})
                except Exception as e:record(where,op,[],f'{type(e).__name__}: {e}')
    for line in open(p/'evaluation/v2/dev_utterances.jsonl',encoding='utf-8'):
        u=json.loads(line);req=u.get('expected_request')
        if u.get('expected_operation')=='analyze' and req and u.get('expected_total') is not None:
            exp={'total':u['expected_total']} if not req.get('compare_start') else {'total_current':u['expected_total']}
            if isinstance(u['expected_total'],dict):exp=u['expected_total']
            try:record(u['id'],'utterance analyze',check_analyze(p,req,exp))
            except Exception as e:record(u['id'],'utterance analyze',[],f'{type(e).__name__}: {e}')
    graded=[r for r in results if r['pass'] is not None];failed=[r for r in graded if not r['pass']]
    summary={'graded':len(graded),'passed':len(graded)-len(failed),'failed':len(failed),'agent_only_steps':len(results)-len(graded),
             'by_kind':{k:{'graded':sum(1 for r in graded if r['kind']==k),'passed':sum(1 for r in graded if r['kind']==k and r['pass'])} for k in sorted({r['kind'] for r in graded})}}
    save(p/'evidence/task_answer_check.json',{'status':'pass' if not failed else 'fail','summary':summary,'failures':failed,'results':results,
        'meaning':'Engine reproduces the independent oracle answers; this is NOT an agent score (no agent was run).'})
    print(json.dumps(summary,indent=1));[print('FAIL',f['where'],f['kind'],f['diffs'][:4],f.get('error')) for f in failed[:40]]
    return failed

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);a=ap.parse_args()
    if run(a.package):raise SystemExit(1)
