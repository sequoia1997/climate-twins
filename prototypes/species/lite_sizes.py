"""python lite_sizes.py WORKDIR ssp245 s01 ... : sizes of the classified ('lite') product, cts + png + webp tiles"""
import json, sys
from pathlib import Path
import encode as E
work, ssp, ids = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
res = {}
for sid in ids:
    res[sid] = E.lite_sizes(E.load_base(work, sid), E.load(work, sid, ssp))
    print(sid, res[sid], flush=True)
Path(work / "lite_sizes.json").write_text(json.dumps(res, indent=1))
