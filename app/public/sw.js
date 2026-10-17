// Service worker da Friday: permite instalar a app e abrir a interface sem rede.
// A conversa precisa sempre do Core; aqui só se guarda a "casca" da interface.
const CACHE = "friday-shell-v1";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(["/", "/manifest.webmanifest", "/icon.svg"])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

// Rede primeiro (para ter sempre a versão nova); cache só se não houver rede.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  if (["/ws", "/pair", "/twilio", "/health"].some((p) => url.pathname.startsWith(p))) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          // Só guarda respostas boas (um erro não pode ficar em cache).
          const copy = response.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then((hit) => hit || caches.match("/"))),
  );
});
