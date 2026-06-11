// src/elevatorsim/web/frontend/src/components/Scoreboard.jsx
// Kid-readable scoreboard: three plain-language stats, both teams side by
// side, the better side wears a little crown. The whole panel answers one
// question: "who is winning right now?"
import React from 'react';
import { useLang } from '../i18n.jsx';

const fmt = (v) => {
  if (typeof v !== 'number') return v;
  return Number.isInteger(v) ? v : v.toFixed(1);
};

function ScoreRow({ emoji, label, hint, robotVal, brainVal, unit, betterWhen, hasBrain }) {
  let robotWins = false;
  let brainWins = false;
  if (hasBrain && robotVal !== brainVal && betterWhen !== 'neutral') {
    brainWins = betterWhen === 'lower' ? brainVal < robotVal : brainVal > robotVal;
    robotWins = !brainWins;
  }

  const cell = (val, isWinner, tone) => (
    <div
      className={`flex-1 flex items-center justify-center gap-1.5 rounded-xl py-2 px-2 border-2 transition-colors ${
        isWinner
          ? tone === 'robot'
            ? 'bg-[var(--robot-fill)] border-[var(--robot)]'
            : 'bg-[var(--brain-fill)] border-[var(--brain)]'
          : 'bg-[var(--well)] border-transparent'
      }`}
    >
      {isWinner && <span className="text-sm leading-none">👑</span>}
      <span className={`text-lg font-extrabold ${tone === 'robot' ? 'text-[var(--robot-text)]' : 'text-[var(--brain-text)]'}`}>
        {val === null ? '—' : fmt(val)}
      </span>
      <span className="text-[10px] font-bold text-[var(--ink-3)]">{unit}</span>
    </div>
  );

  return (
    <div className="flex items-center gap-3">
      {cell(robotVal, robotWins, 'robot')}
      <div className="w-36 sm:w-44 shrink-0 text-center">
        <div className="text-sm font-extrabold text-[var(--ink)] leading-tight">
          <span className="mr-1">{emoji}</span>{label}
        </div>
        <div className="text-[10px] font-bold text-[var(--ink-3)]">{hint}</div>
      </div>
      {cell(hasBrain ? brainVal : null, brainWins, 'brain')}
    </div>
  );
}

export default function Scoreboard({
  hWait, aWait, hDelivered, aDelivered, hEnergy, aEnergy, hasBrain,
}) {
  const { t } = useLang();

  // The headline verdict rides on waiting time — the stat kids feel most
  let leadLabel = t('score.tied');
  let leadClass = 'bg-[var(--well)] text-[var(--ink-2)] border-[var(--border-ink)]';
  if (hasBrain && aWait !== hWait) {
    const brainLeads = aWait < hWait;
    leadLabel = t('score.leads', { name: brainLeads ? t('racer.brain.name') : t('racer.robot.name') });
    leadClass = brainLeads
      ? 'bg-[var(--brain-fill)] text-[var(--brain-text)] border-[var(--brain)]'
      : 'bg-[var(--robot-fill)] text-[var(--robot-text)] border-[var(--robot)]';
  }

  return (
    <div className="panel p-4 sm:p-5 flex flex-col gap-3" data-tour="scoreboard">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-lg m-0 flex items-center gap-2 text-[var(--ink)]">
          <span>🏆</span>{t('score.title')}
        </h3>
        <span className={`text-xs font-extrabold px-3 py-1 rounded-full border-2 ${leadClass}`}>
          {leadLabel}
        </span>
      </div>

      {/* Team headers */}
      <div className="flex items-center gap-3 text-[11px] font-extrabold text-[var(--ink-3)]">
        <div className="flex-1 text-center text-[var(--robot-text)]">🤖 {t('racer.robot.name')}</div>
        <div className="w-36 sm:w-44 shrink-0"></div>
        <div className="flex-1 text-center text-[var(--brain-text)]">🧠 {t('racer.brain.name')}</div>
      </div>

      <ScoreRow
        emoji="⏱️" label={t('score.wait')} hint={t('score.wait.hint')}
        robotVal={hWait} brainVal={aWait} unit={t('score.turns')}
        betterWhen="lower" hasBrain={hasBrain}
      />
      <ScoreRow
        emoji="🙋" label={t('score.delivered')} hint={t('score.delivered.hint')}
        robotVal={hDelivered} brainVal={aDelivered} unit={t('score.people')}
        betterWhen="higher" hasBrain={hasBrain}
      />
      <ScoreRow
        emoji="⚡" label={t('score.energy')} hint={t('score.energy.hint')}
        robotVal={hEnergy} brainVal={aEnergy} unit={t('score.kwh')}
        betterWhen="lower" hasBrain={hasBrain}
      />
    </div>
  );
}
