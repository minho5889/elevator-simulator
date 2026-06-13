// src/config/kid.js
// Kid-mode racer identities, keyed by the preset contestant id (robot / brainy).
// Two friendly styles — not "smart vs dumb": zippy Robot vs careful Brainy.

import { getTone } from './accents.js';

export const KID_RACERS = {
  robot: { i18nKey: 'kid.robot', emoji: '🤖', toneSlot: 0 },
  brainy: { i18nKey: 'kid.brainy', emoji: '🧠', toneSlot: 1 },
};

export function kidRacer(id) {
  return KID_RACERS[id] || { i18nKey: null, emoji: '🛗', toneSlot: 0 };
}

export function kidTone(id) {
  return getTone(kidRacer(id).toneSlot);
}
