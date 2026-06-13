// src/components/ArenaSetup.jsx
// Build the matchup: pick K contestants from the ladder, a traffic regime, and
// the building scale, then start the race.
import { useState, useEffect } from 'react';
import { useArena } from '../state/arenaStore.jsx';
import { useLang } from '../i18n.jsx';
import { LADDER, REGIMES, DEFAULT_MATCHUP } from '../config/dispatchers.js';
import { getTone } from '../config/accents.js';
import { BACKEND_URL } from '../config/api.js';

const MAX_CONTESTANTS = 8;

function Slider({ label, value, min, max, step = 1, onChange, suffix = '' }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] font-extrabold text-[var(--ink-2)] flex justify-between">
        <span>{label}</span><span className="mono text-[var(--ink-3)]">{value}{suffix}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))} className="accent-[var(--sun-deep)]" />
    </label>
  );
}

export default function ArenaSetup({ onRace, onPreset, racing }) {
  const { state, dispatch } = useArena();
  const { t } = useLang();
  const { config } = state;
  const [selected, setSelected] = useState(DEFAULT_MATCHUP);
  const [presets, setPresets] = useState([]);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/arena/presets`)
      .then((r) => r.json())
      .then((data) => Array.isArray(data) && setPresets(data))
      .catch(() => {});
  }, []);

  const toggle = (key) => {
    setSelected((s) => s.includes(key)
      ? s.filter((k) => k !== key)
      : (s.length >= MAX_CONTESTANTS ? s : [...s, key]));
  };
  const setCfg = (patch) => dispatch({ type: 'SET_CONFIG', config: patch });

  return (
    <div className="panel p-4 flex flex-col gap-4">
      {/* Quick races (baked presets) */}
      {presets.length > 0 && onPreset && (
        <div>
          <div className="text-xs font-extrabold text-[var(--ink-2)] mb-2 uppercase tracking-wide">
            {t('arena.presets')} <span className="text-[var(--ink-3)] font-bold normal-case lowercase">— {t('arena.presets.hint')}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {presets.map((p) => (
              <button key={p.key} onClick={() => onPreset(p.key)}
                className="btn-chunky text-[13px] font-bold px-3 py-1.5 rounded-full flex items-center gap-1.5">
                <span>{p.emoji}</span>{p.title}
                <span className="text-[10px] mono text-[var(--ink-3)]">{p.num_floors}🏢·{p.num_cars}🛗</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Contestants */}
      <div>
        <div className="text-xs font-extrabold text-[var(--ink-2)] mb-2 uppercase tracking-wide">
          {t('arena.contestants')} <span className="text-[var(--ink-3)] font-bold normal-case">({selected.length}/{MAX_CONTESTANTS})</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {LADDER.map((d) => {
            const on = selected.includes(d.key);
            const tone = getTone(d.toneSlot);
            return (
              <button key={d.key} onClick={() => toggle(d.key)} title={t(`dispatcher.${d.key}.blurb`)}
                className="text-[13px] font-bold px-2.5 py-1.5 rounded-full border-2 transition-all flex items-center gap-1.5"
                style={on
                  ? { background: tone.fill, color: tone.text, borderColor: tone.base, boxShadow: `0 2px 0 ${tone.deep}55` }
                  : { background: 'var(--surface)', color: 'var(--ink-3)', borderColor: 'var(--border-ink)' }}>
                <span>{d.emoji}</span>{t(`dispatcher.${d.key}.name`)}
                {d.model && <span className="text-[9px] mono opacity-70">{t('arena.model')}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {/* Regime */}
      <div>
        <div className="text-xs font-extrabold text-[var(--ink-2)] mb-2 uppercase tracking-wide">{t('arena.traffic')}</div>
        <div className="flex flex-wrap gap-2">
          {REGIMES.map((r) => {
            const on = config.regime === r.key;
            return (
              <button key={r.key} onClick={() => setCfg({ regime: r.key })} title={t(`regime.${r.key}.blurb`)}
                className={`text-[13px] font-bold px-2.5 py-1.5 rounded-full border-2 flex items-center gap-1.5 ${on ? 'btn-sun' : ''}`}
                style={on ? {} : { background: 'var(--surface)', color: 'var(--ink-3)', borderColor: 'var(--border-ink)' }}>
                <span>{r.emoji}</span>{t(`regime.${r.key}.name`)}
              </button>
            );
          })}
        </div>
      </div>

      {/* Scale */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-3">
        <Slider label={t('arena.scale.floors')} value={config.num_floors} min={5} max={60} onChange={(v) => setCfg({ num_floors: v })} />
        <Slider label={t('arena.scale.cars')} value={config.num_cars} min={1} max={12} onChange={(v) => setCfg({ num_cars: v })} />
        <Slider label={t('arena.scale.capacity')} value={config.capacity} min={4} max={48} onChange={(v) => setCfg({ capacity: v })} />
        <Slider label={t('arena.scale.arrival')} value={config.arrival_rate} min={0.2} max={2.5} step={0.1} onChange={(v) => setCfg({ arrival_rate: v })} />
        <Slider label={t('arena.scale.weight')} value={config.max_weight_kg} min={300} max={3000} step={100} onChange={(v) => setCfg({ max_weight_kg: v })} suffix="kg" />
        <Slider label={t('arena.scale.seed')} value={config.seed} min={1} max={9999} onChange={(v) => setCfg({ seed: v })} />
      </div>

      <button className="btn-sun py-3 text-lg font-extrabold rounded-2xl disabled:opacity-50"
        disabled={racing || selected.length === 0}
        onClick={() => onRace(selected.map((key) => ({ id: key, dispatcher: key })))}>
        {racing ? `🏁 ${t('arena.racing')}` : `🏁 ${t('arena.race')}`}
      </button>
    </div>
  );
}
