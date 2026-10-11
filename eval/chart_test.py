"""Headless-browser check of the chart builder: each chart type draws from /api/analyze, figures on the chart equal the API's, a chart
can be saved, listed, edited and deleted, and the server refuses invalid definitions. Run where Playwright is installed (nova2).
Screenshots go to /tmp/chart_shots/."""
import asyncio, json, os, sys, urllib.request
from playwright.async_api import async_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://10.9.0.105:8017").rstrip("/")
OUT = "/tmp/chart_shots"; os.makedirs(OUT, exist_ok=True)
fails = []


def check(c, m):
    print(("  PASS " if c else "  FAIL ") + m)
    if not c:
        fails.append(m)


def post(path, body, hdr=None):
    r = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json", **(hdr or {})})
    try:
        return json.load(urllib.request.urlopen(r, timeout=30))
    except urllib.error.HTTPError as e:
        return {"http": e.code, **json.load(e)}


def api_rows(**kw):
    req = {"measure_id": "M01", "date_basis": "order_date", "scenario_id": "base", "top_n": 10, "sort": "value_desc", **kw}
    return post("/api/analyze", req)


async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        pg = await (await b.new_context(viewport={"width": 1440, "height": 1000})).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:200]))
        pg.on("console", lambda m: errs.append("console: " + m.text[:200]) if m.type == "error" else None)

        async def visit():
            await pg.goto(f"{BASE}/#/charts", wait_until="load")
            await pg.wait_for_function("document.querySelector('#content').dataset.completed==='true'", timeout=20000)
            await pg.wait_for_selector("#cb-canvas svg, #cb-canvas .cb-number, #cb-err:not([hidden])", timeout=20000)

        async def settle():
            await pg.wait_for_timeout(1200)
            await pg.wait_for_function("!document.querySelector('#cb-canvas').textContent.includes('Loading')", timeout=15000)

        print("1. Default chart: orders by territory, May 2016 (bars)")
        await visit()
        await pg.screenshot(path=f"{OUT}/01_default.png")
        want = api_rows(start="2016-05-01", end="2016-06-01", group_by="sales_territory")
        txt = await pg.inner_text("#cb-sum")
        check(f"{want['total']:,}" in txt, f"summary shows the API total {want['total']:,}: {txt[:80]}")
        bars = await pg.evaluate("document.querySelectorAll('#cb-canvas svg rect[fill=\"#1d7a8c\"]').length")
        check(bars == len(want["rows"]), f"one bar per group ({bars} bars, API returned {len(want['rows'])} groups)")
        await pg.click("#cb-actions ~ details summary") if False else await pg.click(".cb-data summary")
        cells = await pg.evaluate("[...document.querySelectorAll('#cb-table tbody tr')].map(r=>[r.cells[0].textContent,Number(r.cells[1].textContent.replace(/,/g,''))])")
        check(cells == [[r["label"], r["value"]] for r in want["rows"]], "the data table equals the API rows, in order")

        print("2. Line chart by month")
        await pg.select_option("#cb-g", "month")
        await pg.fill("#cb-s", "2016-01-01"); await pg.fill("#cb-e", "2016-06-01")
        await settle()
        poly = await pg.evaluate("document.querySelectorAll('#cb-canvas svg polyline').length")
        w2 = api_rows(start="2016-01-01", end="2016-06-01", group_by="month", sort="label_asc")
        check(poly == 1 and f"{w2['total']:,}" in await pg.inner_text("#cb-sum"), f"line chart drawn, total {w2['total']:,} shown")
        check(await pg.evaluate("!document.querySelector('#cb-cs')"), "comparison fields are hidden for a monthly chart (the API forbids them)")
        await pg.screenshot(path=f"{OUT}/02_line.png")

        print("3. Compare two periods (grouped bars)")
        await pg.select_option("#cb-g", "sales_territory")
        await pg.fill("#cb-s", "2016-05-01"); await pg.fill("#cb-e", "2016-06-01")
        await pg.fill("#cb-cs", "2016-04-01"); await pg.fill("#cb-ce", "2016-05-01")
        await settle()
        s3 = await pg.inner_text("#cb-sum")
        check("+96" in s3 and "1,951" in s3, f"comparison summary: {s3[:90]}")
        check(await pg.evaluate("document.querySelectorAll('#cb-canvas svg rect[fill=\"#a9bcc8\"]').length") >= 5, "baseline bars drawn beside the current ones")
        await pg.screenshot(path=f"{OUT}/03_compare.png")

        print("4. Pie, horizontal bars, single number")
        await pg.fill("#cb-cs", ""); await pg.fill("#cb-ce", "")
        await pg.dispatch_event("#cb-ce", "change"); await settle()
        await pg.click("#cb-type button[data-t=pie]"); await settle()
        check(await pg.evaluate("document.querySelectorAll('#cb-canvas svg path').length") >= 5, "pie drawn")
        await pg.screenshot(path=f"{OUT}/04_pie.png")
        await pg.click("#cb-type button[data-t=hbar]"); await settle()
        check(await pg.evaluate("document.querySelectorAll('#cb-canvas svg rect[fill=\"#1d7a8c\"]').length") >= 5, "horizontal bars drawn")
        await pg.select_option("#cb-g", "none"); await settle()
        check("2,047" in await pg.inner_text("#cb-canvas"), "no breakdown shows the single number 2,047")
        await pg.screenshot(path=f"{OUT}/05_number.png")
        check(await pg.evaluate("[...document.querySelectorAll('#cb-type button')].map(b=>b.textContent).join()") == "Number", "only 'Number' is offered without a breakdown")

        print("5. Pie is not offered where parts do not add up")
        await pg.select_option("#cb-m", "M01"); await pg.select_option("#cb-g", "stock_item"); await settle()
        types = await pg.evaluate("[...document.querySelectorAll('#cb-type button')].map(b=>b.textContent)")
        check("Pie" not in types and "Line" not in types, f"item breakdown offers {types} (no pie, no line)")

        print("6. Save, list, edit, delete")
        await pg.select_option("#cb-g", "sales_territory"); await settle()
        await pg.click("#cb-save")
        await pg.wait_for_selector("#cb-err:not([hidden])", timeout=5000)
        check("title" in (await pg.inner_text("#cb-err")).lower(), "saving without a title is refused")
        await pg.fill("#cb-t", "Orders by territory, May 2016")
        await pg.click("#cb-save")
        await pg.wait_for_selector(".cb-card", timeout=10000)
        await pg.wait_for_selector(".cb-card svg", timeout=15000)
        check(await pg.inner_text(".cb-card header b") == "Orders by territory, May 2016", "saved chart appears in My charts, drawn")
        await pg.screenshot(path=f"{OUT}/06_gallery.png", full_page=True)
        await pg.click(".cb-card [data-act=edit]")
        await pg.wait_for_function("document.querySelector('#cb-t') && document.querySelector('#cb-t').value==='Orders by territory, May 2016'", timeout=10000)
        await pg.fill("#cb-t", "Orders by territory (renamed)")
        await pg.click("#cb-save")
        await pg.wait_for_function("document.querySelector('.cb-card header b') && document.querySelector('.cb-card header b').textContent.includes('renamed')", timeout=10000)
        check(len(await pg.query_selector_all(".cb-card")) == 1, "editing updates the same chart (no duplicate)")
        await visit_workspace(pg)
        check("Orders by territory (renamed)" in await pg.inner_text("#content"), "the chart is listed on the Workspace page")
        await pg.goto(f"{BASE}/#/charts", wait_until="load"); await pg.wait_for_selector(".cb-card", timeout=15000)
        await pg.click(".cb-card [data-act=del]"); await pg.wait_for_selector("#ws-yes"); await pg.click("#ws-yes")
        await pg.wait_for_function("!document.querySelector('.cb-card')", timeout=10000)
        check(True, "deleting removes it from My charts")

        print("7. Server refuses invalid definitions")
        h = {"X-Sapience-Write": "1"}
        base = {"title": "t", "measure_id": "M01", "group_by": "sales_territory", "start": "2016-05-01", "end": "2016-06-01", "chart_type": "bar", "top_n": 10}
        mk = lambda **o: post("/api/ws/create", {"kind": "chart", "data": {**base, **o}}, h)
        check(mk(chart_type="line").get("http") == 422, "line chart without a month breakdown refused")
        check(mk(group_by="stock_item", chart_type="pie").get("http") == 422, "pie over a breakdown that does not add up refused")
        check(mk(group_by="month", chart_type="line", compare_start="2016-04-01", compare_end="2016-05-01").get("http") == 422, "monthly chart with a comparison refused")
        check(mk(measure_id="M99").get("http") == 422, "unknown measure refused")
        check(mk(start="2016-07-01", end="2016-08-01").get("http") == 422, "dates outside the archive refused")
        check(mk(end=None).get("http") == 422, "half a period refused")
        ok = mk()
        check("id" in ok, "a valid definition is accepted")
        post("/api/ws/delete", {"id": ok["id"]}, h)

        errs = [e for e in errs if "status of 422" not in e]
        check(not errs, "no console or page errors" + ("" if not errs else ": " + "; ".join(errs[:3])))
        await b.close()
    print("\nFAILED: " + "; ".join(fails) if fails else "\nALL PASSED")
    sys.exit(1 if fails else 0)


async def visit_workspace(pg):
    await pg.goto(f"{BASE}/#/workspace", wait_until="load")
    await pg.wait_for_function("document.querySelector('#content').dataset.completed==='true'", timeout=20000)
    await pg.wait_for_timeout(500)


asyncio.run(run())
