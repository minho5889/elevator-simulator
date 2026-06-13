// src/components/PlaybackBar.jsx
// Transport controls for the race: play/pause, scrub the timeline, change speed,
// or step one tick. Drives the store; the socket hook does the live stepping.
import { useArena } from '../state/arenaStore.jsx';
import { useLang } from '../i18n.jsx';
import { REGIMES_BY_KEY } from '../config/dispatchers.js';

const SPEEDS = [0.5, 1, 2, 4];

export default function PlaybackBar({ socket }) {
  const { state, dispatch } = useArena();
  const { t } = useLang();
  const { playback, config, status } = state;
  const regime = REGIMES_BY_KEY[status.regime];
  const atEnd = playback.maxTick >= config.max_ticks && playback.currentTick >= playback.maxTick;

  return (
    <div className="panel p-2.5 flex items-center gap-3 flex-wrap">
      <span className="text-[13px] font-extrabold px-2.5 py-1 rounded-full text-[var(--sun-text)] flex items-center gap-1.5"
        style={{ background: '#FFF1CC' }}>
        {regime?.emoji} {t(`regime.${status.regime}.name`)}
      </span>

      <button className="btn-chunky w-9 h-9 rounded-xl flex items-center justify-center text-lg"
        title={t('arena.restart')} onClick={() => dispatch({ type: 'SET_TICK', tick: 0 })}>⏮</button>

      <button className="btn-sun w-11 h-9 rounded-xl flex items-center justify-center text-lg disabled:opacity-50"
        disabled={!status.connected || atEnd}
        onClick={() => (playback.isPlaying ? dispatch({ type: 'PAUSE' }) : dispatch({ type: 'PLAY' }))}>
        {playback.isPlaying ? '⏸' : '▶'}
      </button>

      <button className="btn-chunky w-9 h-9 rounded-xl flex items-center justify-center text-base disabled:opacity-40"
        title={t('arena.stepOne')} disabled={!status.connected || atEnd}
        onClick={() => {
          if (playback.currentTick < playback.maxTick) dispatch({ type: 'SET_TICK', tick: playback.currentTick + 1 });
          else socket.step();
        }}>⏭</button>

      <input type="range" min={0} max={Math.max(playback.maxTick, 1)} value={playback.currentTick}
        onChange={(e) => dispatch({ type: 'SET_TICK', tick: Number(e.target.value) })}
        className="flex-1 min-w-[120px] accent-[var(--sun-deep)]" />

      <span className="text-[12px] mono font-bold text-[var(--ink-2)] whitespace-nowrap">
        t {playback.currentTick}/{playback.maxTick}
      </span>

      <select value={playback.speed} onChange={(e) => dispatch({ type: 'SET_SPEED', speed: Number(e.target.value) })}
        className="text-[12px] font-bold rounded-lg border-2 border-[var(--border-ink)] bg-[var(--surface)] px-1.5 py-1">
        {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
      </select>
    </div>
  );
}
