"""Checks a fresh build before it can go live. Writes site/data/report.md and returns an exit status:
0 = routine (safe to merge after a glance), 0 with status "review" = read the report first, 1 = broken build.
Structural checks catch failed downloads and bugs; the comparison with the previous release catches surprises."""
from __future__ import annotations
import gzip, json
import numpy as np
from . import common as C


def header(path):
    raw = gzip.decompress(path.read_bytes())
    assert raw[:4] == b"CTW2", f"{path.name}: bad magic"
    n = int.from_bytes(raw[4:8], "little")
    return json.loads(raw[8:8 + n]), len(raw) - 8 - n


def check_shards(d, index):
    """None if every place in index.json is found at its shard/slot, else a short description of the first problem."""
    ids = {}
    for n, sh in enumerate(index["shards"]):
        try:
            h, _ = header(d / sh["f"])
        except Exception as e:  # noqa: BLE001
            return f"{sh['f']} unreadable: {e}"
        if len(h["ids"]) != sh["n"]:
            return f"{sh['f']} holds {len(h['ids'])} places, index says {sh['n']}"
        ids[n] = h["ids"]
    ci, si = index["cols"].index("s"), index["cols"].index("i")
    for t, r in enumerate(index["rows"]):
        lst = ids.get(r[ci], [])
        if r[si] >= len(lst) or lst[r[si]] != t:
            return f"place {t} ({r[0]}) is not at shard {r[ci]} slot {r[si]}"
    return None


