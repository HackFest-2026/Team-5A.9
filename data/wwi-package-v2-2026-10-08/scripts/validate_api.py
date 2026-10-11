import argparse,urllib.request,urllib.error,json,pathlib,time
from common import save
def run(package,url):
    checks=[]
    def call(route,body=None):
        req=urllib.request.Request(url+route,data=json.dumps(body).encode() if body else None,headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=20) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def check(name,actual,expected):
        checks.append({'name':name,'pass':actual==expected,'actual':actual,'expected':expected});assert actual==expected,name
    status,cap=call('/api/capabilities');check('capabilities',status,200);check('only_verified',all(m['status']=='verified' for m in cap['measures']['items']),True);check('money_hidden',bool({'M10','M11'}&{m['id'] for m in cap['measures']['items']}),False)
    for route in ['/evaluation/holdout_tasks.jsonl','/evaluation/expected_results.json','/manifest.json','/../evaluation/expected_results.json']:
        check('not_public_'+route,call(route)[0],404)
    for mid,expected in [('M01',2047),('M02',17710),('M03',161)]:
        st=time.perf_counter();status,r=call('/api/metric',{'id':mid,'start':'2016-05-01','end':'2016-06-01'});check('http_'+mid,status,200);check('value_'+mid,r['rows'][0]['value'],expected);checks[-1]['seconds']=time.perf_counter()-st
    for body in [{'id':'M10'},{'id':'M01','filters':{'stock_item_id':'80'}},{'id':'M01','date_basis':'picking_completed_time'},{'id':'M01','start':'2016-05-01'},{'id':'M01','limit':201},{'id':'M01','filters':{'stock_item_id':-1}},{'id':'M01','dataset_version':'wrong'}]:
        status,r=call('/api/metric',body);check('invalid_'+str(body),status,422);check('false_completion_'+str(body),r['completed'],False)
    status,r=call('/api/records',{'id':'orders','limit':50,'offset':50});check('pagination',r['offset'],50);check('page_size',len(r['rows']),50)
    status,r=call('/api/records',{'id':'purchase_orders','date_basis':'none'});check('po_header_count',r['total_rows'],2074)
    status,r=call('/api/records',{'id':'orders','date_basis':'picking_completed_time','start':'2016-04-01','end':'2016-05-01'});check('completion_basis',r['date_basis'],'picking_completed_time')
    save(pathlib.Path(package)/'evidence/api_validation.json',{'status':'pass','checks':len(checks),'results':checks,'scope':'HTTP implementation tests, not LLM agent evaluation'});print('API validated',len(checks),flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--url',default='http://127.0.0.1:8017');a=ap.parse_args();run(a.package,a.url)
