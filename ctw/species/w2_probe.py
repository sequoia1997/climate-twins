"""W2 probe (GitHub Actions): which GBIF SQL-download syntax is accepted, are the cached spike-A downloads still alive, and can the
release be reached. Prints only HTTP statuses and short response texts, never the credentials or the request body."""
from __future__ import annotations
import json, os, sys, time
import requests
from . import gbif

SQL_TPL = ("SELECT FLOOR((90 - decimalLatitude) * 24) AS r, FLOOR((decimalLongitude + 180) * 24) AS c, "
           "{period} AS p, COUNT(*) AS n FROM occurrence WHERE {taxon} AND hasCoordinate = TRUE AND hasGeospatialIssues = FALSE "
           "AND occurrenceStatus = 'PRESENT' AND license IN ('CC0_1_0', 'CC_BY_4_0') AND year >= 1970 AND year <= 2020 "
           "AND basisOfRecord IN ('HUMAN_OBSERVATION', 'PRESERVED_SPECIMEN', 'OBSERVATION', 'MACHINE_OBSERVATION') "
           "AND (coordinateUncertaintyInMeters IS NULL OR coordinateUncertaintyInMeters <= 10000) GROUP BY r, c, p")


def variants():
    tick = "speciesKey = 2182727"
    out = {}
    for yname, yq in (("dq", '"year"'), ("bt", "`year`"), ("plain", "year")):
        t = SQL_TPL.replace("year >= 1970 AND year <= 2020", f"{yq} >= 1970 AND {yq} <= 2020")
        out[f"if_{yname}"] = t.format(period=f"IF({yq} <= 1999, 1, 2)", taxon=tick)
        out[f"case_{yname}"] = t.format(period=f"CASE WHEN {yq} <= 1999 THEN 1 ELSE 2 END", taxon=tick)
    return out


def validate(sql: str) -> list:
    out = []
    for path in ["/occurrence/download/request/sql/validate", "/occurrence/download/sql/validate", "/occurrence/download/validate-sql",
                 "/occurrence/download/request/validate"]:
        for kind in ("json", "text"):
            try:
                if kind == "json":
                    r = requests.post(f"{gbif.API}{path}", json={"sql": sql}, auth=gbif.auth(), timeout=60)
                else:
                    r = requests.post(f"{gbif.API}{path}", data=sql, headers={"Content-Type": "text/plain"}, auth=gbif.auth(), timeout=60)
                out.append((path, kind, r.status_code, r.text[:300].replace("\n", " ")))
            except Exception as e:
                out.append((path, kind, type(e).__name__, ""))
    return out


def submit(sql: str):
    body = {"creator": os.environ["GBIF_USER"], "notificationAddresses": [os.environ["GBIF_EMAIL"]], "sendNotification": False,
            "format": "SQL_TSV_ZIP", "sql": sql}
    r = requests.post(f"{gbif.API}/occurrence/download/request", json=body, auth=gbif.auth(), timeout=120)
    return r.status_code, r.text[:600].replace("\n", " ")


def main() -> int:
    res = {}
    # 1 cached spike A downloads
    keys = json.load(open("docs/spikes/data/spike-a/run6-results.json"))
    alive = {}
    for sci, row in keys.items():
        s = gbif.status(row["key"])
        alive[sci] = {"status": s.get("status"), "doi": s.get("doi"), "erase": s.get("eraseAfter"), "size": s.get("size"), "records": s.get("totalRecords")}
    res["cached"] = alive
    print("cached downloads", json.dumps(alive))
    # 2 SQL validation endpoints
    v = variants()
    res["validate"] = {}
    for name, sql in []:
        res["validate"][name] = validate(sql)
        for line in res["validate"][name]:
            print("validate", name, *line)
    # 3 real submissions: variants until one is accepted, then wait for it
    res["submit"] = {}
    accepted = None
    for name, sql in v.items():
        code, text = submit(sql)
        res["submit"][name] = [code, text]
        print("submit", name, code, text)
        if code < 300:
            accepted = (name, text.strip().strip('"'))
            break
    if accepted:
        key = accepted[1]
        t0 = time.time()
        s = gbif.wait(key, every=30, limit_s=75 * 60)
        res["sql_download"] = {"variant": accepted[0], "key": key, "status": s.get("status"), "doi": s.get("doi"), "records": s.get("totalRecords"),
                               "size": s.get("size"), "wait_s": round(time.time() - t0), "format": (s.get("request") or {}).get("format"),
                               "link": s.get("downloadLink")}
        print("sql_download", json.dumps(res["sql_download"]))
        if s.get("status") == "SUCCEEDED":
            import io, zipfile
            r = requests.get(s["downloadLink"], timeout=300)
            z = zipfile.ZipFile(io.BytesIO(r.content))
            for n in z.namelist():
                txt = z.read(n).decode("utf8", "replace")
                print("file", n, len(txt)); print(txt[:600])
                res["sql_download"]["sample"] = txt[:600]
    os.makedirs("work/w2", exist_ok=True)
    json.dump(res, open("work/w2/probe.json", "w"), indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
