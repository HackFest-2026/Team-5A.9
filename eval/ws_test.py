"""Headless-browser check of the workspace (create / edit / delete / restore / revert / draft order / activity log) and that the
source data and analytics are untouched by it. Run where Playwright is installed (nova2). Screenshots go to /tmp/ws_shots/."""
import asyncio, json, os, sys, urllib.request
from playwright.async_api import async_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://10.9.0.105:8017").rstrip("/")
OUT = "/tmp/ws_shots"; os.makedirs(OUT, exist_ok=True)
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


def source_fingerprint():
    a = post("/api/analyze", {"measure_id": "M01", "start": "2016-05-01", "end": "2016-06-01", "compare_start": "2016-04-01", "compare_end": "2016-05-01"})
    rec = post("/api/records", {"id": "customers", "dataset_version": "wwi-data-v1-2026-10-08", "scenario_id": "base", "date_basis": "none", "filters": {"customer_id": 1}, "limit": 1, "offset": 0})
    return (a.get("total_current"), a.get("total_baseline"), rec["rows"][0]["CustomerName"], rec["total_rows"])


async def run():
    before = source_fingerprint()
    print("source before:", before)
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        pg = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:200]))
        pg.on("console", lambda m: errs.append("console: " + m.text[:200]) if m.type == "error" else None)

        async def visit(route):
            await pg.goto(f"{BASE}/#/{route}", wait_until="load")
            await pg.wait_for_timeout(400)
            await pg.wait_for_function("document.querySelector('#content').dataset.completed==='true'", timeout=20000)
            await pg.wait_for_timeout(600)   # workspace panels are added right after

        async def modal_open():
            await pg.wait_for_selector("#ws-modal:not([hidden])", timeout=8000)

        print("1. Create a customer")
        await visit("customers")
        await pg.click("text=+ New customer")
        await modal_open()
        await pg.fill("input[name=name]", "Test Trading Co (workspace)")
        await pg.select_option("select[name=category_id]", index=1)
        await pg.fill("input[name=phone]", "555-0100")
        await pg.screenshot(path=f"{OUT}/01_form.png")
        await pg.click("text=Review changes")
        await pg.wait_for_selector("#ws-save")
        check("Test Trading Co (workspace)" in await pg.inner_text("#ws-body"), "review step shows the new values")
        await pg.screenshot(path=f"{OUT}/02_review.png")
        await pg.click("#ws-save")
        await pg.wait_for_selector("#ws-modal", state="hidden")
        await pg.wait_for_selector("text=Added in your workspace (1)", timeout=10000)
        check(True, "new customer listed under 'Added in your workspace (1)'")
        await pg.screenshot(path=f"{OUT}/03_list_with_new.png")

        print("2. Validation")
        await pg.click("text=+ New customer")
        await modal_open()
        await pg.click("text=Review changes")
        await pg.wait_for_selector("#ws-save")
        await pg.click("#ws-save")
        await pg.wait_for_selector("#ws-err:not([hidden])", timeout=8000)
        check("required" in (await pg.inner_text("#ws-err")).lower(), "empty name rejected by the server: " + (await pg.inner_text("#ws-err")))
        await pg.keyboard.press("Escape")

        print("3. Edit a source customer, then revert")
        await visit("customer/1")
        check("no edits" in (await pg.inner_text("#content")).lower(), "detail page shows the Workspace panel with no edits")
        await pg.click("text=Edit this customer")
        await modal_open()
        await pg.fill("input[name=name]", "Tailspin Toys (Head Office) EDITED")
        await pg.click("text=Review changes")
        await pg.wait_for_selector("#ws-save")
        txt = await pg.inner_text("#ws-body")
        check("EDITED" in txt and "Tailspin Toys (Head Office)" in txt, "review shows before and after")
        await pg.click("#ws-save")
        await pg.wait_for_selector("#ws-modal", state="hidden")
        await pg.wait_for_selector(".ws-panel .ws-diff", timeout=10000)
        check("EDITED" in await pg.inner_text(".ws-panel"), "workspace panel shows the edit")
        check(source_fingerprint() == before, "source row and analytics unchanged after the edit")
        await pg.screenshot(path=f"{OUT}/04_detail_edited.png")
        await pg.click("text=Revert to source")
        await pg.wait_for_selector("#ws-yes")
        await pg.click("#ws-yes")
        await pg.wait_for_selector("#ws-modal", state="hidden")
        await pg.wait_for_function("document.querySelector('.ws-panel') && document.querySelector('.ws-panel').innerText.toLowerCase().includes('no edits')", timeout=10000)
        check(True, "revert returns the record to the source values")

        print("4. Draft order with the item picker")
        await visit("customer/1")
        await pg.click("text=New draft order")
        await modal_open()
        check("Tailspin" in await pg.inner_text(".ws-pick"), "customer prefilled from the page")
        await pg.fill(".ws-lines .ws-find input", "USB missile")
        await pg.click(".ws-lines [data-act=find]")
        await pg.wait_for_selector(".ws-lines [data-act=choose]", timeout=8000)
        await pg.click(".ws-lines [data-act=choose] >> nth=0")
        await pg.fill(".ws-lines .ws-qty", "12")
        await pg.click("text=Review changes")
        await pg.wait_for_selector("#ws-save")
        check("12" in await pg.inner_text("#ws-body") and "USB missile" in await pg.inner_text("#ws-body"), "review lists the line")
        await pg.click("#ws-save")
        await pg.wait_for_selector("#ws-modal", state="hidden")

        print("5. Workspace page, delete, restore, activity")
        await visit("workspace")
        body = await pg.inner_text("#content")
        check("Test Trading Co (workspace)" in body and "Draft order" in body, "workspace lists the new customer and the draft order")
        await pg.screenshot(path=f"{OUT}/05_workspace.png")
        await pg.click("tr:has-text('Test Trading Co') >> text=Delete")
        await pg.wait_for_selector("#ws-yes")
        await pg.click("#ws-yes")
        await pg.wait_for_selector("#ws-modal", state="hidden")
        await pg.wait_for_timeout(800)
        check("Test Trading Co" not in await pg.inner_text("#content"), "deleted record is hidden")
        await pg.check("text=include deleted")
        await pg.wait_for_timeout(1200)
        await pg.click("tr:has-text('Test Trading Co') >> text=Restore")
        await pg.wait_for_timeout(1200)
        await pg.uncheck("text=include deleted")
        await pg.wait_for_timeout(1200)
        check("Test Trading Co" in await pg.inner_text("#content"), "restored record is back")
        await pg.click("text=Activity log")
        await pg.wait_for_selector(".ws-tag.restore", timeout=8000)
        act = await pg.inner_text("#content")
        check(all(w in act.lower() for w in ("create", "edit", "revert", "delete", "restore")), "activity log shows create, edit, revert, delete, restore")
        await pg.screenshot(path=f"{OUT}/06_activity.png")

        print("6. Direct API guards")
        check(post("/api/ws/create", {"kind": "customer", "data": {"name": "x"}}).get("http") == 403, "write without the header is refused (403)")
        h = {"X-Sapience-Write": "1"}
        check(post("/api/ws/create", {"kind": "customer", "data": {"name": "x", "bogus": 1}}, h).get("http") == 422, "unknown field refused")
        check(post("/api/ws/create", {"kind": "order", "data": {"customer_id": 99999, "lines": [{"item_id": 1, "qty": 1}]}}, h).get("http") == 422, "order for a customer that does not exist refused")
        check(post("/api/ws/create", {"kind": "order", "data": {"customer_id": 1, "lines": [{"item_id": 1, "qty": 0}]}}, h).get("http") == 422, "zero quantity refused")
        check(post("/api/ws/edit", {"kind": "order", "ref_id": 1, "data": {}}, h).get("http") == 422, "source orders cannot be edited")

        print("7. Source and analytics untouched")
        after = source_fingerprint()
        check(after == before, f"orders May vs April, customer 1 name and counts identical ({after})")
        errs = [e for e in errs if "status of 422" not in e]   # the deliberate empty-name submit in step 2
        check(not errs, "no console or page errors" + ("" if not errs else ": " + "; ".join(errs[:3])))
        await b.close()
    print("\nFAILED: " + "; ".join(fails) if fails else "\nALL PASSED")
    sys.exit(1 if fails else 0)


asyncio.run(run())
