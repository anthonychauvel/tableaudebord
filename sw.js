// Service worker minimal : juste ce qu'il faut pour que l'installation PWA
// fonctionne et que le tableau de bord s'ouvre même sans réseau (avec les
// dernières données connues). Pas de stratégie sophistiquée — un outil perso
// à une seule page n'en a pas besoin.
const CACHE = "veille-perso-20260731-051404";
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

// donnees.json : réseau d'abord (les alertes doivent être fraîches), cache en
// repli si hors-ligne. Le reste (coquille de l'app) : cache d'abord, c'est
// statique.
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.endsWith("donnees.json")) {
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
