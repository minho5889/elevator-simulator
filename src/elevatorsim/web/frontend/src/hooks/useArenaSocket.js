// src/hooks/useArenaSocket.js
// The imperative WebSocket layer for an arena race, generalized to K contestants.
// Lifts the legacy 2-team WS code out of App.jsx and drives playback: replay
// cached ticks when scrubbed back, send live `step`s at the live edge.

import { useCallback, useEffect, useRef } from 'react';
import { useArena } from '../state/arenaStore.jsx';
import { wsUrl } from '../config/api.js';

export function useArenaSocket() {
  const { state, dispatch } = useArena();
  const wsRef = useRef(null);
  const cfgRef = useRef(state.config);
  const pbRef = useRef(state.playback);
  // Mirror the latest config/playback into refs (in effects, not during render)
  // so the imperative WS callbacks + the playback interval avoid stale closures.
  useEffect(() => { cfgRef.current = state.config; }, [state.config]);
  useEffect(() => { pbRef.current = state.playback; }, [state.playback]);

  const step = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'step' }));
  }, []);

  const spawn = useCallback((source, target) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'spawn', source, target }));
    }
  }, []);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    dispatch({ type: 'SET_CONNECTED', connected: false });
  }, [dispatch]);

  /** Open a socket and start an arena race for the given contestant specs
   *  ([{id, dispatcher, ollama_model_id?}]). */
  const connect = useCallback((contestants) => {
    disconnect();
    const cfg = cfgRef.current;
    const ws = new WebSocket(wsUrl('/api/ws/simulate'));
    wsRef.current = ws;
    ws.onopen = () => {
      dispatch({ type: 'SET_CONNECTED', connected: true });
      ws.send(JSON.stringify({ type: 'init', arena: true, config: { ...cfg, contestants } }));
    };
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      if (msg.type === 'arena_init') {
        dispatch({ type: 'INIT_ARENA', contestants: msg.contestants, config: msg.config, states: msg.states });
      } else if (msg.type === 'arena_state') {
        dispatch({ type: 'INGEST_ARENA_STATE', payload: msg });
      } else if (msg.type === 'error') {
        console.warn('arena error:', msg.message);
      }
    };
    ws.onclose = () => dispatch({ type: 'SET_CONNECTED', connected: false });
    ws.onerror = () => dispatch({ type: 'SET_CONNECTED', connected: false });
  }, [disconnect, dispatch]);

  // Playback driver: while playing, advance one tick per interval. Behind the
  // live edge -> replay a cached tick; at the edge -> request a fresh live step;
  // at max_ticks -> pause.
  useEffect(() => {
    if (!state.playback.isPlaying) return undefined;
    const baseMs = 320;
    const id = setInterval(() => {
      const pb = pbRef.current;
      const cfg = cfgRef.current;
      if (pb.currentTick < pb.maxTick) {
        dispatch({ type: 'SET_TICK', tick: pb.currentTick + 1 });
      } else if (pb.maxTick < cfg.max_ticks && wsRef.current?.readyState === WebSocket.OPEN) {
        step();
      } else {
        dispatch({ type: 'PAUSE' });
      }
    }, baseMs / (state.playback.speed || 1));
    return () => clearInterval(id);
  }, [state.playback.isPlaying, state.playback.speed, dispatch, step]);

  // Tear the socket down on unmount.
  useEffect(() => () => disconnect(), [disconnect]);

  return { connect, step, spawn, disconnect, connected: state.status.connected };
}
