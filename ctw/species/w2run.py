"""W2 production runner (GitHub Actions). Resumable: all state lives in the GitHub release `species-pilot-data` (intermediate assets
`w2-*`), so a run that is cut off, or that hits the 6 hour job limit, is simply started again.

  python -m ctw.species.w2run acquire [--hours 5.5]   request GBIF downloads (3 at a time), wait, fetch, clean, upload `w2-cells-*`,
                                                      `w2-report-*`, `w2-tg-*`, and keep `w2-state.json` (download keys, DOIs) current
  python -m ctw.species.w2run assemble                masks, flags, time split, well-sampled flags, final assets, manifest

GBIF credentials come from the environment (GBIF_USER, GBIF_PWD, GBIF_EMAIL) and are never printed. Set W2_NO_RELEASE=1 to run without the
release (local tests; state then lives in the work folder only).
"""
from __future__ import annotations
import csv, hashlib, json, os, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from . import gbif, native as N, tg, w2cells

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(os.environ.get("W2_WORK", ROOT / "work" / "w2"))
TAG = "species-pilot-data"
NO_REL = os.environ.get("W2_NO_RELEASE") == "1"
VERSION = "v1"
YEAR_Q = os.environ.get("W2_YEAR_Q", '"year"')


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def slug(sci: str) -> str:
    return sci.replace(" ", "_")


def pilot() -> list[dict]:
    rows = list(csv.DictReader(open(ROOT / "data" / "species" / "pilot_v1.csv")))
    keys = {r["scientific_name"]: r for r in csv.DictReader(open(ROOT / "data" / "species" / "native" / "pilot_taxa_resolved.csv"))}
    for r in rows:
        r["taxon_key"] = int(keys[r["scientific_name"]]["gbif_taxon_key"])
    return rows


# --------------------------------------------------------------------------- release as storage
def sh(args, check=True, capture=True):
    return subprocess.run(args, check=check, capture_output=capture, text=True)


def ensure_release():
    if NO_REL:
        return
    if sh(["gh", "release", "view", TAG], check=False).returncode != 0:
        r = sh(["gh", "release", "create", TAG, "--title", "Species pilot data", "--notes", "Data assets of the species pilot (W1 to W5)."], check=False)
        if r.returncode != 0:
            sh(["gh", "release", "view", TAG])          # created by another workstream in the meantime


def rel_assets() -> dict:
    if NO_REL:
        return {p.name: p.stat().st_size for p in (WORK / "release").glob("*")} if (WORK / "release").exists() else {}
    r = sh(["gh", "release", "view", TAG, "--json", "assets"], check=False)
    if r.returncode != 0:
        return {}
    return {a["name"]: a["size"] for a in json.loads(r.stdout)["assets"]}


def rel_get(name: str, dest: Path) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if NO_REL:
        f = WORK / "release" / name
        if f.exists():
            dest.write_bytes(f.read_bytes())
            return dest
        return None
    r = sh(["gh", "release", "download", TAG, "-p", name, "-D", str(dest.parent), "--clobber"], check=False)
    got = dest.parent / name
    if r.returncode == 0 and got.exists():
        if got != dest:
            got.replace(dest)
        return dest
    return None


def rel_put(path: Path, name: str | None = None):
    name = name or path.name
    if NO_REL:
        d = WORK / "release"; d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(Path(path).read_bytes())
        return
    src = Path(path)
    if src.name != name:
        tmp = Path(tempfile.mkdtemp()) / name
        tmp.write_bytes(src.read_bytes()); src = tmp
    for i in range(4):
        r = sh(["gh", "release", "upload", TAG, str(src), "--clobber"], check=False)
        if r.returncode == 0:
            return
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"upload failed: {name}: {r.stderr[:300]}")


# --------------------------------------------------------------------------- state
class State:
    """Download keys and GBIF metadata per job; mirrored to the release after every change."""

    def __init__(self):
        self.lock = threading.Lock()
        self.f = WORK / "w2-state.json"
        self.d: dict = {}
        got = rel_get("w2-state.json", self.f)
        if got:
            self.d = json.load(open(self.f))
        # seeds: spike A downloads (6 Oct 2026) and any keys committed with the workflow
        seeds = {}
        for sci, row in json.load(open(ROOT / "docs" / "spikes" / "data" / "spike-a" / "run6-results.json")).items():
            seeds[sci] = row["key"]
        kf = ROOT / ".github" / "run" / "pilot-w2-keys.json"
        if kf.exists():
            seeds.update(json.load(open(kf)))
        for sci, key in seeds.items():
            self.d.setdefault(f"species:{sci}", {"key": key, "source": "seed"})

    def get(self, job):
        return self.d.get(job, {})

    def set(self, job, **kw):
        with self.lock:
            self.d.setdefault(job, {}).update(kw)
            self.f.parent.mkdir(parents=True, exist_ok=True)
            self.f.write_text(json.dumps(self.d, indent=1, default=str))
            try:
                rel_put(self.f)
            except Exception as e:
                log("state upload failed", type(e).__name__)


