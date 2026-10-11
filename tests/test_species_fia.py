import numpy as np
import pandas as pd
from ctw.species import fia


def plots_state(n_per=60):
    rows = []
    cn = 0
    # periodic cycle 3 (1986), periodic 4 (1999), annual cycles 5,6,7 (2004-2023), annual cycle 8 incomplete
    spec = {3: (1986, [0], 400), 4: (1999, [0], 400), 5: (2007, [1, 2, 3, 4, 5], 600), 6: (2013, [1, 2, 3, 4, 5], 600), 7: (2019, [1, 2, 3, 4, 5], 600), 8: (2024, [1, 2], 200)}
    rng = np.random.default_rng(0)
    for cyc, (yr, subs, n) in spec.items():
        for i in range(n):
            cn += 1
            rows.append(dict(CN=cn, STATECD=10, PLOT_STATUS_CD=1, MEASYEAR=yr + rng.integers(-2, 3), CYCLE=cyc, SUBCYCLE=subs[i % len(subs)],
                             LAT=37 + rng.random() * 3, LON=-85 + rng.random() * 2, DESIGNCD=1))
    return pd.DataFrame(rows)


def test_complete_cycles():
    info = fia.complete_cycles(plots_state())
    assert info["first"] == 3 and info["last"] == 7 and info["ok"]          # incomplete cycle 8 skipped
    assert info["t2"] - info["t1"] > 30


def test_short_interval_dropped():
    p = plots_state(); p = p[p.CYCLE.isin([6, 7])]
    info = fia.complete_cycles(p)
    assert not info["ok"] and "interval" in info["why"]


def test_state_table_and_cellset_shift():
    p = plots_state()
    tree_rows = []
    rng = np.random.default_rng(1)
    for r in p.itertuples():
        # species 318 occupies lat<38 in the first cycle, lat<39.5 in the latest; juveniles north of adults in the latest
        lim = 38 if r.CYCLE <= 4 else 39.5
        if r.LAT < lim:
            tree_rows.append(dict(PLT_CN=r.CN, STATUSCD=1, SPCD=318, DIA=9.0))
        tree_rows.append(dict(PLT_CN=r.CN, STATUSCD=2, SPCD=318, DIA=9.0))            # dead tree ignored
        tree_rows.append(dict(PLT_CN=r.CN, STATUSCD=1, SPCD=318, DIA=3.0))            # sapling below 5 in ignored
    t = pd.DataFrame(tree_rows)
    seeds = pd.DataFrame([dict(PLT_CN=r.CN, SPCD=318, TREECOUNT=3) for r in p.itertuples() if r.LAT < 40.0])
    plots, info = fia.state_plot_table(p, [t], [seeds])
    assert set(plots.window) == {1, 2} and set(plots.cycle) == {3, 7}
    assert plots["a318"].max() == 1                                                  # one live adult per plot at most in this fixture
    cs, cnt = fia.species_cellset(plots, 318, block=12, min_plots=3, cap=30, seed=1, min_interval=15)
    assert len(cs.lat) > 0 and cnt["t2"] - cnt["t1"] >= 15
    assert cs.obs2.sum() >= cs.obs1.sum()
    sa = fia.seedling_adult(plots, 318, min_plots=3, n_boot=20)
    assert sa is not None and sa["north"] >= 0
