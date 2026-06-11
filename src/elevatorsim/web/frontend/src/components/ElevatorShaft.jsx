// src/elevatorsim/web/frontend/src/components/ElevatorShaft.jsx
import React from 'react';
import { useLang } from '../i18n.jsx';

const TONES = {
  robot: { line: 'var(--robot)', deep: 'var(--robot-deep)', text: 'var(--robot-text)', fill: 'var(--robot-fill)' },
  brain: { line: 'var(--brain)', deep: 'var(--brain-deep)', text: 'var(--brain-text)', fill: 'var(--brain-fill)' },
  // Legacy accent names map onto the new teams
  look: { line: 'var(--robot)', deep: 'var(--robot-deep)', text: 'var(--robot-text)', fill: 'var(--robot-fill)' },
  agent: { line: 'var(--brain)', deep: 'var(--brain-deep)', text: 'var(--brain-text)', fill: 'var(--brain-fill)' },
};

// Floors are 0-indexed internally; people see 1-based floors (1 = lobby)
const floorLabel = (idx) => idx + 1;

// How many individual rider figures fit in the cab before we collapse to "+N"
const MAX_VISIBLE_RIDERS = 8;

// One waiting passenger: a little person with a destination flag
function WaitingPassenger({ p }) {
  return (
    <span
      className="flex items-center text-[15px] leading-none select-none"
      title={`${p.id} → floor ${floorLabel(p.target)}`}
    >
      <span>🧍</span>
      <span className="text-[9px] font-bold mono px-1 py-0.5 rounded-md bg-[var(--surface)] border border-[var(--border-ink)] text-[var(--ink-2)] -ml-0.5">
        →{floorLabel(p.target)}
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
    <div className="flex-1 flex bg-[var(--well)] border-2 border-[var(--line-soft)] rounded-2xl p-3 min-h-[420px] relative overflow-hidden">
      {/* Floor rows and waiting queues */}
      <div className="flex-1 flex flex-col justify-between">
        {floorIndices.map(fIdx => {
          const waitingQueue = state.floorQueues[fIdx] || [];

          return (
            <div
              key={fIdx}
              onClick={() => onFloorClick && onFloorClick(fIdx)}
              className={`flex justify-between items-center py-2 h-12 border-b-2 border-dashed border-[var(--line-soft)] last:border-b-0 px-2 rounded-xl transition-colors ${onFloorClick ? 'cursor-pointer hover:bg-[var(--surface)]' : ''}`}
            >
              <span
                className="text-[12px] font-extrabold w-7 h-7 rounded-lg flex items-center justify-center bg-[var(--surface)] border border-[var(--border-ink)] text-[var(--ink-2)] shrink-0"
                aria-label={t('floor.label', { n: floorLabel(fIdx) })}
              >
                {floorLabel(fIdx)}
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

      {/* Vertical tracks — one per car */}
      {carEntries.map(([carId, carState], idx) => {
        const carFloor = carState.floor || 0;
        const carBottomPercentage = (carFloor / Math.max(numFloors - 1, 1)) * 76;
        const doorsOpen = carState.doorState === 'OPEN';
        const riders = carState.onboardPassengers || [];
        const visibleRiders = riders.slice(0, MAX_VISIBLE_RIDERS);
        const hiddenCount = riders.length - visibleRiders.length;

        return (
          <div key={carId} className={`w-24 flex justify-center relative border-l-2 ${idx > 0 ? 'border-[var(--line-soft)]' : 'border-[var(--line)]'}`}>
            {/* Cable */}
            <div className="absolute top-0 bottom-0 w-1 rounded" style={{ background: tones.line, opacity: 0.3 }}></div>

            {/* The cab: big enough to show every rider as their own little person */}
            <div
              className="absolute w-[84px] min-h-[72px] rounded-2xl flex flex-col border-[3px] transition-all duration-300 ease-in-out overflow-hidden"
              style={{
                bottom: `${carBottomPercentage + 2}%`,
                borderColor: tones.deep,
                background: doorsOpen ? 'var(--surface)' : tones.fill,
                boxShadow: `0 4px 0 rgba(62,51,88,0.18)`,
              }}
              title={`${carId} — ${riders.length} riding, doors ${doorsOpen ? 'open' : 'closed'}`}
            >
              {/* Cab header: car id + headcount */}
              <div
                className="flex items-center justify-between px-1.5 pt-1 text-[10px] font-extrabold leading-none"
                style={{ color: tones.text }}
              >
                <span>{carId}</span>
                {riders.length > 0 && <span>×{riders.length}</span>}
              </div>

              {/* Riders: one figure per person on board */}
              <div className="flex-1 flex flex-wrap items-center justify-center content-center gap-x-0 gap-y-0.5 px-1 pb-2 min-h-[34px]">
                {riders.length === 0 ? (
                  <span className="text-[16px] leading-none select-none opacity-50">🛗</span>
                ) : (
                  <>
                    {visibleRiders.map(p => (
                      <span
                        key={p.id}
                        className="text-[15px] leading-none select-none"
                        title={`${p.id} → floor ${floorLabel(p.target)}`}
                      >
                        🧍
                      </span>
                    ))}
                    {hiddenCount > 0 && (
                      <span className="text-[10px] font-extrabold leading-none" style={{ color: tones.text }}>
                        +{hiddenCount}
                      </span>
                    )}
                  </>
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
  );
}
