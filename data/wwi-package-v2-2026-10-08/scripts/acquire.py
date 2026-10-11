"""Explicit source acquisition/refresh only. No business procedure or write SQL."""
from __future__ import annotations
import argparse,datetime,decimal,json,pathlib,sys,time,hashlib,re,shutil
from common import save,load,sha,csvwrite,log
TABLES=['Sales.Customers','Sales.Orders','Sales.OrderLines','Warehouse.StockItems','Warehouse.StockItemHoldings','Purchasing.PurchaseOrders','Purchasing.PurchaseOrderLines','Purchasing.Suppliers','Sales.Invoices','Sales.InvoiceLines','Warehouse.StockItemTransactions','Sales.CustomerCategories','Sales.BuyingGroups','Warehouse.StockGroups','Warehouse.StockItemStockGroups','Warehouse.PackageTypes','Application.People','Application.Cities','Application.StateProvinces','Application.Countries','Application.SystemParameters']
SUPPORTED={'int','bigint','smallint','tinyint','bit','decimal','numeric','money','smallmoney','date','datetime','datetime2','smalldatetime','nvarchar','varchar','nchar','char','uniqueidentifier'}
def main():
    p=argparse.ArgumentParser();p.add_argument('--server',required=True);p.add_argument('--database',required=True);p.add_argument('--auth',choices=['windows'],required=True);p.add_argument('--output',required=True);p.add_argument('--refresh',action='store_true');a=p.parse_args()
    import pyodbc,pyarrow as pa,pyarrow.parquet as pq
    out=pathlib.Path(a.output).resolve()
    if (out/'manifest.json').exists():raise SystemExit('Never overwrite an acquired package. Choose a new versioned output folder, including for explicit --refresh.')
    template=pathlib.Path(__file__).resolve().parents[1]/'sql/source'
    if template.exists() and template.resolve()!=(out/'sql/source').resolve():shutil.copytree(template,out/'sql/source',dirs_exist_ok=True)
    if a.refresh:log(out,{'event':'explicit-refresh','target':str(out),'previous_package_preserved':True})
    if a.database!='WideWorldImporters' or a.server not in ['localhost','lpc:localhost','DESKTOP-K46JKQF']:raise SystemExit('Only the declared local sample instance is allowlisted.')
    drivers=pyodbc.drivers();driver=next((x for x in ['ODBC Driver 18 for SQL Server','ODBC Driver 17 for SQL Server','ODBC Driver 13 for SQL Server','SQL Server Native Client 11.0'] if x in drivers),None)
    if not driver:raise SystemExit('No installed Microsoft ODBC driver; use the documented .NET acquisition fallback.')
    # Shared-memory local connection, matching the previously verified development instance.
    conn=f'DRIVER={{{driver}}};SERVER={a.server};DATABASE={a.database};Trusted_Connection=yes;'
    c=pyodbc.connect(conn,autocommit=True,timeout=15);c.timeout=300;cur=c.cursor()
    log(out,{'event':'connected','driver':driver,'available_drivers':drivers,'auth':'windows','transport':'local-shared-memory-requested','connection_encryption':'installed-driver-default; not overridden','python':sys.version,'pyodbc':pyodbc.version,'pyarrow':pa.__version__})
    def run(name,sql,params=()):
        st=time.perf_counter();target=out/'sql/source'/f'{name}.sql';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(sql,encoding='utf-8')
        try:
            cursor=c.cursor();cursor.execute(sql,params);cols=[d[0] for d in cursor.description];rows=cursor.fetchall();csvwrite(out/'evidence/source_controls'/f'{name}.csv',cols,rows);log(out,{'event':'query','name':name,'parameters':params,'rows':len(rows),'elapsed_seconds':time.perf_counter()-st,'error':None});return cols,rows
        except Exception as e:log(out,{'event':'query','name':name,'parameters':params,'error':str(e)});raise
    cols,rows=run('00_identity',"SELECT @@SERVERNAME ServerName,CONVERT(nvarchar(128),SERVERPROPERTY('Edition')) Edition,CONVERT(nvarchar(128),SERVERPROPERTY('ProductVersion')) ProductVersion,DB_NAME() DatabaseName,CONVERT(nvarchar(33),SYSDATETIME(),126) SourceLocalTime")
    identity=dict(zip(cols,rows[0]));run('00_databases','SELECT name,state_desc FROM sys.databases ORDER BY name')
    run('00_isolation',"SELECT name,snapshot_isolation_state_desc,is_read_committed_snapshot_on FROM sys.databases WHERE name=DB_NAME()")
    sql="""SELECT s.name SchemaName,t.name TableName,c.name ColumnName,ty.name SqlType,c.max_length MaxLength,c.precision Precision,c.scale Scale,c.is_nullable IsNullable,c.column_id Ordinal,c.is_computed IsComputed,CONVERT(nvarchar(max),ep.value) Description,cc.definition ComputedDefinition,c.collation_name Collation FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id JOIN sys.columns c ON c.object_id=t.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id LEFT JOIN sys.extended_properties ep ON ep.class=1 AND ep.major_id=t.object_id AND ep.minor_id=c.column_id AND ep.name=N'Description' LEFT JOIN sys.computed_columns cc ON cc.object_id=c.object_id AND cc.column_id=c.column_id ORDER BY s.name,t.name,c.column_id"""
    cols,rows=run('00_schema',sql);metadata=[dict(zip(cols,r)) for r in rows];save(out/'schema/source_schema.json',metadata)
    cols,rows=run('00_keys',"SELECT OBJECT_SCHEMA_NAME(i.object_id) SchemaName,OBJECT_NAME(i.object_id) TableName,i.name KeyName,i.is_primary_key IsPrimaryKey,i.is_unique IsUnique,COL_NAME(ic.object_id,ic.column_id) ColumnName,ic.key_ordinal KeyOrdinal FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id WHERE i.is_unique=1 AND ic.key_ordinal>0 ORDER BY SchemaName,TableName,KeyName,KeyOrdinal")
    save(out/'schema/keys.json',[dict(zip(cols,r)) for r in rows])
    cols,rows=run('00_relationships',"SELECT fk.name Name,OBJECT_SCHEMA_NAME(fk.parent_object_id) ChildSchema,OBJECT_NAME(fk.parent_object_id) ChildTable,COL_NAME(fc.parent_object_id,fc.parent_column_id) ChildColumn,OBJECT_SCHEMA_NAME(fk.referenced_object_id) ParentSchema,OBJECT_NAME(fk.referenced_object_id) ParentTable,COL_NAME(fc.referenced_object_id,fc.referenced_column_id) ParentColumn,fk.is_disabled IsDisabled,fk.is_not_trusted IsNotTrusted FROM sys.foreign_keys fk JOIN sys.foreign_key_columns fc ON fc.constraint_object_id=fk.object_id ORDER BY Name,fc.constraint_column_id")
    save(out/'schema/relationships.json',[dict(zip(cols,r)) for r in rows])
    run('00_temporal',"SELECT s.name SchemaName,t.name TableName,t.temporal_type_desc TemporalType,OBJECT_SCHEMA_NAME(t.history_table_id) HistorySchema,OBJECT_NAME(t.history_table_id) HistoryTable FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id ORDER BY s.name,t.name")
    run('00_modules',"SELECT OBJECT_SCHEMA_NAME(object_id) SchemaName,OBJECT_NAME(object_id) ModuleName,definition FROM sys.sql_modules WHERE definition LIKE '%QuantityOnHand%' OR definition LIKE '%BackorderOrderID%' OR definition LIKE '%LineProfit%' OR definition LIKE '%ReceivedOuters%' OR definition LIKE '%Currency%' ORDER BY SchemaName,ModuleName")
    activity="SELECT r.session_id,r.command,r.status,s.program_name FROM sys.dm_exec_requests r JOIN sys.dm_exec_sessions s ON s.session_id=r.session_id WHERE r.session_id<>@@SPID AND s.is_user_process=1;"
    def quiet(label):
        for probe in range(12):
            suffix=label+('_probe'+str(probe) if probe else '')
            _,active=run('activity_'+suffix,activity)
            _,writes=run('transactions_'+suffix,"SELECT d.transaction_id,a.name,a.transaction_type,d.database_transaction_begin_time,d.database_transaction_log_record_count,st.session_id,s.is_user_process,s.program_name FROM sys.dm_tran_database_transactions d LEFT JOIN sys.dm_tran_active_transactions a ON a.transaction_id=d.transaction_id LEFT JOIN sys.dm_tran_session_transactions st ON st.transaction_id=d.transaction_id LEFT JOIN sys.dm_exec_sessions s ON s.session_id=st.session_id WHERE d.database_id=DB_ID() AND d.database_transaction_log_record_count>0")
            if active or any(r[7] for r in writes):raise RuntimeError('Concurrent user activity observed. Acquisition certification stopped; arrange a quiescent window.')
            if not writes:return
            log(out,{'event':'verified-wait-for-quiescence','label':label,'probe':probe,'transactions':[tuple(r) for r in writes],'business_export_paused':True})
            time.sleep(1)
        raise RuntimeError('Logged transactions persisted without an identified user workload; acquisition stopped pending quiescence.')
    present=[t for t in TABLES if any(m['SchemaName']+'.'+m['TableName']==t for m in metadata)]
    if not all(t in present for t in TABLES[:10]):raise RuntimeError('Required core or invoice entity absent')
    def counts(label):return run(label,' UNION ALL '.join(f"SELECT '{t}' Entity,COUNT_BIG(*) Records FROM [{t.split('.')[0]}].[{t.split('.')[1]}]" for t in present))[1]
    quiet('start');before=counts('counts_before')
    run('date_bounds',"SELECT 'orders' Entity,MIN(OrderDate) MinDate,MAX(OrderDate) MaxDate FROM Sales.Orders UNION ALL SELECT 'purchases',MIN(OrderDate),MAX(OrderDate) FROM Purchasing.PurchaseOrders UNION ALL SELECT 'invoices',MIN(InvoiceDate),MAX(InvoiceDate) FROM Sales.Invoices")
    run('reference_unpicked',"SELECT COUNT_BIG(*) Lines,COUNT(DISTINCT o.OrderID) Orders,SUM(CONVERT(bigint,ol.Quantity)-ol.PickedQuantity) Units FROM Sales.OrderLines ol JOIN Sales.Orders o ON o.OrderID=ol.OrderID WHERE ol.Quantity>ol.PickedQuantity")
    run('reference_may',"SELECT COUNT_BIG(*) Lines,COUNT(DISTINCT o.OrderID) Orders,SUM(CONVERT(bigint,ol.Quantity)-ol.PickedQuantity) Units FROM Sales.OrderLines ol JOIN Sales.Orders o ON o.OrderID=ol.OrderID WHERE ol.Quantity>ol.PickedQuantity AND o.OrderDate>=? AND o.OrderDate<?",('2016-05-01','2016-06-01'))
    run('reference_incoming',"SELECT COUNT(DISTINCT po.PurchaseOrderID) Orders,COUNT_BIG(*) Lines,SUM((CONVERT(bigint,pl.OrderedOuters)-pl.ReceivedOuters)*si.QuantityPerOuter) Units FROM Purchasing.PurchaseOrders po JOIN Purchasing.PurchaseOrderLines pl ON pl.PurchaseOrderID=po.PurchaseOrderID JOIN Warehouse.StockItems si ON si.StockItemID=pl.StockItemID WHERE po.IsOrderFinalized=0 AND pl.IsOrderLineFinalized=0 AND pl.OrderedOuters>pl.ReceivedOuters")
    baseline=out/'sql/source/01_cutoff_baseline.sql'
    if baseline.exists():run('01_cutoff_baseline',baseline.read_text(encoding='utf-8'))
    previous=out/'sql/source/reference_workflows'
    if previous.exists():
        for f in sorted(previous.glob('*.sql')):
            text=f.read_text(encoding='utf-8-sig');text=re.sub(r'(?m)^GO\s*$','',text);text=re.sub(r'SET STATISTICS (?:TIME|IO) (?:ON|OFF);','',text)
            # Results may have multiple result sets: capture each, including empty headers.
            cursor=c.cursor();start=time.perf_counter();cursor.execute(text);i=0
            while True:
                if cursor.description:cols=[d[0] for d in cursor.description];rr=cursor.fetchall();csvwrite(out/'evidence/source_controls'/f'{f.stem}_{i}.csv',cols,rr);log(out,{'event':'reference','name':f.stem,'result_set':i,'rows':len(rr),'elapsed_seconds':time.perf_counter()-start});i+=1
                if not cursor.nextset():break
    mappings=[];files=[];omitted=[]
    for t in present:
        quiet(t.replace('.','_'));meta=[m for m in metadata if m['SchemaName']+'.'+m['TableName']==t];selected=[m for m in meta if m['SqlType'] in SUPPORTED];omitted.extend({'table':t,'column':m['ColumnName'],'type':m['SqlType'],'reason':'binary/spatial/unsupported unused type omitted explicitly'} for m in meta if m not in selected)
        fields=[];select=[]
        for m in selected:
            typ=m['SqlType'];name=m['ColumnName']
            at={'int':pa.int32(),'bigint':pa.int64(),'smallint':pa.int16(),'tinyint':pa.uint8(),'bit':pa.bool_(),'date':pa.date32()}.get(typ)
            if typ in ('decimal','numeric'):at=pa.decimal128(m['Precision'],m['Scale'])
            elif typ in ('money','smallmoney'):at=pa.decimal128(19 if typ=='money' else 10,4)
            elif typ in ('datetime','datetime2','smalldatetime'):at=pa.timestamp('us')
            if at is None:at=pa.string()
            fields.append(pa.field(name,at,nullable=m['IsNullable']))
            if typ in ('datetime','datetime2','smalldatetime'):
                select.append(f'CONVERT(nvarchar(33),[{name}],126) AS [{name}]')
                if typ=='datetime2' and m['Scale']>6:fields.append(pa.field(name+'__100ns',pa.int8()));m['precision_companion']=name+'__100ns'
            else:select.append(f'[{name}]')
            mappings.append({'table':t,'column':name,'sql_type':typ,'precision':m['Precision'],'scale':m['Scale'],'arrow_type':str(at),'precision_companion':m.get('precision_companion'),'mapping':'datetime2 scale7: microsecond timestamp + residual 100ns tick; timezone naive'} )
        order=[k['ColumnName'] for k in load(out/'schema/keys.json') if k['SchemaName']+'.'+k['TableName']==t and k['IsPrimaryKey']]
        sql='SELECT '+','.join(select)+f' FROM [{t.split(".")[0]}].[{t.split(".")[1]}]'+(' ORDER BY '+','.join('['+x+']' for x in order) if order else '')
        (out/'sql/source'/f'export_{t}.sql').write_text(sql,encoding='utf-8');cursor=c.cursor();cursor.execute(sql);schema=pa.schema(fields);path=out/'data/raw'/f'{t}.parquet';path.parent.mkdir(parents=True,exist_ok=True);writer=pq.ParquetWriter(path,schema,compression='zstd');count=0;start=time.perf_counter()
        while batch:=cursor.fetchmany(5000):
            converted=[]
            for row in batch:
                d={}
                for m,v in zip(selected,row):
                    typ=m['SqlType'];name=m['ColumnName']
                    if typ in ('datetime','datetime2','smalldatetime') and v is not None:
                        s=str(v);frac=(s.split('.')[1] if '.' in s else '').ljust(7,'0');d[name]=datetime.datetime.fromisoformat(s.split('.')[0]+'.'+frac[:6])
                        if m.get('precision_companion'):d[m['precision_companion']]=int(frac[6])
                    else:
                        d[name]=str(v) if typ in ('uniqueidentifier',) and v is not None else v
                        if m.get('precision_companion'):d[m['precision_companion']]=None
                converted.append(d)
            writer.write_table(pa.Table.from_pylist(converted,schema=schema));count+=len(batch)
        writer.close();files.append({'path':str(path.relative_to(out)).replace('\\','/'),'table':t,'rows':count,'columns':[{'name':f.name,'type':str(f.type),'nullable':f.nullable} for f in schema],'sha256':sha(path),'bytes':path.stat().st_size,'exported_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()});log(out,{'event':'export','table':t,'rows':count,'seconds':time.perf_counter()-start,'file':files[-1]});print(t,count,flush=True)
    quiet('end');after=counts('counts_after');c.close();log(out,{'event':'source_closed'})
    if [tuple(x) for x in before]!=[tuple(x) for x in after]:raise RuntimeError('Pre/post counts differ; acquisition remains uncertified')
    save(out/'schema/type_mapping.json',mappings)
    save(out/'manifest.json',{'dataset_version':'wwi-data-v1-2026-10-08','package_version':'1.0.0','source':identity,'business_date_bounds':{'start':'2013-01-01','end_inclusive':'2016-05-31'},'source_schema_sha256':sha(out/'schema/source_schema.json'),'files':files,'omitted_fields':omitted,'omitted_tables':['archive tables except future explicit refresh; no proven historic snapshot','DW not acquired; presence recorded separately'],'consistency':'observed-quiescent-boundary-probes-and-matching-counts; not atomic','time_semantics':'source dates/timestamps are naive sample business times; never UTC-labelled; acquisition log UTC explicit','null_semantics':'Arrow null preserved; empty string distinct','string_semantics':'SQL collation recorded; local exact-ID joins; case-insensitive UI name search uses Unicode casefold and is not SQL collation equivalence','query_version':'v1','metric_version':'v0','tool_versions':{'python':sys.version,'pyarrow':pa.__version__,'pyodbc':pyodbc.version,'driver':driver},'attribution':{'publisher':'Microsoft Wide World Importers simulated sample','source':'https://github.com/microsoft/sql-server-samples/releases/tag/wide-world-importers-v1.0','notice':'not audited operations; local binary lineage not independently authenticated'},'acquisition_status':'pass-observed-stable','p1_status':'pending','p2_status':'pending'})
if __name__=='__main__':main()
