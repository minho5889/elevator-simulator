// src/config/accents.js
// Contestant identity palette. Slots 0 and 1 ARE the existing robot (blue) and
// brain (pink) duo, so a 2-contestant race is byte-identical to today. The ramp
// is hand-tuned for AA contrast on the cream/well surfaces and spaced for
// color-blind separability (blue / amber / magenta / teal axes, no red-green
// adjacency for meaning). Mirrored as --c0..--c10 CSS variables in index.css.

export const TONES = [
  { base: '#4FA8E8', deep: '#2F86CC', text: '#195E96', fill: '#DDF0FF' }, // 0 robot blue (look)
  { base: '#F66FB0', deep: '#E04695', text: '#AD1F72', fill: '#FFE4F1' }, // 1 brain pink (structural)
  { base: '#3BBE6E', deep: '#28A057', text: '#1E7A43', fill: '#DBF6E5' }, // 2 grass green (eta)
  { base: '#B28BF5', deep: '#9165E8', text: '#6B41C4', fill: '#ECE2FF' }, // 3 grape (agentic/gemini)
  { base: '#FF9F45', deep: '#E7811F', text: '#9C5408', fill: '#FFE9D2' }, // 4 tangerine (fcfs)
  { base: '#2DC4C4', deep: '#179E9E', text: '#0E7A7A', fill: '#D4F5F5' }, // 5 teal (nearest)
  { base: '#E86A6A', deep: '#CF4A4A', text: '#9E2B2B', fill: '#FCE0E0' }, // 6 coral (look_park)
  { base: '#7E8CE8', deep: '#5666D4', text: '#3B49B0', fill: '#E2E6FF' }, // 7 periwinkle (dd_delayed)
  { base: '#C9A227', deep: '#A88615', text: '#7A6005', fill: '#F7EDC8' }, // 8 mustard (dd_immediate)
  { base: '#6FB23B', deep: '#56962A', text: '#3F6E1B', fill: '#E6F4D6' }, // 9 olive (shuttle)
  { base: '#D46FC4', deep: '#B84BA6', text: '#8A2A7C', fill: '#F8E0F4' }, // 10 orchid (zoned)
];

/** Tone quadruple for a slot (clamps into range). */
export function getTone(slot) {
  return TONES[((slot % TONES.length) + TONES.length) % TONES.length];
}

/** Zone-band washes — desaturated warm fields, deliberately NOT contestant
 *  colors, so a band never reads as a team. Cycled per car index. */
export const ZONE_WASHES = [
  'rgba(231,215,184,0.55)', 'rgba(201,224,196,0.50)', 'rgba(196,219,231,0.50)',
  'rgba(231,210,196,0.50)', 'rgba(214,205,231,0.50)', 'rgba(231,225,196,0.50)',
];

export function zoneWash(carIndex) {
  return ZONE_WASHES[((carIndex % ZONE_WASHES.length) + ZONE_WASHES.length) % ZONE_WASHES.length];
}
