"""S3 batch 5 data runner (GitHub Actions): ALL GBIF downloads requested up front, native-range masks, final occurrence assets s5_*.

  python -m ctw.species.s2run acquire [--hours 5.5]   request every download (species batches + the herp and fish target-group SQL downloads, 3 at a
                                                      a time), wait, fetch, route rows to species by specieskey, clean, store; migrants also get month counts
  python -m ctw.species.s2run native                  WCVP native areas (plants) and GRIIS introduced-country rows for the batch species
  python -m ctw.species.s2run assemble                masks, flags, target-group lookups, seasonal cells, final assets s5_*, per-species summary CSV;
                                                      FAILS LOUDLY when any species has no cells (batch-1 lesson: empty tables must never reach the fit stage)

Species and download batches: data/species/batch5.csv (status 'selected'; column dl_batch; column season = 'breeding' for migrants). Everything is stored
on the release `species-pilot-data` under names that start with s5_ (no earlier asset is ever replaced); a rerun skips what is stored (resumable).
Cleaning is the pilot's (ctw.species.w2cells.CellCleaner, one instance per species). Target-group grids: the pilot's four plus new herp and fish SQL
downloads (s2_tg_density_<group>_v1.npz). GBIF credentials come from the environment (GBIF_USER, GBIF_PWD, GBIF_EMAIL) and are never printed.
Local tests: S5_NO_RELEASE=1 (state and assets then live under the work folder).
"""
from __future__ import annotations
import csv, json, os, shutil, sys, tempfile, threading, time, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests

from . import gbif, native as N, tg, w2cells, w2run as W

ROOT = Path(__file__).resolve().parents[2]
BATCH_CSV = ROOT / "data" / "species" / "batch5.csv"
WORK = Path(os.environ.get("S5_WORK", ROOT / "work" / "s5"))
VERSION = "v1"
NO_REL = os.environ.get("S5_NO_RELEASE") == "1"
W.NO_REL = NO_REL
W.TAG = os.environ.get("W2_TAG", "species-data-batch5")
W.EXTRA_TAGS = [t for t in os.environ.get("W2_EXTRA_TAGS", "species-pilot-data").split(",") if t]
W.WORK = WORK            # w2run's release helpers use this folder in no-release mode


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def slug(sci: str) -> str:
    return sci.replace(" ", "_")


def read_batch(status: str = "selected") -> list[dict]:
    with open(BATCH_CSV, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["status"] == status]


def batches(rows) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["dl_batch"], []).append(r)
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- state (mirrored to the release as s5_state.json)
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.f = WORK / "s5_state.json"
        self.d: dict = {}
        if W.rel_get("s5_state.json", self.f):
            self.d = json.load(open(self.f))

    def get(self, job):
        return self.d.get(job, {})

    def set(self, job, **kw):
        with self.lock:
            self.d.setdefault(job, {}).update(kw)
            self.f.parent.mkdir(parents=True, exist_ok=True)
            self.f.write_text(json.dumps(self.d, indent=1, default=str))
            try:
                W.rel_put(self.f)
            except Exception as e:
                log("state upload failed", type(e).__name__)


# --------------------------------------------------------------------------- GBIF multi-species download
def predicate_multi(keys: list[int]) -> dict:
    p = gbif.predicate(keys[0])
    p["predicates"][0] = {"type": "in", "key": "TAXON_KEY", "values": [str(k) for k in keys]}      # same filters as the pilot, several taxa
    return p


def request_multi(keys: list[int]) -> str:
    body = {"creator": os.environ["GBIF_USER"], "notificationAddresses": [os.environ["GBIF_EMAIL"]], "sendNotification": False,
            "format": "SIMPLE_PARQUET", "predicate": predicate_multi(keys)}
    r = requests.post(f"{gbif.API}/occurrence/download/request", json=body, auth=gbif.auth(), timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"download request refused: HTTP {r.status_code} {r.text[:400]}")      # never echo the body: it holds the address
    return r.text.strip().strip('"')


