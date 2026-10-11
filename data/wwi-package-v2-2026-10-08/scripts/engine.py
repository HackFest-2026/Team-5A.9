"""Allowlisted parameterized read queries. No caller-provided SQL or identifiers."""
from __future__ import annotations
from common import db,load,query
from request_models import Request
from pathlib import Path
METRICS=['M01','M02','M03','M04','M05','M12_orders_category']
def order_where(r,alias='l'):
    terms=[f'{alias}.ScenarioID=?'];params=[r.scenario_id];f=r.filters
    if r.date_basis!='order_date':raise ValueError('Order measures require explicit order_date; completion/delivery basis is a different operation.')
    if r.start:terms.extend([f'{alias}.OrderDate>=?',f'{alias}.OrderDate<?']);params.extend([r.start,r.end])
    for field,col in [('customer_id','CustomerID'),('stock_item_id','StockItemID'),('order_id','OrderID'),('order_line_id','OrderLineID')]:
        value=getattr(f,field)
        if value is not None:terms.append(f'{alias}.{col}=?');params.append(value)
    if f.supplier_id is not None:
        terms.append(f'EXISTS(SELECT 1 FROM analytics.items si WHERE si.StockItemID={alias}.StockItemID AND si.ScenarioID={alias}.ScenarioID AND si.SupplierID=?)');params.append(f.supplier_id)
    if f.stock_group_id is not None:
        terms.append(f'EXISTS(SELECT 1 FROM raw.Warehouse_StockItemStockGroups b WHERE b.StockItemID={alias}.StockItemID AND b.StockGroupID=?)');params.append(f.stock_group_id)
    if f.purchase_order_id is not None or f.purchase_line_id is not None:raise ValueError('Purchase ID cannot filter order measures without an allocation rule.')
    if f.status=='quantity-not-yet-picked':terms.append(f'{alias}.UnpickedUnits>0')
    elif f.status=='picking-incomplete':terms.append(f'{alias}.OrderPickingCompletedWhen IS NULL')
    elif f.status=='picking-complete':terms.append(f'{alias}.OrderPickingCompletedWhen IS NOT NULL')
    elif f.status!='all':raise ValueError('Purchasing status is invalid for orders.')
    return ' AND '.join(terms),params
def metric_sql(mid,r):
    if mid in ['M01','M02','M03','M12_orders_category']:
        where,params=order_where(r)
        if mid=='M01':sql=f"SELECT COUNT(DISTINCT l.OrderID)::BIGINT AS value FROM analytics.order_lines l WHERE {where}"
        elif mid=='M02':sql=f"SELECT COALESCE(SUM(l.UnpickedUnits),0)::BIGINT AS value FROM analytics.order_lines l WHERE {where}"
        elif mid=='M03':sql=f"SELECT COUNT(DISTINCT CASE WHEN l.UnpickedUnits>0 THEN l.OrderID END)::BIGINT AS value FROM analytics.order_lines l WHERE {where}"
        else:sql=f"SELECT COALESCE(cat.CustomerCategoryName,'unknown') category,COUNT(DISTINCT l.OrderID)::BIGINT AS value FROM analytics.order_lines l LEFT JOIN raw.Sales_Customers c ON c.CustomerID=l.CustomerID LEFT JOIN raw.Sales_CustomerCategories cat USING(CustomerCategoryID) WHERE {where} GROUP BY 1 ORDER BY 1"
        return sql,params
    if mid=='M04':
        if r.date_basis!='none' or r.start:raise ValueError('Holdings are undated stored state; use date_basis=none and no interval.')
        if any(getattr(r.filters,k) is not None for k in ['customer_id','order_id','order_line_id','purchase_order_id','purchase_line_id']) or r.filters.status!='all':raise ValueError('Holdings cannot accept customer/order/purchase/status filters.')
        terms=['h.ScenarioID=?'];params=[r.scenario_id]
        if r.filters.stock_item_id is not None:terms.append('h.StockItemID=?');params.append(r.filters.stock_item_id)
        if r.filters.supplier_id is not None:terms.append('s.SupplierID=?');params.append(r.filters.supplier_id)
        if r.filters.stock_group_id is not None:terms.append('EXISTS(SELECT 1 FROM raw.Warehouse_StockItemStockGroups b WHERE b.StockItemID=h.StockItemID AND b.StockGroupID=?)');params.append(r.filters.stock_group_id)
        return 'SELECT h.StockItemID,s.StockItemName,h.QuantityOnHand,h.ReorderLevel,h.TargetStockLevel FROM analytics.holdings h JOIN analytics.items s ON s.StockItemID=h.StockItemID AND s.ScenarioID=h.ScenarioID WHERE '+' AND '.join(terms)+' ORDER BY h.StockItemID LIMIT ? OFFSET ?',params+[r.limit,r.offset]
    if mid=='M05':
        if r.date_basis not in ['purchase_order_date','expected_delivery_date','none']:raise ValueError('Incoming measure supports purchase_order_date or expected_delivery_date; not order_date.')
        if any(getattr(r.filters,k) is not None for k in ['customer_id','order_id','order_line_id']) or r.filters.status not in ['all','incoming']:raise ValueError('Incoming supply is not allocated by customer/order.')
        terms=['i.ScenarioID=?'];params=[r.scenario_id]
        for f,col in [('stock_item_id','StockItemID'),('supplier_id','SupplierID'),('purchase_order_id','PurchaseOrderID'),('purchase_line_id','PurchaseOrderLineID')]:
            value=getattr(r.filters,f)
            if value is not None:terms.append('i.'+col+'=?');params.append(value)
        if r.filters.stock_group_id is not None:terms.append('EXISTS(SELECT 1 FROM raw.Warehouse_StockItemStockGroups b WHERE b.StockItemID=i.StockItemID AND b.StockGroupID=?)');params.append(r.filters.stock_group_id)
        if r.start:
            col={'purchase_order_date':'PurchaseOrderDate','expected_delivery_date':'ExpectedDeliveryDate'}[r.date_basis];terms.extend(['i.'+col+'>= ?','i.'+col+'< ?']);params.extend([r.start,r.end])
        return 'SELECT COALESCE(SUM(IncomingUnits),0)::BIGINT AS value FROM analytics.incoming i WHERE '+' AND '.join(terms),params
    raise ValueError('Unsupported or unverified measure: '+mid)
