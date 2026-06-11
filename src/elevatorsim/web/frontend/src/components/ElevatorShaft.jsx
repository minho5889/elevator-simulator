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

// One waiting passenger: a little person with a destination flag
function WaitingPassenger({ p }) {
  return (
    <span
      className="flex items-center text-[13px] leading-none select-none"
      title={`${p.id} → floor ${p.target}`}
    >
      <span>🧍</span>
      <span className="text-[9px] font-bold mono px-1 py-0.5 rounded-md bg-[var(--surface)] border border-[var(--border-ink)] text-[var(--ink-2)] -ml-0.5">
        →{p.target}
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
    <div className="flex-1 flex bg-[var(--well)] border-2 border-[var(--line-soft)] rounded-2xl p-3 min-h-[360px] relative overflow-hidden">
      {/* Floor rows and waiting queues */}
      <div className="flex-1 flex flex-col justify-between">
        {floorIndices.map(fIdx => {
          const waitingQueue = state.floorQueues[fIdx] || [];

          return (
            <div
              key={fIdx}
              onClick={() => onFloorClick && onFloorClick(fIdx)}
              className={`flex justify-between items-center py-2 h-10 border-b-2 border-dashed border-[var(--line-soft)] last:border-b-0 px-2 rounded-xl transition-colors ${onFloorClick ? 'cursor-pointer hover:bg-[var(--surface)]' : ''}`}
            >
              <span
                className="text-[11px] font-extrabold w-6 h-6 rounded-lg flex items-center justify-center bg-[var(--surface)] border border-[var(--border-ink)] text-[var(--ink-2)]"
                aria-label={t('floor.label', { n: fIdx })}
              >
                {fIdx}
              </span>

              <div className="flex gap-1 max-w-[160px] overflow-hidden justify-end items-center">
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
        const carBottomPercentage = (carFloor / Math.max(numFloors - 1, 1)) * 82;
        const doorsOpen = carState.doorState === 'OPEN';
        const riders = (carState.onboardPassengers || []).length;

        return (
          <div key={carId} className={`w-14 flex justify-center relative border-l-2 ${idx > 0 ? 'border-[var(--line-soft)]' : 'border-[var(--line)]'}`}>
            {/* Cable */}
            <div className="absolute top-0 bottom-0 w-0.5 rounded" style={{ background: tones.line, opacity: 0.3 }}></div>

            <div
              className="absolute w-12 h-11 rounded-xl flex flex-col justify-center items-center border-2 transition-all duration-300 ease-in-out"
              style={{
                bottom: `${carBottomPercentage + 2}%`,
                borderColor: tones.deep,
                background: doorsOpen ? 'var(--surface)' : tones.fill,
                boxShadow: `0 3px 0 ${doorsOpen ? 'rgba(62,51,88,0.12)' : 'rgba(62,51,88,0.18)'}`,
              }}
              title={`${carId} — ${riders} riding, doors ${doorsOpen ? 'open' : 'closed'}`}
            >
              <span className="text-[12px] leading-none select-none">
                {riders > 0 ? '🧑‍🤝‍🧑' : '🛗'}
              </span>
              <span className="text-[10px] font-extrabold leading-tight" style={{ color: tones.text }}>
                {riders > 0 ? `×${riders}` : carId}
              </span>

              {/* Doors */}
              <div className="w-full flex justify-center gap-1 absolute -bottom-0.5 px-1.5">
                <span
                  className="h-1 rounded-sm transition-all duration-300"
                  style={{ background: tones.deep, width: doorsOpen ? '4px' : '12px', opacity: doorsOpen ? 1 : 0.5 }}
                ></span>
                <span
                  className="h-1 rounded-sm transition-all duration-300"
                  style={{ background: tones.deep, width: doorsOpen ? '4px' : '12px', opacity: doorsOpen ? 1 : 0.5 }}
                ></span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
