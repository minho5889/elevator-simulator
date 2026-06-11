// src/elevatorsim/web/frontend/src/components/WaitTimeChart.jsx
import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer
} from 'recharts';

// Chart accent colors (mirror the --look / --agent CSS variables)
const LOOK_COLOR = '#6FA28D';
const AGENT_COLOR = '#D97757';

// Light tooltip matching the warm-paper surface system
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-[var(--surface)] border border-[var(--line)] rounded-lg px-3 py-2">
      <div className="text-[10px] text-[var(--ink-3)] mb-1.5">Tick {label}</div>
      <div className="flex flex-col gap-1">
        {payload.map((entry) => (
          <div key={entry.dataKey} className="flex items-center gap-2 text-[11px] font-mono" style={{ color: entry.dataKey === 'look' ? 'var(--look-text)' : 'var(--agent-text)' }}>
            <span className="w-2.5 h-0.5 inline-block rounded" style={{ background: entry.color }} />
            <span className="font-medium">{entry.dataKey === 'look' ? 'LOOK' : 'Gemini'}</span>
            <span className="ml-auto tabular-nums">{entry.value ?? '—'} ticks</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Recharts average wait-time comparison chart.
// Animation is disabled so the line tracks the real-time playback without re-tweening each tick.
export default function WaitTimeChart({ data, currentTick, maxWait, hasAgentic }) {
  const axisTick = { fill: '#68645C', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' };
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="lookFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={LOOK_COLOR} stopOpacity={0.18} />
            <stop offset="100%" stopColor={LOOK_COLOR} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="agentFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={AGENT_COLOR} stopOpacity={0.14} />
            <stop offset="100%" stopColor={AGENT_COLOR} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(42,39,35,0.07)" vertical={false} />
        <XAxis
          dataKey="tick" type="number" domain={[0, 'dataMax']}
          tick={axisTick} tickLine={false} axisLine={{ stroke: 'rgba(42,39,35,0.12)' }}
          tickMargin={6}
        />
        <YAxis
          width={42} domain={[0, Math.ceil(maxWait)]} allowDecimals={false}
          tick={axisTick} tickLine={false} axisLine={false}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'rgba(42,39,35,0.25)', strokeDasharray: '3 3' }} />
        <ReferenceLine x={currentTick} stroke="#7A766D" strokeOpacity={0.7} strokeDasharray="2 3" />
        <Area
          type="monotone" dataKey="look" name="LOOK heuristic"
          stroke={LOOK_COLOR} strokeWidth={2} fill="url(#lookFill)"
          dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false}
        />
        {hasAgentic && (
          <Area
            type="monotone" dataKey="gemini" name="Gemini agent"
            stroke={AGENT_COLOR} strokeWidth={2} strokeDasharray="4 3" fill="url(#agentFill)"
            dot={false} activeDot={{ r: 4, strokeWidth: 0 }} connectNulls isAnimationActive={false}
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  );
}