def stored(rows, have) -> bool:
    return all(f"s5_cells_{slug(r['scientific_name'])}.parquet" in have and f"s5_report_{slug(r['scientific_name'])}.json" in have
               and f"s5_datasets_{slug(r['scientific_name'])}.json" in have
               and (not r.get("season") or f"s5_seasonal_{slug(r['scientific_name'])}.parquet" in have) for r in rows)


def route_and_clean(folder, rows: list[dict], land=None, ref=None):
    """Read the unzipped multi-species SIMPLE_PARQUET and feed each species' rows (by `specieskey`) to its own CellCleaner (the pilot's cleaning,
    unchanged). Returns ({taxon key: cleaner}, number of rows that belong to none of the species)."""
    cleaners = {int(r["gbif_taxon_key"]): w2cells.CellCleaner(land=land, ref=ref, keep_cultivated=(r["group"] == "crop")) for r in rows}
    for r in rows:
        if r.get("season"):
            cleaners[int(r["gbif_taxon_key"])].keep_months = True          # migrants: month of each record kept for the seasonal cells
    unmatched = 0
    names = {int(r["gbif_taxon_key"]): r.get("scientific_name") for r in rows}
    first = True
    for d in w2cells.read_batches(folder, extra=("specieskey", "species", "taxonkey")):
        if first:
            log("download columns used for routing:", [c for c in ("specieskey", "species", "taxonkey") if c in d])
            first = False
        hit = np.zeros(len(d), bool)
        for k, cc in cleaners.items():
            m = np.zeros(len(d), bool)
            if "specieskey" in d:
                m |= pd.to_numeric(d["specieskey"], errors="coerce").to_numpy() == k
            if "species" in d and names.get(k):
                m |= d["species"].astype("string").fillna("").to_numpy() == names[k]
            if "taxonkey" in d:
                m |= pd.to_numeric(d["taxonkey"], errors="coerce").to_numpy() == k
            m &= ~hit
            if m.any():
                cc.feed(d[m])
                hit |= m
        unmatched += int((~hit).sum())
    return cleaners, unmatched


TG_GROUPS = ("herp",)             # fish: the batch-2 target-group SQL download came back empty and batch 5 has no fish; herp grid is read from the batch-2 assets


def request_tg(g: str) -> str:
    last = None
    for yq in ('"year"', "`year`", "year"):          # the pilot found that the quoting of the year column differs; try the variants
        try:
            return W.request_sql(tg.sql_for(g, yq))
        except RuntimeError as e:
            last = e
            if "HTTP 400" not in str(e):
                raise
            log("sql refused", g, yq, str(e)[:200])
    raise last


def process_tg(g: str, key: str, state: State) -> bool:
    s = gbif.status(key)
    meta = W.download_meta(s, key)
    if s["status"] != "SUCCEEDED":
        state.set(f"tg:{g}", **meta)
        return False
    tmp = Path(tempfile.gettempdir()) / f"s2-tg-{g}"
    shutil.rmtree(tmp, ignore_errors=True)
    z = W.fetch_zip(s["downloadLink"], tmp)
    grid, seen, nrows = tg.parse_tsv_zip(str(z), with_seen=True)
    meta["rows_in_sql_result"], meta["values_seen"] = nrows, seen
    shutil.rmtree(tmp, ignore_errors=True)
    if int(grid[0].sum()) == 0:
        state.set(f"tg:{g}", **meta, total=0)
        raise RuntimeError(f"target group {g}: the SQL download is empty, not stored")
    out = WORK / "tg"; out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / f"s2_tg_density_{g}_v1.npz", all=grid[0], p1_1970_1999=grid[1], p2_2000_2020=grid[2])
    W.rel_put(out / f"s2_tg_density_{g}_v1.npz")
    state.set(f"tg:{g}", **meta, processed=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), total=int(grid[0].sum()), cells=int((grid[0] > 0).sum()))
    log("processed target group", g, int(grid[0].sum()), "records in", int((grid[0] > 0).sum()), "cells")
    return True


