"""Does the loaded data follow ERPNext's own schema? Runs INSIDE the backend container (read-only queries).
Checks, per document type used: (1) rows exist, (2) every mandatory field is filled, (3) every Link field points at a record that exists,
plus accounting balance (GL debits = credits) and stock consistency (stock ledger = Bin = loaded holdings).
Also lists everything we ADDED to the stock schema (custom fields)."""
import json, frappe
frappe.init(site='frontend', sites_path='.'); frappe.connect()
q = lambda s, *a: frappe.db.sql(s, a)
DOCTYPES = ['Customer', 'Supplier', 'Item', 'Sales Person', 'Territory', 'Customer Group', 'Item Group', 'Sales Order', 'Sales Invoice',
            'Purchase Order', 'Purchase Receipt', 'Stock Reconciliation']
SKIP_TYPES = {'Section Break', 'Column Break', 'Tab Break', 'HTML', 'Button', 'Heading', 'Image', 'Fold', 'Table', 'Table MultiSelect'}
report = {'doctypes': {}}
total_orphans = total_missing = 0
for dt in DOCTYPES:
    meta = frappe.get_meta(dt)
    tables = [(dt, meta)] + [(f.options, frappe.get_meta(f.options)) for f in meta.get_table_fields()]
    for name, m in tables:
        n = q(f"select count(*) from `tab{name}`")[0][0]
        row = {'rows': n, 'mandatory_missing': {}, 'orphan_links': {}}
        if n:
            for f in m.fields:
                if f.fieldtype in SKIP_TYPES or not f.fieldname:
                    continue
                if f.reqd and not f.default and f.fieldtype not in ('Check',):
                    bad = q(f"select count(*) from `tab{name}` where `{f.fieldname}` is null or `{f.fieldname}`=''")[0][0]
                    if bad:
                        row['mandatory_missing'][f.fieldname] = bad; total_missing += bad
                if f.fieldtype == 'Link' and f.options and frappe.db.exists('DocType', f.options) and not frappe.get_meta(f.options).issingle:
                    bad = q(f"select count(*) from `tab{name}` t left join `tab{f.options}` y on y.name=t.`{f.fieldname}` "
                            f"where t.`{f.fieldname}` is not null and t.`{f.fieldname}`!='' and y.name is null")[0][0]
                    if bad:
                        row['orphan_links'][f"{f.fieldname} -> {f.options}"] = bad; total_orphans += bad
        report['doctypes'][name] = row
# accounting and stock integrity
gl = q("select round(sum(debit),2), round(sum(credit),2), count(*) from `tabGL Entry` where is_cancelled=0")[0]
report['gl_entries'] = {'debit': float(gl[0]), 'credit': float(gl[1]), 'balanced': abs(float(gl[0]) - float(gl[1])) < 0.01, 'rows': gl[2]}
sle_vs_bin = q("select count(*) from tabBin b join (select item_code, sum(actual_qty) q from `tabStock Ledger Entry` where is_cancelled=0 group by 1) s "
               "on s.item_code=b.item_code where abs(b.actual_qty - s.q) > 0.0001")[0][0]
report['stock_ledger_matches_bin_all_items'] = (sle_vs_bin == 0); report['items_where_ledger_differs_from_bin'] = sle_vs_bin
report['negative_stock_items'] = q("select count(*) from tabBin where actual_qty < 0")[0][0]
report['invoice_lines_not_linked_to_sales_order'] = q("select count(*) from `tabSales Invoice Item` i join `tabSales Invoice` s on s.name=i.parent where s.docstatus=1 and (i.sales_order is null or i.sales_order='')")[0][0]
report['invoice_lines_total'] = q("select count(*) from `tabSales Invoice Item` i join `tabSales Invoice` s on s.name=i.parent where s.docstatus=1")[0][0]
report['docstatus'] = {dt: dict(q(f"select docstatus, count(*) from `tab{dt}` group by 1")) for dt in ['Sales Order', 'Sales Invoice', 'Purchase Order', 'Purchase Receipt']}
# what we added to the stock schema
cf = q("select dt, fieldname, fieldtype from `tabCustom Field` order by dt, idx")
report['custom_fields_added'] = {}
for dt, fn, ft in cf:
    report['custom_fields_added'].setdefault(dt, []).append(f"{fn} ({ft})")
report['doctypes_created_by_us'] = [r[0] for r in q("select name from tabDocType where custom=1")]
report['totals'] = {'orphan_link_rows': total_orphans, 'mandatory_missing_rows': total_missing}
# size of the real app (for the "hundreds of pages" question)
report['app_surface'] = {
    'list_views (doctypes with a list page)': q("select count(*) from tabDocType where istable=0 and issingle=0 and custom=0")[0][0],
    'single_pages (doctypes that are settings forms)': q("select count(*) from tabDocType where issingle=1")[0][0],
    'reports': q("select count(*) from tabReport")[0][0], 'workspaces': q("select count(*) from tabWorkspace")[0][0],
    'desk_pages': q("select count(*) from tabPage")[0][0],
    'doctypes_with_data_we_loaded': len([d for d, r in report['doctypes'].items() if r['rows']]),
}
json.dump(report, open('wwi_load/schema_check.json', 'w'), indent=1, default=str)
print(json.dumps(report, indent=1, default=str)[:6000])
frappe.destroy()
