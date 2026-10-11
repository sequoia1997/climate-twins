"""Run the delivery bench in headless Chromium. Usage: python bench/bench.py ENC_DIR NPM_DIR RESULT_JSON [species]
ENC_DIR holds <ssp>/<species>/{base,scen}/... made by encode.py; NPM_DIR is a folder with node_modules/pmtiles and geotiff.
Env: PW_CHROMIUM optional. Profiles: desktop (1440x900, dpr1, no throttle) and mobile (390x844, dpr3, 1.6 Mbit/s, 150 ms RTT, CPU x4)."""
import asyncio, json, os, ssl, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from playwright.async_api import async_playwright

HERE = Path(__file__).parent
enc, npm, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
SP = sys.argv[4] if len(sys.argv) > 4 else "s01"
cert = Path(os.environ.get("CERT_DIR", "/tmp/cert"))
root = Path(tempfile.mkdtemp())
(root / "vendor").mkdir()
(root / "index.html").symlink_to(HERE / "bench.html")
(root / "vendor/pmtiles.js").symlink_to(npm / "node_modules/pmtiles/dist/pmtiles.js")
(root / "vendor/geotiff.js").symlink_to(npm / "node_modules/geotiff/dist-browser/geotiff.js")
(root / "d").symlink_to(enc.resolve())
PORT = 8443
srv = subprocess.Popen(["node", str(HERE / "serve.js"), str(root), str(PORT), str(cert)], stdout=subprocess.PIPE)
srv.stdout.readline()
ctx_ssl = ssl._create_unverified_context()
def srvlog():
    return json.load(urllib.request.urlopen(f"https://localhost:{PORT}/__log", context=ctx_ssl))

PROFILES = {
    "desktop": dict(vw=1440, vh=900, dpr=1, css=900, z=2, f=8, net=None, cpu=1),
    "mobile": dict(vw=390, vh=844, dpr=3, css=390, z=3, f=4, net=dict(offline=False, latency=150, downloadThroughput=1.6e6 / 8, uploadThroughput=0.75e6 / 8), cpu=4),
}
FMTS = ["png", "webp", "pmtiles", "cts", "cog"]

async def main():
    res = {}
    async with async_playwright() as p:
        kw = {"args": ["--no-sandbox", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-certificate-errors"]}
        if os.environ.get("PW_CHROMIUM"):
            kw["executable_path"] = os.environ["PW_CHROMIUM"]
        b = await p.chromium.launch(**kw)
        for pname, P in PROFILES.items():
            for fmt in FMTS:
                runs = []
                for rep in range(3):
                    ctx = await b.new_context(viewport={"width": P["vw"], "height": P["vh"]}, device_scale_factor=P["dpr"], ignore_https_errors=True)
                    pg = await ctx.new_page()
                    errs = []
                    pg.on("pageerror", lambda e: errs.append(str(e)))
                    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                    cdp = await ctx.new_cdp_session(pg)
                    await pg.goto(f"https://localhost:{PORT}/index.html?css={P['css']}&z={P['z']}&f={P['f']}&sp={SP}")
                    await pg.wait_for_function("window.ready===true")
                    srvlog()
                    await cdp.send("Network.enable")
                    if P["net"]:
                        await cdp.send("Network.emulateNetworkConditions", P["net"])
                    if P["cpu"] != 1:
                        await cdp.send("Emulation.setCPUThrottlingRate", {"rate": P["cpu"]})
                    try:
                        r = await pg.evaluate(f"go('{fmt}','ssp245','ssp370')")
                    except Exception as e:
                        r = {"error": str(e)[:300]}
                    r["server"] = srvlog()
                    r["errors"] = errs[:3]
                    # split the server log: everything is counted; first-draw vs switch bytes are approximated by the
                    # scen-only fraction below, so also run a first-draw-only pass for the byte count
                    runs.append(r)
                    await ctx.close()
                    print(pname, fmt, rep, {k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items() if k in ("period_switch_ms", "error")},
                          r.get("first", {}).get("total_ms"), r.get("scenario_switch", {}).get("total_ms"), r["server"]["n"], r["server"]["bytes"], flush=True)
                # bytes of first draw only
                ctx = await b.new_context(viewport={"width": P["vw"], "height": P["vh"]}, device_scale_factor=P["dpr"], ignore_https_errors=True)
                pg = await ctx.new_page()
                await pg.goto(f"https://localhost:{PORT}/index.html?css={P['css']}&z={P['z']}&f={P['f']}&sp={SP}")
                await pg.wait_for_function("window.ready===true")
                srvlog()
                try:
                    await pg.evaluate(f"go('{fmt}','ssp245',null)")
                except Exception:
                    pass
                fl = srvlog()
                await ctx.close()
                res.setdefault(pname, {})[fmt] = dict(runs=runs, first_draw_requests=fl["n"], first_draw_bytes=fl["bytes"], urls_sample=fl["urls"][:6])
        await b.close()
    out.write_text(json.dumps(res, indent=1))

try:
    asyncio.run(main())
finally:
    srv.terminate()
