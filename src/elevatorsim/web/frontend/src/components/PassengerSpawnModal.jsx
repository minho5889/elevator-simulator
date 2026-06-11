// src/elevatorsim/web/frontend/src/components/PassengerSpawnModal.jsx
import React from 'react';
import { useLang } from '../i18n.jsx';

export default function PassengerSpawnModal({ activeSpawnFloor, floors, spawnPassenger, onClose }) {
  const { t } = useLang();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[rgba(62,51,88,0.45)]" onClick={onClose}>
      <div
        className="bounce-in w-full max-w-sm p-6 bg-[var(--surface)] border-[3px] border-[var(--border-ink)] rounded-3xl relative"
        style={{ boxShadow: '0 8px 0 rgba(62,51,88,0.15)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-xl m-0 mb-1 text-[var(--ink)] flex items-center gap-2">
          <span>🧍</span>
          {t('spawn.title')}
        </h3>
        <p className="text-xs font-semibold text-[var(--ink-2)] mb-4">
          {t('spawn.desc', { floor: activeSpawnFloor + 1 })}
        </p>

        <div className="grid grid-cols-5 gap-2.5 my-4">
          {Array.from({ length: floors }, (_, idx) => {
            if (idx === activeSpawnFloor) return null;
            return (
              <button
                key={idx}
                onClick={() => spawnPassenger(activeSpawnFloor, idx)}
                className="btn-chunky h-11 font-extrabold text-base text-[var(--ink)] hover:bg-[var(--sun)] hover:border-[var(--sun-deep)]"
              >
                {idx + 1}F
              </button>
            );
          })}
        </div>

        <div className="flex justify-end mt-4">
          <button
            onClick={onClose}
            className="btn-chunky px-4 py-2 text-xs font-extrabold text-[var(--ink-2)]"
          >
            {t('spawn.cancel')}
          </button>
        </div>
      </div>
    </div>
  );
}