def process_batch(bid: str, key: str, rows: list[dict], state: State) -> bool:
    t0 = time.time()
    s = gbif.status(key)
    meta = W.download_meta(s, key)
    if s["status"] != "SUCCEEDED":
        state.set(f"batch:{bid}", **meta)
        return False
    tmp = Path(os.environ.get("S5_TMP", tempfile.gettempdir())) / f"s5-{bid}"
    shutil.rmtree(tmp, ignore_errors=True)
    z = W.fetch_zip(s["downloadLink"], tmp)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(tmp)
    z.unlink()
    ref, land = W.ref_set()
    cleaners, unmatched = route_and_clean(tmp, rows, land, ref)
    by_key = {int(r["gbif_taxon_key"]): r for r in rows}
    shutil.rmtree(tmp, ignore_errors=True)
    out = WORK / "cells"; out.mkdir(parents=True, exist_ok=True)
    finished = {k: cc.finish() for k, cc in cleaners.items()}
    empty = [by_key[k]["scientific_name"] for k, (cells, rep) in finished.items() if len(cells) == 0 or rep["steps"][0]["left"] == 0]
    log("records per species:", {by_key[k]["scientific_name"]: finished[k][1]["steps"][0]["left"] for k in finished}, "| unmatched rows:", unmatched)
    if empty:      # batch-1 lesson: the first acquire run stored empty tables. Nothing is stored for this batch; the run fails loudly.
        raise RuntimeError(f"download {bid}: no cells for {empty} (routing or filter problem; unmatched rows {unmatched}); nothing stored")
    for k, cc in cleaners.items():
        r = by_key[k]; sci = r["scientific_name"]
        cells, rep = finished[k]
        if r.get("season"):
            sea = cc.finish_seasonal("N")
            sea.to_parquet(out / f"s5_seasonal_{slug(sci)}.parquet", compression="zstd", index=False)
            W.rel_put(out / f"s5_seasonal_{slug(sci)}.parquet")
            rep["seasonal_cells"] = int(len(sea)); rep["records_without_month"] = int(sea["m00"].sum())
        rep.update({"group": r["group"], "treatment": "crop_cultivated" if r["group"] == "crop" else "wild_native", "species": sci, "download_key": key,
                    "download_batch": bid, "species_in_download": len(rows), "records_in_download_all_species": meta["records"],
                    "unmatched_records_in_download": unmatched, "process_s": round(time.time() - t0),
                    **{x: meta[x] for x in ("doi", "created", "citation", "licence")},
                    "records": rep["steps"][0]["left"]})
        cells.to_parquet(out / f"s5_cells_{slug(sci)}.parquet", compression="zstd", index=False)
        (out / f"s5_report_{slug(sci)}.json").write_text(json.dumps(rep, indent=1))
        (out / f"s5_datasets_{slug(sci)}.json").write_text(json.dumps(cc.datasets))
        for n in (f"s5_datasets_{slug(sci)}.json", f"s5_cells_{slug(sci)}.parquet", f"s5_report_{slug(sci)}.json"):
            W.rel_put(out / n)
        log("processed", sci, rep["n_cells"], "cells", rep["steps"][0]["left"], "records")
    state.set(f"batch:{bid}", **meta, processed=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), species=[r["scientific_name"] for r in rows],
              unmatched_records=unmatched)
    return True


