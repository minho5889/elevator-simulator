// src/components/Leaderboard.jsx
// Multi-contestant scoreboard: a metric × contestant matrix, crowning the best
// cell per row. Generalizes the 2-team Scoreboard to K. Reads live snapshot
// metrics straight from the store (no client computation).
import { useArena } from '../state/arenaStore.jsx';
import { useLang } from '../i18n.jsx';
import { METRICS } from '../config/dispatchers.js';
import { getTone } from '../config/accents.js';

function fmt(v, key) {
  if (v == null) return '—';
  if (key === 'completion') return `${Math.round(v * 100)}%`;
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

export default function Leaderboard() {
  const { state } = useArena();
  const { t } = useLang();
  const rows = state.contestants.filter((c) => c.available && c.metrics);
  if (rows.length < 2) return null;

  const bestByMetric = {};
  for (const m of METRICS) {
    const vals = rows.map((c) => c.metrics[m.key]).filter((v) => v != null);
    if (!vals.length) continue;
    bestByMetric[m.key] = m.betterWhen === 'max' ? Math.max(...vals) : Math.min(...vals);
  }

  return (
    <div className="panel p-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th className="text-left text-[11px] font-extrabold text-[var(--ink-3)] uppercase px-2 py-1">{t('arena.metricHead')}</th>
            {rows.map((c) => {
              const tone = getTone(c.toneSlot);
              return (
                <th key={c.id} className="px-2 py-1">
                  <span className="inline-flex items-center gap-1 font-display font-extrabold text-[13px]" style={{ color: tone.text }}>
                    {c.emoji}<span className="hidden sm:inline">{t(`dispatcher.${c.dispatcher}.name`)}</span>
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {METRICS.map((m) => (
            <tr key={m.key} className="border-t border-[var(--line-soft)]">
              <td className="px-2 py-1.5 text-[12px] font-bold text-[var(--ink-2)] whitespace-nowrap">{m.emoji} {t(`metric.${m.key}`)}</td>
              {rows.map((c) => {
                const v = c.metrics[m.key];
                const isBest = v != null && bestByMetric[m.key] != null && v === bestByMetric[m.key];
                const tone = getTone(c.toneSlot);
                return (
                  <td key={c.id} className="px-2 py-1.5 text-center mono font-bold"
                    style={isBest ? { background: tone.fill, color: tone.text, borderRadius: 8 } : { color: 'var(--ink-2)' }}>
                    {isBest && '👑 '}{fmt(v, m.key)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
