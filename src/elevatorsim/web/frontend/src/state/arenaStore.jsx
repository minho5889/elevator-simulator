// src/state/arenaStore.jsx
// One reducer + Context for the whole arena. Replaces App.jsx's ~25 useState
// blobs and the 2-team heuristicData/agenticData duo with a single keyed-by-
// contestant store. Per-tick derived render state (shaft geometry, chart points)
// is NOT stored here — components derive it with useMemo on the current tick.

import { createContext, useContext, useReducer } from 'react';
import { dispatcherMeta } from '../config/dispatchers.js';

const DEFAULT_CONFIG = {
  seed: 1000,
  num_floors: 24,
  num_cars: 6,
  capacity: 24,
  max_weight_kg: 1600,
  arrival_rate: 0.8,
  regime: 'up_peak',
  max_ticks: 400,
  min_epoch_ticks: 120,
};

const initialState = {
  config: DEFAULT_CONFIG,
  contestants: [],              // [{id,dispatcher,label,emoji,toneSlot,available,reason,snapshots,latestTick,error,metrics}]
  playback: { currentTick: 0, maxTick: 0, isPlaying: false, speed: 1, mode: 'idle' },
  status: { connected: false, regime: DEFAULT_CONFIG.regime, limits: { max_floors: 60, max_cars: 12, max_capacity: 64 } },
  ui: { settingsOpen: false, focusRegion: null, activeSpawnFloor: null },
};

function mergeContestant(entry) {
  const meta = dispatcherMeta(entry.dispatcher);
  return {
    id: entry.id,
    dispatcher: entry.dispatcher,
    label: entry.label || meta.label,
    emoji: meta.emoji,
    toneSlot: meta.toneSlot,
    available: entry.available !== false,
    reason: entry.unavailable_reason || null,
    snapshots: {},
    latestTick: -1,
    error: null,
    metrics: null,
  };
}

function reducer(state, action) {
  switch (action.type) {
    case 'SET_CATALOG':
      return { ...state, status: { ...state.status, limits: action.limits || state.status.limits } };

    case 'SET_CONFIG':
      return { ...state, config: { ...state.config, ...action.config } };

    case 'SET_CONNECTED':
      return { ...state, status: { ...state.status, connected: action.connected } };

    case 'INIT_ARENA': {
      const contestants = (action.contestants || []).map(mergeContestant);
      // Seed tick-0 snapshots if the init message carried them.
      if (action.states) {
        for (const snap of action.states) {
          const c = contestants.find((x) => x.id === snap.contestant_id);
          if (c) { c.snapshots = { 0: snap }; c.latestTick = 0; c.metrics = snap.metrics; }
        }
      }
      return {
        ...state,
        contestants,
        status: { ...state.status, regime: action.config?.regime ?? state.status.regime },
        // Auto-run on init: the playback driver starts stepping the live race.
        playback: { currentTick: 0, maxTick: 0, isPlaying: true, speed: state.playback.speed, mode: 'live' },
      };
    }

    case 'INGEST_ARENA_STATE': {
      const { tick, states, events, errors } = action.payload;
      const contestants = state.contestants.map((c) => {
        const snap = states?.find((s) => s.contestant_id === c.id);
        const next = { ...c };
        if (snap) {
          next.snapshots = { ...c.snapshots, [tick]: snap };
          next.latestTick = tick;
          next.metrics = snap.metrics;
        }
        if (errors && c.id in errors) next.error = errors[c.id];
        if (events && events[c.id]) next.lastEvents = events[c.id];
        return next;
      });
      const follow = state.playback.isPlaying || state.playback.currentTick === state.playback.maxTick;
      return {
        ...state,
        contestants,
        playback: {
          ...state.playback,
          maxTick: tick,
          currentTick: follow ? tick : state.playback.currentTick,
        },
      };
    }

    case 'SET_TICK':
      return { ...state, playback: { ...state.playback, currentTick: Math.max(0, Math.min(action.tick, state.playback.maxTick)) } };

    case 'PLAY':
      return { ...state, playback: { ...state.playback, isPlaying: true } };
    case 'PAUSE':
      return { ...state, playback: { ...state.playback, isPlaying: false } };
    case 'SET_SPEED':
      return { ...state, playback: { ...state.playback, speed: action.speed } };

    case 'CONTESTANT_ERROR': {
      const contestants = state.contestants.map((c) =>
        c.id === action.id ? { ...c, error: action.message } : c);
      return { ...state, contestants };
    }

    case 'SET_UI':
      return { ...state, ui: { ...state.ui, ...action.ui } };

    case 'RESET':
      return { ...state, contestants: [], playback: { ...initialState.playback, speed: state.playback.speed } };

    default:
      return state;
  }
}

const ArenaContext = createContext(null);

export function ArenaProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return <ArenaContext.Provider value={{ state, dispatch }}>{children}</ArenaContext.Provider>;
}

export function useArena() {
  const ctx = useContext(ArenaContext);
  if (!ctx) throw new Error('useArena must be used within <ArenaProvider>');
  return ctx;
}
