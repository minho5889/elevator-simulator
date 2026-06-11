// src/elevatorsim/web/frontend/src/components/ConsoleTerminal.jsx
import React from 'react';

// Event logs are debugging artifacts, not headline content: a quiet
// collapsed drawer keeps them one click away without competing with the shafts.
export default function ConsoleTerminal({ logRef, logs, title }) {
  return (
    <details className="mt-3 group">
      <summary className="text-xs text-[var(--ink-3)] cursor-pointer select-none py-1 list-none flex items-center gap-1.5 hover:text-[var(--ink-2)] transition-colors">
        <span className="inline-block transition-transform group-open:rotate-90 text-[10px]">▸</span>
        {title} <span className="font-mono">({logs.length})</span>
      </summary>
      <div
        ref={logRef}
        className="mt-1.5 h-28 overflow-y-auto text-[11px] font-mono text-[var(--ink-2)] flex flex-col gap-1 scroll-smooth bg-[var(--well)] border border-[var(--line-soft)] rounded-lg p-3"
      >
        {logs.length === 0 ? (
          <span className="text-[var(--ink-3)] italic">No events yet — press play or step.</span>
        ) : (
          logs.map((log, idx) => {
            const isAgentDecision = log.includes('Decided by Gemini');
            const isBoarded = log.includes('BOARDED');
            const isDeboarded = log.includes('DEBOARDED');

            let colorClass = 'text-[var(--ink-2)]';
            if (isAgentDecision) colorClass = 'text-[var(--agent-text)] font-medium';
            else if (isDeboarded) colorClass = 'text-[var(--look-text)]';
            else if (isBoarded) colorClass = 'text-[var(--ink)]';

            return (
              <div key={idx} className={`${colorClass} leading-relaxed`}>
                {log}
              </div>
            );
          })
        )}
      </div>
    </details>
  );
}
