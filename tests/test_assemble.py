# tests/test_assemble.py
"""Gate tests for WO-003 — Stage-3 dataset assembly (scripts/assemble.py).

Authored by Lane A BEFORE Lane B implements (gate-first, restoring the
discipline that slipped on WO-002). Skips until scripts/assemble.py exists, then
becomes the enforced pre-GPU FORMAT-FIDELITY gate: every SFT sample is built
through the shared train==prod anchor, the assistant target is a bare
StructuralPlan (no reasoning leak), rationales stay teacher-only, and the
train/held-out split has zero leakage. A format slip here is the #1 silent SFT
killer — the model trains on one prompt and is served another.

Expected interface for scripts/assemble.py (Antigravity implements):
  build_sample(record: dict, rationale: str | None = None) -> dict
      Returns one chat-format SFT sample:
        {"messages": [ {system}, {user}, {assistant} ],
         "rationale": <str or absent>}     # teacher-only, NEVER in messages
      where {system,user} == build_structural_messages(record["input_view"])
      and {assistant}.content == structural_target_json(plan from record["label"]).
  split(records: list[dict]) -> {"train": [...], "heldout": [...]}
      Held-out = records on the held-out seed set per regime PLUS records of one
      config (floors, cars) never present in train. Train and held-out disjoint.
  assemble(records, rationales: dict | None = None) -> {"train":[samples], "heldout":[samples]}
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from elevatorsim.policy.schemas import StructuralPlan
from elevatorsim.policy.structural import (
    STRUCTURAL_SYSTEM_PROMPT,
    build_structural_messages,
    structural_target_json,
)

_ASSEMBLE = Path(__file__).resolve().parents[1] / "scripts" / "assemble.py"
if not _ASSEMBLE.exists():
    pytest.skip(
        "scripts/assemble.py not yet implemented (WO-003) — gate skips until then.",
        allow_module_level=True,
    )

_spec = importlib.util.spec_from_file_location("assemble", _ASSEMBLE)
assemble = importlib.util.module_from_spec(_spec)
sys.modules["assemble"] = assemble
_spec.loader.exec_module(assemble)


def _record(seed=7, regime="up_peak", floors=32, cars=8, mode="dd_delayed", hold="balanced"):
    iv = json.dumps({"frac_origin_lobby": 1.0, "num_floors": floors}, sort_keys=True)
    return {
        "descriptor": {"seed": seed, "regime": regime, "floors": floors, "cars": cars,
                       "warmup": "conventional"},
        "input_view": iv,
        "label": {"mode": mode, "hold": hold},
        "scored": [],
    }


def test_sample_uses_the_train_prod_anchor():
    rec = _record()
    sample = assemble.build_sample(rec)
    msgs = sample["messages"]
    expected_prompt = build_structural_messages(rec["input_view"])
    assert msgs[:2] == expected_prompt                      # system+user via the anchor
    assert msgs[0]["content"] == STRUCTURAL_SYSTEM_PROMPT
    assert msgs[2]["role"] == "assistant"


def test_assistant_target_is_a_bare_structural_plan():
    rec = _record(mode="zoned", hold="fill_batch")
    sample = assemble.build_sample(rec)
    target = sample["messages"][2]["content"]
    # Exactly the canonical target — no reasoning, no extra keys, parses to the label.
    assert target == structural_target_json(StructuralPlan(mode="zoned", hold="fill_batch"))
    parsed = json.loads(target)
    assert set(parsed) == {"mode", "hold"}
    StructuralPlan.model_validate_json(target)


def test_rationale_is_teacher_only_never_in_output():
    rec = _record()
    sample = assemble.build_sample(rec, rationale="lobby peak -> destination dispatch")
    # The rationale must NOT appear in any message (it would corrupt the output).
    blob = json.dumps(sample["messages"])
    assert "lobby peak" not in blob
    assert sample.get("rationale") == "lobby peak -> destination dispatch"


def test_every_assembled_output_parses_as_structural_plan():
    """Format-fidelity: across a mixed batch, every assistant target is valid."""
    recs = [_record(seed=s, mode=m, hold=h)
            for s in range(20) for m in ("conventional", "dd_delayed", "zoned")
            for h in ("balanced",)]
    out = assemble.assemble(recs)
    for sample in out["train"] + out["heldout"]:
        StructuralPlan.model_validate_json(sample["messages"][2]["content"])


def test_split_has_no_leakage():
    """Held-out seeds/config never appear in train (no train/eval contamination)."""
    recs = (
        [_record(seed=s, regime=r) for s in range(30) for r in ("up_peak", "lunch")]
        + [_record(seed=900, floors=52, cars=10, regime="uniform")]  # the unseen config
    )
    out = assemble.assemble(recs)
    train_ids = {(s["messages"][1]["content"]) for s in out["train"]}
    held_ids = {(s["messages"][1]["content"]) for s in out["heldout"]}
    assert train_ids.isdisjoint(held_ids)
    # The unseen-config sample must be held out, never trained on.
    held_floors = {json.loads(_input_view_of(s)).get("num_floors") for s in out["heldout"]}
    train_floors = {json.loads(_input_view_of(s)).get("num_floors") for s in out["train"]}
    assert 52 in held_floors and 52 not in train_floors


def _input_view_of(sample: dict) -> str:
    """Recover the input_view from a sample's user message (after the template)."""
    user = sample["messages"][1]["content"]
    return user[len("Traffic summary: "):-len("\nPlan:")]
