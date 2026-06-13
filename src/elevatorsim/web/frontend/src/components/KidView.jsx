// src/components/KidView.jsx
// The kid-first experience: pick a day, then watch two friendly racers with big
// shafts, a simple scoreboard, and two big buttons. No jargon, no tick counter.
import { useArena } from '../state/arenaStore.jsx';
import { useLang } from '../i18n.jsx';
import { snapshotAt } from '../hooks/useSnapshots.js';
import { kidRacer, kidTone } from '../config/kid.js';
import ElevatorShaft from './ElevatorShaft.jsx';
import DayPicker from './DayPicker.jsx';
import KidScoreboard from './KidScoreboard.jsx';

function KidRacer({ contestant }) {
  const { state } = useArena();
  const { t } = useLang();
  const { config, playback } = state;
  const r = kidRacer(contestant.id);
  const tone = kidTone(contestant.id);
  const snapshot = snapshotAt(contestant, playback.currentTick);
  return (
    <div className="panel overflow-hidden flex flex-col" style={{ borderColor: tone.base, boxShadow: `0 6px 0 ${tone.deep}55` }}>
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--line-soft)]">
        <span className="text-4xl select-none">{r.emoji}</span>
        <div>
          <div className="font-display font-extrabold text-2xl leading-tight" style={{ color: tone.text }}>
            {r.i18nKey ? t(`${r.i18nKey}.name`) : contestant.id}
          </div>
          <div className="text-sm text-[var(--ink-3)]">{r.i18nKey ? t(`${r.i18nKey}.blurb`) : ''}</div>
        </div>
      </div>
      <ElevatorShaft snapshot={snapshot} numFloors={config.num_floors} numCars={config.num_cars}
        toneSlot={r.toneSlot} maxWeightKg={config.max_weight_kg} />
    </div>
  );
}

export default function KidView({ onDay }) {
  const { state, dispatch } = useArena();
  const { t } = useLang();
  const { contestants, playback } = state;

  if (!contestants.length) return <DayPicker onDay={onDay} />;

  const atEnd = playback.maxTick > 0 && playback.currentTick >= playback.maxTick;
  const playLabel = playback.isPlaying
    ? `⏸ ${t('kid.pause')}`
    : atEnd ? `🔁 ${t('kid.watchAgain')}` : `▶ ${t('kid.play')}`;
  const onPlay = () => {
    if (playback.isPlaying) { dispatch({ type: 'PAUSE' }); return; }
    if (atEnd) dispatch({ type: 'SET_TICK', tick: 0 });
    dispatch({ type: 'PLAY' });
  };

  return (
    <div className="flex flex-col gap-4">
      <KidScoreboard />
      <div className="flex items-center justify-center gap-3 flex-wrap">
        <button className="btn-sun text-xl font-extrabold px-7 py-3 rounded-2xl" onClick={onPlay}>{playLabel}</button>
        <button className="btn-chunky text-lg font-extrabold px-5 py-3 rounded-2xl"
          onClick={() => dispatch({ type: 'RESET' })}>🏙️ {t('kid.pickAnother')}</button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {contestants.map((c) => <KidRacer key={c.id} contestant={c} />)}
      </div>
    </div>
  );
}
