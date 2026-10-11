"""Headless-browser check of the WWI console: every page renders, no console errors, Browse lists work, and the in-app assistant
answers and opens the matching page. Screenshots go to /tmp/ui_shots/."""
import asyncio, os, sys
from playwright.async_api import async_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://10.9.0.105:8017").rstrip("/")
OUT = "/tmp/ui_shots"; os.makedirs(OUT, exist_ok=True)
fails = []


def check(c, m):
    print(("  PASS " if c else "  FAIL ") + m)
    if not c:
        fails.append(m)


async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        pg = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)[:200]))
        pg.on("console", lambda m: errs.append("console: " + m.text[:200]) if m.type == "error" else None)
        pg.on("requestfailed", lambda r: errs.append("requestfailed: " + r.url[:120]))

        async def visit(route, wait_text=None, shot=None, timeout=20000):
            await pg.goto(f"{BASE}/#/{route}", wait_until="load")
            await pg.wait_for_timeout(500)
            await pg.wait_for_function("document.querySelector('#content').dataset.completed==='true' || !document.querySelector('#error').hidden", timeout=timeout)
            err = await pg.evaluate("document.querySelector('#error').hidden ? '' : document.querySelector('#error').textContent")
            if shot:
                await pg.screenshot(path=f"{OUT}/{shot}.png")
            return err

        print("1. Pages")
        for route, title, shot in [("overview", "Overview", "01_overview"), ("fulfilment", "Fulfilment", "02_fulfilment"), ("supply", "Supply", "03_supply"),
                                    ("analysis?measure_id=M01&group_by=sales_territory&start=2016-05-01&end=2016-06-01&compare_start=2016-04-01&compare_end=2016-05-01", "Analysis", "04_analysis"),
                                    ("customers", "Customers", "05_customers"), ("orders", "Orders", "06_orders"), ("items", "Stock items", "07_items"),
                                    ("suppliers", "Suppliers", "08_suppliers"), ("purchases", "Purchase orders", "09_purchases")]:
            err = await visit(route, shot=shot)
            t = await pg.inner_text("#title")
            rows = await pg.evaluate("document.querySelectorAll('#content tbody tr').length")
            active = await pg.evaluate("[...document.querySelectorAll('nav a.active')].map(a=>a.textContent.trim()).join(',')")
            stale = await pg.evaluate("document.querySelector('#content').innerText.slice(0,400)")
            check(not err and t == title, f"{title}: renders, no error banner (rows on screen: {rows}, active nav: '{active}')")
        err = await visit("customer/1", shot="10_customer_detail")
        check(not err, "customer detail page opens")
        check(await pg.evaluate("[...document.querySelectorAll('nav a.active')].map(a=>a.textContent.trim()).join(',')") == "Customers", "detail page highlights its parent in the sidebar")

        print("\n2. Browse search")
        await visit("customers")
        await pg.fill("#bf", "tailspin"); await pg.click("#content form button[type=submit]")
        await pg.wait_for_selector("#bf-out button", timeout=10000)
        n = await pg.evaluate("document.querySelectorAll('#bf-out button').length")
        check(n >= 3, f"search 'tailspin' returned {n} matches")
        await pg.click("#bf-out button")
        await pg.wait_for_function("location.hash.includes('/customer/')", timeout=8000)
        check(True, "clicking a match opens that customer")

        print("\n3. Assistant")
        await visit("overview")
        await pg.click("#ask-open")
        await pg.wait_for_function("document.querySelector('#sap-status').className==='ok'", timeout=10000)
        check(True, "panel opens and reports the service online: " + await pg.inner_text("#sap-status"))
        await pg.screenshot(path=f"{OUT}/11_assistant_open.png")
        await pg.click(".sap-chip >> nth=0")
        await pg.wait_for_selector(".sap-msg.bot:not(.sap-work) .sap-meta", timeout=120000)
        txt = await pg.inner_text("#sap-msgs")
        check("96" in txt and "4.92" in txt, "answer states +96 / 4.92% (matches the answer key)")
        await pg.wait_for_function("location.hash.startsWith('#/analysis')", timeout=8000)
        check(True, "the assistant opened the Analysis page itself: " + (await pg.evaluate("location.hash"))[:90])
        await pg.wait_for_function("document.querySelector('#content').dataset.completed==='true'", timeout=20000)
        await pg.screenshot(path=f"{OUT}/12_assistant_answer.png")
        # the journey (ledger): the real steps of this question; the last three are completed by the browser after it opens the page,
        # reads it and compares what it shows with the answer
        await pg.wait_for_function("window.sapienceLedgers && window.sapienceLedgers[0] && window.sapienceLedgers[0].trail.filter(s=>s.who==='browser').length===3 && window.sapienceLedgers[0].trail.filter(s=>s.who==='browser').every(s=>s.status!=='pending')", timeout=60000)
        tr = await pg.evaluate("window.sapienceLedgers[0].trail.map(s=>s.n+':'+s.who+':'+s.status+':'+s.title)")
        print("   trail:", " | ".join(tr))
        check(all(x.split(":")[2] == "done" for x in tr if ":browser:" in x), "journey: the page was opened, read and matched the answer")
        called = await pg.evaluate("(()=>{const s=window.sapienceLedgers[0].trail.find(x=>x.title==='Called analyze');return s?s.kv.map(k=>k.join('=')).join(' ; '):''})()")
        check("M01" in called and "2016-05-01" in called, "journey: the analyze step lists the exact arguments and result: " + called[:120])
        opened = await pg.evaluate("window.sapienceLedgers[0].trail.find(x=>x.who==='browser').title")
        check("Analysis" in opened, "journey: names the page that was opened: " + opened)
        await pg.click(".sap-journey >> nth=0")
        await pg.wait_for_selector("#sap-modal:not([hidden]) .jy-cell", timeout=5000)
        n = await pg.evaluate("document.querySelectorAll('#sap-modal .jy-cell').length")
        lg = await pg.evaluate("document.querySelectorAll('#sap-modal .jy-log > li').length")
        f = await pg.evaluate("document.querySelectorAll('#sap-modal .jy-facts tbody tr').length")
        check(n == len(tr) and lg == n and f >= 3, f"infographic shows the {n} real steps, {lg} log entries and {f} ledger entries")
        await pg.screenshot(path=f"{OUT}/14_journey_modal.png")
        await pg.click("#sap-modal-close")
        await pg.fill("#sap-input", "Which states inside Great Lakes moved?")
        await pg.click("#sap-send")
        await pg.wait_for_function("document.querySelectorAll('.sap-msg.bot .sap-meta').length>=2", timeout=120000)
        txt = await pg.inner_text("#sap-msgs")
        check("65" in txt, "follow-up (same conversation) mentions Great Lakes +65")
        await pg.screenshot(path=f"{OUT}/13_assistant_followup.png")

        # a different question gives a different trail (name filter, single total) and the page figure is compared with it
        await pg.click("#sap-new")                      # fresh conversation, so no scope is carried over
        await pg.fill("#sap-input", "How many orders did Great Lakes place in May 2016?")
        await pg.click("#sap-send")
        await pg.wait_for_function("document.querySelectorAll('.sap-msg.bot .sap-meta').length>=1", timeout=120000)
        await pg.wait_for_function("(()=>{const L=window.sapienceLedgers[window.sapienceLedgers.length-1];const b=L.trail.filter(s=>s.who==='browser');return b.length===3&&b.every(s=>s.status!=='pending')})()", timeout=60000)
        tr3 = await pg.evaluate("window.sapienceLedgers[window.sapienceLedgers.length-1].trail.map(s=>s.n+':'+s.who+':'+s.status+':'+s.title+':'+s.detail)")
        print("   trail 3:", " | ".join(tr3))
        check(any("Called analyze:296 orders" in x for x in tr3) and any("Great Lakes → sales_territory" in x for x in tr3), "a different question produces its own trail (name resolved to a territory, single total 296)")
        check(all(x.split(":")[2] == "done" for x in tr3 if ":browser:" in x) and any("Compared" in x for x in tr3), "single-total answer was compared with the page and matched")
        called3 = await pg.evaluate("(()=>{const L=window.sapienceLedgers[window.sapienceLedgers.length-1];const s=L.trail.find(x=>x.title==='Called analyze');return s?s.kv.map(k=>k.join('=')).join(' ; '):''})()")
        check("Great Lakes" in called3 and "296" in called3, "analyze step shows the territory filter and the total 296: " + called3[:140])

        real = [e for e in errs if "favicon" not in e]
        check(not real, f"no console errors or failed requests {real[:3]}")
        await b.close()
    print("\n" + ("ALL CHECKS PASSED" if not fails else f"{len(fails)} FAILED: {fails}"))

asyncio.run(run())
