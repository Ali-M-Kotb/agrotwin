/* AgroTwin service worker — AI-generated (Claude) under human review.
 * App shell cached for offline use in the field; API calls go to the network first and fall
 * back to the last good answer, so a farmer with a weak signal still sees their plan. */
const SHELL = "agrotwin-shell-v3";
const API = "agrotwin-api-v3";
const ASSETS = ["/", "/static/style.css", "/static/app.js", "/static/map.js", "/static/icon.svg",
  "/static/i18n/en.json", "/static/i18n/ar.json", "/static/vendor/leaflet.js", "/static/vendor/leaflet.css",
  "/static/vendor/plotly.min.js", "/static/vendor/legends/layers.json"];

self.addEventListener("install", (e) => e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys().then((ks) => Promise.all(ks.filter((k) => ![SHELL, API].includes(k)).map((k) => caches.delete(k)))).then(() => self.clients.claim())));

self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (u.origin !== location.origin) return;                    // map tiles: browser cache only
  if (u.pathname.startsWith("/api/")) {
    if (e.request.method !== "GET") return;
    e.respondWith(fetch(e.request).then((r) => {
      if (r.ok) { const copy = r.clone(); caches.open(API).then((c) => c.put(e.request, copy)); }
      return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  // App shell: network first so updates show at once; cached copy when the field has no signal.
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok && e.request.method === "GET") { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request)));
});
