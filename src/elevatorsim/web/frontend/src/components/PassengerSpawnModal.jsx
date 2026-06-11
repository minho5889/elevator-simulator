// src/elevatorsim/web/frontend/src/components/PassengerSpawnModal.jsx
import React from 'react';
import { UserCheck } from 'lucide-react';

export default function PassengerSpawnModal({ activeSpawnFloor, floors, spawnPassenger, onClose }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[rgba(42,39,35,0.45)]">
      <div className="w-full max-w-sm p-6 bg-[var(--surface)] border border-[var(--line)] rounded-xl relative">
        <h3 className="text-base font-medium text-[var(--ink)] mb-1 flex items-center gap-2">
          <UserCheck className="text-[var(--ink-3)] w-4 h-4" />
          Spawn passenger
        </h3>
        <p className="text-xs text-[var(--ink-2)] mb-4">
          Pick a destination for the passenger starting at floor {activeSpawnFloor}.
        </p>

        <div className="grid grid-cols-5 gap-2.5 my-4">
          {Array.from({ length: floors }, (_, idx) => {
            if (idx === activeSpawnFloor) return null;
            return (
              <button
                key={idx}
                onClick={() => spawnPassenger(activeSpawnFloor, idx)}
                className="h-10 rounded-lg bg-[var(--well)] hover:bg-[var(--ink)] hover:text-[var(--paper)] font-mono font-medium text-sm text-[var(--ink)] border border-[var(--line)] hover:border-transparent transition"
              >
                {idx}
              </button>
            );
          })}
        </div>

        <div className="flex justify-end mt-4">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-transparent hover:bg-[var(--well)] border border-[var(--line)] rounded-lg text-xs font-medium text-[var(--ink-2)] transition"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
