import { registerServiceWorker } from "./pwa";

function nav(withSw = true) {
  const calls: string[] = [];
  return {
    calls,
    nav: withSw ? { serviceWorker: { register: async (url: string) => void calls.push(url) } } : {},
  };
}

test("regista o service worker em HTTPS", async () => {
  const n = nav();
  expect(await registerServiceWorker(n.nav as any, { isSecureContext: true, isTauri: false })).toBe(true);
  expect(n.calls).toEqual(["/sw.js"]);
});

test("não regista dentro do Tauri nem sem HTTPS", async () => {
  const a = nav();
  expect(await registerServiceWorker(a.nav as any, { isSecureContext: true, isTauri: true })).toBe(false);
  const b = nav();
  expect(await registerServiceWorker(b.nav as any, { isSecureContext: false, isTauri: false })).toBe(false);
  expect([...a.calls, ...b.calls]).toEqual([]);
});

test("browser sem suporte não rebenta", async () => {
  expect(await registerServiceWorker(nav(false).nav as any, { isSecureContext: true, isTauri: false })).toBe(false);
});
