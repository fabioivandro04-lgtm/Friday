// Endereço do Core e token de emparelhamento, guardados neste dispositivo.

// alwaysListening: microfone sempre ligado; o Core só responde a "Friday" ([wake] no friday.toml).
export type Settings = { coreUrl: string; token: string; alwaysListening?: boolean };

const KEY = "friday.settings";
const LOCAL_CORE = "http://127.0.0.1:8765";

function defaultCoreUrl(origin: string): string {
  // Servida pelo Core (PC ou telemóvel via Tailscale): o Core é a própria origem.
  // No Tauri ou no `npm run dev`, o Core está neste PC.
  if (origin.startsWith("tauri:") || /^https?:\/\/localhost:5173$/.test(origin)) return LOCAL_CORE;
  return origin.startsWith("http") ? origin : LOCAL_CORE;
}

export function loadSettings(origin: string = location.origin): Settings {
  const fallback = { coreUrl: defaultCoreUrl(origin), token: "" };
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

export function saveSettings(s: Settings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    // Sem armazenamento (modo privado): fica só para esta sessão.
  }
}
