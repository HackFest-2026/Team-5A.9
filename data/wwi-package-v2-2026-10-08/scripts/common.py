from __future__ import annotations
import csv,hashlib,json,time,datetime,decimal,pathlib,sys,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
class LoggedCursor:
    def __init__(self,description,rows):self.description=description;self.rows=rows;self.position=0
    def fetchall(self):r=self.rows[self.position:];self.position=len(self.rows);return r
    def fetchone(self):
        if self.position>=len(self.rows):return None
        r=self.rows[self.position];self.position+=1;return r
class LoggedConnection:
    def __init__(self,connection,package):self.connection=connection;self.package=pathlib.Path(package)
    def execute(self,sql,params=()):
        started=time.perf_counter();qid=uuid.uuid4().hex
        try:
            cur=self.connection.execute(sql,params);description=cur.description;rows=cur.fetchall();cols=[x[0] for x in description] if description else []
            result='evidence/query_runs/'+qid+'.csv';csvwrite(self.package/result,cols,rows)
            log(self.package,{'event':'local_query','query_id':qid,'sql':sql,'parameters':params,'seconds':time.perf_counter()-started,'row_count':len(rows),'columns':cols,'result_file':result,'status':'pass'})
            return LoggedCursor(description,rows)
        except Exception as e:
            log(self.package,{'event':'local_query','query_id':qid,'sql':sql,'parameters':params,'seconds':time.perf_counter()-started,'status':'failure','error':str(e)});raise
    def close(self):self.connection.close()
def save(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
def load(path):return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def csvwrite(path,cols,rows):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(cols);w.writerows(rows)
def db(package,readonly=True):
    import duckdb
    c=duckdb.connect(str(pathlib.Path(package)/'data/wwi.duckdb'),read_only=readonly)
    return LoggedConnection(c,package)
def query(c,sql,params=()):
    cur=c.execute(sql,params);cols=[x[0] for x in cur.description];return cols,cur.fetchall()
def log(package,event):
    p=pathlib.Path(package)/'evidence/acquisition_log.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('a',encoding='utf-8') as f:f.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**event},default=str)+'\n')
