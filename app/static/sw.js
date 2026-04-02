const CACHE = 'duribugi-v1';
const STATIC = [
  '/',
  '/style.css',
  '/app.js',
  '/js/utils.js',
  '/js/pin.js',
  '/js/dashboard.js',
  '/js/entries.js',
  '/js/accounts.js',
  '/js/report.js',
  '/js/assets.js',
  '/js/messages.js',
  '/js/settings.js',
  '/logo.png',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(STATIC))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // API 요청은 항상 네트워크
  if (url.pathname.startsWith('/api')) {
    return;
  }

  // 정적 자산은 캐시 우선, 없으면 네트워크
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request))
  );
});
