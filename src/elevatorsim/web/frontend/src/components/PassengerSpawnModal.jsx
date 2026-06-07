// src/elevatorsim/web/frontend/src/components/PassengerSpawnModal.jsx
import React from 'react';
import { UserCheck } from 'lucide-react';

export default function PassengerSpawnModal({ activeSpawnFloor, floors, spawnPassenger, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
      <div className="glass-panel w-full max-w-sm p-6 bg-slate-900 border border-slate-700/60 rounded-xl relative">
        <h3 className="text-lg font-bold text-white mb-2 flex items-center gap-2">
          <UserCheck className="text-cyan-400 w-5 h-5" />
          Spawn Passenger
        </h3>
        <p className="text-xs text-slate-400 mb-4">
          Select destination floor for passenger starting at <strong>Floor {activeSpawnFloor}</strong>.
        </p>
        
        <div className="grid grid-cols-5 gap-2.5 my-4">
          {Array.from({ length: floors }, (_, idx) => {
            if (idx === activeSpawnFloor) return null;
            return (
              <button
                key={idx}
                onClick={() => spawnPassenger(activeSpawnFloor, idx)}
                className="h-10 rounded-lg bg-slate-800 hover:bg-cyan-500 hover:text-slate-950 font-mono font-bold text-sm text-slate-300 border border-slate-700 hover:border-transparent transition"
              >
                {idx}
              </button>
            );
          })}
        </div>
        
        <div className="flex justify-end mt-4">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs font-semibold text-slate-300 hover:text-white transition"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
