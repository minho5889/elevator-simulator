// src/elevatorsim/web/frontend/src/components/ElevatorShaft.jsx
import React from 'react';

const TONES = {
  look: { line: 'var(--look)', text: 'var(--look-text)', fill: 'var(--look-fill)' },
  agent: { line: 'var(--agent)', text: 'var(--agent-text)', fill: 'var(--agent-fill)' },
};

export default function ElevatorShaft({ state, numFloors, numCars = 1, accent = 'look', onFloorClick }) {
  const tones = TONES[accent] || TONES.look;
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
    <div className="flex-1 flex bg-[var(--well)] border border-[var(--line-soft)] rounded-lg p-3 min-h-[360px] relative">
      {/* Floor rows and waiting queues */}
      <div className="flex-1 flex flex-col justify-between">
        {floorIndices.map(fIdx => {
          const waitingQueue = state.floorQueues[fIdx] || [];

          return (
            <div
              key={fIdx}
              onClick={() => onFloorClick && onFloorClick(fIdx)}
              className={`flex justify-between items-center py-2 h-10 border-b border-dashed border-[var(--line-soft)] last:border-b-0 px-2 rounded transition-colors ${onFloorClick ? 'cursor-pointer hover:bg-[var(--surface)]' : ''}`}
            >
              <span className="text-[11px] font-mono text-[var(--ink-3)] w-5 text-center" aria-label={`Floor ${fIdx}`}>
                {fIdx}
              </span>

              <div className="flex gap-1.5 max-w-[150px] overflow-hidden justify-end items-center">
                {waitingQueue.map(p => (
                  <span
                    key={p.id}
                    className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--surface)] border border-[var(--line)] text-[var(--ink-2)]"
                    title={`Passenger ${p.id} heading to floor ${p.target}`}
                  >
                    {p.id}→{p.target}
                  </span>
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

        return (
          <div key={carId} className={`w-14 flex justify-center relative border-l ${idx > 0 ? 'border-[var(--line-soft)]' : 'border-[var(--line)]'}`}>
            <div
              className="absolute w-11 h-10 rounded-lg flex flex-col justify-center items-center border transition-all duration-300 ease-in-out"
              style={{
                bottom: `${carBottomPercentage + 2}%`,
                borderColor: tones.line,
                background: tones.fill,
              }}
              title={`Car ${carId} — doors ${doorsOpen ? 'open' : 'closed'}`}
            >
              <span className="text-[11px] font-mono font-semibold" style={{ color: tones.text }}>
                {carId}·{(carState.onboardPassengers || []).length}
              </span>

              <div className="w-full flex justify-center gap-1 absolute bottom-1 px-1.5">
                <span className="w-2 h-0.5 rounded-sm" style={{ background: doorsOpen ? tones.line : '#C9C5BA' }}></span>
                <span className="w-2 h-0.5 rounded-sm" style={{ background: doorsOpen ? tones.line : '#C9C5BA' }}></span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
