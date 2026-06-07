// src/elevatorsim/web/frontend/src/components/WaitTimeChart.jsx
import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer
} from 'recharts';

// Chart accent colors (mirror the --look-cyan / --agent-violet CSS variables)
const LOOK_COLOR = '#06b6d4';
const AGENT_COLOR = '#a78bfa';

// Dark, glass-styled tooltip for the wait-time comparison chart
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-slate-900/95 border border-slate-700 rounded-lg px-3 py-2 shadow-xl backdrop-blur-sm">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1.5">Tick {label}</div>
      <div className="flex flex-col gap-1">
        {payload.map((entry) => (
          <div key={entry.dataKey} className="flex items-center gap-2 text-[11px] font-mono" style={{ color: entry.color }}>
            <span className="w-2.5 h-0.5 inline-block rounded" style={{ background: entry.color }} />
            <span className="font-semibold">{entry.dataKey === 'look' ? 'LOOK' : 'Gemini'}</span>
            <span className="ml-auto tabular-nums">{entry.value ?? '—'} ticks</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Recharts average wait-time comparison chart (replaces the hand-rolled SVG).
// Animation is disabled so the line tracks the real-time playback without re-tweening each tick.
export default function WaitTimeChart({ data, currentTick, maxWait, hasAgentic }) {
  const axisTick = { fill: '#64748b', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' };
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: -16, bottom: 0 }}>
        <defs>
          <linearGradient id="lookFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={LOOK_COLOR} stopOpacity={0.35} />
            <stop offset="100%" stopColor={LOOK_COLOR} stopOpacity={0} />
          </linearGradient>
          <linearGradient id="agentFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={AGENT_COLOR} stopOpacity={0.3} />
            <stop offset="100%" stopColor={AGENT_COLOR} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
        <XAxis
          dataKey="tick" type="number" domain={[0, 'dataMax']}
          tick={axisTick} tickLine={false} axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
          tickMargin={6}
        />
        <YAxis
          width={42} domain={[0, Math.ceil(maxWait)]} allowDecimals={false}
          tick={axisTick} tickLine={false} axisLine={false}
        />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.18)', strokeDasharray: '3 3' }} />
        <ReferenceLine x={currentTick} stroke="#e2e8f0" strokeOpacity={0.55} strokeDasharray="2 3" />
        <Area
          type="monotone" dataKey="look" name="LOOK Heuristic"
          stroke={LOOK_COLOR} strokeWidth={2} fill="url(#lookFill)"
          dot={false} activeDot={{ r: 4, strokeWidth: 0 }} isAnimationActive={false}
        />
        {hasAgentic && (
          <Area
            type="monotone" dataKey="gemini" name="Gemini Agent"
            stroke={AGENT_COLOR} strokeWidth={2} strokeDasharray="4 3" fill="url(#agentFill)"
            dot={false} activeDot={{ r: 4, strokeWidth: 0 }} connectNulls isAnimationActive={false}
          />
        )}
      </AreaChart>
    </ResponsiveContainer>
  );
}
