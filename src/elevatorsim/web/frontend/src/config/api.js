// src/config/api.js
// Same origin in production (frontend served by FastAPI on :8000); direct to
// :8000 in dev (vite on another port, CORS is open). Mirrors the convention the
// legacy App.jsx used so dev and prod both work.

export const BACKEND_URL =
  window.location.hostname === 'localhost' ? 'http://localhost:8000' : '';

export function wsUrl(path) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host =
    window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
  return `${proto}//${host}${path}`;
}