def execute_metric(package,mid,r):
    r=Request.model_validate(r) if isinstance(r,dict) else r
    catalog=Path(package)/'catalog/measures.json'
    if catalog.exists():
        accepted={m['id'] for m in load(catalog)['items'] if m['status']=='verified'}
        if mid not in accepted:raise ValueError('Measure not exposed as verified')
    sql,params=metric_sql(mid,r);c=db(package);cols,rows=query(c,sql,params);c.close()
    return {'dataset_version':r.dataset_version,'scenario_id':r.scenario_id,'metric_id':mid,'date_basis':r.date_basis,'applied_filters':r.model_dump(mode='json'),'columns':cols,'rows':[dict(zip(cols,row)) for row in rows],'query_id':mid,'limit':r.limit,'offset':r.offset}
def chart_sql(cid,r):
    if cid in ['monthly-orders','top-unpicked','picking-status','category-orders']:
        where,params=order_where(r)
        if cid=='monthly-orders':
            return f"WITH a AS(SELECT strftime(OrderDate,'%Y-%m') AS month,COUNT(DISTINCT OrderID)::BIGINT AS value FROM analytics.order_lines l WHERE {where} GROUP BY 1),spine AS(SELECT DISTINCT Month FROM analytics.calendar WHERE Date>=? AND Date<?) SELECT spine.Month AS month,COALESCE(a.value,0)::BIGINT AS value FROM spine LEFT JOIN a ON a.month=spine.Month ORDER BY 1",params+[r.start or '2013-01-01',r.end or '2016-06-01']
        if cid=='top-unpicked':return f"SELECT l.StockItemID,s.StockItemName AS label,SUM(l.UnpickedUnits)::BIGINT AS value FROM analytics.order_lines l JOIN analytics.items s ON s.StockItemID=l.StockItemID AND s.ScenarioID=l.ScenarioID WHERE {where} AND l.UnpickedUnits>0 GROUP BY 1,2 ORDER BY value DESC,l.StockItemID LIMIT ?",params+[min(r.limit,20)]
        if cid=='picking-status':return f"SELECT CASE WHEN l.OrderPickingCompletedWhen IS NULL THEN 'Picking incomplete' ELSE 'Picking complete' END AS label,COUNT(DISTINCT l.OrderID)::BIGINT AS value FROM analytics.order_lines l WHERE {where} GROUP BY 1 ORDER BY 1",params
        return metric_sql('M12_orders_category',r)
    if cid=='holdings-reorder':return metric_sql('M04',r)
    if cid=='incoming-supplier':
        # Reuse the canonical approved incoming predicate/parameters, then change only the grouping.
        sql,params=metric_sql('M05',r);sql=sql.replace('SELECT COALESCE(SUM(IncomingUnits),0)::BIGINT AS value','SELECT i.SupplierID,s.SupplierName AS label,COALESCE(SUM(IncomingUnits),0)::BIGINT AS value');sql=sql.replace('FROM analytics.incoming i WHERE','FROM analytics.incoming i JOIN raw.Purchasing_Suppliers s ON s.SupplierID=i.SupplierID WHERE');return sql+' GROUP BY i.SupplierID,s.SupplierName ORDER BY value DESC,i.SupplierID',params
    raise ValueError('Unsupported chart')
