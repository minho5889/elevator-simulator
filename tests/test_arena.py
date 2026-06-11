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
        "hc5_equiv", "delivered", "spawned", "completion", "refusals", "ref_per_del",
    ):
        assert key in result
    assert result["spawned"] > 0
    assert result["delivered"] > 0
    assert 0.0 <= result["completion"] <= 1.0
    # No weight limit -> no refusals.
    assert result["refusals"] == 0


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
