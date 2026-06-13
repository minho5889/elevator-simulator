// src/ArenaApp.jsx
// Two experiences sharing one engine:
//  • Kid mode (default): pick a day, watch two friendly racers, simple score.
//  • Grown-up mode: the full arena — any contestants, every slider, all metrics.
import { useArena } from './state/arenaStore.jsx';
import { useArenaSocket } from './hooks/useArenaSocket.js';
import { useLang } from './i18n.jsx';
import { BACKEND_URL } from './config/api.js';
import ArenaSetup from './components/ArenaSetup.jsx';
import ArenaGrid from './components/ArenaGrid.jsx';
import Leaderboard from './components/Leaderboard.jsx';
import PlaybackBar from './components/PlaybackBar.jsx';
import KidView from './components/KidView.jsx';

export default function ArenaApp() {
  const { state, dispatch } = useArena();
  const socket = useArenaSocket();
  const { t, lang, setLang } = useLang();
  const grownUp = state.ui.grownUp;

  const onRace = (specs) => {
    dispatch({ type: 'RESET' });
    socket.connect(specs);
    dispatch({ type: 'PLAY' });
  };

  const onPreset = async (key) => {
    socket.disconnect(); // a baked preset replays from cache, no live socket
    try {
      const r = await fetch(`${BACKEND_URL}/api/arena/presets/${key}`);
      if (!r.ok) return;
      dispatch({ type: 'LOAD_PRESET', preset: await r.json() });
    } catch {
      /* network error — leave the current state untouched */
    }
  };

  const toggleMode = () => {
    socket.disconnect();
    dispatch({ type: 'RESET' });
    dispatch({ type: 'SET_UI', ui: { grownUp: !grownUp } });
  };

  const hasRace = state.contestants.length > 0;

  return (
    <div className="min-h-screen w-full">
      <div className="max-w-[1500px] mx-auto px-4 py-6 flex flex-col gap-4">
        <header className="flex items-end justify-between flex-wrap gap-2">
          <div>
            <h1 className="font-display font-extrabold text-3xl sm:text-4xl text-[var(--ink)] leading-none">
              🛗 {t('arena.title')}
            </h1>
            <p className="text-sm text-[var(--ink-3)] mt-1">{t('arena.tagline')}</p>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-chunky text-xs font-extrabold px-3 py-1.5 rounded-xl" onClick={toggleMode}>
              {grownUp ? `🧒 ${t('kid.kidMode')}` : `🧑 ${t('kid.grownUp')}`}
            </button>
            <button className="btn-chunky text-xs font-extrabold px-2.5 py-1.5 rounded-xl"
              onClick={() => setLang(lang === 'en' ? 'ko' : 'en')} title="Language">
              {lang === 'en' ? '한국어' : 'EN'}
            </button>
            {grownUp && (
              <span className="text-xs mono font-bold px-2.5 py-1 rounded-full border-2 border-[var(--border-ink)]"
                style={{ background: socket.connected ? 'var(--robot-fill)' : 'var(--well)', color: 'var(--ink-2)' }}>
                {socket.connected ? `● ${t('arena.live')}` : `○ ${t('arena.idle')}`}
              </span>
            )}
          </div>
        </header>

        {grownUp ? (
          <>
            <ArenaSetup onRace={onRace} onPreset={onPreset} racing={false} />
            {hasRace && <PlaybackBar socket={socket} />}
            {hasRace && <Leaderboard />}
            <ArenaGrid />
          </>
        ) : (
          <KidView onDay={onPreset} />
        )}
      </div>
    </div>
  );
}
