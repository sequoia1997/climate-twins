"""Browser test of the species page (web/species.html + web/species/app.js) on REAL pilot outputs (tests/fixtures/species: sugar maple,
laughing kookaburra with withheld numbers, American robin breeding-season fit). Offline: map style, fonts and CDN are stubbed.
Usage: python tests/test_species_page.py [outdir]   (SHOTS=0 skips screenshots)   Environment: PW_CHROMIUM, PW_MAPLIBRE_DIR (dist folder of maplibre-gl 5.24.0).
Builds the data with ctw.species_site into a temporary site folder laid out like site/, serves it, and runs at 1440x900 and 390x844, light and dark.
Fails (exit 1) on a JS error, a blank map, horizontal overflow, an unnamed control, a figure showing both views, a row tap changing the view,
missing tier / not-a-forecast / withheld text, or a keyboard search that does not select."""
import asyncio, functools, http.server, io, json, os, shutil, sys, tempfile, threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures" / "species"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "species" / "img"
SHOTS = os.environ.get("SHOTS", "1") != "0"


def make_site(dst: Path):
    from ctw import species_site
    species_site.build(FIX, dst / "species" / "data", log=lambda *a: None)
    (dst / "species" / "basemap.js").write_bytes((ROOT / "web" / "species" / "basemap.js").read_bytes())
    (dst / "species" / "land.cts").write_bytes((ROOT / "web" / "species" / "land.cts").read_bytes())
    (dst / "species" / "app.js").write_text((ROOT / "web" / "species" / "app.js").read_text())
    R2 = "https://species.climatetwins.org/"
    import re as _re
    (dst / "methods.html").write_text(_re.sub(r"\{\{[A-Z_0-9]+\}\}", "0", (ROOT / "web" / "methods.html").read_text()).replace("__SITE_URL__", "").replace('content="https://species.climatetwins.org/"', 'content="species/data/"'))
    for n in ("species.html", "species-methods.html"):
        if (ROOT / "web" / n).exists():
            (dst / n).write_text((ROOT / "web" / n).read_text().replace("__SITE_URL__", "").replace(f'content="{R2}"', 'content="species/data/"'))


def serve(d):
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=str(d)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


async def settle(pg, n=1):
    await pg.wait_for_function(f"window.__sceneReady>={n}", timeout=90000)
    await pg.wait_for_timeout(1200)


