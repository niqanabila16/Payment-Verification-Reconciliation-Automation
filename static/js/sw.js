/* Service worker.
   - Static files: cache-first, so pages keep their styling when the central computer is off.
   - The Teller "New receipt" page: network-first with a cached fallback, so a branch can still open the
     form at night and queue receipts (receipts.js stores them and syncs later).
   - Shows desktop notifications and opens the right page when one is clicked.
   Needs HTTPS or localhost (browser rule for service workers). */
const STATIC_CACHE = 'static-v1';
const PAGES_CACHE = 'pages-v1';
const OFFLINE_PAGE_PATH = '/teller/';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (![STATIC_CACHE, PAGES_CACHE].includes(key)) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/static/')) {
    event.respondWith((async () => {
      const cache = await caches.open(STATIC_CACHE);
      const cached = await cache.match(request);
      const refresh = fetch(request).then((response) => { if (response.ok) cache.put(request, response.clone()); return response; }).catch(() => cached);
      return cached || refresh;
    })());
    return;
  }

  if (request.mode === 'navigate' && url.pathname === OFFLINE_PAGE_PATH) {
    event.respondWith((async () => {
      const cache = await caches.open(PAGES_CACHE);
      try {
        const response = await fetch(request);
        // Only cache real pages: a redirect to the sign-in page must not replace the form.
        if (response.ok && !response.redirected) cache.put(request, response.clone());
        return response;
      } catch {
        return (await cache.match(request)) || Response.error();
      }
    })());
  }
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'clear-pages') caches.delete(PAGES_CACHE);
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if ('focus' in client) { await client.focus(); if ('navigate' in client) await client.navigate(target); return; }
    }
    await self.clients.openWindow(target);
  })());
});
