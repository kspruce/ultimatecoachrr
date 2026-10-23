// Keeps the scouting game cards a phone has opened readable when the signal
// drops at the field. Registered from /scouting/ so it never sees any other
// part of the site. Always asks the network first and only falls back to the
// saved copy when the network fails or is too slow.
const CACHE = 'scouting-cards-v1';
const MAX_CARDS = 12;
const CARD = /^\/scouting\/\d+\/card$/;
const SLOW_MS = 4000;

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k.startsWith('scouting-cards-') && k !== CACHE)
                                    .map(k => caches.delete(k))))
      .then(() => self.clients.claim()));
});

function cacheable(response) {
  // Not a redirect (e.g. to the sign-in page) and not an error
  return response && !response.redirected && (response.ok || response.type === 'opaque');
}

async function trimCards(cache) {
  const cards = (await cache.keys()).filter(r => CARD.test(new URL(r.url).pathname));
  for (const old of cards.slice(0, Math.max(0, cards.length - MAX_CARDS))) {
    await cache.delete(old);
  }
}

async function networkFirst(request, isCard) {
  const cache = await caches.open(CACHE);
  const network = fetch(request).then(async response => {
    if (cacheable(response)) {
      await cache.put(request, response.clone());
      if (isCard) await trimCards(cache);
    }
    return response;
  });
  network.catch(() => {});  // handled below; don't report it twice
  if (!isCard) {
    return network.catch(() => cache.match(request).then(hit => hit || Response.error()));
  }
  // A card: give the network a few seconds, then show the saved copy if there is one
  const slow = new Promise(resolve => setTimeout(resolve, SLOW_MS));
  try {
    const first = await Promise.race([network, slow.then(() => cache.match(request))]);
    if (first) return first;
    return await network;
  } catch (err) {
    const hit = await cache.match(request);
    if (hit) return hit;
    throw err;
  }
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (request.mode === 'navigate') {
    if (url.origin === location.origin && CARD.test(url.pathname)) {
      event.respondWith(networkFirst(request, true));
    }
    return;
  }
  // The stylesheets, fonts and scripts a card page needs to look right offline
  if (['style', 'font', 'script'].includes(request.destination)) {
    event.respondWith(networkFirst(request, false));
  }
});
