"""Load the built site in a headless browser and exercise it. Usage: python tests/test_page.py site [place ...]
Fails (exit 1) on any JavaScript error, a panel without results, or missing new sections. Also checks the download
plan: at load the page fetches only index.json, overview.dat and na.dat (no per-place shard); picking a place fetches
its shard (once) and, for a world place, the world pool.
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
    fails, found, missing = [], set(), set()
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
            errs, fetched = [], []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("response", lambda r: fetched.append((r.url.split("/", 3)[-1].split("?")[0], int(r.headers.get("content-length", 0)))) if "/data/" in r.url else None)
            await pg.goto(f"http://127.0.0.1:{port}/index.html")
            await pg.wait_for_function("document.getElementById('loading')===null", timeout=240000)
            first = [u for u, _ in fetched]
            sharded = "data/index.json" in first
            if not sharded:
                fails.append("data/index.json was not fetched")
            if any(u.startswith("data/p/") for u in first):
                fails.append(f"per-place shards were fetched before any pick: {[u for u in first if u.startswith('data/p/')]}")
            if sharded:
                nt = await pg.evaluate("[NT,D.targets.length,D.idx.rows.length,D.idx.shards.reduce((a,s)=>a+s.n,0)]")
                if len(set(nt)) != 1:
                    fails.append(f"place counts disagree: {nt}")
                if w == 1440:
                    print(f"startup download: {sum(b for u, b in fetched if u != 'data/world.dat') / 1e6:.2f} MB (index, overview, North America pool); {nt[0]} places, {len(await pg.evaluate('D.idx.shards'))} shards")
            nv = await pg.evaluate("NV")
            picked, world_picked = set(), False
            for place in PLACES:
                i = await pg.evaluate(f"D.targets.findIndex(t=>t.n.startsWith({place!r}))")
                if i < 0:
                    missing.add(place)                          # quick test runs build only 12 places
                    continue
                found.add(place)
                before = sum(1 for u, _ in fetched if u.startswith("data/p/"))
                sh = await pg.evaluate(f"D.targets[{i}].s")
                await pg.evaluate(f"select({i},false)")        # resolves when the place's data is loaded and it is shown
                await pg.wait_for_timeout(300)
                after = sum(1 for u, _ in fetched if u.startswith("data/p/"))
                if after - before != (0 if sh in picked else 1):
                    fails.append(f"{place}: expected {0 if sh in picked else 1} shard fetches, saw {after - before}")
                picked.add(sh)
                world_picked |= bool(await pg.evaluate(f"D.targets[{i}].g===1"))
                sel = await pg.evaluate("S.sel")
                if sel != i:
                    fails.append(f"{place}: not selected after select() ({sel})")
                txt = await pg.inner_text("#result")
                if "How the climates compare" not in txt:
                    fails.append(f"{place}: no comparison")
                if nv >= 16 and "Humidity" not in txt:
                    fails.append(f"{place}: no humidity section")
                if nv >= 16 and "Hardiness zone" not in txt:
                    fails.append(f"{place}: no climate type / zone table")
            if world_picked:
                ws = await pg.evaluate("worldState")
                if ws != "ready":
                    fails.append(f"world data did not load ({ws})")
            att = await pg.inner_text("#attrib")
            if "Methods & Sources" not in att:
                fails.append("attribution missing the methods link")
            fails += [f"{w}px {scheme}: JavaScript error: {e}" for e in errs]
            await ctx.close()
        await b.close()
    if len(found) < 3:
        fails.append(f"only {len(found)} of the test places exist in the data (missing: {sorted(missing)})")
    if fails:
        print("PAGE TEST FAILED\n" + "\n".join(fails))
        sys.exit(1)
    print(f"page test passed ({len(found)} places, 2 viewports)" + (f"; not in this build: {sorted(missing)}" if missing else ""))


asyncio.run(main())
