"""Feasibility spike: a prototype VACP-style bridge (window.__vacp) injected into the stock ERPNext desk, no rebuild of ERPNext.
Every expected value comes from SQL against the ERPNext database, and UI facts are read from the page itself.
Usage: python spike_vacp_erpnext.py [base_url]        (needs playwright; docker access for the SQL oracle)"""
import asyncio, json, subprocess, sys, time
from playwright.async_api import async_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://10.9.0.108:8081").rstrip("/")
DBNAME = "_5e5899d8398b5f7b"
failures, timings = [], []


def sql(q):
    out = subprocess.run(["docker", "exec", "wwi-erpnext-db-1", "mariadb", "-uroot", "-padmin", "-N", "-e", f"use `{DBNAME}`; {q}"],
                         capture_output=True, text=True, check=True).stdout.strip()
    return out


def check(cond, msg):
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


# ---- prototype bridge: this is the code that would become the real erpnext-webui-bridge --------------------------------
BRIDGE = r"""
(() => {
  const DOCTYPES = {'sales-orders':'Sales Order','invoices':'Sales Invoice','customers':'Customer','items':'Item','purchase-orders':'Purchase Order'};
  const STATUS = {'Sales Order':['Draft','On Hold','To Deliver and Bill','To Bill','To Deliver','Completed','Cancelled','Closed'],
                  'Sales Invoice':['Draft','Paid','Unpaid','Overdue','Cancelled','Return','Credit Note Issued']};
  const ISO = /^\d{4}-\d{2}-\d{2}$/;
  const DATEFIELD = {'Sales Order':'transaction_date','Sales Invoice':'posting_date','Purchase Order':'transaction_date'};
  const ready = () => typeof frappe !== 'undefined' && frappe.session && frappe.session.user && frappe.session.user !== 'Guest';
  const need = () => { if (!ready()) throw new Error('Not logged in to ERPNext'); };
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  async function listReady(doctype, ms = 10000) {
    const t0 = Date.now();
    while (Date.now() - t0 < ms) {
      if (window.cur_list && cur_list.doctype === doctype && cur_list.data && !cur_list.__loading && document.querySelector('.list-count')?.innerText.trim()) { await sleep(150); return true; }
      await sleep(100);
    }
    return false;
  }
  async function idle(ms = 10000) { const t0 = Date.now(); let quiet = 0;
    while (Date.now() - t0 < ms) { quiet = (frappe.request.ajax_count || 0) === 0 ? quiet + 1 : 0; if (quiet >= 4) return; await sleep(100); } }
  async function applyFilters(doctype, filters) {   // filters: [[field, op, value], ...]
    if (!(window.cur_list && cur_list.doctype === doctype && frappe.get_route()[0] === 'List')) { frappe.set_route('List', doctype); await listReady(doctype); }
    await cur_list.filter_area.set(filters.map(([f, op, v]) => [doctype, f, op, v]));
    await sleep(200); await idle(); await listReady(doctype); return state();
  }
  const current = (doctype) => (window.cur_list && cur_list.doctype === doctype) ? cur_list.filter_area.get().map(x => [x[1], x[2], x[3]]) : [];
  const state = async () => {
    const route = ready() ? frappe.get_route() : [];
    const s = {logged_in: ready(), route, url: location.pathname + location.search};
    if (ready() && window.cur_list && route[0] === 'List') {
      s.doctype = cur_list.doctype;
      s.filters = cur_list.filter_area.get().map(f => [f[1], f[2], f[3]]);
      s.rows_on_screen = cur_list.data.length;
      s.count_label = document.querySelector('.list-count')?.innerText.trim();
      s.total = (await frappe.call({method:'frappe.client.get_count', args:{doctype: cur_list.doctype, filters: cur_list.get_filters_for_args()}})).message;
    }
    return s;
  };
  const actions = {
    'erpnext.navigate': async ({view, keep_filters}) => {
      need(); const dt = DOCTYPES[view]; if (!dt) throw new Error('unknown view ' + view + '; one of ' + Object.keys(DOCTYPES));
      frappe.set_route('List', dt); await listReady(dt);
      // ERPNext remembers each user's last list filters; start from a clean list unless asked to keep them
      if (!keep_filters && cur_list.filter_area.get().length) { await cur_list.filter_area.clear(); await sleep(200); await idle(); await listReady(dt); }
      return state();
    },
    'erpnext.clear_filters': async ({doctype}) => {
      need(); if (!(window.cur_list && cur_list.doctype === doctype)) throw new Error('list ' + doctype + ' is not open');
      await cur_list.filter_area.clear(); await sleep(200); await idle(); await listReady(doctype); return state();
    },
    'erpnext.set_period': async ({doctype, start, end}) => {
      need(); const f = DATEFIELD[doctype]; if (!f) throw new Error('no date field for ' + doctype);
      if (!ISO.test(start) || !ISO.test(end) || start > end) throw new Error('bad period');
      return applyFilters(doctype, current(doctype).filter(x => x[0] !== f).concat([[f, 'Between', [start, end]]]));
    },
    'erpnext.set_filters': async ({doctype, status, customer}) => {
      need(); const add = [];
      if (status !== undefined) { if (!(STATUS[doctype] || []).includes(status)) throw new Error('invalid status ' + status + ' for ' + doctype + '; one of ' + (STATUS[doctype] || [])); add.push(['status', '=', status]); }
      if (customer !== undefined) { if (!(await frappe.db.exists('Customer', customer))) throw new Error('unknown customer ' + customer + ' (use erpnext.resolve first)'); add.push(['customer', '=', customer]); }
      const keys = add.map(x => x[0]);
      return applyFilters(doctype, current(doctype).filter(x => !keys.includes(x[0])).concat(add));
    },
    'erpnext.open_record': async ({doctype, name}) => {
      need(); if (!(await frappe.db.exists(doctype, name))) throw new Error('record not found: ' + doctype + ' ' + name);
      frappe.set_route('Form', doctype, name); await sleep(800); return {route: frappe.get_route(), title: cur_frm && cur_frm.doc && cur_frm.doc.name};
    },
    'erpnext.query': async ({doctype, measure, start, end, group_by}) => {
      need(); const f = DATEFIELD[doctype]; const M = {count:'count(name)', net_total:'sum(net_total)', grand_total:'sum(grand_total)'};
      if (!M[measure]) throw new Error('unknown measure ' + measure + '; one of ' + Object.keys(M));
      const args = {doctype, fields: [`${M[measure]} as value`].concat(group_by ? [group_by] : []), filters: [['docstatus','=',1],[f,'between',[start,end]]], limit_page_length: 0};
      if (group_by) args.group_by = group_by;
      return (await frappe.call({method:'frappe.client.get_list', args})).message;
    },
  };
  window.__vacp = {
    version: 'prototype-0',
    getCapabilities: () => ({actions: Object.keys(actions), views: DOCTYPES}),
    getState: state,
    execute: async ({name, params}) => {
      const t0 = performance.now();
      try { if (!actions[name]) throw new Error('unknown action ' + name); const result = await actions[name](typeof params === 'string' ? JSON.parse(params) : (params || {}));
            return {ok: true, name, result, ms: Math.round(performance.now() - t0)}; }
      catch (e) { return {ok: false, name, error: String(e.message || e), ms: Math.round(performance.now() - t0)}; }
    },
  };
})();
"""


