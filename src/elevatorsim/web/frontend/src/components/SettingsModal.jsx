// src/elevatorsim/web/frontend/src/components/SettingsModal.jsx
import React from 'react';
import { Settings, Key } from 'lucide-react';

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
  setOllamaModelId
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
      <div className="glass-panel w-full max-w-md p-6 bg-slate-900 border border-slate-700/60 rounded-xl relative">
        <h2 className="text-xl font-bold text-white mb-2 flex items-center gap-2">
          <Settings className="text-cyan-400 w-5 h-5" />
          Settings & Configurations
        </h2>
        <p className="text-xs text-slate-400 leading-relaxed mb-4">
          Configure custom elevator simulations by toggling your LLM provider.
          API keys and endpoints are stored <strong>locally</strong> in your browser.
        </p>

        {/* LLM Provider Selector */}
        <div className="flex flex-col gap-2 mb-4">
          <label className="text-xs text-slate-300 font-semibold">
            LLM Provider
          </label>
          <select 
            value={llmProvider} 
            onChange={(e) => setLlmProvider(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm outline-none text-white focus:border-cyan-500"
          >
            <option value="gemini">Google Gemini (Cloud)</option>
            <option value="gemma">Ollama / Gemma 4 (Local)</option>
          </select>
        </div>

        {llmProvider === 'gemini' ? (
          <div className="flex flex-col gap-2 mb-4">
            <label className="text-xs text-slate-300 font-semibold flex items-center gap-1">
              <Key className="w-3.5 h-3.5" />
              GEMINI_API_KEY
            </label>
            <input 
              type="password" 
              placeholder="AIzaSy..."
              value={userApiKey} 
              onChange={(e) => setUserApiKey(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm outline-none text-white placeholder-slate-600 focus:border-cyan-500"
            />
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-2 mb-4">
              <label className="text-xs text-slate-300 font-semibold">
                Ollama Host URL
              </label>
              <input 
                type="text" 
                placeholder="http://localhost:11434"
                value={ollamaHost} 
                onChange={(e) => setOllamaHost(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm outline-none text-white placeholder-slate-600 focus:border-cyan-500"
              />
            </div>
            <div className="flex flex-col gap-2 mb-4">
              <label className="text-xs text-slate-300 font-semibold">
                Ollama Model ID
              </label>
              <input 
                type="text" 
                placeholder="gemma4:e4b"
                value={ollamaModelId} 
                onChange={(e) => setOllamaModelId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm outline-none text-white placeholder-slate-600 focus:border-cyan-500"
              />
            </div>
          </>
        )}

        {keyCheckResult && llmProvider === 'gemini' && (
          <div className={`p-3 rounded-lg text-xs mb-4 ${keyCheckResult.success ? 'bg-emerald-950/30 border border-emerald-500/30 text-emerald-400' : 'bg-red-950/30 border border-red-500/30 text-red-400'}`}>
            {keyCheckResult.message}
          </div>
        )}

        <div className="flex gap-3 justify-end mt-6">
          {llmProvider === 'gemini' && (
            <button 
              onClick={handleTestKey}
              disabled={keyChecking}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 font-semibold rounded-lg text-xs transition disabled:opacity-50"
            >
              {keyChecking ? 'Testing...' : 'Test Connection'}
            </button>
          )}
          <button 
            onClick={handleSaveSettings}
            className="px-4 py-1.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded-lg text-xs transition"
          >
            Save & Close
          </button>
        </div>
      </div>
    </div>
  );
}
