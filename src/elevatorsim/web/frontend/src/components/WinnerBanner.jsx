// src/elevatorsim/web/frontend/src/components/WinnerBanner.jsx
// End-of-race celebration: confetti rain + a big friendly verdict card.
import React, { useMemo } from 'react';
import { useLang } from '../i18n.jsx';

const CONFETTI_COLORS = ['#4FA8E8', '#F66FB0', '#FFC23E', '#3BBE6E', '#B28BF5'];

function ConfettiRain({ count = 60 }) {
  const pieces = useMemo(() =>
    Array.from({ length: count }, (_, i) => ({
      left: Math.random() * 100,
      delay: Math.random() * 1.2,
      duration: 2.2 + Math.random() * 1.8,
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      tilt: Math.random() * 360,
    })), [count]);

  return (
    <>
      {pieces.map((p, i) => (
        <span
          key={i}
          className="confetti-piece"
          style={{
            left: `${p.left}vw`,
            background: p.color,
            transform: `rotate(${p.tilt}deg)`,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
          }}
        />
      ))}
    </>
  );
}

export default function WinnerBanner({ winner, pct, onRaceAgain, onClose }) {
  const { t } = useLang();

  const isTie = winner === 'tie';
  const emoji = isTie ? '🤝' : winner === 'brain' ? '🧠' : '🤖';
  const title = isTie ? t('winner.tie') : winner === 'brain' ? t('winner.brain') : t('winner.robot');
  const sub = isTie || !pct ? t('winner.waitTie') : t('winner.waitLess', { pct });

  const toneClass = isTie
    ? 'border-[var(--border-ink)]'
    : winner === 'brain'
      ? 'border-[var(--brain)]'
      : 'border-[var(--robot)]';

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-[rgba(62,51,88,0.45)]" onClick={onClose}>
      {!isTie && <ConfettiRain />}
      <div
        className={`bounce-in w-full max-w-md p-8 bg-[var(--surface)] border-[3px] ${toneClass} rounded-3xl text-center relative`}
        style={{ boxShadow: '0 8px 0 rgba(62,51,88,0.15)' }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={title}
      >
        <div className="text-6xl mb-2 floaty select-none">{isTie ? '🤝' : '🏆'}</div>
        <h2 className="text-3xl m-0 text-[var(--ink)] flex items-center justify-center gap-2">
          <span>{emoji}</span> {title}
        </h2>
        <p className="text-sm font-bold text-[var(--ink-2)] mt-2 mb-6">{sub}</p>

        <div className="flex gap-3 justify-center flex-wrap">
          <button onClick={onRaceAgain} className="btn-sun px-6 py-2.5 text-base font-extrabold">
            🔁 {t('winner.again')}
          </button>
          <button onClick={onClose} className="btn-chunky px-5 py-2.5 text-sm font-extrabold text-[var(--ink-2)]">
            {t('winner.tryAnother')}
          </button>
        </div>
      </div>
    </div>
  );
}