async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        await ctx.add_init_script(BRIDGE)                       # <- injected before any page script, stock ERPNext untouched
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)[:160]))

        async def act(name, params=None):
            t = time.time()
            r = await page.evaluate("([n, p]) => window.__vacp.execute({name: n, params: p})", [name, params or {}])
            timings.append((name, round((time.time() - t) * 1000)))
            return r

        print(f"=== prototype VACP bridge on stock ERPNext ({BASE}) ===")

        print("\n1. Injection and not-logged-in behaviour")
        await page.goto(BASE + "/login", wait_until="load")
        check(await page.evaluate("typeof window.__vacp") == "object", "window.__vacp exists on the login page (injected, no ERPNext rebuild)")
        r = await act("erpnext.navigate", {"view": "sales-orders"})
        check(r["ok"] is False and "Not logged in" in r["error"], f"action refused before login: {r.get('error')}")

        print("\n2. Log in, then check what the desk exposes")
        resp = await ctx.request.post(BASE + "/api/method/login", data={"usr": "Administrator", "pwd": "admin"})
        check(resp.ok, "REST login with the same cookie jar")
        await page.goto(BASE + "/app/home", wait_until="load")
        await page.wait_for_function("window.frappe && frappe.session && frappe.session.user === 'Administrator' && frappe.router", timeout=30000)
        info = await page.evaluate("({frappe: typeof frappe, set_route: typeof frappe.set_route, get_route: typeof frappe.get_route, router: typeof frappe.router, call: typeof frappe.call, db: typeof frappe.db, version: frappe.boot && frappe.boot.versions && frappe.boot.versions.frappe})")
        check(all(info[k] in ("function", "object") for k in ("frappe", "set_route", "get_route", "router", "call", "db")), f"desk globals present without any hook: {info}")
        check(await page.evaluate("typeof window.__vacp") == "object", "bridge survived the desk boot")

        print("\n3. Navigation without a page reload")
        await page.evaluate("window.__marker = 12345")
        r = await act("erpnext.navigate", {"view": "sales-orders"})
        check(r["ok"], f"navigate -> sales orders ({r.get('ms')} ms)")
        check(await page.evaluate("window.__marker") == 12345, "SPA route change did not reload the page")
        check(r["ok"] and r["result"]["doctype"] == "Sales Order", "state reports doctype = Sales Order")
        exp_total = int(sql("select count(*) from `tabSales Order`"))
        check(r["ok"] and r["result"]["total"] == exp_total, f"unfiltered total {r['result']['total'] if r['ok'] else '?'} == SQL {exp_total}")

        print("\n4. Period filter (April 2016) against SQL and against what the page shows")
        r = await act("erpnext.set_period", {"doctype": "Sales Order", "start": "2016-04-01", "end": "2016-04-30"})
        exp = int(sql("select count(*) from `tabSales Order` where docstatus=1 and transaction_date between '2016-04-01' and '2016-04-30'"))
        check(r["ok"], f"set_period ({r.get('ms')} ms): {r.get('error', '')}")
        if r["ok"]:
            s = r["result"]
            check(s["total"] == exp, f"filtered count {s['total']} == SQL {exp}")
            # ERPNext's list label stops counting at 1,000 ("20 of 1,000+"); exact totals come from the count API, as with metasfresh's 5,000-row cap
            label_ok = ("1,000+" in s["count_label"]) if exp > 1000 else (str(exp) in s["count_label"].replace(",", ""))
            check(label_ok, f"the page's own label is consistent ('{s['count_label']}'; labels cap at 1,000+, so the bridge reports the exact total from the count API)")
            check(any(f[0] == "transaction_date" for f in s["filters"]), f"filter is visibly applied in the filter bar: {s['filters']}")
            check("transaction_date" in s["url"], f"deep link carries the filter: {s['url'][:120]}")

        print("\n5. Status + period, then narrowing by customer")
        r = await act("erpnext.set_filters", {"doctype": "Sales Order", "status": "Completed"})
        exp = int(sql("select count(*) from `tabSales Order` where docstatus=1 and status='Completed' and transaction_date between '2016-04-01' and '2016-04-30'"))
        check(r["ok"] and r["result"]["total"] == exp, f"status=Completed within April: page {r['result']['total'] if r['ok'] else r.get('error')} == SQL {exp} (period filter kept)")
        cust = sql("select customer from `tabSales Order` where docstatus=1 and transaction_date between '2016-04-01' and '2016-04-30' limit 1")
        r = await act("erpnext.set_filters", {"doctype": "Sales Order", "customer": cust})
        exp = int(sql(f"select count(*) from `tabSales Order` where docstatus=1 and status='Completed' and customer='{cust}' and transaction_date between '2016-04-01' and '2016-04-30'"))
        check(r["ok"] and r["result"]["total"] == exp, f"customer '{cust}' narrows to {exp}")

        print("\n6. Guardrails: invalid values are refused and the screen does not change")
        before = await page.evaluate("location.pathname + location.search")
        r1 = await act("erpnext.set_filters", {"doctype": "Sales Order", "status": "Almost Done"})
        r2 = await act("erpnext.set_filters", {"doctype": "Sales Order", "customer": "Tailspin Nonexistent Ltd"})
        r3 = await act("erpnext.open_record", {"doctype": "Sales Order", "name": "SO-DOES-NOT-EXIST"})
        r4 = await act("erpnext.hack_everything", {})
        r5 = await act("erpnext.set_period", {"doctype": "Sales Order", "start": "2016-05-31", "end": "2016-01-01"})
        check(not r1["ok"] and not r2["ok"] and not r3["ok"] and not r4["ok"] and not r5["ok"], "5 invalid calls all rejected (bad status, unknown customer, missing record, unknown action, reversed dates)")
        check(await page.evaluate("location.pathname + location.search") == before, "URL unchanged after the rejected calls")
        print("     e.g. ->", r1["error"][:110])

        print("\n7. Analytics through the API behind the page (aggregation without the 5,000-row cap)")
        r = await act("erpnext.query", {"doctype": "Sales Invoice", "measure": "net_total", "start": "2015-12-01", "end": "2015-12-31"})
        exp = float(sql("select sum(net_total) from `tabSales Invoice` where docstatus=1 and posting_date between '2015-12-01' and '2015-12-31'"))
        got = float(r["result"][0]["value"]) if r["ok"] and r["result"] else None
        check(got is not None and abs(got - exp) < 0.01, f"M10 Dec 2015 net sales {got} == SQL {exp}  (WWI raw: 4,458,811.25)")
        r = await act("erpnext.query", {"doctype": "Sales Order", "measure": "count", "start": "2016-05-01", "end": "2016-05-31", "group_by": "territory"})
        rows = r["result"] if r["ok"] else []
        exp = int(sql("select count(*) from `tabSales Order` where docstatus=1 and transaction_date between '2016-05-01' and '2016-05-31'"))
        check(sum(int(x["value"]) for x in rows) == exp, f"grouped by territory: {len(rows)} groups, total {sum(int(x['value']) for x in rows)} == SQL {exp}")

        print("\n8. Open a record, then browser Back works (ERPNext's own popstate handler is not disturbed)")
        so = sql("select name from `tabSales Order` where docstatus=1 and wwi_order_id=67257")
        r = await act("erpnext.open_record", {"doctype": "Sales Order", "name": so})
        check(r["ok"] and r["result"]["title"] == so, f"opened form {so}")
        await page.go_back()
        await page.wait_for_timeout(1200)
        route = await page.evaluate("frappe.get_route()")
        check(route[0] == "List" and route[1] == "Sales Order", f"history.back() returns to the filtered list: {route}")

        print("\n9. Bridge survives a hard reload (injected again by the loader)")
        await page.reload(wait_until="load")
        await page.wait_for_function("window.__vacp && window.frappe && frappe.session && frappe.session.user === 'Administrator'", timeout=30000)
        r = await act("erpnext.navigate", {"view": "invoices"})
        check(r["ok"] and r["result"]["doctype"] == "Sales Invoice", "navigate works after reload")

        check(not errors, f"no uncaught page errors ({errors[:2]})")
        await page.screenshot(path="/tmp/erpnext_vacp_spike.png")
        await browser.close()

    print("\nlatency (ms) per action:", ", ".join(f"{n.split('.')[-1]}={t}" for n, t in timings))
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' FAILED'}")
    for f in failures:
        print("  -", f)

asyncio.run(run())
