// Instalação no ecrã inicial do telemóvel (PWA). O browser só aceita em HTTPS.

type Env = { isSecureContext: boolean; isTauri: boolean };

export async function registerServiceWorker(
  nav: Navigator = navigator,
  env: Env = { isSecureContext: window.isSecureContext, isTauri: "__TAURI_INTERNALS__" in window },
): Promise<boolean> {
  if (env.isTauri || !env.isSecureContext || !("serviceWorker" in nav)) return false;
  try {
    await nav.serviceWorker.register("/sw.js");
    return true;
  } catch {
    return false;
  }
}
