// service-worker.js
const CACHE_NAME = 'gameday-cache-v1';
const urlsToCache = [
  '/static/css/gameday.css',
  '/static/js/gameday.js'
  // Remove other URLs that might not exist
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        // Use a more resilient approach to caching
        const cachePromises = urlsToCache.map(url => {
          // Attempt to cache each URL individually
          return fetch(url)
            .then(response => {
              if (!response.ok) {
                throw new Error(`Failed to cache ${url}`);
              }
              return cache.put(url, response);
            })
            .catch(error => {
              console.warn(`Failed to cache ${url}: ${error.message}`);
              // Continue despite the error
              return Promise.resolve();
            });
        });
        
        return Promise.all(cachePromises);
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
        return fetch(event.request)
          .catch(error => {
            console.warn(`Fetch failed for ${event.request.url}: ${error.message}`);
            // Return a simple response for navigation requests
            if (event.request.mode === 'navigate') {
              return new Response('You are offline. Please reconnect to use this app.', {
                headers: { 'Content-Type': 'text/plain' }
              });
            }
            // For other requests, just propagate the error
            throw error;
          });
      })
  );
});

// Add an activate event to clean up old caches
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

if (event.request.mode === 'navigate') {
  return caches.match('/static/offline.html')
    .catch(() => {
      return new Response('You are offline. Please reconnect to use this app.', {
        headers: { 'Content-Type': 'text/plain' }
      });
    });
}