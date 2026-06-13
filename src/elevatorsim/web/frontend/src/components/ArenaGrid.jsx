// src/components/ArenaGrid.jsx
// Responsive grid of contestant lanes: 1-up on mobile, 2-up default, 3-up for
// 3 contestants, 4-up beyond. Each lane sizes its own shaft to the column width.
import { useArena } from '../state/arenaStore.jsx';
import { useLang } from '../i18n.jsx';
import ContestantPanel from './ContestantPanel.jsx';

function colsFor(n) {
  if (n <= 1) return 'grid-cols-1';
  if (n === 2) return 'grid-cols-1 md:grid-cols-2';
  if (n === 3) return 'grid-cols-1 md:grid-cols-3';
  return 'grid-cols-1 sm:grid-cols-2 xl:grid-cols-4';
}

export default function ArenaGrid() {
  const { state } = useArena();
  const { t } = useLang();
  const { contestants } = state;
  if (!contestants.length) {
    return (
      <div className="panel p-10 text-center text-[var(--ink-3)]">
        <div className="text-4xl mb-2">🏙️</div>
        <div className="font-display font-bold text-[var(--ink-2)]">{t('arena.empty.title')}</div>
        <div className="text-sm mt-1">{t('arena.empty.sub')}</div>
      </div>
    );
  }
  return (
    <div className={`grid gap-4 ${colsFor(contestants.length)}`}>
      {contestants.map((c) => <ContestantPanel key={c.id} contestant={c} />)}
    </div>
  );
}