# --------------------------------------------------------------------------- GBIF jobs
def request_sql(sql: str) -> str:
    body = {"creator": os.environ["GBIF_USER"], "notificationAddresses": [os.environ["GBIF_EMAIL"]], "sendNotification": False,
            "format": "SQL_TSV_ZIP", "sql": sql}
    r = requests.post(f"{gbif.API}/occurrence/download/request", json=body, auth=gbif.auth(), timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"download request refused: HTTP {r.status_code} {r.text[:400]}")
    return r.text.strip().strip('"')


def fetch_zip(link: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    f = dest / "dl.zip"
    for i in range(5):
        try:
            with requests.get(link, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(f, "wb") as o:
                    for ch in r.iter_content(1 << 22):
                        o.write(ch)
            return f
        except Exception:
            if i == 4:
                raise
            time.sleep(10 * (i + 1))
    return f


def download_meta(s: dict, key: str) -> dict:
    return {"status": s.get("status"), "doi": s.get("doi"), "records": s.get("totalRecords"), "size_bytes": s.get("size"),
            "created": s.get("created"), "modified": s.get("modified"), "erase_after": s.get("eraseAfter"),
            "format": (s.get("request") or {}).get("format"), "licence": s.get("license"), "citation": gbif.citation(key, s),
            "predicate": (s.get("request") or {}).get("predicate"), "sql": (s.get("request") or {}).get("sql")}


_REF = {}
GROUP_OF = {r["scientific_name"]: r["group"] for r in csv.DictReader(open(ROOT / "data" / "species" / "pilot_v1.csv"))}


def ref_set():
    if "v" not in _REF:
        _REF["v"] = w2cells.reference_set(WORK / "cache")
    return _REF["v"]


def process_species(sci: str, key: str, state: State):
    group = GROUP_OF.get(sci, "")
    import shutil, zipfile
    job = f"species:{sci}"
    t0 = time.time()
    s = gbif.status(key)
    meta = download_meta(s, key)
    if s["status"] != "SUCCEEDED":
        state.set(job, **meta)
        return False
    tmp = Path(os.environ.get("W2_TMP", tempfile.gettempdir())) / f"w2-{slug(sci)}"
    shutil.rmtree(tmp, ignore_errors=True)
    z = fetch_zip(s["downloadLink"], tmp)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(tmp)
    z.unlink()
    ref, land = ref_set()
    cc = w2cells.CellCleaner(land=land, ref=ref, keep_cultivated=(group == "crop"))
    for d in w2cells.read_batches(tmp):
        cc.feed(d)
    cells, rep = cc.finish()
    shutil.rmtree(tmp, ignore_errors=True)
    rep.update({"group": group, "treatment": "crop_cultivated" if group == "crop" else "wild_native", "species": sci, "download_key": key, "process_s": round(time.time() - t0), **{k: meta[k] for k in ("doi", "records", "created", "citation", "licence")}})
    out = WORK / "cells"; out.mkdir(parents=True, exist_ok=True)
    cells.to_parquet(out / f"w2-cells-{slug(sci)}.parquet", compression="zstd", index=False)
    (out / f"w2-report-{slug(sci)}.json").write_text(json.dumps(rep, indent=1))
    (out / f"w2-datasets-{slug(sci)}.json").write_text(json.dumps(cc.datasets))
    rel_put(out / f"w2-datasets-{slug(sci)}.json")
    rel_put(out / f"w2-cells-{slug(sci)}.parquet")
    rel_put(out / f"w2-report-{slug(sci)}.json")
    state.set(job, **meta, processed=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    log("processed", sci, rep["n_cells"], "cells", rep["steps"][0]["left"], "records", f"{rep['process_s']}s")
    return True


def process_tg(group: str, key: str, state: State):
    import shutil
    job = f"tg:{group}"
    s = gbif.status(key)
    meta = download_meta(s, key)
    if s["status"] != "SUCCEEDED":
        state.set(job, **meta)
        return False
    tmp = Path(tempfile.gettempdir()) / f"w2-tg-{group}"
    shutil.rmtree(tmp, ignore_errors=True)
    z = fetch_zip(s["downloadLink"], tmp)
    g, seen, nrows = tg.parse_tsv_zip(str(z), with_seen=True)
    meta["rows_in_sql_result"], meta["values_seen"] = nrows, seen
    if int(g[0].sum()) == 0:
        state.set(job, **meta, processed=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), total=0)
        raise RuntimeError(f"target group {group}: the SQL download is empty, not stored")
    out = WORK / "tg"; out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / f"w2-tg-{group}.npz", grid=g)
    rel_put(out / f"w2-tg-{group}.npz")
    shutil.rmtree(tmp, ignore_errors=True)
    state.set(job, **meta, processed=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), total=int(g[0].sum()), cells=int((g[0] > 0).sum()))
    log("processed tg", group, int(g[0].sum()), "records in", int((g[0] > 0).sum()), "cells")
    return True


