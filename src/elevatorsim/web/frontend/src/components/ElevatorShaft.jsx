// src/elevatorsim/web/frontend/src/components/ElevatorShaft.jsx
import React from 'react';

export default function ElevatorShaft({ state, numFloors, numCars = 1, accentColor, onFloorClick }) {
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
    <div className="flex-1 flex bg-slate-950/60 border border-[var(--border-color)] rounded-lg p-3 min-h-[360px] relative">
      {/* Floor boundaries and queue details */}
      <div className="flex-1 flex flex-col justify-between">
        {floorIndices.map(fIdx => {
          const waitingQueue = state.floorQueues[fIdx] || [];

          return (
            <div 
              key={fIdx} 
              onClick={() => onFloorClick && onFloorClick(fIdx)}
              className={`flex justify-between items-center py-2 h-10 border-b border-dashed border-slate-900 last:border-b-0 px-2 rounded transition-colors ${onFloorClick ? 'cursor-pointer hover:bg-slate-900/40' : ''}`}
            >
              <div className="flex items-center gap-1">
                <span className={`text-xs font-mono font-bold w-5 h-5 flex items-center justify-center rounded bg-slate-900 text-slate-500`}>
                  {fIdx}
                </span>
                <span className="text-[10px] text-slate-600 uppercase font-bold tracking-wider">Floor</span>
              </div>

              <div className="flex gap-1.5 max-w-[150px] overflow-hidden justify-end">
                {waitingQueue.map(p => (
                  <span 
                    key={p.id} 
                    className="text-[9px] font-mono px-1.5 py-0.5 rounded font-medium bg-slate-900 border border-slate-800 text-slate-400"
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

      {/* Vertical Tracks - one per car */}
      {carEntries.map(([carId, carState], idx) => {
        const carFloor = carState.floor || 0;
        const carBottomPercentage = (carFloor / Math.max(numFloors - 1, 1)) * 82;

        return (
          <div key={carId} className={`w-14 flex justify-center relative ${idx > 0 ? 'border-l border-slate-900/50' : 'border-l border-slate-900'}`}>
            <div 
              className="absolute w-11 h-10 rounded-lg flex flex-col justify-center items-center border transition-all duration-300 ease-in-out"
              style={{ 
                bottom: `${carBottomPercentage + 2}%`,
                borderColor: accentColor,
                background: `radial-gradient(ellipse at center, ${accentColor}12 0%, #1e293b 100%)`,
                boxShadow: `0 0 12px 0 ${accentColor}24`
              }}
            >
              <div className="flex w-full justify-between px-1 absolute top-0.5 text-[7px] text-slate-400 font-bold uppercase tracking-wide">
                <span>Car</span>
                <span style={{ color: accentColor }}>{carId}</span>
              </div>

              <span className="text-xs font-mono font-bold text-white mt-2">
                {(carState.onboardPassengers || []).length}
              </span>

              <div 
                className="w-full flex justify-between absolute bottom-0.5 px-1.5"
                style={{ animation: carState.doorState === 'OPEN' ? 'doorPulse 1.5s infinite' : 'none' }}
              >
                <span className={`w-1 h-2 rounded-sm ${carState.doorState === 'OPEN' ? 'bg-emerald-400' : 'bg-slate-700'}`}></span>
                <span className="text-[6px] font-bold text-slate-500 uppercase">{carState.doorState}</span>
                <span className={`w-1 h-2 rounded-sm ${carState.doorState === 'OPEN' ? 'bg-emerald-400' : 'bg-slate-700'}`}></span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