def run(cfg=None, previous=None) -> int:
    cfg = cfg or C.config()
    G = cfg["gates"]
    out, problems, notes = [], [], []
    d = C.SITE / "data"
    try:
        na, nb = header(d / "na.dat"); w, wb = header(d / "world.dat")
        S = json.load(open(d / "summary.json"))
        index = json.load(open(d / "index.json"))
        ov, _ = header(d / "overview.dat")
    except Exception as e:  # noqa: BLE001
        (d / "report.md").write_text(f"# Build check: FAILED\n\nCould not read the new data files: {e}\n")
        (d / "status.txt").write_text("fail")
        return 1
    T = C.targets()
    n_na, n_w = int((T.g == 0).sum()), int((T.g == 1).sum())
    gi = index["cols"].index("g")
    i_na = sum(1 for r in index["rows"] if r[gi] == 0)
    i_w = len(index["rows"]) - i_na
    shard_problem = check_shards(d, index)
    chk = [
        (i_na >= n_na - 5, f"North American places: {i_na} of {n_na}"),
        (i_w >= n_w - max(10, n_w // 50), f"World cities: {i_w} of {n_w}"),
        (ov["n"] == len(index["rows"]), f"Overview covers {ov['n']} of {len(index['rows'])} places"),
        (shard_problem is None, f"Place data files: {len(index['shards'])} shards" + (f" ({shard_problem})" if shard_problem else "")),
        (na["NP"] > 90000, f"North American pool cells: {na['NP']:,}"),
        (w["NP"] > 60000, f"World pool cells: {w['NP']:,}"),
        (len(na["models"]) == len(C.models(cfg)), f"Climate models: {len(na['models'])} of {len(C.models(cfg))}"),
        (S["selfchk_median"] < 0.5, f"Self-check (today's climate finds itself): median {S['selfchk_median']:.2f} σ (expect < 0.5)"),
        (np.isnan(S["tc_check_median"]) or S["tc_check_median"] < 1.5, f"TerraClimate vs AdaptWest at the same places: median {S['tc_check_median']:.2f} σ"),
    ]
    for ok, msg in chk:
        out.append(("✅ " if ok else "❌ ") + msg)
        if not ok:
            problems.append(msg)
    try:                                                       # optional: sensitivity to model resolution (nexcheck)
        from . import nexcheck
        nx = json.load(open(d / "nexcheck.json"))
        tot = max(sum(nx["summary"][k] for k in ("ok", "moderate", "high")), 1)
        hi = nx["summary"]["high"] / tot > nexcheck.settings(cfg)["high_share_note"]
        notes.append(("⚠️ " if hi else "") + nexcheck.summary_line(nx) + (" (informational; does not change the status)" if hi else ""))
    except Exception:  # noqa: BLE001 - file absent when the Extreme days job has not produced nexdeltas.npz yet
        pass
    notes.append(f"Recent-climate years: {S['recent_years'][0]}–{S['recent_years'][1]}")
    sz = [s["b"] for s in index["shards"] if "b" in s]
    if sz:
        notes.append(f"Page downloads: index {(d / 'index.json').stat().st_size / 1e3:.0f} kB, North America core {(d / 'na.dat').stat().st_size / 1e6:.1f} MB, "
                     f"world core {(d / 'world.dat').stat().st_size / 1e6:.1f} MB, then one of {len(sz)} place files "
                     f"(median {sorted(sz)[len(sz) // 2] / 1e3:.0f} kB, largest {max(sz) / 1e3:.0f} kB) per place picked.")
    if S["sealevel_places"]:
        notes.append(f"Coastal places with sea-level projections: {S['sealevel_places']}")
    else:
        notes.append("⚠️ No sea-level projections: the sealevel job did not produce data/sealevel.json. "
                     "Its log has a line starting 'sea level step failed' with the reason. The page simply omits sea level.")
    if S["cc_fill"]:
        notes.append("Humidity change filled at constant relative humidity (model lacks humidity output): " + ", ".join(S["cc_fill"]))
    if S["unusable"]:
        notes.append("Places without usable data: " + ", ".join(S["unusable"]))
    status = "fail" if problems else "routine"
    if previous and not problems:
        P = json.load(open(previous))
        common = [k for k in S["places"] if k in P["places"]]
        moved, dsig = [], []
        for k in common:
            a, b = np.array(S["places"][k]["ll"]), np.array(P["places"][k]["ll"])
            if a.shape != b.shape:
                continue
            moved.append((C.haversine_km(a[..., 0], a[..., 1], b[..., 0], b[..., 1]) > G["moved_km"]).mean())
            dsig.append(np.abs(np.array(S["places"][k]["sig"]) - np.array(P["places"][k]["sig"])).ravel())
        ms = float(np.mean(moved)) if moved else float("nan")
        md = float(np.median(np.concatenate(dsig))) if dsig else float("nan")
        worst = sorted(((float(np.abs(np.array(S["places"][k]["sig"]) - np.array(P["places"][k]["sig"])).max()), k) for k in common
                        if np.array(S["places"][k]["sig"]).shape == np.array(P["places"][k]["sig"]).shape), reverse=True)[:10]
        out.append(f"{'✅' if ms <= G['max_moved_share'] else '⚠️'} Best matches that moved more than {G['moved_km']} km: {ms:.1%} (routine if ≤ {G['max_moved_share']:.0%})")
        out.append(f"{'✅' if md <= G['max_median_dsigma'] else '⚠️'} Median change in best-match σ: {md:.2f} (routine if ≤ {G['max_median_dsigma']})")
        if ms > G["max_moved_share"] or md > G["max_median_dsigma"]:
            status = "review"
        if P.get("method_version") != S["method_version"]:
            status = "review" if status != "fail" else status
            notes.append(f"Method version changed: {P.get('method_version')} → {S['method_version']} (always reviewed)")
        notes.append("Largest σ changes: " + "; ".join(f"{k} ({v:.2f})" for v, k in worst))
    elif not previous:
        notes.append("No previous release to compare with.")
        status = "review" if status != "fail" else status
    title = {"routine": "routine update", "review": "needs review", "fail": "FAILED"}[status]
    rep = [f"# Build check: {title}", "", f"Data version {S['data_version']}, method {S['method_version']}.", ""] + [f"- {x}" for x in out] + ["", "## Notes", ""] + [f"- {x}" for x in notes]
    (d / "report.md").write_text("\n".join(rep) + "\n")
    (d / "status.txt").write_text(status)
    print("\n".join(rep))
    return 1 if status == "fail" else 0