def acquire(hours: float):
    ensure_release()
    state = State()
    have = rel_assets()
    rows = pilot()
    jobs = []        # (job id, kind, name, request fn)
    def req_tg(g):
        last = None
        for yq in ([YEAR_Q] if os.environ.get("W2_YEAR_Q") else ['"year"', "`year`", "year"]):
            try:
                return request_sql(tg.sql_for(g, yq))
            except RuntimeError as e:
                last = e
                if "HTTP 400" not in str(e):
                    raise
                log("sql refused", g, yq, str(e)[:200])
        raise last
    for g in tg.GROUPS:            # target-group SQL downloads first: they are the slowest and the least certain
        jobs.append((f"tg:{g}", "tg", g, lambda g=g: req_tg(g)))
    for r in rows:
        sci = r["scientific_name"]
        jobs.append((f"species:{sci}", "species", sci, lambda t=r["taxon_key"]: gbif.request_download(t)))

    def done(job, kind, name):
        return (f"w2-cells-{slug(name)}.parquet" in have and f"w2-report-{slug(name)}.json" in have and f"w2-datasets-{slug(name)}.json" in have) if kind == "species" else (f"w2-tg-{name}.npz" in have and (state.get(job).get("total") or 0) > 0)

    for g in tg.GROUPS:        # an earlier SQL download that came back empty is never reused
        if state.get(f"tg:{g}").get("processed") and not (state.get(f"tg:{g}").get("total") or 0) > 0:
            state.set(f"tg:{g}", key=None, processed=None, total=None, status=None)
            log("discarded empty target-group download", g)
    todo = [j for j in jobs if not done(*j[:3])]
    log(f"{len(jobs) - len(todo)} of {len(jobs)} jobs already stored, {len(todo)} to do")
    deadline = time.time() + hours * 3600
    pending: dict[str, str] = {}              # job -> key being prepared by GBIF
    ex = ThreadPoolExecutor(max_workers=2)
    futures: dict = {}
    failed = {}
    queue = list(todo)
    state.set("_run", started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    while queue or pending or futures:
        # finished processing
        for job, fut in list(futures.items()):
            if fut.done():
                del futures[job]
                try:
                    ok = fut.result()
                except Exception as e:
                    failed[job] = f"{type(e).__name__}: {e}"[:300]
                    log("processing failed", job, failed[job])
        # start / resume requests while slots are free
        for j in list(queue):
            job, kind, name, req = j
            known = state.get(job).get("key")
            if known:
                st = gbif.status(known)
                if st["status"] in ("FAILED", "CANCELLED", "KILLED", "FILE_ERASED"):
                    log("download", job, "ended as", st["status"], "- requesting a new one")
                    known = None
            if known:
                queue.remove(j); pending[job] = known
                continue
            if len(pending) >= 3 or time.time() > deadline - 600:
                continue
            try:
                key = req()
            except RuntimeError as e:
                if "420" in str(e):
                    continue
                failed[job] = str(e)[:300]; queue.remove(j); log("request failed", job, failed[job]); continue
            state.set(job, key=key, requested=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), source="requested")
            queue.remove(j); pending[job] = key
            log("requested", job, key)
        # poll
        for job, key in list(pending.items()):
            st = gbif.status(key)
            if st["status"] in ("PREPARING", "RUNNING", "SUSPENDED"):
                continue
            del pending[job]
            kind, name = job.split(":", 1)
            if st["status"] != "SUCCEEDED":
                failed[job] = st["status"]; state.set(job, **download_meta(st, key)); log("download", job, st["status"]); continue
            log("ready", job, key)
            futures[job] = ex.submit(process_species if kind == "species" else process_tg, name, key, state)
        if time.time() > deadline:
            log("time limit reached; state saved, start the workflow again to continue")
            break
        time.sleep(30 if (pending or queue) else 5)
    ex.shutdown(wait=True)
    left = [j[0] for j in jobs if not (done(*j[:3]) or state.get(j[0]).get("processed"))]
    log("failed:", failed, "| not yet processed:", left)
    (WORK / "acquire_summary.json").write_text(json.dumps({"failed": failed, "not_processed": left}, indent=1))
    return 0 if not failed else 1


