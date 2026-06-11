// src/elevatorsim/web/frontend/src/components/TourOverlay.jsx
// First-visit guided tour. Each step spotlights one element (via the
// .tour-highlight box-shadow trick) and floats a speech-bubble card next
// to it. Step 1 is a centered welcome with no target.
import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLang } from '../i18n.jsx';

const STEPS = [
  { target: null, titleKey: 'tour.1.title', bodyKey: 'tour.1.body' },
  { target: '[data-tour="scenarios"]', titleKey: 'tour.2.title', bodyKey: 'tour.2.body' },
  { target: '[data-tour="start"]', titleKey: 'tour.3.title', bodyKey: 'tour.3.body' },
  { target: '[data-tour="robot"]', titleKey: 'tour.4.title', bodyKey: 'tour.4.body' },
  { target: '[data-tour="brain"]', titleKey: 'tour.5.title', bodyKey: 'tour.5.body' },
  { target: '[data-tour="scoreboard"]', titleKey: 'tour.6.title', bodyKey: 'tour.6.body' },
];

export default function TourOverlay({ onFinish }) {
  const { t } = useLang();
  const [step, setStep] = useState(0);
  const [cardPos, setCardPos] = useState(null); // null = centered
  const highlightedRef = useRef(null);

  const clearHighlight = () => {
    if (highlightedRef.current) {
      highlightedRef.current.classList.remove('tour-highlight');
      highlightedRef.current = null;
    }
  };

  useLayoutEffect(() => {
    clearHighlight();
    const { target } = STEPS[step];
    if (!target) {
      setCardPos(null);
      return;
    }

    const el = document.querySelector(target);
    if (!el) {
      setCardPos(null);
      return;
    }

    el.classList.add('tour-highlight');
    highlightedRef.current = el;
    // Instant scroll: a smooth scroll would race the position measurement below
    el.scrollIntoView({ behavior: 'auto', block: 'center' });

    const id = requestAnimationFrame(() => {
      const r = el.getBoundingClientRect();
      const cardW = Math.min(360, window.innerWidth - 32);
      const below = r.bottom < window.innerHeight * 0.6;
      const top = below ? Math.min(r.bottom + 16, window.innerHeight - 220) : Math.max(r.top - 220, 16);
      const left = Math.min(Math.max(r.left + r.width / 2 - cardW / 2, 16), window.innerWidth - cardW - 16);
      setCardPos({ top, left, width: cardW });
    });

    return () => cancelAnimationFrame(id);
  }, [step]);

  useEffect(() => () => clearHighlight(), []);

  const finish = () => {
    clearHighlight();
    localStorage.setItem('tour_done', '1');
    onFinish();
  };

  const isLast = step === STEPS.length - 1;
  const { titleKey, bodyKey } = STEPS[step];

  const card = (
    <div
      className="bounce-in bg-[var(--surface)] border-[3px] border-[var(--sun)] rounded-3xl p-6 flex flex-col gap-3"
      style={{
        boxShadow: '0 8px 0 rgba(62,51,88,0.18)',
        ...(cardPos
          ? { position: 'fixed', top: cardPos.top, left: cardPos.left, width: cardPos.width, zIndex: 65 }
          : { maxWidth: 420, width: '100%' }),
      }}
      role="dialog"
      aria-label={t(titleKey)}
    >
      <h3 className="text-xl m-0 text-[var(--ink)]">{t(titleKey)}</h3>
      <p className="text-sm font-bold text-[var(--ink-2)] m-0 leading-relaxed">{t(bodyKey)}</p>

      <div className="flex items-center justify-between mt-1">
        <div className="flex gap-1.5" aria-hidden="true">
          {STEPS.map((_, i) => (
            <span
              key={i}
              className="w-2 h-2 rounded-full transition-colors"
              style={{ background: i === step ? 'var(--sun-deep)' : 'var(--line)' }}
            />
          ))}
        </div>
        <div className="flex gap-2">
          <button onClick={finish} className="px-3 py-1.5 text-xs font-extrabold text-[var(--ink-3)] bg-transparent border-0 cursor-pointer hover:text-[var(--ink-2)]">
            {t('tour.skip')}
          </button>
          {step > 0 && (
            <button onClick={() => setStep(step - 1)} className="btn-chunky px-3.5 py-1.5 text-xs font-extrabold text-[var(--ink-2)]">
              {t('tour.back')}
            </button>
          )}
          <button
            onClick={() => (isLast ? finish() : setStep(step + 1))}
            className="btn-sun px-4 py-1.5 text-sm font-extrabold"
          >
            {isLast ? t('tour.done') : t('tour.next')}
          </button>
        </div>
      </div>
    </div>
  );

  // Centered welcome step gets its own dim layer; spotlight steps rely on
  // the highlighted element's giant box-shadow to dim the page.
  if (!cardPos) {
    return (
      <div className="fixed inset-0 z-[64] flex items-center justify-center p-4 bg-[rgba(62,51,88,0.55)]">
        {card}
      </div>
    );
  }

  return card;
}
