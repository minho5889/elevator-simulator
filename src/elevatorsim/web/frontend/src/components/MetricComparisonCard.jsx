// src/elevatorsim/web/frontend/src/components/MetricComparisonCard.jsx
import React from 'react';

export default function MetricComparisonCard({ title, hVal, aVal, unit, icon }) {
  const isBetter = aVal !== null && aVal < hVal; // A lower wait time or moves is usually better
  
  return (
    <div className="bg-slate-950/40 border border-[var(--border-color)] rounded-xl p-3 flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)] font-medium">
        {icon}
        {title}
      </div>
      <div className="flex items-baseline justify-between mt-1">
        {/* LOOK Heuristic value */}
        <div className="flex flex-col">
          <span className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">LOOK</span>
          <span className="text-sm font-mono font-bold text-slate-300">{hVal} <span className="text-[10px] font-normal text-slate-500">{unit}</span></span>
        </div>

        {/* Gemini Agent value */}
        <div className="flex flex-col text-right">
          <span className="text-[9px] uppercase tracking-wider text-slate-500 font-bold">Gemini</span>
          {aVal === null ? (
            <span className="text-xs text-slate-600 font-semibold">N/A</span>
          ) : (
            <span className={`text-sm font-mono font-bold ${isBetter ? 'text-emerald-400' : aVal > hVal ? 'text-slate-400' : 'text-slate-300'}`}>
              {aVal} <span className="text-[10px] font-normal text-slate-500">{unit}</span>
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