def diag():
    """Why did the target-group SQL return 0 rows? One taxon-only query that groups by the columns the real filter tests and prints the
    values GBIF's SQL engine uses for them (no credentials printed)."""
    sql = ('SELECT license, hasCoordinate, hasGeospatialIssues, occurrenceStatus, basisOfRecord, '
           'FLOOR((90 - decimalLatitude) * 24) AS r, IF("year" <= 1999, 1, 2) AS p, COUNT(*) AS n FROM occurrence WHERE species = 'Ixodes scapularis' '
           'GROUP BY license, hasCoordinate, hasGeospatialIssues, occurrenceStatus, basisOfRecord, FLOOR((90 - decimalLatitude) * 24), IF("year" <= 1999, 1, 2)')
    t0 = time.time()
    while True:
        try:
            key = request_sql(sql); break
        except RuntimeError as e:
            log("request:", str(e)[:300])
            if "420" not in str(e) or time.time() - t0 > 3600:
                return 1
            time.sleep(60)
    log("diag download", key)
    s = gbif.wait(key, every=30, limit_s=90 * 60)
    log("status", s.get("status"), s.get("totalRecords"))
    if s.get("status") == "SUCCEEDED":
        import io, zipfile
        z = zipfile.ZipFile(io.BytesIO(requests.get(s["downloadLink"], timeout=300).content))
        df = pd.read_csv(z.open(z.namelist()[0]), sep="\t")
        for c in ["license", "hasCoordinate", "hasGeospatialIssues", "occurrenceStatus", "basisOfRecord"]:
            if c in df:
                log(c, df.groupby(c)["n"].sum().to_dict())
        log("columns", list(df.columns), "rows", len(df))
        log(df.head(8).to_string())
    return 0


