// src/elevatorsim/web/frontend/src/components/ElevatorShaft.jsx
// A storybook building on a sunny sky, now scaled from a 5-floor cottage to a
// 60-floor tower. The sky / roof / grass frame is sacred at every density; only
// the *interior* densifies: emoji riders -> count chips, full windows -> floor
// lines, plus zone-band overlays and per-car weight gauges from the snapshot.
import { useMemo } from 'react';
import { useLang } from '../i18n.jsx';
import { getTone, zoneWash } from '../config/accents.js';

const floorName = (idx) => `${idx + 1}F`;
const MAX_VISIBLE_RIDERS = 8;

const PEOPLE = ['🧒', '👧', '👦', '👩', '👨', '👵', '👴', '👩‍🦰', '👨‍🦱', '👱‍♀️', '🧑‍🎓', '👷'];
const personEmoji = (id) => {
  const n = parseInt(String(id).replace(/\D/g, ''), 10);
  return PEOPLE[(Number.isNaN(n) ? 0 : n) % PEOPLE.length];
};

// Density tiers from floor count. Detailed = the beloved cottage (byte-stable at
// floors<=14); compact = the tower (thin rows, count chips, prominent zones).
function densityTier(numFloors) {
  if (numFloors <= 14) return 'detailed';
  if (numFloors <= 32) return 'compact';
  return 'schematic';
}

function WaitingPassenger({ p }) {
  return (
    <span
      className="flex items-center text-[17px] leading-none select-none"
      title={`${p.id}${p.weight ? ` (${p.weight}kg)` : ''} → ${floorName(p.target)}`}
    >
      <span>{personEmoji(p.id)}</span>
      <span className="text-[9px] font-bold mono px-1 py-0.5 rounded-md bg-[var(--surface)] border border-[var(--border-ink)] text-[var(--ink-2)] -ml-0.5">
        →{floorName(p.target)}
      </span>
    </span>
  );
}

function Window() {
  return (
    <span className="inline-block w-4 h-5 rounded-[3px] border-2 border-[var(--building-deep)] bg-[#C8E6F8] relative pointer-events-none">
      <span className="absolute inset-x-0 top-1/2 h-[1.5px] bg-[var(--building-deep)] opacity-60"></span>
      <span className="absolute inset-y-0 left-1/2 w-[1.5px] bg-[var(--building-deep)] opacity-60"></span>
    </span>
  );
}

// A compact passenger cluster for dense floors: up to a couple avatars then a count.
function QueueChip({ queue, tone }) {
  if (!queue.length) return null;
  const head = queue.slice(0, 2);
  return (
    <span className="flex items-center gap-0.5 select-none" title={`${queue.length} waiting`}>
      {head.map((p) => <span key={p.id} className="text-[12px] leading-none">{personEmoji(p.id)}</span>)}
      {queue.length > 2 && (
        <span className="text-[9px] font-extrabold mono px-1 rounded-full"
          style={{ background: tone.fill, color: tone.text, border: `1px solid ${tone.deep}` }}>
          +{queue.length - 2}
        </span>
      )}
    </span>
  );
}

