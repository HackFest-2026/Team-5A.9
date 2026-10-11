"""Moved-package test: deny network/source connector calls in this process."""
import argparse,pathlib,sys,socket
from common import save,db
def unavailable(*a,**kw):raise RuntimeError('Source/network access disabled for offline acceptance probe')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);a=ap.parse_args();p=pathlib.Path(a.package).resolve()
    import pyodbc
    pyodbc.connect=unavailable;socket.create_connection=unavailable;socket.socket.connect=unavailable
    from build_local import build
    from validate import validate
    build(p);validate(p);c=db(p);row=c.execute("SELECT COUNT(DISTINCT OrderID),SUM(UnpickedUnits) FROM analytics.order_lines WHERE ScenarioID='base' AND UnpickedUnits>0").fetchone();c.close()
    from validate_contract import validate as validate_contract
    from engine import execute_metric,execute_chart,records
    validate_contract(p)
    results={}
    for mid,basis in [('M01','order_date'),('M02','order_date'),('M03','order_date'),('M04','none'),('M05','none'),('M12_orders_category','order_date')]:
        result=execute_metric(p,mid,{'date_basis':basis,'limit':200});results[mid]=result['rows']
    fixture=execute_metric(p,'M02',{'scenario_id':'no_incoming_v1'})['rows'][0]['value'];assert fixture==120
    incoming=execute_metric(p,'M05',{'scenario_id':'no_incoming_v1','date_basis':'none'})['rows'][0]['value'];assert incoming==0
    for chart,basis in [('monthly-orders','order_date'),('category-orders','order_date'),('top-unpicked','order_date'),('picking-status','order_date'),('holdings-reorder','none'),('incoming-supplier','none')]:execute_chart(p,chart,{'date_basis':basis})
    for entity,basis in [('orders','order_date'),('order_lines','order_date'),('items','none'),('purchase_orders','none'),('purchase_lines','none'),('customers','none'),('suppliers','none')]:records(p,entity,{'date_basis':basis,'limit':1})
    import duckdb,pyarrow,pydantic
    modules={x.__name__:x.__file__ for x in [duckdb,pyarrow,pydantic]}
    if not all(str(p) in str(v) for v in modules.values()):raise RuntimeError('Offline probe loaded libraries outside moved package')
    save(p/'evidence/offline_move_probe.json',{'status':'pass','package_directory':str(p),'python_prefix':sys.prefix,'module_locations':modules,'source_connector':'pyodbc.connect denied','network':'socket connect denied','rebuilt_from':'relative package Parquet and scripts','unpicked_orders':row[0],'unpicked_units':row[1],'dataset_scope':'base-only metrics plus separately requested fixture','verified_measures_queried':list(results),'charts_queried':6,'record_entities_queried':7,'fixture_units':fixture,'fixture_incoming':incoming,'contract_validation':'pass','limitation':'process instrumentation disables source connectors; live SQL service was not stopped or reconfigured'})
    print('Offline moved-package probe passed',row,flush=True)
if __name__=='__main__':main()
