"""Allowlisted query CLI: no credentials, SQL Server or network required."""
import argparse,json,pathlib
from engine import execute_metric,execute_chart,records
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package',default=str(pathlib.Path(__file__).resolve().parents[1]));ap.add_argument('--kind',choices=['metric','chart','records'],required=True);ap.add_argument('--id',required=True);ap.add_argument('--request',default='{}',help='JSON typed request; default is base-only and no interval');a=ap.parse_args()
    operation={'metric':execute_metric,'chart':execute_chart,'records':records}[a.kind];print(json.dumps(operation(a.package,a.id,json.loads(a.request)),indent=2,default=str,ensure_ascii=False))
if __name__=='__main__':main()
