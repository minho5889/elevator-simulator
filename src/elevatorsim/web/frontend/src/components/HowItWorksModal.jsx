// src/elevatorsim/web/frontend/src/components/HowItWorksModal.jsx
// The "what is this and what should I expect" page, written for someone
// seeing the simulator for the first time. Six emoji-led story cards.
import React from 'react';
import { useLang } from '../i18n.jsx';

const SECTIONS = [
  { emoji: '🏢', titleKey: 'how.1.title', bodyKey: 'how.1.body', tone: 'sun' },
  { emoji: '🤖', titleKey: 'how.2.title', bodyKey: 'how.2.body', tone: 'robot' },
  { emoji: '🧠', titleKey: 'how.3.title', bodyKey: 'how.3.body', tone: 'brain' },
  { emoji: '🏆', titleKey: 'how.4.title', bodyKey: 'how.4.body', tone: 'sun' },
  { emoji: '🔮', titleKey: 'how.5.title', bodyKey: 'how.5.body', tone: 'sun' },
  { emoji: '🛠️', titleKey: 'how.6.title', bodyKey: 'how.6.body', tone: 'ink' },
];

const TONE_CLASSES = {
  sun: 'bg-[#FFF3D6] border-[var(--sun)]',
  robot: 'bg-[var(--robot-fill)] border-[var(--robot)]',
  brain: 'bg-[var(--brain-fill)] border-[var(--brain)]',
  ink: 'bg-[var(--well)] border-[var(--border-ink)]',
};

export default function HowItWorksModal({ onClose }) {
  const { t } = useLang();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[rgba(62,51,88,0.45)]" onClick={onClose}>
      <div
        className="bounce-in w-full max-w-2xl bg-[var(--surface)] border-[3px] border-[var(--border-ink)] rounded-3xl relative max-h-[88vh] flex flex-col"
        style={{ boxShadow: '0 8px 0 rgba(62,51,88,0.15)' }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t('how.title')}
      >
        <div className="flex items-center justify-between p-6 pb-4">
          <h2 className="text-2xl m-0 text-[var(--ink)] flex items-center gap-2">
            <span>📖</span> {t('how.title')}
          </h2>
          <button
            onClick={onClose}
            aria-label={t('how.close')}
            className="btn-chunky w-9 h-9 flex items-center justify-center text-base font-extrabold text-[var(--ink-2)]"
          >
            ✕
          </button>
        </div>

        <div className="px-6 pb-4 overflow-y-auto flex flex-col gap-3">
          {SECTIONS.map(({ emoji, titleKey, bodyKey, tone }) => (
            <div key={titleKey} className={`flex gap-4 p-4 rounded-2xl border-2 ${TONE_CLASSES[tone]}`}>
              <div className="text-3xl select-none shrink-0" aria-hidden="true">{emoji}</div>
              <div>
                <h3 className="text-base m-0 mb-1 text-[var(--ink)]">{t(titleKey)}</h3>
                <p className="text-sm font-semibold text-[var(--ink-2)] m-0 leading-relaxed">{t(bodyKey)}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="p-6 pt-3 flex justify-end">
          <button onClick={onClose} className="btn-sun px-6 py-2.5 text-base font-extrabold">
            {t('how.close')}
          </button>
        </div>
      </div>
    </div>
  );
}
