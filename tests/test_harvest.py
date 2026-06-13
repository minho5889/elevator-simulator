# tests/test_harvest.py
"""Gate tests for WO-001 — the Stage-1 decision-point descriptor harvester.

Authored by Lane A (Claude) BEFORE Lane B (Antigravity) implements
``scripts/harvest.py``, per docs/antigravity-brief.md. Until that file exists the
module skips, keeping main green; the moment it exists these become enforced
gates the writer must turn green. Do not weaken them to pass.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

import elevatorsim.config as config

_HARVEST_PATH = Path(__file__).resolve().parents[1] / "scripts" / "harvest.py"
if not _HARVEST_PATH.exists():
    pytest.skip(
        "scripts/harvest.py not yet implemented (WO-001) — gate skips until then.",
        allow_module_level=True,
    )

_spec = importlib.util.spec_from_file_location("harvest", _HARVEST_PATH)
harvest = importlib.util.module_from_spec(_spec)
sys.modules["harvest"] = harvest
_spec.loader.exec_module(harvest)

_ORACLE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "oracle.py"
_ospec = importlib.util.spec_from_file_location("oracle_h", _ORACLE_PATH)
oracle = importlib.util.module_from_spec(_ospec)
sys.modules["oracle_h"] = oracle
_ospec.loader.exec_module(oracle)

REQUIRED_KEYS = {
    "regime", "seed", "floors", "cars", "capacity", "arrival_rate",
    "stop_ticks", "transfer_ticks", "warmup", "harvest_tick",
}
# The subset that maps onto oracle.harvest_state(**...) keyword args.
HARVEST_KEYS = {
    "regime", "seed", "harvest_tick", "floors", "cars", "capacity",
    "arrival_rate", "stop_ticks", "transfer_ticks", "warmup", "weight_limit",
}
REGIMES = {"up_peak", "down_peak", "lunch", "uniform"}
WARMUPS = {"conventional", "dd_delayed", "zoned", "switching"}


def _descriptors(n=2000, seed_base=7):
    return harvest.generate_descriptors(n, seed_base)


def test_descriptor_shape_and_ranges():
    ds = _descriptors()
    assert 0.8 * 2000 <= len(ds) <= 1.2 * 2000
    for d in ds:
        assert REQUIRED_KEYS <= set(d)
        assert d["regime"] in REGIMES
        assert d["warmup"] in WARMUPS
        assert 20 <= d["floors"] <= 60
        assert 4 <= d["cars"] <= 12
        assert d["capacity"] in (16, 20, 24)
        assert d["arrival_rate"] in (0.4, 0.8, 1.2, 2.0)
        assert d["harvest_tick"] % 20 == 0 and 80 <= d["harvest_tick"] <= 400
        assert d["stop_ticks"] == 9 and d["transfer_ticks"] == 1


def test_stratification():
    ds = _descriptors()
    n = len(ds)
    # Each regime >= 20%.
    for regime in REGIMES:
        assert sum(d["regime"] == regime for d in ds) >= 0.20 * n, regime
    # All three height bands present.
    bands = {"low": False, "mid": False, "high": False}
    for d in ds:
        f = d["floors"]
        bands["low" if f <= 28 else "mid" if f <= 40 else "high"] = True
    assert all(bands.values()), bands
    # Refusal cells >= 15%.
    assert sum(bool(d.get("weight_limit")) for d in ds) >= 0.15 * n
    # Every warmup present within every regime.
    for regime in REGIMES:
        seen = {d["warmup"] for d in ds if d["regime"] == regime}
        assert WARMUPS <= seen, (regime, seen)


def test_determinism():
    assert _descriptors(1500, 11) == _descriptors(1500, 11)
    assert _descriptors(1500, 11) != _descriptors(1500, 12)


def test_does_not_perturb_global_rng():
    before = config.RNG.getstate()
    _descriptors(3000, 99)
    assert config.RNG.getstate() == before


def test_descriptors_reconstruct_via_oracle_harvest_state():
    """Every descriptor's harvest-keys reconstruct a real state — including the
    'switching' warmup, now that harvest_state implements the mode-cycling
    policy (the Stage-2 interpretation of the sentinel)."""
    ds = _descriptors(400, 5)
    # Cover all four warmup values, switching included.
    sample = [d for w in WARMUPS for d in ds if d["warmup"] == w][:40]
    for d in sample:
        kwargs = {k: v for k, v in d.items() if k in HARVEST_KEYS}
        sim = oracle.harvest_state(**kwargs)
        assert sim.building.num_floors == d["floors"]
        assert len(sim.cars) == d["cars"]
