// src/components/DayPicker.jsx
// The kid entry point: big friendly day cards. Tap one to watch the race.
import { useState, useEffect } from 'react';
import { useLang } from '../i18n.jsx';
import { BACKEND_URL } from '../config/api.js';

export default function DayPicker({ onDay }) {
  const { t } = useLang();
  const [days, setDays] = useState([]);

  useEffect(() => {
    fetch(`${BACKEND_URL}/api/arena/presets`)
      .then((r) => r.json())
      .then((d) => Array.isArray(d) && setDays(d))
      .catch(() => {});
  }, []);

  return (
    <div className="flex flex-col items-center gap-5 py-6">
      <h2 className="font-display font-extrabold text-4xl text-[var(--ink)]">{t('kid.pickDay')}</h2>
      <p className="text-lg text-[var(--ink-3)]">{t('kid.pickDay.hint')}</p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 w-full max-w-4xl">
        {days.map((d) => (
          <button key={d.key} onClick={() => onDay(d.key)}
            className="panel p-6 flex flex-col items-center gap-3 transition-transform hover:-translate-y-1 active:translate-y-0.5 focus-visible:-translate-y-1"
            style={{ minHeight: 210 }}>
            <span className="text-7xl select-none">{d.emoji}</span>
            <span className="font-display font-extrabold text-2xl text-[var(--ink)]">{t(`day.${d.key}.name`)}</span>
            <span className="text-base text-[var(--ink-3)] text-center leading-snug">{t(`day.${d.key}.desc`)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
