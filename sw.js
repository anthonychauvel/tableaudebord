// Service worker minimal : juste ce qu'il faut pour que l'installation PWA
// fonctionne et que le tableau de bord s'ouvre même sans réseau (avec les
// dernières données connues). Pas de stratégie sophistiquée — un outil perso
// à une seule page n'en a pas besoin.
const CACHE = "veille-perso-20260930-bouton";
const SHELL = ["./", "./index.html", "./manifest.json", "./donnees.json",
               "./icons/icon-192.png", "./icons/icon-512.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// donnees.json ET la page elle-même : réseau d'abord, cache en repli si
// hors-ligne. La page était servie « cache d'abord » : une nouvelle version de
// l'interface (bouton Relancer, 30/09/2026) restait invisible sur le téléphone
// jusqu'au passage suivant de la veille. Le reste (icônes, manifest) : cache
// d'abord, c'est statique.
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith("donnees.json") || url.pathname.endsWith("/")
      || url.pathname.endsWith("index.html") || e.request.mode === "navigate") {
    e.respondWith(
      fetch(e.request)
        .then((r) => { caches.open(CACHE).then((c) => c.put(e.request, r.clone())); return r; })
        .catch(() => caches.match(e.request))
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then((r) => r || fetch(e.request))
  );
});
