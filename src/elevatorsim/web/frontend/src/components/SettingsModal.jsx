// src/elevatorsim/web/frontend/src/components/SettingsModal.jsx
import React from 'react';
import { Settings, Key } from 'lucide-react';
import { useLang } from '../i18n.jsx';

const inputClass = "w-full bg-[var(--well)] border-2 border-[var(--border-ink)] rounded-xl px-3 py-2 text-sm font-semibold outline-none text-[var(--ink)] placeholder-[var(--ink-3)] focus:border-[var(--brain)]";

export default function SettingsModal({
  userApiKey,
  setUserApiKey,
  keyChecking,
  keyCheckResult,
  handleTestKey,
  handleSaveSettings,
  llmProvider,
  setLlmProvider,
  ollamaHost,
  setOllamaHost,
  ollamaModelId,
  setOllamaModelId,
  carSpeeds = [1.0],
  setCarSpeeds,
  onClose,
}) {
  const { t } = useLang();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[rgba(62,51,88,0.45)]" onClick={onClose}>
      <div
        className="bounce-in w-full max-w-md p-6 bg-[var(--surface)] border-[3px] border-[var(--border-ink)] rounded-3xl relative max-h-[85vh] overflow-y-auto"
        style={{ boxShadow: '0 8px 0 rgba(62,51,88,0.15)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-xl m-0 mb-1 text-[var(--ink)] flex items-center gap-2">
          <Settings className="text-[var(--ink-3)] w-5 h-5" />
          {t('settings.title')}
        </h2>
        <p className="text-xs font-semibold text-[var(--ink-2)] leading-relaxed mb-4">
          {t('settings.desc')}
        </p>

        {/* LLM provider selector */}
        <div className="flex flex-col gap-1.5 mb-4">
          <label className="text-xs text-[var(--ink-2)] font-extrabold">
            {t('settings.provider')}
          </label>
          <select
            value={llmProvider}
            onChange={(e) => setLlmProvider(e.target.value)}
            className={inputClass}
          >
            <option value="gemini">{t('settings.provider.gemini')}</option>
            <option value="gemma">{t('settings.provider.gemma')}</option>
            <option value="mock">{t('settings.provider.mock')}</option>
          </select>
        </div>

        {llmProvider === 'gemini' && (
          <div className="flex flex-col gap-1.5 mb-4">
            <label className="text-xs text-[var(--ink-2)] font-extrabold flex items-center gap-1">
              <Key className="w-3.5 h-3.5" />
              {t('settings.key')}
            </label>
            <input
              type="password"
              placeholder="AIzaSy..."
              value={userApiKey}
              onChange={(e) => setUserApiKey(e.target.value)}
              className={inputClass}
            />
          </div>
        )}

        {llmProvider === 'gemma' && (
          <>
            <div className="flex flex-col gap-1.5 mb-4">
              <label className="text-xs text-[var(--ink-2)] font-extrabold">
                {t('settings.ollamaHost')}
              </label>
              <input
                type="text"
                placeholder="http://localhost:11434"
                value={ollamaHost}
                onChange={(e) => setOllamaHost(e.target.value)}
                className={inputClass}
              />
            </div>
            <div className="flex flex-col gap-1.5 mb-4">
              <label className="text-xs text-[var(--ink-2)] font-extrabold">
                {t('settings.ollamaModel')}
              </label>
              <input
                type="text"
                placeholder="gemma4:e4b"
                value={ollamaModelId}
                onChange={(e) => setOllamaModelId(e.target.value)}
                className={inputClass}
              />
            </div>
          </>
        )}

        {llmProvider === 'mock' && (
          <div className="p-3 bg-[var(--well)] border-2 border-[var(--line-soft)] rounded-xl text-xs font-semibold text-[var(--ink-2)] mb-4 leading-relaxed">
            {t('settings.mockNote')}
          </div>
        )}

        {/* Car speeds */}
        {carSpeeds && carSpeeds.length > 0 && (
          <div className="border-t-2 border-[var(--line-soft)] pt-4 mt-4">
            <label className="text-xs text-[var(--ink-2)] font-extrabold mb-2 block">
              {t('settings.carSpeeds')}
            </label>
            <div className="flex flex-col gap-3">
              {carSpeeds.map((speed, idx) => (
                <div key={idx} className="flex items-center gap-3">
                  <span className="text-xs mono font-bold text-[var(--ink-2)] w-12">
                    C{idx + 1}
                  </span>
                  <input
                    type="range"
                    min="0.5"
                    max="3.0"
                    step="0.5"
                    value={speed}
                    aria-label={`Speed of car C${idx + 1}`}
                    onChange={(e) => {
                      const nextSpeeds = [...carSpeeds];
                      nextSpeeds[idx] = parseFloat(e.target.value);
                      setCarSpeeds(nextSpeeds);
                    }}
                    className="flex-1 accent-[#F5A623] h-1.5 cursor-pointer"
                  />
                  <span className="text-xs mono font-bold text-[var(--ink)] w-8 text-right">
                    {speed.toFixed(1)}x
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {keyCheckResult && llmProvider === 'gemini' && (
          <div className={`p-3 rounded-xl text-xs font-bold mb-4 mt-4 border-2 ${keyCheckResult.success ? 'bg-[#E5F7EC] border-[var(--grass)] text-[var(--grass-text)]' : 'bg-[var(--error-fill)] border-[#F09595] text-[var(--error-text)]'}`}>
          {keyCheckResult.message}
          </div>
        )}

        <div className="flex gap-3 justify-end mt-6">
          {llmProvider === 'gemini' && (
            <button
              onClick={handleTestKey}
              disabled={keyChecking}
              className="btn-chunky px-3.5 py-2 text-xs font-extrabold text-[var(--ink-2)] disabled:opacity-50"
            >
              {keyChecking ? t('settings.testing') : t('settings.test')}
            </button>
          )}
          <button
            onClick={handleSaveSettings}
            className="btn-sun px-5 py-2 text-sm font-extrabold"
          >
            {t('settings.save')}
          </button>
        </div>
      </div>
    </div>
  );
}