export default function ElevatorShaft({
  snapshot, numFloors, numCars = 1, toneSlot = 0, maxWeightKg = null, onFloorClick,
}) {
  const { t } = useLang();
  const tone = getTone(toneSlot);
  const tier = densityTier(numFloors);

  // Normalize the snapshot into the renderer's shape (tolerant of an empty tick).
  const { cars, queueAt, zones } = useMemo(() => {
    const carList = snapshot?.cars || [];
    const q = snapshot?.floor_queues || {};
    return {
      cars: carList,
      queueAt: (f) => q[String(f)] || [],
      zones: snapshot?.zones || null,
    };
  }, [snapshot]);

  const floorIndices = Array.from({ length: numFloors }, (_, i) => numFloors - 1 - i);
  const rowH = tier === 'detailed' ? 'h-12' : tier === 'compact' ? 'h-7' : 'h-[18px]';
  const detailed = tier === 'detailed';

  // Zone bands: car_id -> [lo, hi]; drawn as desaturated washes behind the floors.
  const bands = useMemo(() => {
    if (!zones) return [];
    return Object.entries(zones).map(([cid, range], i) => ({ cid, lo: range[0], hi: range[1], wash: zoneWash(i) }));
  }, [zones]);
  const floorTop = (f) => `${((numFloors - 1 - f) / Math.max(numFloors, 1)) * 100}%`;
  const bandHeight = `${(1 / Math.max(numFloors, 1)) * 100}%`;

  return (
    <div
      className="flex-1 relative rounded-2xl overflow-hidden flex flex-col min-h-[460px]"
      style={{ background: 'linear-gradient(180deg, #BFE3F7 0%, #DDF0FB 55%, #F2F6E9 100%)' }}
    >
      <span className="absolute top-2 left-3 text-2xl select-none floaty" aria-hidden="true">☀️</span>
      <span className="absolute top-5 right-6 text-xl select-none floaty" style={{ animationDelay: '1.2s' }} aria-hidden="true">☁️</span>

      <div className="relative z-10 flex-1 flex flex-col mx-6 mt-7">
        {/* Roof */}
        <div className="relative mx-1">
          <div className="absolute -top-5 right-10 w-1.5 h-5 rounded-t-full bg-[var(--building-deep)]">
            <span className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-[#FF6B6B]"></span>
          </div>
          <div className="absolute -top-3.5 left-7 w-8 h-3.5 rounded-t-lg bg-[var(--building-deep)]"></div>
          <div className="h-4 rounded-t-xl bg-[var(--building-deep)]"></div>
        </div>

        {/* Building body */}
        <div className="flex-1 flex bg-[var(--well)] border-x-[10px] border-[var(--building)] relative overflow-hidden">
          {/* Zone-band overlay (behind the floors) */}
          {bands.length > 0 && (
            <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
              {bands.map((b) => (
                <div key={b.cid} className="absolute left-0 right-0 flex items-start justify-start"
                  style={{ top: floorTop(b.hi), height: `calc(${bandHeight} * ${b.hi - b.lo + 1})`, background: b.wash, borderTop: '1px solid rgba(62,51,88,0.10)', borderBottom: '1px solid rgba(62,51,88,0.10)' }}>
                  <span className="text-[8px] font-extrabold mono m-0.5 px-1 rounded"
                    style={{ background: 'var(--surface)', color: 'var(--ink-2)', border: '1px solid var(--border-ink)' }}>
                    {b.cid}·{b.lo + 1}-{b.hi + 1}F
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Floors + waiting queues */}
          <div className="flex-1 flex flex-col justify-between relative z-[1]">
            {floorIndices.map((fIdx, rowIdx) => {
              const waitingQueue = queueAt(fIdx);
              const isLobby = fIdx === 0;
              return (
                <div
                  key={fIdx}
                  onClick={() => onFloorClick && onFloorClick(fIdx)}
                  className={`flex items-center gap-2 ${rowH} px-2 transition-colors border-b border-[var(--slab)] last:border-b-0 ${rowIdx % 2 === 0 ? 'bg-[rgba(255,255,255,0.30)]' : ''} ${onFloorClick ? 'cursor-pointer hover:bg-[var(--surface)]' : ''}`}
                >
                  {(detailed || fIdx % 5 === 0 || isLobby) && (
                    <span className="text-[10px] font-extrabold px-1 h-5 rounded-md flex items-center justify-center bg-[var(--building)] text-[#6B5836] shrink-0"
                      aria-label={t('floor.label', { n: fIdx + 1 })}>
                      {floorName(fIdx)}
                    </span>
                  )}

                  {detailed && (
                    <span className="flex gap-1.5 items-end self-end opacity-80 shrink-0" aria-hidden="true">
                      {isLobby ? (
                        <span className="inline-block w-6 h-8 rounded-t-lg bg-[var(--building-deep)] relative pointer-events-none">
                          <span className="absolute right-1 top-1/2 w-1 h-1 rounded-full bg-[#FFF6E5]"></span>
                        </span>
                      ) : (
                        <span className="flex gap-1.5 items-center self-center pb-1"><Window /><Window /></span>
                      )}
                    </span>
                  )}

                  <div className="flex-1 flex gap-1 flex-wrap overflow-hidden justify-end items-center max-h-full">
                    {detailed
                      ? waitingQueue.map((p) => <WaitingPassenger key={p.id} p={p} />)
                      : <QueueChip queue={waitingQueue} tone={tone} />}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Cabs — one shaft per car */}
          {cars.map((carState, idx) => {
            const carFloor = carState.floor || 0;
            const carBottomPercentage = (carFloor / Math.max(numFloors - 1, 1)) * 76;
            const doorsOpen = carState.door_state === 'OPEN';
            const riders = carState.onboard || [];
            const visibleRiders = riders.slice(0, MAX_VISIBLE_RIDERS);
            const hiddenCount = riders.length - visibleRiders.length;
            const loadKg = carState.weight_kg ?? riders.reduce((s, p) => s + (p.weight || 0), 0);
            const capWeight = maxWeightKg ?? carState.max_weight_kg;
            const isFull = capWeight != null && (carState.refused_recently || (capWeight - loadKg) < 30);
            const loadPct = capWeight ? Math.min((loadKg / capWeight) * 100, 100) : 0;
            const shaftW = detailed ? 'w-24' : 'w-14';
            const cabW = detailed ? 84 : 48;

            return (
              <div key={carState.car_id || idx}
                className={`${shaftW} flex justify-center relative border-l-[3px] ${idx > 0 ? 'border-dashed' : ''} z-[2]`}
                style={{ borderColor: 'var(--building)', background: 'rgba(0,0,0,0.03)' }}>
                <div className="absolute top-0 bottom-0 w-1 rounded" style={{ background: tone.base, opacity: 0.3 }}></div>

                <div
                  className="absolute rounded-xl flex flex-col border-[3px] transition-all duration-300 ease-in-out overflow-hidden"
                  style={{
                    width: `${cabW}px`, minHeight: detailed ? 64 : 40,
                    bottom: `${carBottomPercentage + 2}%`,
                    borderColor: tone.deep,
                    background: doorsOpen ? 'var(--surface)' : tone.fill,
                    boxShadow: '0 4px 0 rgba(62,51,88,0.18)',
                  }}
                  title={riders.length > 0
                    ? `${carState.car_id}: ${riders.length} riding, ${loadKg}kg${capWeight ? ` / ${capWeight}kg` : ''} — doors ${doorsOpen ? 'open' : 'closed'}`
                    : `${carState.car_id}: empty — doors ${doorsOpen ? 'open' : 'closed'}`}
                >
                  {riders.length > 0 && (
                    <span className="absolute top-0.5 right-1 text-[10px] font-extrabold leading-none" style={{ color: tone.text }}>×{riders.length}</span>
                  )}
                  {isFull && (
                    <span className="tb-refused absolute top-0.5 left-1 text-[9px] font-extrabold leading-none px-1 py-0.5 rounded bg-[#FF6B6B] text-white">{t('shaft.full')}</span>
                  )}

                  <div className="flex-1 flex flex-wrap items-center justify-center content-center gap-y-0.5 px-1 pt-2 pb-2.5 min-h-[28px]">
                    {detailed ? (
                      <>
                        {visibleRiders.map((p) => (
                          <span key={p.id} className="text-[16px] leading-none select-none"
                            title={`${p.id}${p.weight ? ` (${p.weight}kg)` : ''} → ${floorName(p.target)}`}>
                            {personEmoji(p.id)}
                          </span>
                        ))}
                        {hiddenCount > 0 && <span className="text-[10px] font-extrabold leading-none" style={{ color: tone.text }}>+{hiddenCount}</span>}
                      </>
                    ) : (
                      riders.length > 0 && <span className="text-[12px] font-extrabold leading-none" style={{ color: tone.text }}>👤{riders.length}</span>
                    )}
                  </div>

                  {capWeight != null && riders.length > 0 && (
                    <div className="mx-1.5 mb-2 h-1 rounded-full bg-[rgba(62,51,88,0.12)] overflow-hidden">
                      <div className={`h-full rounded-full transition-all duration-300 ${loadPct > 85 && !isFull ? 'tb-gauge-warn' : ''}`}
                        style={{ width: `${loadPct}%`, background: isFull ? '#FF6B6B' : tone.deep }}></div>
                    </div>
                  )}

                  <div className="w-full flex justify-center gap-1 absolute bottom-0.5 px-2">
                    {[0, 1].map((d) => (
                      <span key={d} className="h-1.5 rounded-sm transition-all duration-300"
                        style={{ background: tone.deep, width: doorsOpen ? '6px' : `${cabW / 3.5}px`, opacity: doorsOpen ? 1 : 0.5 }}></span>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="h-2 bg-[var(--building-deep)] mx-1"></div>
      </div>

      <div className="relative z-0 h-4 bg-[#8FD9A8]">
        <span className="absolute -top-5 left-1 text-2xl select-none" aria-hidden="true">🌳</span>
        <span className="absolute -top-3.5 right-2 text-base select-none" aria-hidden="true">🌷</span>
      </div>
    </div>
  );
}
