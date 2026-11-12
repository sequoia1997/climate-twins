"""Spike B probe 3: enumerate CHELSA v2.1 climatologies (S3 listing): variables, periods, models, scenarios, sizes."""
import re, sys, collections, urllib.parse
sys.path.insert(0, "ctw/species")
from spike_b_probe import get_text, head, sec, gb

HOST = "https://os.unil.cloud.switch.ch/chelsa02"


def list_all(prefix, delim="", cap=20000):
    keys, marker = [], ""
    while len(keys) < cap:
        t = get_text(f"{HOST}?prefix={urllib.parse.quote(prefix)}&max-keys=1000&marker={urllib.parse.quote(marker)}" + (f"&delimiter={delim}" if delim else ""))
        ks = re.findall(r"<Key>([^<]+)</Key>", t)
        sz = re.findall(r"<Size>(\d+)</Size>", t)
        keys += list(zip(ks, map(int, sz)))
        if "<IsTruncated>true</IsTruncated>" not in t or not ks:
            break
        marker = ks[-1]
    return keys

sec("top levels")
for pre in ["", "chelsa/", "chelsa/global/", "chelsa/global/climatologies/"]:
    t = get_text(f"{HOST}?prefix={pre}&delimiter=/&max-keys=100")
    print(repr(pre), re.findall(r"<Prefix>([^<]+)</Prefix>", t)[:30])
for var in ["tasmax", "pr", "bio", "pet", "cmi", "tas"]:
    ks = list_all(f"chelsa/global/climatologies/{var}/", cap=6000)
    print(f"\n--- {var}: {len(ks)} keys, total {sum(s for _, s in ks)/1e9:.1f} GB (cap 6000)")
    for k, s in ks[:3]:
        print("   ", k, gb(s))
    per = collections.Counter(re.findall(r"/(\d{4}-\d{4})/", "".join(k + "\n" for k, _ in ks)))
    print("   periods:", dict(per))
    mod = sorted(set(re.findall(r"/(?:\d{4}-\d{4})/([A-Za-z0-9\-]+)/(?:ssp\d+)/", "\n".join(k for k, _ in ks))))
    ssp = sorted(set(re.findall(r"(ssp\d+)", "\n".join(k for k, _ in ks))))
    print("   models:", mod, "ssps:", ssp)
# the bio group may live under another prefix
for pre in ["chelsa/global/bioclim/", "chelsa/global/", "chelsa/global/climatologies/bio/"]:
    t = get_text(f"{HOST}?prefix={pre}&delimiter=/&max-keys=100")
    print(repr(pre), re.findall(r"<Prefix>([^<]+)</Prefix>", t)[:30], re.findall(r"<Key>([^<]+)</Key>", t)[:5])
print("done")
