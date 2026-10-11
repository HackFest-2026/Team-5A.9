"""P3 bounded history feasibility review of already-acquired evidence only."""
import argparse,pathlib,csv,datetime,time,collections
from common import db,query,save,load,csvwrite
def run(package):
    p=pathlib.Path(package);assert load(p/'manifest.json').get('p2_status')=='pass','P2 gate required';start=time.perf_counter();c=db(p);out=p/'evidence/candidates'
    def export(name,sql,params=()):
        (p/'sql/local'/f'{name}.sql').write_text(sql,encoding='utf-8');cols,rr=query(c,sql,params);csvwrite(out/f'{name}.csv',cols,rr);return rr
    estimates=[]
    for dt in ['2016-04-01','2016-05-01','2016-06-01']:
        sql='SELECT COUNT(*) AS EstimatedOpenLines FROM raw.Sales_OrderLines l JOIN raw.Sales_Orders o USING(OrderID) WHERE o.OrderDate<? AND (l.PickingCompletedWhen IS NULL OR l.PickingCompletedWhen>=?)'
        n=export('history_'+dt.replace('-',''),sql,[dt,dt])[0][0];estimates.append([dt,n])
        export('history_sample_'+dt.replace('-',''),'SELECT o.OrderID,o.OrderDate,o.BackorderOrderID,l.OrderLineID,l.StockItemID,l.Quantity,l.PickedQuantity,l.PickingCompletedWhen FROM raw.Sales_OrderLines l JOIN raw.Sales_Orders o USING(OrderID) WHERE o.OrderDate<? AND (l.PickingCompletedWhen IS NULL OR l.PickingCompletedWhen>=?) ORDER BY o.OrderID,l.OrderLineID LIMIT 10',[dt,dt])
    stored=export('history_final_control','SELECT COUNT(*) AS StoredCompletionNullLines,COUNT(*) FILTER(WHERE Quantity>PickedQuantity) AS QuantityUnpickedLines FROM raw.Sales_OrderLines WHERE PickingCompletedWhen IS NULL')[0]
    export('history_invalid_dates','SELECT COUNT(*) FILTER(WHERE l.PickingCompletedWhen<CAST(o.OrderDate AS TIMESTAMP)) AS CompletionBeforeCreation,COUNT(*) FILTER(WHERE l.PickedQuantity>l.Quantity) AS OverpickedLines,COUNT(*) FILTER(WHERE o.BackorderOrderID IS NOT NULL) AS ReferencingOriginalLines FROM raw.Sales_OrderLines l JOIN raw.Sales_Orders o USING(OrderID)')
    export('history_inventory_probe','SELECT COUNT(*) AS MovementRows,COUNT(*) FILTER(WHERE Quantity>0) AS PositiveMovements,COUNT(*) FILTER(WHERE Quantity<0) AS NegativeMovements,MIN(TransactionOccurredWhen) AS FirstMovement,MAX(TransactionOccurredWhen) AS LastMovement FROM raw.Warehouse_StockItemTransactions')
    modules=list(csv.DictReader((p/'evidence/source_controls/00_modules.csv').open(encoding='utf-8',newline='')));review=[]
    for row in modules:
        body=row['definition'] or ''
        if 'BackorderOrderID' in body and ('DELETE' in body or 'INSERT' in body):
            name=row['SchemaName']+'.'+row['ModuleName'];path='evidence/candidates/history_logic_'+name+'.sql';(p/path).write_text(body,encoding='utf-8');review.append({'module':name,'path':path,'retained_line_deletes':'DELETE' in body,'backorder_link':True,'procedure_execution':'never'})
    # Completely separate oracle uses raw rows and datetime comparisons, not the estimated-count SQL.
    import pyarrow.parquet as pq
    oo={r['OrderID']:r for r in pq.read_table(p/'data/raw/Sales.Orders.parquet').to_pylist()};ll=pq.read_table(p/'data/raw/Sales.OrderLines.parquet').to_pylist();ind=[]
    for dt,n in estimates:
        d=datetime.date.fromisoformat(dt);t=datetime.datetime.fromisoformat(dt);nn=sum(oo[l['OrderID']]['OrderDate']<d and (l['PickingCompletedWhen'] is None or l['PickingCompletedWhen']>=t) for l in ll);assert nn==n;ind.append(nn)
    assert estimates[-1][1]==stored[0]
    save(out/'history_verdict.json',{'status':'blocked-exact-history','estimated_open_line_count':'candidate outside primary dashboard','three_boundaries':estimates,'independent_counts':ind,'final_stored_null_completion_lines':stored[0],'final_stored_underpicked_lines':stored[1],'final_agreement':'passes numerical check; does not validate prior event history','assumptions':['Current surviving rows treated as if they existed unchanged from OrderDate','Date-only creation assumes the disclosed midnight boundary','Null final completion treated as still open','No complete amendment/cancellation/delete/partial-pick timeline exists in this extract'],'source_procedure_review':review,'failure_cases':['Backorder procedure changes/moves lines and creates targets; current line existence is incomplete lifecycle evidence','Current PickedQuantity cannot establish units remaining at a past timestamp','Movement rows are not automatically pick events; no certified opening balance or adjustment completeness for historical holdings'],'exact_remaining_units':'blocked: timestamped quantity-change history unavailable','exact_inventory_balances':'blocked: opening balance and signed complete movement semantics not certified','budget_minutes':120,'elapsed_seconds':time.perf_counter()-start,'source_access':'none; acquired metadata/procedure definitions only','procedures_run':False})
    c.close();print('P3 history reviewed; exact reconstruction blocked with evidence',flush=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--package',required=True);ap.add_argument('--stage',required=True,choices=['p3']);ap.add_argument('--investigation',required=True,choices=['history']);a=ap.parse_args();run(a.package)
