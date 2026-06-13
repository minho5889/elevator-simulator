# tests/test_structural_agent.py
"""P7 inference surface: the learned structural policy provider + dispatcher.

Offline tests (fallback, wiring, frozen prompt) run everywhere; the real-model
smoke test is skipped unless a local Ollama with a gemma model is reachable.
"""

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

from elevatorsim.policy.schemas import StructuralPlan
from elevatorsim.policy.structural import (
    STRUCTURAL_SYSTEM_PROMPT,
    STRUCTURAL_USER_TEMPLATE,
    StructuralDispatcher,
    build_structural_messages,
    structural_target_json,
)
from elevatorsim.policy.structural_agent import (
    LLMStructuralProvider,
    render_traffic_summary,
)
from elevatorsim.config import OLLAMA_MODEL_ID

_ROOT = Path(__file__).resolve().parents[1]
_ospec = importlib.util.spec_from_file_location("oracle_sa", _ROOT / "scripts" / "oracle.py")
oracle = importlib.util.module_from_spec(_ospec)
sys.modules["oracle_sa"] = oracle
_ospec.loader.exec_module(oracle)


class _Fixed(LLMStructuralProvider):
    """Provider with a deterministic model — no Ollama, for offline tests."""

    def __init__(self, plan: StructuralPlan):
        self._plan = plan
        self._last_plan = plan
        self.stats = {"calls": 0, "invalid": 0}

    def _query_model(self, summary: str) -> StructuralPlan:
        return self._plan


class _Failing(LLMStructuralProvider):
    """Provider whose model call always raises — exercises the fallback path."""

    def __init__(self):
        self._last_plan = StructuralPlan(mode="conventional", hold="balanced")
        self.stats = {"calls": 0, "invalid": 0}

    def _query_model(self, summary: str) -> StructuralPlan:
        raise RuntimeError("model unavailable")


def test_render_traffic_summary_is_compact_and_excludes_call_dump():
    """The model input is the ~200-char traffic summary, not the 17 KB call dump."""
    sim = oracle.harvest_state("up_peak", 7, 120, floors=32)
    s = render_traffic_summary(sim)
    assert len(s) < 600  # compact; the full floor_calls dump is ~17 KB
    d = json.loads(s)
    assert d["frac_origin_lobby"] == 1.0  # up-peak signal present
    assert "floor_calls" not in d and "cars" not in d  # no per-passenger bloat


def test_provider_falls_back_to_last_plan_on_failure():
    """A model/parse failure forfeits to the last committed plan (a no-op epoch)."""
    sim = oracle.harvest_state("lunch", 7, 120, floors=20)
    p = _Failing()
    plan = p(sim)
    assert (plan.mode, plan.hold) == ("conventional", "balanced")  # cold-start default
    assert p.stats == {"calls": 1, "invalid": 1}
    assert p.valid_rate == 0.0


def test_provider_commits_then_reuses_last_good_plan():
    """A success updates the last plan; a later failure reuses it, not the default."""
    sim = oracle.harvest_state("lunch", 7, 120, floors=20)
    good = _Fixed(StructuralPlan(mode="zoned", hold="fill_batch"))
    assert good(sim).mode == "zoned"
    assert good.valid_rate == 1.0
    # Now make the same provider fail and confirm it reuses the committed plan.
    good._query_model = lambda summary: (_ for _ in ()).throw(RuntimeError("boom"))
    plan = good(sim)
    assert (plan.mode, plan.hold) == ("zoned", "fill_batch")
    assert good.stats["invalid"] == 1


def test_dispatcher_wiring_drives_a_full_episode():
    """A provider-backed StructuralDispatcher runs a full episode and delivers."""
    # The arena engine now lives in the importable package; patch the canonical
    # dispatcher factory (registry._make_dispatcher) to inject a fixed-plan policy.
    from elevatorsim.arena import registry
    from elevatorsim.arena.run import run_one

    base = registry._make_dispatcher
    registry._make_dispatcher = lambda n: (
        StructuralDispatcher(_Fixed(StructuralPlan(mode="zoned", hold="balanced")), min_epoch_ticks=300)
        if n == "_fixed" else base(n)
    )
    try:
        r = run_one("_fixed", "lunch", 7, floors=32, cars=8, capacity=24,
                    arrival_rate=2.0, ticks=900, stop_ticks=9, transfer_ticks=1)
    finally:
        registry._make_dispatcher = base
    assert r["delivered"] > 0 and r["completion"] > 0.3


