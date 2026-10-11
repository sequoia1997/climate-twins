"""W4 probe 2: file listings inside the Forest Service RDS zips (ranged reads of the central directory) and FIA coordinate-fuzzing text."""
import io, re, sys, zipfile, urllib.request
UA = {"User-Agent": "climate-twins-w4/0.1 (mailto:forest4science@gmail.com)"}
class Ranged(io.RawIOBase):
    def __init__(self, url):
        self.url = url; self.pos = 0
        r = urllib.request.urlopen(urllib.request.Request(url, headers=dict(UA, Range="bytes=0-0")), timeout=60)
        cr = r.headers.get("Content-Range"); self.size = int(cr.split("/")[1]) if cr else int(r.headers.get("Content-Length", 0))
        print("  size", self.size, "range support", bool(cr), flush=True)
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self, o, w=0):
        self.pos = o if w == 0 else self.pos + o if w == 1 else self.size + o; return self.pos
    def readinto(self, b):
        n = len(b)
        if self.pos >= self.size: return 0
        end = min(self.pos + n, self.size) - 1
        d = urllib.request.urlopen(urllib.request.Request(self.url, headers=dict(UA, Range="bytes=%d-%d" % (self.pos, end))), timeout=120).read()
        b[:len(d)] = d; self.pos += len(d); return len(d)
for rid in ("RDS-2019-0029", "RDS-2024-0020"):
    u = "https://www.fs.usda.gov/rds/archive/products/%s/%s.zip" % (rid, rid)
    print("\n==", u, flush=True)
    try:
        z = zipfile.ZipFile(io.BufferedReader(Ranged(u), 1 << 16))
        names = z.namelist(); print("  entries", len(names))
        for n in names[:60]: print("   ", n, z.getinfo(n).file_size)
        for kw in ("acesac", "acer", "sugar", "ACSA", "saccharum", "quealb", "pinstr", "poptre", "acerub"):
            print("  entries containing", kw, [n for n in names if kw.lower() in n.lower()][:6])
    except Exception as e: print("  FAIL", type(e).__name__, e)
for u in ("https://www.fs.usda.gov/rds/archive/products/RDS-2024-0020/RDS-2024-0020_Metadata_Fileindex.zip",):
    print("\n==", u, flush=True)
    try:
        b = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=120).read()
        z = zipfile.ZipFile(io.BytesIO(b)); names = z.namelist(); print("  entries", len(names), names[:40])
        for n in names:
            if n.lower().endswith((".csv", ".txt")) and z.getinfo(n).file_size < 3_000_000:
                t = z.read(n).decode("latin-1"); print("  --", n, len(t)); print(t[:1500])
                for kw in ("saccharum", "alba", "strobus", "tremuloides", "rubrum", "Acer"):
                    print("    count", kw, t.count(kw))
    except Exception as e: print("  FAIL", type(e).__name__, e)
def text(h):
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h); return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))
for u in ("https://research.fs.usda.gov/programs/fia/plot-location", "https://research.fs.usda.gov/products/dataandtools/fia-datamart",
          "https://research.fs.usda.gov/programs/fia/data-tools", "https://research.fs.usda.gov/understory/forest-inventory-and-analysis-database-user-guide-nfi",
          "https://www.fia.fs.usda.gov/library/field-guides-methods-proc/", "https://research.fs.usda.gov/programs/fia/faq"):
    try:
        h = urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read(4_000_000).decode("utf8", "replace")
        t = text(h); print("\n==", u, len(t))
        for m in re.finditer(r"(?i)(fuzz|swap|perturb|confidential)", t):
            print("   ...", t[max(0, m.start() - 250):m.start() + 350]); break
    except Exception as e: print("\n==", u, "FAIL", type(e).__name__, str(e)[:100])
