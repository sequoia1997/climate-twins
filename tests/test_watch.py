"""The monthly watcher's host and new-product checks (network replaced by a stub)."""
from ctw import common as C
from ctw import watch as W


def test_hosts_reports_only_the_sources_that_fail(monkeypatch):
    monkeypatch.setattr(W, "_probe", lambda url, timeout=60: "chelsa02" not in url)
    out = W.hosts(C.config())
    assert len(out) == 1 and "CHELSA" in out[0] and "TerraClimate" not in out[0]


def test_hosts_silent_when_everything_answers(monkeypatch):
    monkeypatch.setattr(W, "_probe", lambda url, timeout=60: True)
    assert W.hosts(C.config()) == []


def test_new_chelsa_period_is_flagged(monkeypatch):
    monkeypatch.setattr(W, "_probe", lambda url, timeout=60: "1991-2020" in url)
    monkeypatch.setattr(C, "http", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    out = W.new_products()
    assert len(out) == 1 and "CHELSA 1991-2020" in out[0]
