from __future__ import annotations
import argparse,pathlib,json,datetime,decimal,time
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from common import load,log
from engine import execute_metric,execute_chart,records
from request_models import Request
def serve(package,port):
    package=pathlib.Path(package).resolve()
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,obj):
            data=json.dumps(obj,default=str,ensure_ascii=False).encode('utf-8');self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def do_GET(self):
            route=urlparse(self.path).path
            if route=='/api/capabilities':
                docs={n:load(package/'catalog'/f'{n}.json') for n in ['measures','charts','views','contract_version']};docs['measures']['items']=[m for m in docs['measures']['items'] if m['status']=='verified'];self.send(200,docs);return
            if route=='/api/scenario':self.send(200,load(package/'data/synthetic/no_incoming_v1/scenario.json'));return
            if route in ['/','/index.html','/app.js','/style.css']:
                name='index.html' if route=='/' else route[1:];file=package/'app'/name
                if not file.exists():self.send(404,{'error':'Asset unavailable'});return
                content=file.read_bytes();self.send_response(200);self.send_header('Content-Type',{'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8'}[name]);self.send_header('Content-Length',str(len(content)));self.end_headers();self.wfile.write(content);return
            self.send(404,{'error':'Unknown route; evaluator files are not exposed'})
        def do_POST(self):
            st=time.perf_counter()
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<=0 or length>16384:raise ValueError('Request body must be 1..16384 bytes')
                body=json.loads(self.rfile.read(length));kind=urlparse(self.path).path;identifier=body.pop('id',None);r=Request.model_validate(body)
                if kind=='/api/metric':result=execute_metric(package,identifier,r)
                elif kind=='/api/chart':result=execute_chart(package,identifier,r)
                elif kind=='/api/records':result=records(package,identifier,r)
                else:self.send(404,{'error':'Unknown operation'});return
                result['query_wall_seconds']=time.perf_counter()-st;self.send(200,result)
            except (ValueError,TypeError,KeyError,json.JSONDecodeError) as e:
                log(package,{'event':'api_failure','route':self.path,'seconds':time.perf_counter()-st,'status':422,'error':str(e)});self.send(422,{'error':str(e),'completed':False})
            except Exception as e:
                log(package,{'event':'api_failure','route':self.path,'seconds':time.perf_counter()-st,'status':500,'error':str(e)});self.send(500,{'error':str(e),'completed':False})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);print(f'WWI local dashboard http://127.0.0.1:{port} (read only)',flush=True);server.serve_forever()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',required=True);p.add_argument('--port',type=int,default=8017);a=p.parse_args();serve(a.package,a.port)
