// src/elevatorsim/web/frontend/src/components/ConsoleTerminal.jsx
import React from 'react';

export default function ConsoleTerminal({ logRef, logs, title }) {
  return (
    <div className="mt-4 bg-slate-950 border border-slate-900 rounded-lg p-3 flex flex-col gap-1.5">
      <div className="text-[10px] text-slate-400 uppercase tracking-widest font-bold border-b border-slate-900 pb-1.5 flex justify-between items-center">
        <span>{title}</span>
        <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full pulse-glow"></span>
      </div>
      <div 
        ref={logRef}
        className="h-28 overflow-y-auto text-[10px] font-mono text-slate-400 flex flex-col gap-1.5 scroll-smooth"
      >
        {logs.length === 0 ? (
          <span className="text-slate-400 italic">No events occurred yet. Play or step to start.</span>
        ) : (
          logs.map((log, idx) => {
            // Highlight agent reasoning logs or specific tags
            const isAgentDecision = log.includes('Decided by Gemini');
            const isBoarded = log.includes('BOARDED');
            const isDeboarded = log.includes('DEBOARDED');
            
            let colorClass = 'text-slate-400';
            if (isAgentDecision) colorClass = 'text-purple-400 font-semibold';
            else if (isBoarded) colorClass = 'text-cyan-400';
            else if (isDeboarded) colorClass = 'text-emerald-400';

            return (
              <div key={idx} className={`${colorClass} leading-relaxed`}>
                {log}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
