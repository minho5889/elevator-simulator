# src/elevatorsim/arena/__init__.py
"""Importable arena core — the dispatcher ladder, regimes, and single-run scorer
lifted out of ``scripts/arena.py`` so the web layer can reuse them without
depending on the (non-package) ``scripts/`` directory.

``scripts/arena.py`` re-exports everything here for back-compat (its CLI, the
ladder table, and the existing tests are unchanged).
"""

from elevatorsim.arena.registry import (
    CONTESTANT_LADDER,
    CONTESTANT_META,
    DISPATCHERS,
    REGIMES,
    _make_dispatcher,
    make_dispatcher,
    structural_available,
)
from elevatorsim.arena.run import (
    analytic_rtt,
    expected_stops,
    hc5_from_interval,
    highest_reversal,
    percentile,
    run_one,
)

__all__ = [
    "CONTESTANT_LADDER",
    "CONTESTANT_META",
    "DISPATCHERS",
    "REGIMES",
    "_make_dispatcher",
    "make_dispatcher",
    "structural_available",
    "analytic_rtt",
    "expected_stops",
    "hc5_from_interval",
    "highest_reversal",
    "percentile",
    "run_one",
]
