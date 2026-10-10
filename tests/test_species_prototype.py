"""Smoke test and screenshots for the SYNTHETIC species prototype (prototypes/species/index.html).
Usage: python tests/test_species_prototype.py [outdir]     (default outdir: docs/spikes/img; set SHOTS=0 to skip screenshots)
Needs prototypes/species/data/ (python prototypes/species/build_site_data.py WORK prototypes/species/data).
Environment: PW_CHROMIUM (browser binary) and PW_MAPLIBRE_DIR (local MapLibre dist) for offline use.
Fails (exit 1) on a JavaScript error, horizontal overflow, an unnamed control, or a map that draws nothing."""
import asyncio, functools, http.server, os, sys, threading
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1] / "prototypes" / "species"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "docs" / "spikes" / "img"
SHOTS = os.environ.get("SHOTS", "1") != "0"


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


async def settle(pg):
    await pg.wait_for_function("window.__sceneReady>=1", timeout=60000)
    await pg.wait_for_timeout(1500)


async def main():
    port = serve(); fails = []
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        kw = {"args": ["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]}
        if os.environ.get("PW_CHROMIUM"): kw["executable_path"] = os.environ["PW_CHROMIUM"]
        b = await p.chromium.launch(**kw)
        for name, w, h, scheme, dpr in [("desktop-light", 1440, 900, "light", 1), ("desktop-dark", 1440, 900, "dark", 1), ("mobile-light", 390, 844, "light", 2), ("mobile-dark", 390, 844, "dark", 2)]:
            ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, device_scale_factor=dpr, reduced_motion="reduce", has_touch=(w < 500), is_mobile=(w < 500))
            if os.environ.get("PW_MAPLIBRE_DIR"):
                d = os.environ["PW_MAPLIBRE_DIR"]
                async def lib(r): await r.fulfill(path=os.path.join(d, r.request.url.split("/dist/")[-1]))
                await ctx.route("https://cdn.jsdelivr.net/npm/maplibre-gl@*/dist/*", lib)
            await ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
            await ctx.route("https://fonts.gstatic.com/**", lambda r: r.abort())
            pg = await ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "ERR_FAILED" not in m.text else None)
            await pg.goto(f"http://127.0.0.1:{port}/index.html")
            await settle(pg)
            # the map drew something: read back the canvas
            lit = await pg.evaluate("""() => { const m = window.__map, c = m.getCanvas(); const t = document.createElement('canvas'); t.width = c.width; t.height = c.height;
                const x = t.getContext('2d'); x.drawImage(c, 0, 0); const a = x.getImageData(0, 0, t.width, t.height).data; let n = 0; const r0 = a[0], g0 = a[1], b0 = a[2];
                for (let i = 0; i < a.length; i += 4) if (Math.abs(a[i] - r0) + Math.abs(a[i + 1] - g0) + Math.abs(a[i + 2] - b0) > 30) n++; return n; }""")
            if lit < 500: fails.append(f"{name}: map canvas looks empty ({lit} px differ from the corner)")
            ov = await pg.evaluate("[document.documentElement.scrollWidth, innerWidth, document.getElementById('panel').scrollWidth, document.getElementById('panel').clientWidth]")
            if ov[0] > ov[1] or ov[2] > ov[3] + 1: fails.append(f"{name}: horizontal overflow {ov}")
            unnamed = await pg.evaluate("""[...document.querySelectorAll('button,input,select')].filter(e => !(e.getAttribute('aria-label') || e.textContent.trim() || (e.labels && e.labels.length) || e.getAttribute('title'))).map(e => e.outerHTML.slice(0, 80))""")
            if unnamed: fails.append(f"{name}: controls without a name {unnamed}")
            if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-change.png"))
            # exercise controls: scenario, period, dispersal, toggles, species, place
            await pg.click("#ssp button:nth-child(4)"); await pg.wait_for_function("window.__sceneReady>=2", timeout=60000)
            await pg.click("#per button:nth-child(2)"); await pg.click("#disp button:nth-child(2)")
            await pg.check("#o-agree"); await pg.check("#o-novel"); await pg.wait_for_timeout(1200)
            if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-ssp585-2100-limited-overlays.png"))
            await pg.click("#view button:nth-child(1)"); await pg.wait_for_timeout(500)
            await pg.fill("#search", "tick"); await pg.keyboard.press("ArrowDown"); await pg.keyboard.press("Enter"); await pg.wait_for_function("window.__sceneReady>=3", timeout=60000); await pg.wait_for_timeout(1200)
            if "Forest tick" not in await pg.inner_text("#sp-head"): fails.append(f"{name}: search did not select the tick")
            await pg.click("#view button:nth-child(3)"); await pg.uncheck("#o-novel"); await pg.wait_for_timeout(800)
            if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-tick.png"))
            if w < 500:
                await pg.click("#grab"); await pg.wait_for_timeout(500)
                if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-sheet-full.png"))
                await pg.click("#grab"); await pg.click("#sh-tog"); await pg.wait_for_timeout(500)
                if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-sheet-peek.png"))
                await pg.click("#sh-tog")
            else:
                await pg.evaluate("document.getElementById('panel').scrollTop=1e5"); await pg.wait_for_timeout(300)
                if SHOTS: await pg.screenshot(path=str(OUT / f"{name}-panel-bottom.png"))
            # keyboard: Tab reaches the first controls in order
            await pg.focus("#search"); seq = []
            for _ in range(6):
                await pg.keyboard.press("Tab"); seq.append(await pg.evaluate("document.activeElement.id || document.activeElement.tagName"))
            await pg.select_option("#place", index=5); await pg.wait_for_timeout(200)
            ov = await pg.evaluate("[document.documentElement.scrollWidth, innerWidth, document.getElementById('panel').scrollWidth, document.getElementById('panel').clientWidth]")
            if ov[0] > ov[1] or ov[2] > ov[3] + 1: fails.append(f"{name}: horizontal overflow after interaction {ov}")
            if errs: fails.append(f"{name}: errors {errs[:3]}")
            print(name, "ok" if not errs else "errors", "lit px", lit, "tab order", seq)
            await ctx.close()
        await b.close()
    for f in fails: print("FAIL", f)
    sys.exit(1 if fails else 0)


asyncio.run(main())