def execute_chart(package,cid,r):
    r=Request.model_validate(r) if isinstance(r,dict) else r;catalog=load(Path(package)/'catalog/charts.json');entry=next((x for x in catalog['items'] if x['id']==cid),None)
    if not entry:raise ValueError('Chart not published')
    sql,params=chart_sql(cid,r);c=db(package);cols,rows=query(c,sql,params);c.close();result_rows=[dict(zip(cols,row)) for row in rows]
    if cid=='monthly-orders':
        import datetime,calendar
        for row in result_rows:
            y,m=map(int,row['month'].split('-'));first=datetime.date(y,m,1);next_month=datetime.date(y+(m==12),1 if m==12 else m+1,1)
            row['partial_selected_month']=bool((r.start and r.start>first) or (r.end and r.end<next_month))
            row['archive_end_month']=row['month']=='2016-05'
    return {'dataset_version':r.dataset_version,'scenario_id':r.scenario_id,'chart_id':cid,'measure_id':entry['measure_id'],'date_basis':r.date_basis,'applied_filters':r.model_dump(mode='json'),'rows':result_rows,'caption':entry['caption']}
def records(package,entity,r):
    r=Request.model_validate(r) if isinstance(r,dict) else r;f=r.filters;params=[]
    if entity in ['orders','order_lines']:
        # Record filtering is independently explicit for completion and expected dates.
        basis=r.date_basis
        if basis not in ['order_date','expected_delivery_date','picking_completed_time']:raise ValueError('Unsupported order-record date basis')
        canonical=r.model_copy(update={'date_basis':'order_date','start':None,'end':None});where,params=order_where(canonical)
        if r.start:col={'order_date':'OrderDate','expected_delivery_date':'ExpectedDeliveryDate','picking_completed_time':'LinePickingCompletedWhen' if entity=='order_lines' else 'OrderPickingCompletedWhen'}[basis];where+=f' AND l.{col}>=? AND l.{col}<?';params.extend([r.start,r.end])
        if entity=='orders':sql='SELECT DISTINCT l.OrderID,l.CustomerID,c.CustomerName,l.OrderDate,l.ExpectedDeliveryDate,l.OrderPickingCompletedWhen,l.BackorderOrderID FROM analytics.order_lines l JOIN raw.Sales_Customers c ON c.CustomerID=l.CustomerID WHERE '+where+' ORDER BY l.OrderID'
        else:sql='SELECT l.*,s.StockItemName FROM analytics.order_lines l JOIN analytics.items s ON s.StockItemID=l.StockItemID AND s.ScenarioID=l.ScenarioID WHERE '+where+' ORDER BY l.OrderID,l.OrderLineID'
    elif entity in ['items','holdings']:
        if r.date_basis!='none' or r.start or any(getattr(f,k) is not None for k in ['customer_id','order_id','order_line_id','purchase_order_id','purchase_line_id']) or f.status!='all':raise ValueError('Item/holdings detail needs stored undated scope and item/supplier/group filters only')
        where='s.ScenarioID=?';params=[r.scenario_id]
        if f.stock_item_id is not None:where+=' AND s.StockItemID=?';params.append(f.stock_item_id)
        if f.supplier_id is not None:where+=' AND s.SupplierID=?';params.append(f.supplier_id)
        if f.stock_group_id is not None:where+=' AND EXISTS(SELECT 1 FROM raw.Warehouse_StockItemStockGroups b WHERE b.StockItemID=s.StockItemID AND b.StockGroupID=?)';params.append(f.stock_group_id)
        sql='SELECT s.StockItemID,s.StockItemName,s.SupplierID,s.QuantityPerOuter,s.UnitPackageID,s.OuterPackageID,h.QuantityOnHand,h.ReorderLevel,h.TargetStockLevel FROM analytics.items s JOIN analytics.holdings h ON h.StockItemID=s.StockItemID AND h.ScenarioID=s.ScenarioID WHERE '+where+' ORDER BY s.StockItemID'
    elif entity in ['purchase_orders','purchase_lines']:
        if r.date_basis not in ['none','purchase_order_date','expected_delivery_date']:raise ValueError('Invalid purchasing date basis')
        if any(getattr(f,k) is not None for k in ['customer_id','order_id','order_line_id']) or f.status not in ['all','incoming','all-history']:raise ValueError('Purchasing records cannot assume customer/order allocation')
        where="?='base'";params=[r.scenario_id]
        for field,col in [('stock_item_id','l.StockItemID'),('purchase_order_id','p.PurchaseOrderID'),('purchase_line_id','l.PurchaseOrderLineID'),('supplier_id','p.SupplierID')]:
            value=getattr(f,field)
            if value is not None:where+=' AND '+col+'=?';params.append(value)
        if f.stock_group_id is not None:where+=' AND EXISTS(SELECT 1 FROM raw.Warehouse_StockItemStockGroups b WHERE b.StockItemID=l.StockItemID AND b.StockGroupID=?)';params.append(f.stock_group_id)
        if f.status=='incoming':where+=' AND NOT p.IsOrderFinalized AND NOT l.IsOrderLineFinalized AND l.OrderedOuters>l.ReceivedOuters'
        if r.start:col='p.OrderDate' if r.date_basis=='purchase_order_date' else 'p.ExpectedDeliveryDate';where+=' AND '+col+'>=? AND '+col+'<?';params.extend([r.start,r.end])
        sql='SELECT p.PurchaseOrderID,l.PurchaseOrderLineID,l.StockItemID,p.SupplierID,su.SupplierName,p.OrderDate PurchaseOrderDate,p.ExpectedDeliveryDate,l.OrderedOuters,l.ReceivedOuters,l.LastReceiptDate,p.IsOrderFinalized,l.IsOrderLineFinalized,s.QuantityPerOuter,(CAST(l.OrderedOuters AS BIGINT)-l.ReceivedOuters)*s.QuantityPerOuter ArithmeticRemainingUnits FROM raw.Purchasing_PurchaseOrders p JOIN raw.Purchasing_PurchaseOrderLines l USING(PurchaseOrderID) JOIN raw.Warehouse_StockItems s USING(StockItemID) JOIN raw.Purchasing_Suppliers su ON su.SupplierID=p.SupplierID WHERE '+where+' ORDER BY p.PurchaseOrderID,l.PurchaseOrderLineID'
        if entity=='purchase_orders':sql='SELECT DISTINCT p.PurchaseOrderID,p.SupplierID,su.SupplierName,p.OrderDate PurchaseOrderDate,p.ExpectedDeliveryDate,p.IsOrderFinalized FROM raw.Purchasing_PurchaseOrders p JOIN raw.Purchasing_PurchaseOrderLines l USING(PurchaseOrderID) JOIN raw.Purchasing_Suppliers su ON su.SupplierID=p.SupplierID WHERE '+where+' ORDER BY p.PurchaseOrderID'
    elif entity in ['customers','suppliers']:
        if r.date_basis!='none' or r.start or f.status!='all' or any(getattr(f,k) is not None for k in ['stock_group_id','order_id','order_line_id','purchase_order_id','purchase_line_id']):raise ValueError('Lookup requires undated lookup-ID scope')
        if entity=='customers':
            if f.supplier_id is not None or f.stock_item_id is not None:raise ValueError('Unsupported customer lookup filter')
            sql='SELECT CustomerID,CustomerName,CustomerCategoryID,BuyingGroupID FROM raw.Sales_Customers WHERE (? IS NULL OR CustomerID=?) ORDER BY CustomerID';params=[f.customer_id,f.customer_id]
        else:
            if f.customer_id is not None:raise ValueError('Unsupported supplier lookup filter')
            sql='SELECT SupplierID,SupplierName,SupplierCategoryID FROM raw.Purchasing_Suppliers WHERE (? IS NULL OR SupplierID=?) ORDER BY SupplierID';params=[f.supplier_id,f.supplier_id]
            if f.stock_item_id is not None:raise ValueError('Resolve item nominated supplier ID first; do not silently ignore item selection')
    else:raise ValueError('Unsupported entity')
    c=db(package);_,count_rows=query(c,'SELECT COUNT(*) AS RecordCount FROM ('+sql+') q',params);count=count_rows[0][0];cols,rows=query(c,sql+' LIMIT ? OFFSET ?',params+[r.limit,r.offset]);c.close()
    return {'dataset_version':r.dataset_version,'scenario_id':r.scenario_id,'entity':entity,'date_basis':r.date_basis,'applied_filters':r.model_dump(mode='json'),'total_rows':count,'rows':[dict(zip(cols,row)) for row in rows],'limit':r.limit,'offset':r.offset,'has_more':r.offset+len(rows)<count,'provenance':'synthetic fixture' if r.scenario_id!='base' else 'source stored sample state'}



