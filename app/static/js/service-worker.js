// service-worker.js
const CACHE_NAME = 'gameday-cache-v1';
const urlsToCache = [
  '/static/css/gameday.css',
  '/static/js/gameday.js',
  '/static/img/field.png',
  '/static/bootstrap/css/bootstrap.min.css',
  '/static/bootstrap/js/bootstrap.bundle.min.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request);
      })
      .catch(() => {
        // If both cache and network fail, return a simple offline page
        if (event.request.mode === 'navigate') {
          return caches.match('/offline.html');
        }
      })
  );
});
