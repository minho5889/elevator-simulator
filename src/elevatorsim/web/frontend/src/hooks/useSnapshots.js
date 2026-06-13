// src/hooks/useSnapshots.js
// Consume the per-tick STATE SNAPSHOT stream the arena backend sends, in O(1).
// Falls back to replaying the legacy event stream (reconstructState) for old
// preset caches that predate snapshots.

import { reconstructState } from '../utils/simulationHelper.js';

/**
 * The snapshot for a contestant at `tick`. Exact hit when state_every==1; else
 * the most recent snapshot at or before `tick`. Returns null if none yet.
 */
export function snapshotAt(contestant, tick) {
  if (!contestant) return null;
  const snaps = contestant.snapshots;
  if (snaps && snaps[tick]) return snaps[tick];
  if (snaps) {
    let best = null;
    let bestKey = -1;
    for (const k in snaps) {
      const kt = Number(k);
      if (kt <= tick && kt > bestKey) { bestKey = kt; best = snaps[k]; }
    }
    if (best) return best;
  }
  // Legacy event-stream preset: reconstruct on the fly (no zones/mode/weight).
  if (contestant.events) {
    const r = reconstructState(contestant.events, tick, contestant.numFloors, contestant.numCars);
    return legacyToSnapshot(r, contestant.id, tick);
  }
  return null;
}

/** Adapt a legacy reconstructState() result into the snapshot shape so the
 *  shaft renderer has one contract. Zones/mode/assignment are simply absent. */
function legacyToSnapshot(r, id, tick) {
  return {
    contestant_id: id,
    tick,
    cars: Object.entries(r.cars).map(([car_id, c]) => ({
      car_id,
      floor: c.floor,
      position: c.floor,
      target_floor: c.targetFloor,
      direction: 0,
      door_state: c.doorState,
      door_timer: 0,
      onboard: c.onboardPassengers.map((p) => ({ id: p.id, target: p.target, weight: p.weight })),
      passenger_count: c.onboardPassengers.length,
      capacity: null,
      weight_kg: c.onboardPassengers.reduce((s, p) => s + (p.weight || 0), 0),
      max_weight_kg: null,
      service_range: null,
      assigned_only: false,
      refused_recently: c.refusedRecently || false,
    })),
    floor_queues: Object.fromEntries(
      Object.entries(r.floorQueues)
        .filter(([, q]) => q.length)
        .map(([f, q]) => [f, q.map((p) => ({ id: p.id, target: p.target, weight: p.weight }))]),
    ),
    metrics: null,
  };
}
