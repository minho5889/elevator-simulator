// src/elevatorsim/web/frontend/src/components/MetricComparisonCard.jsx
import React from 'react';

const fmt = (v) => {
  if (typeof v !== 'number') return v;
  return Number.isInteger(v) ? v : v.toFixed(1);
};

// Delta-first stat cell: the dashboard's whole question is "is the agent
// better than LOOK?", so the agent value leads and the delta is the verdict.
// betterWhen: 'lower' (wait, moves, energy), 'higher' (deliveries), 'neutral' (spawns).
export default function MetricComparisonCard({ title, hVal, aVal, unit, icon, betterWhen = 'lower' }) {
  const hasAgent = aVal !== null && aVal !== undefined;
  const big = hasAgent ? aVal : hVal;

  let deltaLabel = null;
  let deltaClass = 'text-[var(--ink-3)]';
  if (hasAgent) {
    if (aVal === hVal) {
      deltaLabel = 'even';
    } else if (hVal > 0) {
      const pct = Math.round(((aVal - hVal) / hVal) * 100);
      deltaLabel = `${pct > 0 ? '+' : '−'}${Math.abs(pct)}% vs LOOK`;
    } else {
      deltaLabel = `${aVal > hVal ? '+' : '−'}${fmt(Math.abs(aVal - hVal))} vs LOOK`;
    }
    if (betterWhen !== 'neutral' && aVal !== hVal) {
      const agentBetter = betterWhen === 'lower' ? aVal < hVal : aVal > hVal;
      deltaClass = agentBetter ? 'text-[var(--look-text)]' : 'text-[var(--agent-text)]';
    }
  }

  return (
    <div className="bg-[var(--surface)] p-4 flex flex-col gap-1">
      <div className="flex items-center gap-1.5 text-xs text-[var(--ink-3)]">
        {icon}
        {title}
      </div>
      <div className="text-xl font-mono font-medium text-[var(--ink)]">
        {fmt(big)} <span className="text-[11px] font-normal text-[var(--ink-3)]">{unit}</span>
      </div>
      <div className="text-xs">
        {hasAgent ? (
          <span className={deltaClass}>{deltaLabel}</span>
        ) : (
          <span className="text-[var(--ink-3)]">LOOK baseline</span>
        )}
      </div>
    </div>
  );
}