def acquire(hours: float) -> int:
    """Every download is requested as soon as a GBIF slot is free (3 at a time: the two target-group SQL downloads first, then the species batches),
    each is processed when it finishes; a processing step never blocks new requests for longer than one batch."""
    W.ensure_release()
    state = State()
    have = {} if os.environ.get("S5_REDO") == "1" else W.rel_assets()      # S5_REDO=1: reprocess the stored downloads (no new GBIF request)
    bs = batches(read_batch())
    jobs: dict[str, dict] = {}           # job id -> {"kind", "rows"}; the state key is "batch:<id>" or "tg:<group>"
    for g in TG_GROUPS:
        if f"s2_tg_density_{g}_v1.npz" not in have:
            jobs[f"tg:{g}"] = {"kind": "tg", "rows": []}
    for b, rs in bs.items():
        if not stored(rs, have):
            jobs[f"batch:{b}"] = {"kind": "batch", "rows": rs}
    log(f"{len(jobs)} download jobs to do ({sum(1 for j in jobs.values() if j['kind'] == 'tg')} target-group SQL, {sum(1 for j in jobs.values() if j['kind'] == 'batch')} of {len(bs)} species batches)")
    deadline = time.time() + hours * 3600
    pending: dict[str, str] = {}
    queue = list(jobs)
    failed: dict = {}
    state.set("_run", started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def fill():
        for j in list(queue):
            known = state.get(j).get("key")
            if known:
                st = gbif.status(known)
                if st["status"] in ("FAILED", "CANCELLED", "KILLED", "FILE_ERASED"):
                    log("download", j, "ended as", st["status"], "- requesting a new one")
                    known = None
            if known:
                queue.remove(j); pending[j] = known
                continue
            if len(pending) >= 3 or time.time() > deadline - 600:
                continue
            try:
                key = request_tg(j[3:]) if jobs[j]["kind"] == "tg" else request_multi([int(r["gbif_taxon_key"]) for r in jobs[j]["rows"]])
            except RuntimeError as e:
                if "420" in str(e):
                    continue
                failed[j] = str(e)[:300]; queue.remove(j); log("request failed", j, failed[j]); continue
            state.set(j, key=key, requested=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), species=[r["scientific_name"] for r in jobs[j]["rows"]])
            queue.remove(j); pending[j] = key
            log("requested", j, key)

    while queue or pending:
        fill()
        for j, key in list(pending.items()):
            st = gbif.status(key)
            if st["status"] in ("PREPARING", "RUNNING", "SUSPENDED"):
                continue
            del pending[j]
            if st["status"] != "SUCCEEDED":
                failed[j] = st["status"]; state.set(j, **W.download_meta(st, key)); log("download", j, st["status"]); continue
            log("ready", j, key)
            fill()
            try:
                if jobs[j]["kind"] == "tg":
                    process_tg(j[3:], key, state)
                else:
                    process_batch(j[6:], key, jobs[j]["rows"], state)      # sequential: one batch at a time keeps disk and memory inside the runner limits
            except Exception as e:
                failed[j] = f"{type(e).__name__}: {e}"[:400]; log("processing failed", j, failed[j])
        if time.time() > deadline:
            log("time limit reached; state saved, start the workflow again to continue")
            break
        time.sleep(30 if (pending or queue) else 5)
    have = W.rel_assets()
    left = [f"batch:{b}" for b, rs in bs.items() if not stored(rs, have)] + [f"tg:{g}" for g in TG_GROUPS if f"s2_tg_density_{g}_v1.npz" not in have]
    log("failed:", failed, "| jobs not stored:", left)
    summ = {"failed": failed, "not_stored": left,
            "downloads": {k: {x: v.get(x) for x in ("key", "doi", "records", "status", "processed", "unmatched_records")} for k, v in state.d.items() if not k.startswith("_")}}
    (WORK / "acquire_summary.json").write_text(json.dumps(summ, indent=1))
    return 0 if not failed and not left else 1


# --------------------------------------------------------------------------- native-range inputs
def native_inputs() -> int:
    """WCVP native areas for the plants (trees, wild plants) and GRIIS introduced-country rows for every species."""
    W.ensure_release()
    rows = read_batch()
    cache = WORK / "cache"; cache.mkdir(parents=True, exist_ok=True)
    plants = [r["scientific_name"] for r in rows if r["native_source"] == "wcvp"]
    wc = N.build_wcvp_pilot(plants, cache, cache / "s5_wcvp.json")
    missing = [n for n in plants if n not in wc]
    log("WCVP entries", len(plants) - len(missing), "of", len(plants), "missing:", missing)
    gr = N.build_griis_pilot([r["scientific_name"] for r in rows if r["kind"] != "crop"], cache / "s5_griis.json")
    log("GRIIS rows", {k: len(v) for k, v in gr.items() if not k.startswith("_")})
    W.rel_put(cache / "s5_wcvp.json"); W.rel_put(cache / "s5_griis.json")
    return 0


