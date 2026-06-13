// src/components/ContestantPanel.jsx
// One contestant lane: identity header (+ live structural mode/hold badge) over
// its adaptive ElevatorShaft. Greys out gracefully when a model is unavailable.
import { useArena } from '../state/arenaStore.jsx';
import { snapshotAt } from '../hooks/useSnapshots.js';
import { getTone } from '../config/accents.js';
import ElevatorShaft from './ElevatorShaft.jsx';

const MODE_LABEL = { conventional: 'Collective', dd_delayed: 'Destination', zoned: 'Zoned' };

export default function ContestantPanel({ contestant }) {
  const { state } = useArena();
  const { config, playback } = state;
  const tone = getTone(contestant.toneSlot);
  const snapshot = snapshotAt(contestant, playback.currentTick);
  const structural = snapshot?.structural;
  const m = contestant.metrics;

  return (
    <div className="panel overflow-hidden flex flex-col" style={{ borderColor: tone.base, boxShadow: `0 5px 0 ${tone.deep}55` }}>
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[var(--line-soft)]">
        <span className="text-xl select-none">{contestant.emoji}</span>
        <div className="min-w-0 flex-1">
          <div className="font-display font-extrabold text-[15px] leading-tight truncate" style={{ color: tone.text }}>
            {contestant.label}
          </div>
          {m && (
            <div className="text-[11px] mono text-[var(--ink-3)] truncate">
              wait {m.awt ?? '—'} · done {Math.round((m.completion || 0) * 100)}%{m.refusals ? ` · ${m.refusals}🚫` : ''}
            </div>
          )}
        </div>
        {structural && (structural.mode || structural.hold) && (
          <div className="flex gap-1 shrink-0">
            <span key={structural.mode} className="tb-mode-flip text-[10px] font-extrabold mono px-1.5 py-0.5 rounded-lg"
              style={{ background: tone.fill, color: tone.text, border: `1.5px solid ${tone.deep}` }}>
              {MODE_LABEL[structural.mode] || structural.mode || '…'}
            </span>
            {structural.hold && structural.mode !== 'conventional' && (
              <span className="text-[10px] font-bold mono px-1.5 py-0.5 rounded-lg bg-[var(--well)] text-[var(--ink-2)] border border-[var(--border-ink)]">
                {structural.hold}
              </span>
            )}
          </div>
        )}
      </div>

      {contestant.available ? (
        <ElevatorShaft
          snapshot={snapshot}
          numFloors={config.num_floors}
          numCars={config.num_cars}
          toneSlot={contestant.toneSlot}
          maxWeightKg={config.max_weight_kg}
        />
      ) : (
        <div className="flex-1 min-h-[460px] flex flex-col items-center justify-center text-center p-6 gap-2">
          <span className="text-3xl">😴</span>
          <div className="font-display font-bold text-[var(--ink-2)]">Sat this one out</div>
          <div className="text-xs text-[var(--ink-3)] max-w-[260px]">{contestant.reason || 'Unavailable'}</div>
        </div>
      )}
      {contestant.error && (
        <div className="px-3 py-1.5 text-[11px] mono text-[var(--error-text)] bg-[var(--error-fill)] border-t border-[var(--border-ink)]">
          ⚠ {contestant.error}
        </div>
      )}
    </div>
  );
}
