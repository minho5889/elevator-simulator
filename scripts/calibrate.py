#!/usr/bin/env python3
# scripts/calibrate.py
"""Stage-2 oracle calibration harness — the correct, non-circular label-quality gate.

The deployed structural policy switches modes per epoch, so the right question is
NOT "does one label match the single-mode HC5 grid winner" — it is "does the
oracle POLICY, picking per epoch, beat or match the best single fixed mode in
every regime?" This drives a ``StructuralDispatcher`` whose plan provider is the
oracle, runs it full-episode across all regimes, and compares its HC5 to the best
fixed mode for that regime.

Used to LOCK the oracle's (weights, horizon, settle) defaults [scripts/oracle.py].
The locked config (settle=horizon=300, throughput-balanced weights) was selected
because it clears every regime and GENERALISES to held-out seeds and a held-out
height (48fl) — closing the lunch myopia the freeze flagged (0.88 -> 1.02).

Re-run after any change to the oracle, the cost function, or the structural
dispatchers, to confirm the policy still isn't beaten by a fixed mode anywhere:
    uv run python scripts/calibrate.py
    uv run python scripts/calibrate.py --seeds 9,10,11 --floors 48   # held-out check
"""

import argparse
import importlib.util
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from elevatorsim.policy.structural import StructuralDispatcher

_ROOT = Path(__file__).resolve().parent
_oracle_spec = importlib.util.spec_from_file_location("oracle_cal", _ROOT / "oracle.py")
oracle = importlib.util.module_from_spec(_oracle_spec)
sys.modules["oracle_cal"] = oracle
_oracle_spec.loader.exec_module(oracle)

# Best fixed mode per regime (from the measured winner grid, skyscraper-plan §7).
FIXED_BEST = {"up_peak": "dd_delayed", "down_peak": "dd_delayed",
              "lunch": "zoned", "uniform": "look"}
REGIMES = list(FIXED_BEST)


def _eval(args: Tuple) -> Tuple:
    """One (kind, regime, seed) full-episode HC5. Runs in a worker process."""
    kind, regime, seed, floors, cars, epoch, horizon, settle = args
    a_spec = importlib.util.spec_from_file_location("arena_cal", _ROOT / "arena.py")
    arena = importlib.util.module_from_spec(a_spec)
    sys.modules["arena_cal"] = arena
    a_spec.loader.exec_module(arena)

    cell = dict(floors=floors, cars=cars, capacity=24, arrival_rate=2.0, ticks=900,
                stop_ticks=9, transfer_ticks=1, population=floors * 100)
    if kind == "oracle":
        def provider(sim):
            best, _ = oracle.label_decision(sim, horizon, settle_ticks=settle)
            return best
        base = arena._make_dispatcher
        arena._make_dispatcher = (
            lambda n: StructuralDispatcher(provider, min_epoch_ticks=epoch)
            if n == "oracle" else base(n)
        )
        hc5 = arena.run_one("oracle", regime, seed, **cell)["hc5"]
    else:
        hc5 = arena.run_one(FIXED_BEST[regime], regime, seed, **cell)["hc5"]
    return (kind, regime, hc5)


def calibrate(
    seeds: List[int], floors: int, cars: int, epoch: int,
    horizon: Optional[int], settle: Optional[int],
) -> Dict[str, Tuple[float, float, float]]:
    """Return {regime: (oracle_hc5, best_fixed_hc5, ratio)} averaged over seeds."""
    horizon = oracle.DEFAULT_HORIZON if horizon is None else horizon
    settle = oracle.DEFAULT_SETTLE if settle is None else settle
    tasks = [
        (kind, regime, seed, floors, cars, epoch, horizon, settle)
        for kind in ("oracle", "fixed") for regime in REGIMES for seed in seeds
    ]
    with Pool(min(8, len(tasks))) as pool:
        results = pool.map(_eval, tasks)

    agg: Dict[Tuple[str, str], List[float]] = {}
    for kind, regime, hc5 in results:
        agg.setdefault((kind, regime), []).append(hc5)

    out = {}
    for regime in REGIMES:
        oh = sum(agg[("oracle", regime)]) / len(seeds)
        fh = sum(agg[("fixed", regime)]) / len(seeds)
        out[regime] = (oh, fh, oh / fh if fh else 0.0)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Stage-2 oracle-policy calibration gate.")
    parser.add_argument("--seeds", default="7,8")
    parser.add_argument("--floors", type=int, default=32)
    parser.add_argument("--cars", type=int, default=8)
    parser.add_argument("--epoch", type=int, default=300)
    parser.add_argument("--horizon", type=int, default=None)
    parser.add_argument("--settle", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=0.97,
                        help="min oracle/fixed HC5 ratio to PASS in every regime")
    args = parser.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]

    res = calibrate(seeds, args.floors, args.cars, args.epoch, args.horizon, args.settle)
    h = oracle.DEFAULT_HORIZON if args.horizon is None else args.horizon
    s = oracle.DEFAULT_SETTLE if args.settle is None else args.settle
    print(f"oracle-policy vs best fixed mode | seeds={seeds} floors={args.floors} "
          f"epoch={args.epoch} horizon={h} settle={s}")
    worst = 1e9
    for regime in REGIMES:
        oh, fh, ratio = res[regime]
        worst = min(worst, ratio)
        verdict = "OK" if ratio >= args.threshold else "BELOW"
        print(f"  {regime:10} oracle={oh:7.1f}  best_fixed={fh:7.1f} ({FIXED_BEST[regime]:10})  "
              f"ratio={ratio:.3f}  {verdict}")
    passed = worst >= args.threshold
    print(f"\n{'PASS' if passed else 'FAIL'} — min ratio {worst:.3f} "
          f"(threshold {args.threshold})")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
