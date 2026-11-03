// Aadi SpendOS service worker: makes the app installable and lets the shell open instantly or offline.
// It NEVER touches API traffic or other origins: financial data is always fetched live and is never stored by this worker.
const CACHE = 'spendos-shell-v3'
const SHELL = ['/', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png', '/icons/apple-touch-icon.png', '/icons/favicon.png']

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE)
    await cache.addAll(SHELL)
    // also store the fingerprinted script and style files the page needs, found by reading the page itself
    const html = await (await fetch('/', { cache: 'reload' })).text()
    const assets = [...new Set(html.match(/\/assets\/[^"']+\.(?:js|css)/g) || [])]
    await cache.addAll(assets)
    await self.skipWaiting()
  })())
})

self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()))
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return
  if (req.mode === 'navigate') {
    // pages: try the network first so a new release is picked up, fall back to the cached shell when offline
    event.respondWith(fetch(req).then((res) => { const copy = res.clone(); caches.open(CACHE).then((c) => c.put('/', copy)); return res }).catch(() => caches.match('/', { ignoreVary: true })))
    return
  }
  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/icons/')) {
    // fingerprinted build files never change: cache first
    event.respondWith(caches.match(req, { ignoreVary: true }).then((hit) => hit || fetch(req).then((res) => { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); return res })))
  }
})
