// src/elevatorsim/web/frontend/src/components/ElevatorShaft.jsx
// A cartoon building cross-section: roof on top, sand-colored walls,
// solid floor slabs with "1F/2F" signs, grass at street level, and the
// elevator cab riding a cable shaft on the right.
import React from 'react';
import { useLang } from '../i18n.jsx';

const TONES = {
  robot: { line: 'var(--robot)', deep: 'var(--robot-deep)', text: 'var(--robot-text)', fill: 'var(--robot-fill)' },
  brain: { line: 'var(--brain)', deep: 'var(--brain-deep)', text: 'var(--brain-text)', fill: 'var(--brain-fill)' },
  // Legacy accent names map onto the new teams
  look: { line: 'var(--robot)', deep: 'var(--robot-deep)', text: 'var(--robot-text)', fill: 'var(--robot-fill)' },
  agent: { line: 'var(--brain)', deep: 'var(--brain-deep)', text: 'var(--brain-text)', fill: 'var(--brain-fill)' },
};

// Floors are 0-indexed internally; people see "1F" (lobby) and up
const floorName = (idx) => `${idx + 1}F`;

// How many individual rider figures fit in the cab before we collapse to "+N"
const MAX_VISIBLE_RIDERS = 8;

// One waiting passenger: a little person with a destination flag
function WaitingPassenger({ p }) {
  return (
    <span
      className="flex items-center text-[15px] leading-none select-none"
      title={`${p.id} → ${floorName(p.target)}`}
    >
      <span>🧍</span>
      <span className="text-[9px] font-bold mono px-1 py-0.5 rounded-md bg-[var(--surface)] border border-[var(--border-ink)] text-[var(--ink-2)] -ml-0.5">
        →{floorName(p.target)}
      </span>
    </span>
  );
}