def test_frozen_system_prompt_carries_the_contract():
    """The frozen prompt names every mode/hold and is shared by the inference path."""
    for token in ("conventional", "dd_delayed", "zoned", "depart_now", "balanced", "fill_batch"):
        assert token in STRUCTURAL_SYSTEM_PROMPT
    assert "Respond with the plan only." in STRUCTURAL_SYSTEM_PROMPT
    # The inference provider defaults to this exact frozen string (train == prod):
    # the same object the assembly path (WO-003) will import.
    import inspect
    default = inspect.signature(LLMStructuralProvider.__init__).parameters["system_prompt"].default
    assert default is STRUCTURAL_SYSTEM_PROMPT


def test_anchor_build_structural_messages():
    """The shared prompt builder produces the exact (system, user) pair."""
    iv = '{"frac_origin_lobby":1.0}'
    msgs = build_structural_messages(iv)
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == STRUCTURAL_SYSTEM_PROMPT
    assert msgs[1]["content"] == STRUCTURAL_USER_TEMPLATE.format(input_view=iv)
    assert msgs[1]["content"] == f"Traffic summary: {iv}\nPlan:"


def test_anchor_target_json_is_canonical_and_parses():
    """The assistant target is minimal (mode+hold only), standard-spaced, parses."""
    s = structural_target_json(StructuralPlan(mode="zoned", hold="fill_batch"))
    assert s == '{"mode": "zoned", "hold": "fill_batch"}'  # exact canonical form
    assert json.loads(s) == {"mode": "zoned", "hold": "fill_batch"}  # no extra keys
    back = StructuralPlan.model_validate_json(s)
    assert (back.mode, back.hold) == ("zoned", "fill_batch")


def test_inference_builds_prompt_through_the_anchor():
    """train == prod: the provider must route its prompt through the anchor, not
    an inline f-string that could silently drift from assembly (WO-003)."""
    import inspect
    src = inspect.getsource(LLMStructuralProvider._query_model)
    assert "build_structural_messages" in src
    assert "Traffic summary:" not in src  # no inline duplicate of the template


# --- Gemma-4 render-identity facts (the render-identity gate, training-plan §5) ---
# Verified against TWO authoritative sources that agree: the served gemma4:e4b GGUF
# vocab (ollama blob) AND google/gemma-4-E4B-it/chat_template.jinja.
#
# Gemma 4 CHANGED its turn delimiters. It does NOT use Gemma-2/3's
# <start_of_turn>/<end_of_turn> — those strings are NOT tokens in the Gemma-4 vocab
# (id 105='<|turn>', 106='<turn|>', 50='<|tool_response>', 1='<eos>', 2='<bos>').
# The official template renders: <bos><|turn>system\n{sys}<turn|>\n<|turn>user\n
# {user}<turn|>\n<|turn>model\n{target}<turn|>\n  (assistant role -> 'model';
# turn-ending EOS = <turn|>, id 106). Hard-coding the old <start_of_turn> markers in
# a Modelfile TEMPLATE or a trainer f-string tokenizes them as RAW TEXT and silently
# poisons train==prod — the #1 pre-GPU killer. The fix is to inherit Ollama's
# built-in `RENDERER gemma4`/`PARSER gemma4` and format the trainer via the model's
# own tokenizer.apply_chat_template, so both sides apply the SAME official template.
_GEMMA2_PHANTOM_MARKERS = ("<start_of_turn>", "<end_of_turn>")
_GEMMA4_TURN_OPEN = "<|turn>"
_GEMMA4_TURN_CLOSE = "<turn|>"  # turn-ending EOS, token id 106
_GEMMA4_BASE_ID = "google/gemma-4-E4B-it"


def _modelfile_directives(text: str) -> str:
    """The Modelfile with comment lines stripped — active directives only.

    Rationale comments legitimately NAME the phantom markers to warn against them;
    the structural gate must inspect the directives, not the prose."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def _extract_template_value(directives: str):
    """Return the TEMPLATE directive's value (triple-quoted block or single line)."""
    m = re.search(r'TEMPLATE\s+"""(.*?)"""', directives, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"^\s*TEMPLATE\s+(.+)$", directives, re.MULTILINE)
    return m.group(1).strip() if m else None


