import numpy as np
import pandas as pd
from ctw.species import gbif_split as GS, hindcast as H


def world(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    # 20 x 20 blocks of 12 cells; every block gets target-group records, most blocks well sampled in both periods, a third only in period 2
    tg, occ = [], []
    for br in range(300, 320):
        for bc in range(2000, 2020):
            n1 = 40 if (br + bc) % 3 else 3                 # poorly sampled in period 1
            tg += [dict(group="bird", row=br * 12, col=bc * 12, year=1985, n=n1), dict(group="bird", row=br * 12, col=bc * 12, year=2010, n=60)]
            # species: south of block row 310 in period 1, everywhere south of 306 later (northward expansion = lower row numbers)
            if br >= 310 and n1 >= 20:
                occ.append(dict(species="x", row=br * 12, col=bc * 12, year=1985))
            if br >= 306:
                occ.append(dict(species="x", row=br * 12, col=bc * 12, year=2010))
    return pd.DataFrame(occ), pd.DataFrame(tg)


def test_well_sampled_rule():
    occ, tg = world()
    w = GS.well_sampled(tg, "bird")
    assert 0 < len(w) < 400 and (w.n1 >= 20).all() and (w.n2 >= 20).all()


def test_split_detects_northward_expansion_and_effort_gap():
    occ, tg = world()
    well = GS.species_cellset(occ, tg, "x", "bird", well_only=True)
    allc = GS.species_cellset(occ, tg, "x", "bird", well_only=False)
    assert len(well.lat) < len(allc.lat)
    o = H.observed_change(well, n_boot=30)
    assert o["north"] > 0 and o["detectable"]
    gap = GS.effort_gap(well, allc)
    assert gap["n_well"] < gap["n_all"]


def test_scores_variant():
    occ, tg = world()
    sc = pd.DataFrame(dict(row=np.repeat(np.arange(3600, 3840, 12), 20)[:400], col=np.tile(np.arange(24000, 24240, 12), 20)[:400]))
    sc["score1"], sc["score2"] = 0.2, 0.8
    cs = GS.species_cellset(occ, tg, "x", "bird", scores=sc, thr=0.5)
    assert cs.score1 is not None and len(cs.score1) == len(cs.lat)
