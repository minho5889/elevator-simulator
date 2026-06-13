// src/ArenaApp.jsx
// The skyscraper Arena: build a matchup of dispatcher contestants, race them up
// a tower under a chosen traffic regime, and watch the snapshot stream live.
import { useArena } from './state/arenaStore.jsx';
import { useArenaSocket } from './hooks/useArenaSocket.js';
import ArenaSetup from './components/ArenaSetup.jsx';
import ArenaGrid from './components/ArenaGrid.jsx';
import Leaderboard from './components/Leaderboard.jsx';
import PlaybackBar from './components/PlaybackBar.jsx';

export default function ArenaApp() {
  const { state, dispatch } = useArena();
  const socket = useArenaSocket();

  const onRace = (specs) => {
    dispatch({ type: 'RESET' });
    socket.connect(specs);
    dispatch({ type: 'PLAY' });
  };

  const hasRace = state.contestants.length > 0;

  return (
    <div className="min-h-screen w-full">
      <div className="max-w-[1500px] mx-auto px-4 py-6 flex flex-col gap-4">
        <header className="flex items-end justify-between flex-wrap gap-2">
          <div>
            <h1 className="font-display font-extrabold text-3xl sm:text-4xl text-[var(--ink)] leading-none">
              🛗 Elevator Arena
            </h1>
            <p className="text-sm text-[var(--ink-3)] mt-1">Race elevator brains up a skyscraper.</p>
          </div>
          <span className="text-xs mono font-bold px-2.5 py-1 rounded-full border-2 border-[var(--border-ink)]"
            style={{ background: socket.connected ? 'var(--robot-fill)' : 'var(--well)', color: 'var(--ink-2)' }}>
            {socket.connected ? '● live' : '○ idle'}
          </span>
        </header>

        <ArenaSetup onRace={onRace} racing={false} />
        {hasRace && <PlaybackBar socket={socket} />}
        {hasRace && <Leaderboard />}
        <ArenaGrid />
      </div>
    </div>
  );
}
