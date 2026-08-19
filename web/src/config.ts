// Бэкенд всегда слушает порт 8000 — независимо от того, что отдало эту страницу
// (dev-сервер Vite на 5173 или сам бэкенд на 8000).
const host = window.location.hostname || 'localhost';
const secure = window.location.protocol === 'https:';

export const API_BASE = `${secure ? 'https' : 'http'}://${host}:8000`;
export const WS_BASE = `${secure ? 'wss' : 'ws'}://${host}:8000`;