export default function ElevatorShaft({ state, numFloors, numCars = 1, accent = 'robot', onFloorClick }) {
  const { t } = useLang();
  const tones = TONES[accent] || TONES.robot;
  const floorIndices = Array.from({ length: numFloors }, (_, i) => numFloors - 1 - i);
  const carIds = Object.keys(state.cars || {});

  // If no multi-car data, fall back to legacy single-car shape
  const carsData = carIds.length > 0 ? state.cars : {
    C1: {
      floor: state.carFloor || 0,
      targetFloor: state.targetFloor,
      doorState: state.doorState || "CLOSED",
      onboardPassengers: state.onboardPassengers || []
    }
  };

  const carEntries = Object.entries(carsData);

  return (
    <div className="flex-1 flex flex-col min-h-[440px]">
      {/* Roof: parapet slab with a little antenna */}
      <div className="relative mx-1">
        <div className="absolute -top-4 right-12 w-1.5 h-4 rounded-t-full bg-[var(--building-deep)]"></div>
        <div className="absolute -top-2.5 left-10 w-8 h-2.5 rounded-t-md bg-[var(--building-deep)] opacity-70"></div>
        <div className="h-4 rounded-t-xl bg-[var(--building-deep)]"></div>
      </div>

      {/* Building body: thick sand walls around the floors + shaft */}
      <div
        className="flex-1 flex bg-[var(--well)] border-x-[10px] border-[var(--building)] relative overflow-hidden"
      >
        {/* Floor rows and waiting queues */}
        <div className="flex-1 flex flex-col justify-between">
          {floorIndices.map((fIdx, rowIdx) => {
            const waitingQueue = state.floorQueues[fIdx] || [];

            return (
              <div
                key={fIdx}
                onClick={() => onFloorClick && onFloorClick(fIdx)}
                className={`flex justify-between items-center h-12 px-2 transition-colors border-b-[4px] last:border-b-0 border-[var(--slab)] ${rowIdx % 2 === 0 ? 'bg-[rgba(255,255,255,0.35)]' : ''} ${onFloorClick ? 'cursor-pointer hover:bg-[var(--surface)]' : ''}`}
              >
                <span
                  className="text-[11px] font-extrabold px-1.5 h-6 rounded-md flex items-center justify-center bg-[var(--building)] text-[#6B5836] shrink-0"
                  aria-label={t('floor.label', { n: fIdx + 1 })}
                >
                  {floorName(fIdx)}
                </span>

                <div className="flex gap-1 flex-wrap overflow-hidden justify-end items-center max-h-full">
                  {waitingQueue.map(p => (
                    <WaitingPassenger key={p.id} p={p} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        {/* Elevator shafts — one per car */}
        {carEntries.map(([carId, carState], idx) => {
          const carFloor = carState.floor || 0;
          const carBottomPercentage = (carFloor / Math.max(numFloors - 1, 1)) * 76;
          const doorsOpen = carState.doorState === 'OPEN';
          const riders = carState.onboardPassengers || [];
          const visibleRiders = riders.slice(0, MAX_VISIBLE_RIDERS);
          const hiddenCount = riders.length - visibleRiders.length;

          return (
            <div key={carId} className={`w-24 flex justify-center relative border-l-[3px] border-[var(--building)] ${idx > 0 ? 'border-dashed' : ''}`} style={{ background: 'rgba(0,0,0,0.03)' }}>
              {/* Cable */}
              <div className="absolute top-0 bottom-0 w-1 rounded" style={{ background: tones.line, opacity: 0.3 }}></div>

              {/* The cab: shows every rider as their own little person */}
              <div
                className="absolute w-[84px] min-h-[64px] rounded-xl flex flex-col border-[3px] transition-all duration-300 ease-in-out overflow-hidden"
                style={{
                  bottom: `${carBottomPercentage + 2}%`,
                  borderColor: tones.deep,
                  background: doorsOpen ? 'var(--surface)' : tones.fill,
                  boxShadow: `0 4px 0 rgba(62,51,88,0.18)`,
                }}
                title={riders.length > 0
                  ? `${riders.length} riding — doors ${doorsOpen ? 'open' : 'closed'}`
                  : `Empty — doors ${doorsOpen ? 'open' : 'closed'}`}
              >
                {/* Headcount badge, only when someone is aboard */}
                {riders.length > 0 && (
                  <span
                    className="absolute top-0.5 right-1 text-[10px] font-extrabold leading-none"
                    style={{ color: tones.text }}
                  >
                    ×{riders.length}
                  </span>
                )}

                {/* Riders: one figure per person; an empty cab is just an empty room */}
                <div className="flex-1 flex flex-wrap items-center justify-center content-center gap-x-0 gap-y-0.5 px-1 pt-2 pb-2.5 min-h-[34px]">
                  {visibleRiders.map(p => (
                    <span
                      key={p.id}
                      className="text-[15px] leading-none select-none"
                      title={`${p.id} → ${floorName(p.target)}`}
                    >
                      🧍
                    </span>
                  ))}
                  {hiddenCount > 0 && (
                    <span className="text-[10px] font-extrabold leading-none" style={{ color: tones.text }}>
                      +{hiddenCount}
                    </span>
                  )}
                </div>

                {/* Doors: slide apart when open */}
                <div className="w-full flex justify-center gap-1 absolute bottom-0.5 px-2">
                  <span
                    className="h-1.5 rounded-sm transition-all duration-300"
                    style={{ background: tones.deep, width: doorsOpen ? '6px' : '24px', opacity: doorsOpen ? 1 : 0.5 }}
                  ></span>
                  <span
                    className="h-1.5 rounded-sm transition-all duration-300"
                    style={{ background: tones.deep, width: doorsOpen ? '6px' : '24px', opacity: doorsOpen ? 1 : 0.5 }}
                  ></span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Street level: grass + sidewalk */}
      <div className="h-2 bg-[var(--building-deep)] mx-1"></div>
      <div className="h-2.5 rounded-b-lg bg-[#8FD9A8]"></div>
    </div>
  );
}
