// src/components/KidScoreboard.jsx
// Two big friendly numbers per racer — People delivered (more is better) and
// Waiting time (shorter is better) — with a crown for the winner at the end.
import { useArena } from '../state/arenaStore.jsx';
import { useLang } from '../i18n.jsx';
import { snapshotAt } from '../hooks/useSnapshots.js';
import { kidRacer, kidTone } from '../config/kid.js';

export default function KidScoreboard() {
  const { state } = useArena();
  const { t } = useLang();
  const { contestants, playback } = state;
  if (contestants.length < 2) return null;

  const rows = contestants.map((c) => {
    const snap = snapshotAt(c, playback.currentTick);
    const m = snap?.metrics || c.metrics || {};
    return { id: c.id, wait: m.awt, delivered: m.delivered ?? 0 };
  });

  const atEnd = playback.maxTick > 0 && playback.currentTick >= playback.maxTick;
  let winner = null;
  if (atEnd) {
    const sorted = [...rows].sort((a, b) => (b.delivered - a.delivered) || ((a.wait ?? 1e9) - (b.wait ?? 1e9)));
    if (sorted[0].delivered !== sorted[1].delivered || sorted[0].wait !== sorted[1].wait) winner = sorted[0].id;
  }
  const name = (id) => (kidRacer(id).i18nKey ? t(`${kidRacer(id).i18nKey}.name`) : id);

  return (
    <div className="grid grid-cols-2 gap-4">
      {rows.map((r) => {
        const tone = kidTone(r.id);
        const isWin = winner === r.id;
        return (
          <div key={r.id} className="panel p-4 flex flex-col items-center gap-2"
            style={{ borderColor: tone.base, boxShadow: `0 5px 0 ${tone.deep}55`, background: isWin ? tone.fill : 'var(--surface)' }}>
            <div className="flex items-center gap-2 font-display font-extrabold text-2xl" style={{ color: tone.text }}>
              <span className="text-3xl select-none">{kidRacer(r.id).emoji}</span>{name(r.id)}{isWin && ' 🏆'}
            </div>
            <div className="flex gap-8 mt-1">
              <div className="text-center">
                <div className="text-4xl font-extrabold mono" style={{ color: tone.text }}>{r.delivered}</div>
                <div className="text-sm font-bold text-[var(--ink-2)]">{t('kid.score.delivered')}</div>
                <div className="text-xs text-[var(--ink-3)]">⬆ {t('kid.score.deliveredHint')}</div>
              </div>
              <div className="text-center">
                <div className="text-4xl font-extrabold mono" style={{ color: tone.text }}>{r.wait ?? '—'}</div>
                <div className="text-sm font-bold text-[var(--ink-2)]">{t('kid.score.wait')}</div>
                <div className="text-xs text-[var(--ink-3)]">⬇ {t('kid.score.waitHint')}</div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
