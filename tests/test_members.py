"""Ensemble-member selection (ctw/cmip6.py Archive.members), on a synthetic catalogue. Run: pytest tests/test_members.py"""
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ctw import cmip6  # noqa: E402

SCEN = ("ssp126", "ssp245")


def archive(rows):
    a = object.__new__(cmip6.Archive)
    a.df = pd.DataFrame(rows, columns=["source_id", "experiment_id", "member_id", "table_id", "variable_id", "grid_label"])
    return a


def rows_for(model, members, exps=("historical",) + SCEN, vars_=cmip6.CORE, grid="gn"):
    return [(model, e, m, "Amon", v, grid) for m in members for e in exps for v in vars_]


M = {"name": "X", "member": "r2i1p1f1", "grid": "gn"}


def test_single_member_is_the_configured_one():
    assert archive([]).members(M, 1, SCEN) == ["r2i1p1f1"]


def test_configured_first_then_run_order_same_physics():
    rows = rows_for("X", ["r1i1p1f1", "r2i1p1f1", "r10i1p1f1", "r3i1p1f1", "r4i1p2f1", "r5i1p1f2"])
    a = archive(rows)
    assert a.members(M, 4, SCEN) == ["r2i1p1f1", "r1i1p1f1", "r3i1p1f1", "r10i1p1f1"]      # p2 and f2 excluded, numeric order
    assert a.members(M, 2, SCEN) == ["r2i1p1f1", "r1i1p1f1"]


def test_member_missing_a_scenario_or_variable_is_skipped():
    rows = rows_for("X", ["r1i1p1f1", "r2i1p1f1", "r3i1p1f1"])
    rows += rows_for("X", ["r4i1p1f1"], exps=("historical", "ssp126"))               # no ssp245
    rows += rows_for("X", ["r5i1p1f1"], vars_=("tasmax", "tasmin"))                  # no pr
    assert archive(rows).members(M, 9, SCEN) == ["r2i1p1f1", "r1i1p1f1", "r3i1p1f1"]


def test_other_grid_and_model_ignored():
    rows = rows_for("X", ["r2i1p1f1"]) + rows_for("X", ["r7i1p1f1"], grid="gr") + rows_for("Y", ["r8i1p1f1"])
    assert archive(rows).members(M, 5, SCEN) == ["r2i1p1f1"]