def test_chat_template_render_identity():
    """Pre-GPU train==prod gate [format-fidelity audit G1/G2] — OFFLINE structural half.

    The served Modelfile and the LoRA trainer must render the anchor messages to
    the same token stream, or the fine-tune is train != prod (the single
    highest-severity pre-GPU killer). This half runs EVERYWHERE and CAN FAIL: it
    enforces the renderer-inherit design and forbids the Gemma-2 phantom markers
    that are absent from the Gemma-4 vocab. The token-level identity check is the
    separate ``test_chat_template_token_identity_online`` below.

    HONESTY CONTRACT: this replaced (a) a self-comparing version that always
    passed, and (b) a follow-up that asserted the WRONG Gemma-2 <start_of_turn>
    markers then unconditionally skipped. It now does real, failing-capable work.
    """
    modelfile = Path(__file__).resolve().parents[1] / "Modelfile"
    if not modelfile.exists():
        pytest.skip("Modelfile not committed yet (Stage 5)")
    directives = _modelfile_directives(modelfile.read_text())

    # 1) No Gemma-2 phantom markers in the active directives — their presence IS
    #    the bug (they are not tokens in the Gemma-4 vocab).
    for phantom in _GEMMA2_PHANTOM_MARKERS:
        assert phantom not in directives, (
            f"Modelfile directive uses {phantom!r}, a Gemma-2 phantom token absent "
            f"from the Gemma-4 vocab — it tokenizes as raw text and breaks train==prod."
        )
    # 2) Chat formatting must be INHERITED from Ollama's built-in gemma4 renderer/
    #    parser (the metadata-only fix), not hand-rolled.
    assert re.search(r"^\s*RENDERER\s+gemma4\s*$", directives, re.MULTILINE), (
        "Modelfile must declare `RENDERER gemma4` so Ollama applies the official "
        "Gemma-4 chat template (not a hand-rolled one)."
    )
    assert re.search(r"^\s*PARSER\s+gemma4\s*$", directives, re.MULTILINE), (
        "Modelfile must declare `PARSER gemma4` (owns turn-stop on <turn|>)."
    )
    # 3) TEMPLATE must be the passthrough — never a hand-rolled turn template that
    #    would REPLACE the renderer and reintroduce the '---'-on-repeat breakage.
    template = _extract_template_value(directives)
    assert template is not None, "Modelfile has no TEMPLATE directive"
    assert template.strip() == "{{ .Prompt }}", (
        "TEMPLATE must be the passthrough `{{ .Prompt }}` so RENDERER gemma4 owns "
        f"formatting; got {template.strip()!r}."
    )
    assert _GEMMA4_TURN_OPEN not in template and "<start_of_turn>" not in template, (
        "TEMPLATE must not hard-code turn markers — the renderer emits them."
    )
    # 4) The base must be a Gemma-4 artifact, never Gemma-2.
    from_m = re.search(r"^\s*FROM\s+(.+)$", directives, re.MULTILINE)
    assert from_m, "Modelfile has no FROM"
    from_src = from_m.group(1).strip().lower()
    assert "gemma-2" not in from_src and "gemma2" not in from_src, (
        f"FROM points at a Gemma-2 base ({from_src!r}); this project serves Gemma 4."
    )
    assert "gemma4" in from_src or from_src.endswith(".gguf"), (
        f"FROM should be the gemma4 base or the converted gemma4 GGUF; got {from_src!r}."
    )
    # 5) Deterministic structured decode — matches LLMStructuralProvider's options.
    assert re.search(
        r"^\s*PARAMETER\s+temperature\s+0(\.0+)?\s*$", directives, re.MULTILINE
    ), "Structured decode must be deterministic: PARAMETER temperature 0."
    # 6) Any stop token must be a REAL Gemma-4 token, never the phantom.
    for stop_m in re.finditer(
        r'^\s*PARAMETER\s+stop\s+"?([^"\n]+?)"?\s*$', directives, re.MULTILINE
    ):
        tok = stop_m.group(1).strip()
        assert tok in (_GEMMA4_TURN_CLOSE, "<eos>"), (
            f"stop token {tok!r} is not a real Gemma-4 turn/eos token "
            f"({_GEMMA4_TURN_CLOSE!r} or <eos>)."
        )


