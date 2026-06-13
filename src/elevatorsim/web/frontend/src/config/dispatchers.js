// src/config/dispatchers.js
// The dispatcher ladder the Arena picks contestants from — one source of truth
// for label / blurb / emoji / color slot, mirroring the backend CONTESTANT_META
// (src/elevatorsim/arena/registry.py). The live catalog (with availability) is
// fetched from GET /api/contestants; this provides the display identity.

export const LADDER = [
  { key: 'look',         toneSlot: 0,  emoji: '🤖', label: 'Rule-Bot (LOOK)',        blurb: 'Classic collective LOOK sweep.' },
  { key: 'structural',   toneSlot: 1,  emoji: '🧠', label: 'AI Brain (learned)',     blurb: 'Gemma picks a structural plan per epoch.', model: true },
  { key: 'look_park',    toneSlot: 6,  emoji: '🅿️', label: 'LOOK + Park',            blurb: 'LOOK with main-terminal parking.' },
  { key: 'dd_delayed',   toneSlot: 7,  emoji: '🎫', label: 'Destination (delayed)',  blurb: 'Kiosk dispatch, late car assignment.' },
  { key: 'dd_immediate', toneSlot: 8,  emoji: '⚡', label: 'Destination (instant)',  blurb: 'Kiosk dispatch, locked at check-in.' },
  { key: 'zoned',        toneSlot: 10, emoji: '🗂️', label: 'Zoned',                  blurb: 'One contiguous floor band per car.' },
  { key: 'shuttle',      toneSlot: 9,  emoji: '🚐', label: 'Shuttle (FIFO)',         blurb: 'Batched FIFO, no destination info.' },
  { key: 'eta',          toneSlot: 2,  emoji: '🧭', label: 'ETA-Cost',               blurb: 'Nearest car + directional continuity.' },
  { key: 'nearest',      toneSlot: 5,  emoji: '🎯', label: 'Nearest-Car',            blurb: 'Always sends the closest car.' },
  { key: 'fcfs',         toneSlot: 4,  emoji: '🐌', label: 'First-Come',             blurb: 'Serves calls in arrival order.' },
  { key: 'agentic',      toneSlot: 3,  emoji: '✨', label: 'AI Brain (Gemini)',      blurb: 'Per-decision LLM dispatch (slow / quota-bound).', model: true },
];

export const DISPATCHERS_BY_KEY = Object.fromEntries(LADDER.map((d) => [d.key, d]));

/** Friendly default matchup: Rule-Bot vs the learned AI Brain. */
export const DEFAULT_MATCHUP = ['look', 'structural'];

export function dispatcherMeta(key) {
  return DISPATCHERS_BY_KEY[key] || { key, toneSlot: 0, emoji: '🛗', label: key, blurb: '' };
}

export const REGIMES = [
  { key: 'up_peak',   emoji: '⬆️', label: 'Up-Peak',   blurb: 'Morning rush — everyone leaving the lobby.' },
  { key: 'down_peak', emoji: '⬇️', label: 'Down-Peak', blurb: 'Evening rush — everyone heading down.' },
  { key: 'lunch',     emoji: '🍱', label: 'Lunch',     blurb: 'Bidirectional churn, both ways at once.' },
  { key: 'uniform',   emoji: '⚖️', label: 'Uniform',   blurb: 'Scattered interfloor traffic, no gradient.' },
];

export const REGIMES_BY_KEY = Object.fromEntries(REGIMES.map((r) => [r.key, r]));

/** Per-metric display config for the leaderboard / chart. */
export const METRICS = [
  { key: 'awt',        label: 'Avg wait',   emoji: '⏱️', betterWhen: 'min', unit: 't' },
  { key: 'p95_wait',   label: 'P95 wait',   emoji: '📈', betterWhen: 'min', unit: 't' },
  { key: 'hc5',        label: 'Throughput', emoji: '🚀', betterWhen: 'max', unit: '' },
  { key: 'completion', label: 'Completion', emoji: '✅', betterWhen: 'max', unit: '%' },
  { key: 'refusals',   label: 'Refusals',   emoji: '🚫', betterWhen: 'min', unit: '' },
];