async def main():
    from playwright.async_api import async_playwright
    from PIL import Image
    tmp = Path(tempfile.mkdtemp())
    make_site(tmp)
    port, fails = serve(tmp), []
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        kw = {"args": ["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]}
        if os.environ.get("PW_CHROMIUM"): kw["executable_path"] = os.environ["PW_CHROMIUM"]
        b = await p.chromium.launch(**kw)
        for name, w, h, scheme, dpr in [("desktop-light", 1440, 900, "light", 1), ("desktop-dark", 1440, 900, "dark", 1), ("mobile-light", 390, 844, "light", 2), ("mobile-dark", 390, 844, "dark", 2)]:
            ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, device_scale_factor=dpr, reduced_motion="reduce", has_touch=(w < 500), is_mobile=(w < 500))
            d = os.environ.get("PW_MAPLIBRE_DIR")
            if d:
                async def lib(r): await r.fulfill(path=os.path.join(d, r.request.url.split("/dist/")[-1]))
                await ctx.route("https://cdn.jsdelivr.net/npm/maplibre-gl@*/dist/*", lib)
            for u in ("https://fonts.googleapis.com/**", "https://fonts.gstatic.com/**", "https://tiles.openfreemap.org/**"):
                await ctx.route(u, lambda r: r.abort())
            pg = await ctx.new_page()
            errs, got = [], []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "ERR_FAILED" not in m.text and "Failed to load resource" not in m.text else None)
            pg.on("response", lambda r: got.append((r.url.split("/species/", 1)[-1], int(r.headers.get("content-length", 0)))) if "/species/" in r.url else None)
            await pg.goto(f"http://127.0.0.1:{port}/species.html")
            await settle(pg)
            first = [u for u, _ in got]
            # download plan: at start only index + one species' info + its base and first scenario file (+ land); never another species
            if not any(u.endswith("index.json") for u in first): fails.append(f"{name}: index.json not fetched")
            others = [u for u in first if u.startswith("data/") and "/" in u[5:] and not u[5:].startswith(("acer_saccharum", "index"))]
            if others: fails.append(f"{name}: other species fetched at start {others}")
            if name == "desktop-light":
                tot = sum(n for u, n in got if u.startswith("data/"))
                print("startup: ", {u.split('/')[-1][:24]: n for u, n in got if u.startswith("data/") or "land" in u}, f"total data {tot / 1e3:.0f} kB", await pg.evaluate("window.__T"))
            box = await pg.evaluate("(() => { const r = document.getElementById('map').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
            im = Image.open(io.BytesIO(await pg.screenshot(clip=dict(x=box[0], y=box[1], width=min(box[2], w), height=min(box[3], h * 0.5))))).convert("RGB")
            lit = sum(n for n, (r_, g_, b_) in (im.getcolors(maxcolors=1 << 20) or []) if max(r_, g_, b_) - min(r_, g_, b_) > 60)
            if lit < 300: fails.append(f"{name}: map canvas looks empty ({lit} coloured px)")
            ov = await pg.evaluate("[document.documentElement.scrollWidth, innerWidth, document.getElementById('panel').scrollWidth, document.getElementById('panel').clientWidth]")
            if ov[0] > ov[1] or ov[2] > ov[3] + 1:
                wide = await pg.evaluate("[...document.querySelectorAll('#panel *')].filter(e=>e.getBoundingClientRect().right>document.getElementById('panel').getBoundingClientRect().right+0.5).slice(0,4).map(e=>e.tagName+'#'+e.id+'.'+e.className+' '+Math.round(e.getBoundingClientRect().right))")
                fails.append(f"{name}: horizontal overflow {ov} {wide}")
            unnamed = await pg.evaluate("""[...document.querySelectorAll('button,input,select')].filter(e => !(e.getAttribute('aria-label') || e.textContent.trim() || (e.labels && e.labels.length) || e.title)).map(e => e.outerHTML.slice(0, 80))""")
            if unnamed: fails.append(f"{name}: controls without a name {unnamed}")
            head = await pg.inner_text("#sp-head")
            for need in ("Today's map", "Future map", "not a forecast", "Sugar maple"):
                if need.lower() not in head.lower(): fails.append(f"{name}: sugar maple header lacks '{need}'")
            if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-maple-change.png"))
            # scenario, period, dispersal, overlays
            await pg.click("#ssp button:nth-child(2)"); await settle(pg, 2)
            await pg.click("#per button:nth-child(2)"); await pg.click("#disp button:nth-child(2)")
            await pg.check("#o-agree"); await pg.check("#o-novel"); await pg.wait_for_timeout(1000)
            if "km" not in await pg.inner_text("#disp-d"): fails.append(f"{name}: limited-dispersal text has no distance")
            if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-maple-ssp585-2100-limited-overlays.png"))
            # figure: exactly one view in the flow; a row tap never switches it; the toggle does
            async def fig():
                return await pg.evaluate("""(() => { const f = document.getElementById('summary'); const vis = s => { const e = f.querySelector(s); return !!e && getComputedStyle(e).display !== 'none'; }; return [f.dataset.view, vis('.v-abs'), vis('.v-chg')]; })()""")
            v0 = await fig()
            if v0[1] == v0[2]: fails.append(f"{name}: figure shows {v0}")
            await pg.click("#summary .crow >> nth=0", force=True); await pg.click("#summary .facts dt >> nth=0", force=True)
            if await fig() != v0: fails.append(f"{name}: a row tap changed the figure view")
            await pg.click("#summary .vt button[data-v=chg]")
            v1 = await fig()
            if v1[0] != "chg" or v1[1] or not v1[2]: fails.append(f"{name}: toggle to Change failed {v1}")
            # keyboard search: Tab order reaches buttons; type, arrow, Enter selects
            await pg.click("#pickdet > summary") if not await pg.evaluate("document.getElementById('pickdet').open") else None
            await pg.fill("#search", "robin"); await pg.keyboard.press("ArrowDown"); await pg.keyboard.press("Enter")
            await settle(pg, 3)
            head = await pg.inner_text("#sp-head")
            if "American robin" not in head: fails.append(f"{name}: search did not select the robin")
            for need in ("Today's map: checked", "Future map: direction unreliable", "breeding-season"):
                if need.lower() not in head.lower(): fails.append(f"{name}: robin header lacks '{need}'")
            if not await pg.evaluate("document.getElementById('pickdet').open"): await pg.click("#pickdet > summary")
            await pg.fill("#search", ""); await pg.fill("#search", "kookab"); await pg.keyboard.press("ArrowDown"); await pg.keyboard.press("Enter")
            await settle(pg, 4)
            # kookaburra SSP5-8.5 2081-2100 has withheld numbers
            t = await pg.inner_text("#summary")
            if "withheld" not in t.lower(): fails.append(f"{name}: withheld numbers not shown for the kookaburra: {t[:120]!r}")
            elif "unlike anything" not in t.lower(): fails.append(f"{name}: withheld reason missing")
            if "withheld" not in (await pg.inner_text("#sp-head")).lower(): fails.append(f"{name}: withheld banner missing from the header")
            if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-kookaburra-withheld.png"))
            # picking an organism frames its range; the map repeats the world (no wall at the date line) and draws the data in every copy
            bb = await pg.evaluate("(() => { const m = window.__map, b = m.getBounds(), c = m.getCenter(); return [b.getWest(), b.getEast(), c.lng, m.getMaxBounds() === null || m.getMaxBounds() === undefined]; })()")
            if not (111 < bb[2] < 157 or -50 < bb[2] < 0 or 112 - 360 < bb[2]): fails.append(f"{name}: pick did not frame the organism {bb}")
            if not bb[3]: fails.append(f"{name}: map has max bounds (a wall)")
            await pg.evaluate("window.__map.jumpTo({center: [-226, -25], zoom: 3.2})"); await settle(pg, 2)
            im2 = Image.open(io.BytesIO(await pg.screenshot(clip=dict(x=box[0], y=box[1], width=min(box[2], w), height=min(box[3], h * 0.5))))).convert("RGB")
            lit2 = sum(n for n, (r_, g_, b_) in (im2.getcolors(maxcolors=1 << 20) or []) if max(r_, g_, b_) - min(r_, g_, b_) > 60)
            if lit2 < 300: fails.append(f"{name}: no data drawn on the repeated world west of the date line ({lit2} coloured px)")
            # place list
            await pg.evaluate("document.getElementById('place-det').open = true")
            await pg.wait_for_function("document.querySelectorAll('#place-body ul.pl li').length>0 || document.querySelector('#place-body .answer')", timeout=20000)
            if "of 3 modelled organisms" not in await pg.inner_text("#place-body"): fails.append(f"{name}: place list text missing")
            if SHOTS and w > 500:
                await pg.evaluate("document.getElementById('panel').scrollTop=1e5"); await pg.wait_for_timeout(300)
                await pg.screenshot(path=str(OUT / f"{name}-panel-bottom.png"))
            if w < 500:
                await pg.click("#grab"); await pg.wait_for_timeout(400)
                if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-sheet-full.png"))
                await pg.click("#grab"); await pg.click("#sh-tog"); await pg.wait_for_timeout(300)
                if await pg.evaluate("document.getElementById('panel').getBoundingClientRect().height") > 120: fails.append(f"{name}: sheet did not collapse")
                await pg.click("#sh-tog")
            # browse chips use human labels
            chips = await pg.inner_text("#browse")
            if "_" in chips: fails.append(f"{name}: raw group label in chips {chips!r}")
            # top-level toggle + taxonomy drill-down
            if await pg.locator("nav.modes a[aria-current=page]").inner_text() != "Organisms": fails.append(f"{name}: modes toggle missing or wrong current")
            if await pg.locator("nav.modes a[href='./']").count() != 1: fails.append(f"{name}: no link back to climate twins")
            if not await pg.evaluate("document.getElementById('pickdet').open"): await pg.click("#pickdet > summary")
            n0 = await pg.locator("#results li").count()
            chip = pg.locator("#browse .chips button").first
            if await chip.count():
                await chip.click(); await pg.wait_for_timeout(200)
                if await pg.locator("#results li").count() > n0: fails.append(f"{name}: drill-down grew the list")
                if not await pg.locator("#browse .crumb").count(): fails.append(f"{name}: no breadcrumb after drilling down")
            # phone: tier, confidence and withheld status are visible in the half-open sheet without scrolling
            if w < 500:
                r = await pg.evaluate("(() => { const b = document.getElementById('sh-badges').getBoundingClientRect(); return [b.top, b.bottom, innerHeight, document.getElementById('sh-badges').innerText]; })()")
                if not (r[0] > 0 and r[1] <= r[2]) or "Today" not in r[3] or "withheld" not in r[3].lower(): fails.append(f"{name}: sheet badges not visible/complete {r}")
            # slow file: busy message after ~2 s; centre not meaningful when the file says so (stubbed info)
            pg2 = await ctx.new_page(); e2 = []
            pg2.on("pageerror", lambda e: e2.append(str(e)))
            async def info(r):
                resp = await r.fetch(); j = await resp.json()
                for v in j["by"].values():
                    if "cok" in v: v["cok"] = False
                await r.fulfill(response=resp, json=j)
            async def slow(r):
                await asyncio.sleep(2.8); await r.continue_()
            await pg2.route("**/acer_saccharum/info.*.json", info); await pg2.route("**/acer_saccharum/ssp245.*.cts", slow)
            await pg2.goto(f"http://127.0.0.1:{port}/species.html#acer_saccharum")
            await pg2.wait_for_function("document.getElementById('busy').innerText.includes('Still loading')", timeout=20000)
            await settle(pg2)
            if await pg2.is_visible("#busy"): fails.append(f"{name}: busy indicator stays after loading")
            st = await pg2.inner_text("#summary")
            if "not meaningful" not in st: fails.append(f"{name}: no 'not meaningful' centre text {st[:100]!r}")
            if "moves about" in st: fails.append(f"{name}: centre arrow shown for a centre outside the range")
            if not (await pg2.evaluate("location.hash")).startswith("#acer_saccharum&ssp="): fails.append(f"{name}: hash not kept")
            if e2: fails.append(f"{name}: JS errors (stub page) {e2[:2]}")
            await pg2.close()
            # methods page: loads, DOI table filled from the index, no overflow
            await pg.goto(f"http://127.0.0.1:{port}/methods.html#part-organisms"); await pg.wait_for_function("document.querySelectorAll('#doirows tr').length>=3", timeout=20000)
            ov = await pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
            if ov[0] > ov[1]: fails.append(f"{name}: methods page overflows {ov}")
            body = (await pg.inner_text("body")).lower()
            for need in ("part 1", "part 2", "part 3", "not a forecast", "range shifts: pass, fail, untested", "dispersal", "10.15468/dl.j78pf6", "terraclimate", "nex-gddp", "wcvp", "breeding bird survey", "withheld", "precipitation sensitivity"):
                if need not in body: fails.append(f"{name}: methods page lacks '{need}'")
            if SHOTS and name == "desktop-light": await pg.screenshot(path=str(OUT / "methods-desktop-light.png"), full_page=False)
            await pg.goto(f"http://127.0.0.1:{port}/species.html#acer_saccharum"); await settle(pg)
            # theme toggle keeps working
            await pg.click("#themebtn"); await pg.wait_for_timeout(500)
            if errs: fails.append(f"{name}: JS errors {errs[:3]}")
            await ctx.close()
        await b.close()
    shutil.rmtree(tmp, ignore_errors=True)
    print("FAIL" if fails else "OK", *fails, sep="\n")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    asyncio.run(main())
