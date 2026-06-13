# tests/test_label.py
"""Gate tests for WO-002 — the Stage-2 oracle label driver (scripts/label.py).

Authored by Lane A at audit time (the gate was deferred, not pre-written — a
process slip recorded in the WO-002 audit). Enforces the record contract Stage 3
(WO-003) assembly depends on: schema-valid labels, the compact traffic-summary
input_view, locked-default labeling, determinism, and an unperturbed global RNG.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

import elevatorsim.config as config
from elevatorsim.policy.schemas import StructuralPlan

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("label", _ROOT / "scripts" / "label.py")
label = importlib.util.module_from_spec(_spec)
sys.modules["label"] = label
_spec.loader.exec_module(label)  # also imports scripts/oracle.py as "oracle"
oracle = sys.modules["oracle"]

# A representative descriptor (the harvest_state kwargs WO-001 emits).
def _desc(**over):
    d = {
        "regime": "up_peak", "seed": 7, "harvest_tick": 120, "floors": 32,
        "cars": 8, "capacity": 24, "arrival_rate": 2.0, "stop_ticks": 9,
        "transfer_ticks": 1, "warmup": "conventional", "weight_limit": None,
    }
    d.update(over)
    return d


def test_record_shape_and_label_validates():
    rec = label.label_descriptor(_desc())
    assert set(rec) == {"descriptor", "input_view", "label", "scored"}
    plan = StructuralPlan(**rec["label"])  # the label is a valid frozen plan
    assert plan.mode in ("conventional", "dd_delayed", "zoned")
    assert len(rec["scored"]) == 9  # full candidate breakdown for Tier-B
    json.dumps(rec, sort_keys=True)  # the whole record is JSON-serializable


def test_input_view_is_compact_traffic_summary_only():
    rec = label.label_descriptor(_desc())
    iv = json.loads(rec["input_view"])
    assert "frac_origin_lobby" in iv  # the regime signal is present
    # The G5 amendment: NO per-passenger / per-car bloat in the model input.
    assert "floor_calls" not in iv and "cars" not in iv
    assert len(rec["input_view"]) < 600


def test_label_uses_locked_oracle_defaults():
    """label.py must call label_decision with NO overrides — match the oracle."""
    d = _desc(regime="lunch", seed=8)
    rec = label.label_descriptor(d)
    kwargs = {k: v for k, v in d.items() if k in (
        "regime", "seed", "harvest_tick", "floors", "cars", "capacity",
        "arrival_rate", "stop_ticks", "transfer_ticks", "warmup", "weight_limit")}
    best, _ = oracle.label_decision(oracle.harvest_state(**kwargs))
    assert rec["label"] == {"mode": best.mode, "hold": best.hold}


def test_labeling_is_deterministic():
    d = _desc(regime="down_peak", seed=9)
    a = label.label_descriptor(d)
    b = label.label_descriptor(d)
    assert a["label"] == b["label"]
    assert a["input_view"] == b["input_view"]
    assert [s["cost"] for s in a["scored"]] == [s["cost"] for s in b["scored"]]


def test_global_rng_unperturbed_across_run():
    before = config.RNG.getstate()
    label.label_descriptors([_desc(seed=1), _desc(seed=2, regime="lunch")])
    assert config.RNG.getstate() == before


def test_switching_and_weight_limit_descriptors_label():
    sw = label.label_descriptor(_desc(regime="lunch", warmup="switching", harvest_tick=300))
    assert StructuralPlan(**sw["label"]).mode in ("conventional", "dd_delayed", "zoned")
    wl = label.label_descriptor(_desc(regime="up_peak", weight_limit=150, arrival_rate=2.0))
    assert "mode" in wl["label"]