def test_chat_template_token_identity_online():
    """Pre-GPU train==prod gate — ONLINE token-identity half (the real check).

    Renders the anchor messages with the EXACT Gemma-4 base tokenizer and proves
    the official template (the SAME one the served `RENDERER gemma4` implements):
    (a) uses the new <|turn>…<turn|> scheme — NOT the Gemma-2 phantom markers,
    (b) folds the system turn, (c) maps assistant->model, (d) carries the bare
    target closed by the turn-ending EOS the trainer pins.

    This legitimately requires the Stage-4 training env (transformers + the exact
    base tokenizer), so it SKIPS offline. Set GEMMA4_RENDER_IDENTITY_STRICT=1 in
    the Stage-4 CI to make the skip a HARD failure (the gate must actually run
    before the GPU spend). It never fake-passes and never self-compares.
    """
    base_id = os.environ.get("GEMMA4_BASE", _GEMMA4_BASE_ID)
    strict = os.environ.get("GEMMA4_RENDER_IDENTITY_STRICT") == "1"
    try:
        from transformers import AutoTokenizer

        tok = AutoTokenizer.from_pretrained(base_id)
    except Exception as exc:  # transformers absent / tokenizer not cached (offline)
        if strict:
            pytest.fail(
                f"GEMMA4_RENDER_IDENTITY_STRICT=1 but could not load {base_id!r}: {exc!r}"
            )
        pytest.skip(
            "online token-identity deferred to the Stage-4 training env "
            f"(needs transformers + the exact {base_id} tokenizer): {exc!r}"
        )

    iv = '{"frac_origin_lobby": 1.0, "num_floors": 32}'
    plan = StructuralPlan(mode="zoned", hold="fill_batch")
    target = structural_target_json(plan)
    messages = build_structural_messages(iv) + [{"role": "assistant", "content": target}]
    rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)

    # The Gemma-4 turn scheme — NOT the Gemma-2 phantom markers (wrong-base tripwire).
    assert _GEMMA4_TURN_OPEN in rendered and _GEMMA4_TURN_CLOSE in rendered, (
        f"base tokenizer {base_id!r} did not emit the Gemma-4 <|turn>…<turn|> scheme"
    )
    assert "<start_of_turn>" not in rendered and "<end_of_turn>" not in rendered, (
        f"{base_id!r} emitted Gemma-2 markers — wrong base model for the served gemma4:e4b"
    )
    # System folded into a leading <|turn>system block; assistant rendered as model.
    assert "<|turn>system" in rendered, "system turn was not folded as Gemma-4 expects"
    assert STRUCTURAL_SYSTEM_PROMPT.splitlines()[0] in rendered, "system content missing"
    assert "<|turn>model" in rendered, "assistant role was not mapped to 'model'"
    # The bare {mode,hold} target rides in the model turn (closed by <turn|> EOS).
    assert target in rendered
    # Token-level: re-rendering with the generation prompt only APPENDS the model
    # opener, proving prompt == train-prefix (train==prod at the token boundary).
    train_ids = tok.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    prompt_ids = tok.apply_chat_template(
        build_structural_messages(iv), tokenize=True, add_generation_prompt=True
    )
    assert isinstance(train_ids, list) and isinstance(prompt_ids, list)
    # The served prompt is a strict prefix of the trained sequence up to the model
    # turn: the model only has to emit the target + <turn|>. (If this diverges, the
    # model was trained on a prompt it is never served — the silent SFT killer.)
    assert train_ids[: len(prompt_ids)] == prompt_ids, (
        "served prompt (add_generation_prompt) is not a prefix of the trained "
        "sequence — train != prod at the token level"
    )


def _ollama_ready() -> bool:
    try:
        import ollama
        models = [m.get("model", "") for m in ollama.list().get("models", [])]
        return any(OLLAMA_MODEL_ID in m or "gemma4" in m for m in models)
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_ready(), reason="local Ollama + gemma model not available")
def test_real_model_returns_valid_plan():
    """Smoke: the real model produces a schema-valid plan via the production path.

    Latency is the dedicated G5 gate's concern (measured ~1.65s steady-state),
    not this test's — the first call here includes the ~9.6 GB cold model load.
    """
    sim = oracle.harvest_state("up_peak", 7, 120, floors=32)
    provider = LLMStructuralProvider()
    plan = provider(sim)
    assert isinstance(plan, StructuralPlan)
    assert plan.mode in ("conventional", "dd_delayed", "zoned")
    assert provider.valid_rate == 1.0