# --------------------------------------------------------------------------- assemble
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def assemble():
    ensure_release()
    cache = WORK / "cache"; cache.mkdir(parents=True, exist_ok=True)
    out = WORK / "final"; out.mkdir(parents=True, exist_ok=True)
    rows = pilot()
    state = State()
    fe = N.subunits(cache); lab = N.label_raster(fe)
    td = N.tdwg_units(cache); labt = N.label_raster(td)
    unit_cont = np.array(["-"] + [f["properties"].get("CONTINENT") or "-" for f in fe])
    wcvp = json.load(open(N.DATA_DIR / "wcvp_pilot.json"))
    griis = json.load(open(N.DATA_DIR / "griis_pilot.json"))
    groups = {}
    for gname in tg.GROUPS:
        p = rel_get(f"w2-tg-{gname}.npz", WORK / "tg" / f"w2-tg-{gname}.npz")
        groups[gname] = np.load(p)["grid"] if p else None
        log("target group", gname, "available" if p else "MISSING")
    species_tables, excluded_tables, report, masks = [], [], {}, {}
    pooled: dict[str, np.ndarray] = {}
    for r in rows:
        sci = r["scientific_name"]; tgname = tg.PILOT_GROUP_TO_TG[r["group"]]
        pc = rel_get(f"w2-cells-{slug(sci)}.parquet", WORK / "cells" / f"w2-cells-{slug(sci)}.parquet")
        pr = rel_get(f"w2-report-{slug(sci)}.json", WORK / "cells" / f"w2-report-{slug(sci)}.json")
        if not pc:
            log("MISSING cells for", sci); report[sci] = {"missing": True}; continue
        cells = pd.read_parquet(pc); rep = json.load(open(pr))
        cur = N.curated_mask(r["native_continents_curated"], fe, lab)
        has_w = sci in wcvp
        wm = N.tdwg_mask(wcvp[sci]["native"], td, labt) if has_w else None
        is_crop = r["group"] == "crop"
        final = np.ones((N.NROW, N.NCOL), bool) if is_crop else (wm if has_w else cur)
        gi = N.griis_units(griis.get(sci, []), fe)
        gm = np.zeros(len(fe) + 1, bool)
        for i in gi:
            gm[i + 1] = True
        gmask = gm[lab]
        ri, ci = cells["row"].to_numpy(), cells["col"].to_numpy()
        cells["native_curated"] = cur[ri, ci]
        cells["native_wcvp"] = (wm[ri, ci].astype(np.int8) if has_w else np.int8(-1))
        cells["griis_intro"] = gmask[ri, ci]
        keep = final[ri, ci]
        removed = cells[~keep]
        rm_cont = pd.Series(unit_cont[lab[removed["row"].to_numpy(), removed["col"].to_numpy()]]).value_counts().to_dict()
        ambiguous = [x for x in griis.get(sci, []) if not ((x.get("establishmentMeans") or "").upper().startswith("INTRODUCED"))]
        rep["native_mask"] = {
            "source": ("none: crop modelled where cultivated (owner decision, no wild native-range mask)" if is_crop else "WCVP (data, TDWG level 3)" if has_w else "curated (our judgement, Natural Earth subunits)"),
            "treatment": "crop_cultivated" if is_crop else "wild_native",
            "curated_spec": r["native_continents_curated"], "mask_cells_land_curated": int(cur.sum()), "mask_cells_final": int(final.sum()),
            "cells_in": int(len(cells)), "cells_kept": int(keep.sum()), "cells_removed": int((~keep).sum()),
            "records_in": int(cells["n_records"].sum()), "records_kept": int(cells.loc[keep, "n_records"].sum()),
            "removed_cells_by_continent": {str(k): int(v) for k, v in rm_cont.items()},
            "cells_kept_not_in_curated": int((keep & ~cells["native_curated"].to_numpy()).sum()),
            "cells_curated_but_removed": int((~keep & cells["native_curated"].to_numpy()).sum()),
            "cells_kept_in_griis_introduced_country": int((keep & cells["griis_intro"].to_numpy()).sum()),
            "griis_units": sorted({fe[i]["properties"]["NAME"] for i in gi}),
            "griis_rows_total": len(griis.get(sci, [])), "griis_rows_ambiguous_not_applied": len(ambiguous),
            "wcvp_native_areas": len(wcvp[sci]["native"]) if has_w else None}
        if not is_crop:
            masks[f"{slug(sci)}__final"] = np.packbits(final, axis=1)
        masks[f"{slug(sci)}__curated"] = np.packbits(cur, axis=1)
        for df, bucket in ((cells[keep], species_tables), (removed, excluded_tables)):
            df = df.copy()
            df.insert(0, "species", sci); df.insert(0, "species_key", r["taxon_key"])
            df["group"] = r["group"]; df["tg_group"] = tgname
            df["treatment"] = "crop_cultivated" if is_crop else "wild_native"
            df["kind"] = "crop" if is_crop else "wild"
            bucket.append(df)
        pooled.setdefault(tgname, np.zeros((3, 1, 1)))      # placeholder: pooled fallback is built below only when the group grid is missing
        report[sci] = rep
    main = pd.concat(species_tables, ignore_index=True)
    excl = pd.concat(excluded_tables, ignore_index=True) if excluded_tables else main.iloc[:0]
    # target-group well-sampled flags
    for name, df in (("main", main), ("excl", excl)):
        for c in ("tg_block_p1", "tg_block_p2"):
            df[c] = np.int64(-1)
        df["ws20"] = False; df["ws100"] = False
        df["tg_source"] = "none"
    for gname, grid in groups.items():
        for df in (main, excl):
            m = (df["tg_group"] == gname).to_numpy()
            if not m.any():
                continue
            if grid is None:
                # fallback: pool the kept pilot cells of this group (record counts per period) as a crude density
                pool = main[(main["tg_group"] == gname)]
                g = np.zeros((3, tg.NROW, tg.NCOL), np.uint32)
                np.add.at(g[1], (pool["row"].to_numpy(), pool["col"].to_numpy()), pool["n_1970_1999"].to_numpy().astype(np.uint32))
                np.add.at(g[2], (pool["row"].to_numpy(), pool["col"].to_numpy()), pool["n_2000_2020"].to_numpy().astype(np.uint32))
                src = "pooled pilot species (fallback, weak)"
            else:
                g, src = grid, "gbif sql download"
            lk = tg.lookup(g, df.loc[m, "row"].to_numpy(), df.loc[m, "col"].to_numpy())
            for k, v in lk.items():
                df.loc[m, k] = v
            df.loc[m, "tg_source"] = src
    ordered = ["species_key", "species", "group", "kind", "treatment", "tg_group", "row", "col", "lat", "lon", "year_min", "year_max", "n_records", "n_events",
               "n_1970_1999", "n_2000_2020", "n_2021_plus", "native_curated", "native_wcvp", "griis_intro", "tg_block_p1", "tg_block_p2", "ws20", "ws100", "tg_source"]
    main, excl = main[ordered], excl[ordered] if len(excl) else excl
    files = {}

    def save(df, name):
        p = out / name; df.to_parquet(p, compression="zstd", index=False); files[name] = p
    crops = main[main["treatment"] == "crop_cultivated"]
    main = main[main["treatment"] == "wild_native"]
    save(crops, f"occ_cells_crops_cultivated_pilot_{VERSION}.parquet")      # crops: where cultivated, no wild native-range mask
    save(main, f"occ_cells_pilot_{VERSION}.parquet")
    main.to_csv(out / f"occ_cells_pilot_{VERSION}.csv.gz", index=False, compression="gzip"); files[f"occ_cells_pilot_{VERSION}.csv.gz"] = out / f"occ_cells_pilot_{VERSION}.csv.gz"
    save(excl, f"occ_cells_pilot_{VERSION}_excluded_non_native.parquet")
    ws = main[main["ws20"]]
    p1 = ws[ws["n_1970_1999"] > 0].copy(); p1["in_other_period"] = p1["n_2000_2020"] > 0
    p2 = ws[ws["n_2000_2020"] > 0].copy(); p2["in_other_period"] = p2["n_1970_1999"] > 0
    save(p1, f"occ_cells_pilot_{VERSION}_p1_1970_1999_wellsampled.parquet")
    save(p2, f"occ_cells_pilot_{VERSION}_p2_2000_2020_wellsampled.parquet")
    p = out / f"native_masks_pilot_{VERSION}.npz"
    np.savez_compressed(p, **masks); files[p.name] = p
    for gname, grid in groups.items():
        if grid is not None:
            p = out / f"tg_density_{gname}_{VERSION}.npz"
            np.savez_compressed(p, all=grid[0], p1_1970_1999=grid[1], p2_2000_2020=grid[2]); files[p.name] = p
    for sci, rep in report.items():
        rep["download_state"] = {k: v for k, v in state.get(f"species:{sci}").items() if k not in ("predicate",)}
        dp = rel_get(f"w2-datasets-{slug(sci)}.json", WORK / "cells" / f"w2-datasets-{slug(sci)}.json")
        if dp:
            rep["dataset_counts"] = json.load(open(dp))      # records per GBIF datasetKey (input for a derived-dataset registration)
    summary = {"version": VERSION, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "species": report,
               "target_group_downloads": {g: {k: v for k, v in state.get(f"tg:{g}").items()} for g in tg.GROUPS}}
    p = out / f"w2_report_pilot_{VERSION}.json"; p.write_text(json.dumps(summary, indent=1, default=str)); files[p.name] = p
    manifest = {"version": VERSION, "built": summary["built"], "grid": "TerraClimate native 1/24 degree, 4320 x 8640, row 0 = north, cell centre lat = 90 - (row + 0.5) / 24, lon = -180 + (col + 0.5) / 24",
                "licence_filter": "CC0 and CC-BY records only",
                "species_kind": {r["scientific_name"]: ("crop" if r["group"] == "crop" else "wild") for r in rows},
                "kind_note": "crop = modelled where cultivated (CULTIVATED / MANAGED records kept, no native-range mask); wild = CULTIVATED / MANAGED / INTRODUCED records dropped and native-range mask applied", "files": {n: {"bytes": f.stat().st_size, "sha256": sha256(f)} for n, f in files.items()}}
    mp = out / f"manifest_w2_{VERSION}.json"; mp.write_text(json.dumps(manifest, indent=1))
    for n, f in files.items():
        rel_put(f)
    rel_put(mp)
    log("published", len(files) + 1, "assets")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "acquire":
        hrs = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 5.5
        sys.exit(acquire(hrs))
    sys.exit({"assemble": assemble, "diag": diag}[cmd]())
