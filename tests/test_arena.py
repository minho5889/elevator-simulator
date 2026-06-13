# tests/test_arena.py
"""Smoke + determinism tests for the Stage-0 evaluation arena and baseline ladder."""

import importlib.util
import sys
from pathlib import Path

import pytest

# scripts/ is not a package; load arena.py directly by path.
_ARENA_PATH = Path(__file__).resolve().parents[1] / "scripts" / "arena.py"
_spec = importlib.util.spec_from_file_location("arena", _ARENA_PATH)
arena = importlib.util.module_from_spec(_spec)
sys.modules["arena"] = arena
_spec.loader.exec_module(arena)


def test_percentile_basic():
    """Linear-interpolation percentile matches known values."""
    assert arena.percentile([], 95) == 0.0
    assert arena.percentile([5], 95) == 5.0
    # 0/50/100 percentiles of 1..5 are the min/median/max.
    data = [1, 2, 3, 4, 5]
    assert arena.percentile(data, 0) == 1.0
    assert arena.percentile(data, 50) == 3.0
    assert arena.percentile(data, 100) == 5.0
    # p95 of 1..5 interpolates between 4 and 5: rank = .95*4 = 3.8 -> 4.8.
    assert arena.percentile(data, 95) == pytest.approx(4.8)


def test_run_one_returns_full_metric_panel():
    """A single run yields every report-§8 metric key with sane shapes."""
    result = arena.run_one("look", "uniform", seed=1000, ticks=120, arrival_rate=0.3)
    for key in (
        "awt", "attd", "sq_wait", "p95_wait", "max_wait", "energy",
        "hc5", "pct_pop", "rtt_mean", "uppint", "p_bar",
        "delivered", "spawned", "completion", "refusals", "ref_per_del",
    ):
        assert key in result
    assert result["spawned"] > 0
    assert result["delivered"] > 0
    assert 0.0 <= result["completion"] <= 1.0
    # No weight limit -> no refusals; no population arg -> no %POP.
    assert result["refusals"] == 0
    assert result["pct_pop"] is None


def test_run_one_is_deterministic_per_seed():
    """Same dispatcher + seed -> identical metrics (per-seed reproducibility)."""
    a = arena.run_one("look", "lunch", seed=2024, ticks=120)
    b = arena.run_one("look", "lunch", seed=2024, ticks=120)
    assert a == b


def test_traffic_identical_across_dispatchers_at_same_seed():
    """Reseeding makes traffic identical across policies -> same spawned count."""
    look = arena.run_one("look", "up_peak", seed=555, ticks=120)
    fcfs = arena.run_one("fcfs", "up_peak", seed=555, ticks=120)
    assert look["spawned"] == fcfs["spawned"]


def test_weight_limit_produces_refusals():
    """A tight per-car weight cap forces boarding refusals (the G3 lever)."""
    # 5 floors, 1 car, heavy up-peak load, 120kg cap -> at most ~1-2 riders.
    result = arena.run_one(
        "look", "up_peak", seed=1, weight_limit=120.0, arrival_rate=0.6, ticks=200
    )
    assert result["refusals"] > 0


def test_all_baselines_run_and_complete_passengers():
    """Every rung of the ladder runs headless and delivers passengers."""
    for name in ("fcfs", "nearest", "eta", "look"):
        r = arena.run_one(name, "uniform", seed=42, ticks=150, arrival_rate=0.3)
        assert r["delivered"] > 0, f"{name} delivered nobody"


def test_run_cell_aggregates_seeds():
    """run_cell averages across a seed list and keeps per-run detail."""
    cell = arena.run_cell("nearest", "down_peak", [1, 2, 3], ticks=100)
    assert len(cell["runs"]) == 3
    assert cell["mean"]["delivered"] > 0
    assert cell["regime"] == "down_peak"


# ---------------------------------------------------------------------------
# P3 — handling-capacity instrumentation and survivorship discipline
# (skyscraper-plan.md gate S2; Report §5.3, §6, §8)
# ---------------------------------------------------------------------------

def test_analytic_chain_reproduces_kone_anchor():
    """The §6 formula implementation reproduces the published worked example.

    KONE Elevcon 2005: N=19 floors above terminal, P=19.2 per trip, 8 cars,
    RTT 202.3 s -> interval 25.3 s -> ~227.8 persons / 5 min = 12.0% of the
    1,900-person population. Our formula code must land on the same numbers.
    """
    assert arena.expected_stops(19, 19.2) == pytest.approx(12.27, abs=0.05)
    assert arena.highest_reversal(19, 19.2) == pytest.approx(18.48, abs=0.05)
    uppint = 202.3 / 8
    hc5 = arena.hc5_from_interval(19.2, uppint)
    assert hc5 == pytest.approx(227.8, abs=0.5)
    assert hc5 / 1900 * 100 == pytest.approx(12.0, abs=0.1)


def test_s2_conventional_control_reproduces_sizing_band():
    """Gate S2: the simulated reference cell lands on the §6 anchor.

    The §6 building (19 floors above terminal, 8 cars, capacity 24) under
    conventional control (LOOK + main-terminal parking), saturated up-peak,
    with the calibrated tick parameters t_v=1, t_s=9, t_p=1 (1 tick = 1 s),
    measures ~11.9% of population per 5 minutes vs the published 12.0%.
    Naive LOOK without parking strands half the bank upstairs (~8%) — the
    parking rung exists precisely to model conventional staging [Report §1.3].
    """
    results = [
        arena.run_one(
            "look_park", "up_peak", seed, floors=20, cars=8, capacity=24,
            arrival_rate=1.0, ticks=900, stop_ticks=9, transfer_ticks=1,
            population=1900,
        )
        for seed in (7, 8, 9)
    ]
    mean_pct = sum(r["pct_pop"] for r in results) / len(results)
    assert 11.0 <= mean_pct <= 13.0, mean_pct

    for r in results:
        # Cars load essentially full through the single lobby door.
        assert r["p_bar"] >= 0.8 * 24
        # The interval identity holds by construction.
        assert r["uppint"] == pytest.approx(r["rtt_mean"] / 8, abs=0.01)
        # Measured RTT is in the analytic neighbourhood for the observed load
        # (engine charges ~t_s+1 per stop; ±25% covers discretisation).
        predicted = arena.analytic_rtt(19, r["p_bar"], 1.0, 10.0, 1.0)
        assert 0.75 * predicted <= r["rtt_mean"] <= 1.25 * predicted


def test_zero_delivery_reports_none_not_zero():
    """Wait metrics are None (not a flattering 0.0) when nobody completes."""
    r = arena.run_one("fcfs", "uniform", seed=1, ticks=3, arrival_rate=1.0)
    assert r["delivered"] == 0
    assert r["awt"] is None
    assert r["p95_wait"] is None
    assert r["attd"] is None
    assert r["completion"] == 0.0
    assert r["hc5"] == 0.0


def test_star_eligibility_blocks_survivorship_winners():
    """Best-in-column stars require completion near the regime's best.

    The observed live failure: a 150 kg weight cap made nearest/eta deliver ~3%
    of passengers with vacuously low AWT, starring 'best' over LOOK at 63%.
    """
    field = {"look": 0.631, "fcfs": 0.091, "nearest": 0.032, "eta": 0.031}
    assert arena.star_eligible(field) == {"look"}
    # Close completions all stay eligible.
    assert arena.star_eligible({"a": 1.0, "b": 0.95, "c": 0.89}) == {"a", "b"}
    # Nobody delivers -> nobody stars.
    assert arena.star_eligible({"a": 0.0, "b": 0.0}) == set()
    assert arena.star_eligible({}) == set()
