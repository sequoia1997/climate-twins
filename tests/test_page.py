"""Load the built site in a headless browser and exercise it. Usage: python tests/test_page.py site [place ...]
Fails (exit 1) on any JavaScript error, a panel without results, or missing new sections.
Environment: PW_CHROMIUM (browser binary) and PW_MAPLIBRE_DIR (local MapLibre dist) for offline use."""
import asyncio, functools, http.server, os, sys, threading
from playwright.async_api import async_playwright

SITE = sys.argv[1] if len(sys.argv) > 1 else "site"
PLACES = sys.argv[2:] or ["Raleigh, NC", "Phoenix, AZ", "Anchorage, AK", "Singapore", "Lima", "Reykjav", "Sydney", "Miami, FL"]


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    h = functools.partial(Quiet, directory=SITE)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


async def main():
    port = serve()
    fails = []
    async with async_playwright() as p:
        kw = {"args": ["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]}
        if os.environ.get("PW_CHROMIUM"):
            kw["executable_path"] = os.environ["PW_CHROMIUM"]
        b = await p.chromium.launch(**kw)
        for w, h, scheme in [(1440, 900, "light"), (390, 844, "dark")]:
            ctx = await b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme, reduced_motion="reduce")
            if os.environ.get("PW_MAPLIBRE_DIR"):
                d = os.environ["PW_MAPLIBRE_DIR"]
                async def lib(r): await r.fulfill(path=os.path.join(d, r.request.url.split("/dist/")[-1]))
                await ctx.route("https://cdn.jsdelivr.net/npm/maplibre-gl@*/dist/*", lib)
                await ctx.route("https://tiles.openfreemap.org/**", lambda r: r.abort())
                await ctx.route("https://fonts.googleapis.com/**", lambda r: r.abort())
            pg = await ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            await pg.goto(f"http://127.0.0.1:{port}/index.html")
            await pg.wait_for_function("document.getElementById('loading')===null", timeout=240000)
            await pg.wait_for_function("worldState!=='loading'", timeout=120000)
            ws = await pg.evaluate("worldState")
            if ws != "ready":
                fails.append(f"world data did not load ({ws})")
            nv = await pg.evaluate("NV")
            for place in PLACES:
                i = await pg.evaluate(f"D.targets.findIndex(t=>t.n.startsWith({place!r}))")
                if i < 0:
                    fails.append(f"place not found: {place}")
                    continue
                await pg.evaluate(f"select({i},false)")
                await pg.wait_for_timeout(300)
                txt = await pg.inner_text("#result")
                if "How the climates compare" not in txt:
                    fails.append(f"{place}: no comparison")
                if nv >= 16 and "Humidity" not in txt:
                    fails.append(f"{place}: no humidity section")
                if nv >= 16 and "Hardiness zone" not in txt:
                    fails.append(f"{place}: no climate type / zone table")
            att = await pg.inner_text("#attrib")
            if "Methods & Sources" not in att:
                fails.append("attribution missing the methods link")
            fails += [f"{w}px {scheme}: JavaScript error: {e}" for e in errs]
            await ctx.close()
        await b.close()
    if fails:
        print("PAGE TEST FAILED\n" + "\n".join(fails))
        sys.exit(1)
    print(f"page test passed ({len(PLACES)} places, 2 viewports)")


asyncio.run(main())