def sha256(p: Path) -> str:
    return W.sha256(p)


def assemble() -> int:
    W.ensure_release()
    rows = read_batch()
    cache = WORK / "cache"; cache.mkdir(parents=True, exist_ok=True)
    out = WORK / "final"; out.mkdir(parents=True, exist_ok=True)
    state = State()
    fe = N.subunits(cache); lab = N.label_raster(fe)
    td = N.tdwg_units(cache); labt = N.label_raster(td)
    unit_cont = np.array(["-"] + [f["properties"].get("CONTINENT") or "-" for f in fe])
    wp = W.rel_get("s5_wcvp.json", cache / "s5_wcvp.json") or (ROOT / "data/species/native/wcvp_s5.json")
    gp = W.rel_get("s5_griis.json", cache / "s5_griis.json") or (ROOT / "data/species/native/griis_s5.json")
    wcvp, griis = json.load(open(wp)), json.load(open(gp))
    groups = {}
    need = sorted({tg.S2_GROUP_TO_TG[r["group"]] for r in rows})
    for gname in need:
        pre = "s2_" if gname in TG_GROUPS else ""          # herp and fish are new (s5_), the other four are the pilot's grids
        p = W.rel_get(f"{pre}tg_density_{gname}_v1.npz", WORK / "tg" / f"{pre}tg_density_{gname}_v1.npz")
        if not p:
            raise RuntimeError(f"target-group grid {pre}tg_density_{gname}_v1.npz missing from the release")
        z = np.load(p)
        groups[gname] = np.stack([z["all"], z["p1_1970_1999"], z["p2_2000_2020"]])
        log("target group", gname, "loaded")
    species_tables, excluded_tables, report, masks, problems = [], [], {}, {}, []
    for r in rows:
        sci = r["scientific_name"]; tgname = tg.S2_GROUP_TO_TG[r["group"]]
        pc = W.rel_get(f"s5_cells_{slug(sci)}.parquet", WORK / "cells" / f"s5_cells_{slug(sci)}.parquet")
        pr = W.rel_get(f"s5_report_{slug(sci)}.json", WORK / "cells" / f"s5_report_{slug(sci)}.json")
        if not pc:
            log("MISSING cells for", sci); report[sci] = {"missing": True}; problems.append(f"{sci}: no stored cell table"); continue
        cells = pd.read_parquet(pc); rep = json.load(open(pr))
        if len(cells) == 0:
            problems.append(f"{sci}: stored cell table is EMPTY"); report[sci] = {"missing": True}; continue
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
            "source": ("none: crop modelled where recorded (no wild native-range mask)" if is_crop else "WCVP (data, TDWG level 3)" if has_w else "curated (our judgement, Natural Earth subunits)"),
            "treatment": "crop_cultivated" if is_crop else "wild_native", "wanted_source": r["native_source"],
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
        if int(keep.sum()) == 0:
            problems.append(f"{sci}: the native mask removed every cell")
        if not is_crop:
            masks[f"{slug(sci)}__final"] = np.packbits(final, axis=1)
        masks[f"{slug(sci)}__curated"] = np.packbits(cur, axis=1)
        for df, bucket in ((cells[keep], species_tables), (removed, excluded_tables)):
            df = df.copy()
            df.insert(0, "species", sci); df.insert(0, "species_key", int(r["gbif_taxon_key"]))
            df["group"] = r["group"]; df["tg_group"] = tgname
            df["treatment"] = "crop_cultivated" if is_crop else "wild_native"
            df["kind"] = "crop" if is_crop else "wild"
            bucket.append(df)
        report[sci] = rep
    main = pd.concat(species_tables, ignore_index=True)
    excl = pd.concat(excluded_tables, ignore_index=True) if excluded_tables else main.iloc[:0]
    for df in (main, excl):
        for c in ("tg_block_p1", "tg_block_p2"):
            df[c] = np.int64(-1)
        df["ws20"] = False; df["ws100"] = False
        df["tg_source"] = "none"
    for gname, grid in groups.items():
        for df in (main, excl):
            m = (df["tg_group"] == gname).to_numpy()
            if not m.any():
                continue
            lk = tg.lookup(grid, df.loc[m, "row"].to_numpy(), df.loc[m, "col"].to_numpy())
            for k, v in lk.items():
                df.loc[m, k] = v
            df.loc[m, "tg_source"] = "gbif sql download (s2 grid)" if gname in TG_GROUPS else "gbif sql download (pilot grid)"
    ordered = ["species_key", "species", "group", "kind", "treatment", "tg_group", "row", "col", "lat", "lon", "year_min", "year_max", "n_records", "n_events",
               "n_1970_1999", "n_2000_2020", "n_2021_plus", "native_curated", "native_wcvp", "griis_intro", "tg_block_p1", "tg_block_p2", "ws20", "ws100", "tg_source"]
    main, excl = main[ordered], (excl[ordered] if len(excl) else excl)
    files = {}

    def save(df, name):
        p = out / name; df.to_parquet(p, compression="zstd", index=False); files[name] = p
    save(main[main["treatment"] == "crop_cultivated"], f"s5_occ_cells_crops_{VERSION}.parquet")
    save(main[main["treatment"] == "wild_native"], f"s5_occ_cells_{VERSION}.parquet")
    save(excl, f"s5_occ_cells_{VERSION}_excluded_non_native.parquet")
    p = out / f"s5_native_masks_{VERSION}.npz"
    np.savez_compressed(p, **masks); files[p.name] = p
    for sci, rep in report.items():
        rep["download_state"] = {k: v for k, v in state.get(f"batch:{next((r['dl_batch'] for r in rows if r['scientific_name'] == sci), '')}").items() if k not in ("predicate", "sql")}
        dp = W.rel_get(f"s5_datasets_{slug(sci)}.json", WORK / "cells" / f"s5_datasets_{slug(sci)}.json")
        if dp:
            rep["dataset_counts"] = json.load(open(dp))
    # ---- seasonal cells for the migrants (breeding-only fits), same layout as the pilot's occ_cells_pilot_v1_seasonal.parquet
    seas_cfg = {r["scientific_name"]: r for r in csv.DictReader(open(ROOT / "data" / "species" / "native" / "curated_native_v5.csv", encoding="utf-8")) if r["season_scheme"]}
    parts, srep = [], {}
    for r in rows:
        sci = r["scientific_name"]
        if not r.get("season"):
            continue
        cfg = seas_cfg[sci]
        pth = W.rel_get(f"s5_seasonal_{slug(sci)}.parquet", WORK / "cells" / f"s5_seasonal_{slug(sci)}.parquet")
        if not pth:
            problems.append(f"{sci}: no seasonal table"); continue
        d = pd.read_parquet(pth)
        ri, ci = d["row"].to_numpy(), d["col"].to_numpy()
        br = N.curated_mask(cfg["breeding_native_spec"], fe, lab); wi = N.curated_mask(cfg["winter_native_spec"], fe, lab)
        d["in_breeding_mask"], d["in_winter_mask"] = br[ri, ci], wi[ri, ci]
        d["breeding_cell"] = d["in_breeding_mask"] & (d["n_breeding"] > 0)
        d["winter_cell"] = d["in_winter_mask"] & (d["n_winter"] > 0)
        lk = tg.lookup(groups[tg.S2_GROUP_TO_TG[r["group"]]], ri, ci)
        for k in ("tg_block_p1", "tg_block_p2", "ws20", "ws100"):
            d[k] = lk[k]
        d.insert(0, "species", sci); d.insert(0, "species_key", int(r["gbif_taxon_key"]))
        parts.append(d)
        srep[sci] = {"season_scheme": cfg["season_scheme"], "breeding_native_spec": cfg["breeding_native_spec"], "winter_native_spec": cfg["winter_native_spec"],
                     "cells_all": int(len(d)), "breeding_cells": int(d["breeding_cell"].sum()), "winter_cells": int(d["winter_cell"].sum()),
                     "records_breeding_months": int(d["n_breeding"].sum()), "records_winter_months": int(d["n_winter"].sum()), "records_without_month": int(d["m00"].sum()),
                     "note": cfg["introduced_or_migration_note"]}
        if srep[sci]["breeding_cells"] == 0:
            problems.append(f"{sci}: no breeding cells")
    if parts:
        p = out / f"s5_occ_cells_seasonal_{VERSION}.parquet"; pd.concat(parts, ignore_index=True).to_parquet(p, compression="zstd", index=False); files[p.name] = p
        p = out / f"s5_w2_seasonal_report_{VERSION}.json"; p.write_text(json.dumps(srep, indent=1)); files[p.name] = p
    # ---- per-species summary (small, committed back by the workflow so the check does not need the release): fail loudly on empty species
    sumrows = []
    for r in rows:
        sci = r["scientific_name"]; rp = report.get(sci, {})
        nm = rp.get("native_mask") or {}
        sumrows.append({"id": r["id"], "scientific_name": sci, "group": r["group"], "dl_batch": r["dl_batch"], "season": r.get("season", ""), "records": rp.get("records", 0),
                        "cells": rp.get("n_cells", 0), "cells_kept": nm.get("cells_kept", 0), "cells_removed": nm.get("cells_removed", 0), "mask_source": nm.get("source", "")[:40],
                        "breeding_cells": (srep.get(sci) or {}).get("breeding_cells", ""), "doi": rp.get("doi", ""),
                        "ok": bool(nm.get("cells_kept", 0) > 0 and (not r.get("season") or (srep.get(sci) or {}).get("breeding_cells", 0) > 0))})
    sp = out / "batch5_w2_summary.csv"
    pd.DataFrame(sumrows).to_csv(sp, index=False)
    summary = {"version": VERSION, "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "species": report, "problems": problems,
               "target_group_downloads": {g: {k: v for k, v in (state.get(f"tg:{g}") or {}).items() if k not in ("predicate", "sql", "values_seen")} for g in TG_GROUPS}}
    p = out / f"s5_w2_report_{VERSION}.json"; p.write_text(json.dumps(summary, indent=1, default=str)); files[p.name] = p
    manifest = {"version": VERSION, "built": summary["built"], "batch": "S3 batch 5", "species_table": "data/species/batch5.csv",
                "grid": "TerraClimate native 1/24 degree, 4320 x 8640, row 0 = north, cell centre lat = 90 - (row + 0.5) / 24, lon = -180 + (col + 0.5) / 24",
                "licence_filter": "CC0 and CC-BY records only", "tg_grids": "pilot tg_density_<group>_v1.npz (unchanged) for bird, mammal, insect_arachnid, plant; s2_tg_density_herp_v1.npz and s2_tg_density_fish_v1.npz new",
                "species_kind": {r["scientific_name"]: r["kind"] for r in rows},
                "files": {n: {"bytes": f.stat().st_size, "sha256": sha256(f)} for n, f in files.items()}}
    mp = out / f"s5_manifest_w2_{VERSION}.json"; mp.write_text(json.dumps(manifest, indent=1))
    for f in list(files.values()) + [mp]:
        W.rel_put(f)
    log("published", len(files) + 1, "assets;", "species with cells:", sum(1 for v in report.values() if not v.get("missing")))
    if problems:
        log("PROBLEMS (the fit stage must not run for these species):", problems)
        return 1
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "acquire":
        hrs = float(sys.argv[sys.argv.index("--hours") + 1]) if "--hours" in sys.argv else 5.5
        sys.exit(acquire(hrs))
    sys.exit({"native": native_inputs, "assemble": assemble}[cmd]())
