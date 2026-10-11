"""Browser check: the assistant proposes a chart for a chart question, the card shows, Save stores it, and it appears in the Chart builder.
Run where Playwright is installed (nova2). Removes the chart it saved."""
import asyncio, json, sys, urllib.request
from playwright.async_api import async_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://10.9.0.105:8017").rstrip("/")
TITLE = "Chart orders in May 2016 by territory"
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
        pg.on("pageerror", lambda e: errs.append(str(e)[:150]))
        await pg.goto(BASE + "/#/overview", wait_until="load")
        await pg.wait_for_function("document.querySelector('#content').dataset.completed === 'true'", timeout=20000)
        await pg.click("#ask-open")
        await pg.fill("#sap-input", TITLE)
        await pg.click("#sap-send")
        await pg.wait_for_selector(".sap-propose", timeout=240000)
        check(True, "the assistant offered a chart card")
        await pg.click(".sap-psave")
        await pg.wait_for_selector(".sap-propose.saved", timeout=20000)
        check("Saved" in await pg.inner_text(".sap-pmsg"), "Save stores the chart and says so")
        await pg.goto(BASE + "/#/charts", wait_until="load")
        await pg.wait_for_selector(".cb-card", timeout=20000)
        check(TITLE in await pg.inner_text("#cb-gallery"), "the saved chart is listed in the Chart builder")
        recs = json.load(urllib.request.urlopen(BASE + "/api/ws/list?kind=chart"))["records"]
        for r in recs:
            if r["data"]["title"] == TITLE:
                req = urllib.request.Request(BASE + "/api/ws/delete", json.dumps({"id": r["id"]}).encode(),
                                             {"Content-Type": "application/json", "X-Sapience-Write": "1"})
                urllib.request.urlopen(req)
        check(not errs, "no page errors " + str(errs[:2]))
        await b.close()
    print("ALL PASSED" if not fails else "FAILED: " + "; ".join(fails))


asyncio.run(run())
