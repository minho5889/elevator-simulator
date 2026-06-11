// src/elevatorsim/web/frontend/src/components/SettingsModal.jsx
import React from 'react';
import { Settings, Key } from 'lucide-react';

const inputClass = "w-full bg-[var(--well)] border border-[var(--line)] rounded-lg px-3 py-2 text-sm outline-none text-[var(--ink)] placeholder-[var(--ink-3)] focus:border-[var(--agent)]";

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
  setCarSpeeds
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[rgba(42,39,35,0.45)]">
      <div className="w-full max-w-md p-6 bg-[var(--surface)] border border-[var(--line)] rounded-xl relative max-h-[85vh] overflow-y-auto">
        <h2 className="text-base font-medium text-[var(--ink)] mb-1 flex items-center gap-2">
          <Settings className="text-[var(--ink-3)] w-4 h-4" />
          Settings
        </h2>
        <p className="text-xs text-[var(--ink-2)] leading-relaxed mb-4">
          Pick an LLM provider for the agentic dispatcher. Keys and endpoints are stored locally in your browser.
        </p>

        {/* LLM provider selector */}
        <div className="flex flex-col gap-1.5 mb-4">
          <label className="text-xs text-[var(--ink-2)] font-medium">
            LLM provider
          </label>
          <select
            value={llmProvider}
            onChange={(e) => setLlmProvider(e.target.value)}
            className={inputClass}
          >
            <option value="gemini">Google Gemini (cloud)</option>
            <option value="gemma">Ollama / Gemma 4 (local)</option>
            <option value="mock">Mock (offline LOOK)</option>
          </select>
        </div>

        {llmProvider === 'gemini' && (
          <div className="flex flex-col gap-1.5 mb-4">
            <label className="text-xs text-[var(--ink-2)] font-medium flex items-center gap-1">
              <Key className="w-3.5 h-3.5" />
              Gemini API key
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
              <label className="text-xs text-[var(--ink-2)] font-medium">
                Ollama host URL
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
              <label className="text-xs text-[var(--ink-2)] font-medium">
                Ollama model id
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
          <div className="p-3 bg-[var(--well)] border border-[var(--line-soft)] rounded-lg text-xs text-[var(--ink-2)] mb-4 leading-relaxed">
            Mock runs the deterministic LOOK heuristic offline, exercising the agentic pipeline without any LLM calls.
          </div>
        )}

        {/* Car speeds */}
        {carSpeeds && carSpeeds.length > 0 && (
          <div className="border-t border-[var(--line-soft)] pt-4 mt-4">
            <label className="text-xs text-[var(--ink-2)] font-medium mb-2 block">
              Car speeds (floors per tick)
            </label>
            <div className="flex flex-col gap-3">
              {carSpeeds.map((speed, idx) => (
                <div key={idx} className="flex items-center gap-3">
                  <span className="text-xs font-mono text-[var(--ink-2)] w-12">
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
                    className="flex-1 accent-[#2A2723] h-1.5 cursor-pointer"
                  />
                  <span className="text-xs font-mono font-medium text-[var(--ink)] w-8 text-right">
                    {speed.toFixed(1)}x
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {keyCheckResult && llmProvider === 'gemini' && (
          <div className={`p-3 rounded-lg text-xs mb-4 mt-4 border ${keyCheckResult.success ? 'bg-[var(--look-fill)] border-[var(--look)] text-[var(--look-text)]' : 'bg-[var(--error-fill)] border-[#F09595] text-[var(--error-text)]'}`}>
          {keyCheckResult.message}
          </div>
        )}

        <div className="flex gap-3 justify-end mt-6">
          {llmProvider === 'gemini' && (
            <button
              onClick={handleTestKey}
              disabled={keyChecking}
              className="px-3 py-1.5 bg-transparent hover:bg-[var(--well)] border border-[var(--line)] text-[var(--ink-2)] font-medium rounded-lg text-xs transition disabled:opacity-50"
            >
              {keyChecking ? 'Testing…' : 'Test connection'}
            </button>
          )}
          <button
            onClick={handleSaveSettings}
            className="px-4 py-1.5 bg-[var(--ink)] hover:bg-[#3C3833] text-[var(--paper)] font-medium rounded-lg text-xs transition"
          >
            Save and close
          </button>
        </div>
      </div>
    </div>
  );
}
