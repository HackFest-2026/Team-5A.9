"""v2 local server: every v1 route unchanged, plus /api/analyze, /api/resolve, /api/related and /api/contract."""
from __future__ import annotations
import argparse,pathlib,json,time
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from pydantic import ValidationError
from common import load,log
from engine import execute_metric,execute_chart,records
from request_models import Request
from analysis_v2 import analyze,resolve,related,index,typed_id
from workspace import Workspace,schema_public,SCHEMA
LOOKUP_TYPES={'customer_category','buying_group','state_province','sales_territory','salesperson','stock_group','supplier'}
def lookup(package,t):
    seen={}
    for etype,eid,name,alias,detail in index(package):
        if etype==t:seen[eid]=name
    return sorted(({'id':typed_id(t,k),'name':v} for k,v in seen.items()),key=lambda x:x['name'])

CONTRACT_DOCS=['contract_version','views','widgets','filters','charts','measures','analysis_measures','dimensions','glossary','graph','playbooks','operations']
STATIC={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/analysis.js':'analysis.js','/style.css':'style.css','/browse.js':'browse.js','/assistant.js':'assistant.js','/assistant.css':'assistant.css','/workspace.js':'workspace.js','/charts.js':'charts.js','/workspace.css':'workspace.css'}
TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'}

def message(e):
    if isinstance(e,ValidationError):
        return '; '.join(f"{'.'.join(str(p) for p in x['loc']) or 'request'}: {x['msg'].removeprefix('Value error, ')}" for x in e.errors())
    return str(e)

def published(package,mid):
    doc=load(package/'catalog/analysis_measures.json')
    entry=next((m for m in doc['items'] if m['id']==mid),None)
    return entry is not None and entry['status'] in ('verified','published-with-caveat')

def serve(package,port,host='127.0.0.1'):
    package=pathlib.Path(package).resolve()
    _ids={}
    def known_ids(ent):
        if ent not in _ids:_ids[ent]={int(eid) for etype,eid,*_ in index(package) if etype==ent}
        return _ids[ent]
    ws=Workspace(package,known_ids)
    def source_now(kind,ref_id):
        sc=SCHEMA[kind];r=Request.model_validate({'dataset_version':'wwi-data-v1-2026-10-08','scenario_id':'base','date_basis':'none','filters':{{'customer':'customer_id','supplier':'supplier_id','item':'stock_item_id'}[kind]:ref_id},'limit':1,'offset':0})
        rows=records(package,sc['source'],r)['rows']
        if not rows:raise ValueError(f'no {kind} with ID {ref_id} in the source data')
        return {f:rows[0].get(col) for f,col in sc['map'].items()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*a):pass
        def send(self,status,obj):
            data=json.dumps(obj,default=str,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            route=urlparse(self.path).path
            if route=='/api/capabilities':
                docs={n:load(package/'catalog'/f'{n}.json') for n in ['measures','charts','views','contract_version']};docs['measures']['items']=[m for m in docs['measures']['items'] if m['status']=='verified'];self.send(200,docs);return
            if route=='/api/contract':
                docs={n:load(package/'catalog'/f'{n}.json') for n in CONTRACT_DOCS if (package/'catalog'/f'{n}.json').exists()};self.send(200,docs);return
            if route=='/api/lookup':
                t=(parse_qs(urlparse(self.path).query).get('type') or [''])[0]
                if t not in LOOKUP_TYPES:self.send(422,{'error':f'type must be one of {sorted(LOOKUP_TYPES)}','completed':False});return
                self.send(200,lookup(package,t));return
            if route=='/api/scenario':self.send(200,load(package/'data/synthetic/no_incoming_v1/scenario.json'));return
            if route.startswith('/api/ws/'):
                q=parse_qs(urlparse(self.path).query);one=lambda k:(q.get(k) or [None])[0]
                try:
                    if route=='/api/ws/schema':self.send(200,schema_public());return
                    if route=='/api/ws/list':self.send(200,{'records':ws.list(one('kind'),one('deleted')=='1',int(one('ref_id')) if one('ref_id') else None)});return
                    if route=='/api/ws/get':self.send(200,ws.get(int(one('id'))));return
                    if route=='/api/ws/audit':self.send(200,{'audit':ws.audit(int(one('limit') or 100))});return
                    if route=='/api/ws/counts':self.send(200,ws.counts());return
                    if route=='/api/ws/source':
                        k=one('kind');self.send(200,{'values':source_now(k,int(one('ref_id')))});return
                except LookupError as e:self.send(404,{'error':str(e)});return
                except (ValueError,TypeError,KeyError) as e:self.send(422,{'error':str(e)});return
                self.send(404,{'error':'Unknown workspace route'});return
            if route in STATIC:
                file=package/'app'/STATIC[route]
                if not file.exists():self.send(404,{'error':'Asset unavailable'});return
                content=file.read_bytes();self.send_response(200);self.send_header('Content-Type',TYPES[file.suffix]);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content);return
            self.send(404,{'error':'Unknown route; evaluator files are not exposed'})
        def do_POST(self):
            st=time.perf_counter()
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>16384:raise ValueError('Request body must be 1..16384 bytes')
                body=json.loads(self.rfile.read(length));kind=urlparse(self.path).path
                if not isinstance(body,dict):raise ValueError('Request body must be a JSON object')
                if kind.startswith('/api/ws/'):
                    if self.headers.get('X-Sapience-Write')!='1':raise PermissionError('Workspace writes need the X-Sapience-Write header')
                    if kind=='/api/ws/create':out=ws.create(str(body.get('kind')),body.get('data') or {})
                    elif kind=='/api/ws/edit':
                        k=str(body.get('kind'));rid=int(body.get('ref_id'));out=ws.edit_source(k,rid,body.get('data') or {},source_now(k,rid))
                    elif kind=='/api/ws/update':out=ws.update(int(body.get('id')),body.get('data') or {},body.get('version'))
                    elif kind=='/api/ws/delete':out=ws.set_deleted(int(body.get('id')),True)
                    elif kind=='/api/ws/restore':out=ws.set_deleted(int(body.get('id')),False)
                    else:self.send(404,{'error':'Unknown workspace route'});return
                    self.send(200,out);return
                if kind=='/api/analyze':
                    if not published(package,body.get('measure_id')):raise ValueError(f"Measure {body.get('measure_id')} is not published for analysis.")
                    result=analyze(package,body)
                elif kind=='/api/resolve':result=resolve(package,body)
                elif kind=='/api/related':result=related(package,body)
                elif kind in ('/api/metric','/api/chart','/api/records'):
                    identifier=body.pop('id',None);r=Request.model_validate(body)
                    result={'/api/metric':execute_metric,'/api/chart':execute_chart,'/api/records':records}[kind](package,identifier,r)
                else:self.send(404,{'error':'Unknown operation'});return
                result['query_wall_seconds']=time.perf_counter()-st;self.send(200,result)
            except PermissionError as e:self.send(403,{'error':str(e),'completed':False})
            except LookupError as e:
                if isinstance(e,KeyError):log(package,{'event':'api_failure','route':self.path,'seconds':time.perf_counter()-st,'status':422,'error':message(e)});self.send(422,{'error':message(e),'completed':False})
                else:self.send(404,{'error':str(e),'completed':False})
            except (ValueError,TypeError,json.JSONDecodeError) as e:
                log(package,{'event':'api_failure','route':self.path,'seconds':time.perf_counter()-st,'status':422,'error':message(e)});self.send(422,{'error':message(e),'completed':False})
            except Exception as e:
                log(package,{'event':'api_failure','route':self.path,'seconds':time.perf_counter()-st,'status':500,'error':str(e)});self.send(500,{'error':str(e),'completed':False})
    server=ThreadingHTTPServer((host,port),Handler);print(f'WWI v2 local app http://{host}:{port} (analytics read only; workspace edits kept separately)',flush=True);server.serve_forever()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--port',type=int,default=8017);p.add_argument('--host',default='127.0.0.1');a=p.parse_args();serve(a.package,a.port,a.host)
