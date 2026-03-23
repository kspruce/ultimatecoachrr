/**
 * offline_queue.js — Offline event queue with sync-on-reconnect
 *
 * Usage
 * -----
 * Include this script on any page that needs resilient API calls:
 *
 *   <script src="{{ url_for('static', filename='js/offline_queue.js') }}"></script>
 *
 * Then replace a bare fetch() call with:
 *
 *   OfflineQueue.fetch(url, options)
 *     .then(data => { ... })        // called immediately if online, or when replayed
 *     .catch(err => { ... })        // only called if the server returns an error
 *
 * A small connectivity indicator badge is injected into the DOM automatically.
 * When offline, requests are stored in localStorage and replayed in order once
 * connectivity is restored.
 *
 * Limitations
 * -----------
 * • Replay is fire-and-forget — if the replayed request fails, it is dropped
 *   (with a console warning).  This keeps the queue from growing unboundedly.
 * • localStorage keys are per-origin, so queues are isolated between tabs but
 *   shared within the same origin.  A lock (via a simple flag) prevents two
 *   tabs from replaying simultaneously.
 */

(function (global) {
  'use strict';

  // ── Constants ────────────────────────────────────────────────────────────
  const QUEUE_KEY   = 'uc_offline_queue';   // localStorage key
  const REPLAY_FLAG = 'uc_queue_replaying'; // localStorage lock flag

  // ── Connectivity indicator ───────────────────────────────────────────────
  let indicator = null;

  function buildIndicator() {
    const el = document.createElement('div');
    el.id = 'uc-offline-indicator';
    Object.assign(el.style, {
      position:     'fixed',
      bottom:       '14px',
      left:         '14px',
      zIndex:       '9999',
      display:      'none',
      padding:      '6px 12px',
      borderRadius: '6px',
      background:   '#EF4444',
      color:        '#fff',
      fontSize:     '0.78rem',
      fontWeight:   '600',
      boxShadow:    '0 2px 8px rgba(0,0,0,.25)',
      transition:   'opacity .3s',
      pointerEvents:'none',
    });
    document.body.appendChild(el);
    return el;
  }

  function showOffline(queuedCount) {
    if (!indicator) indicator = buildIndicator();
    indicator.textContent = `Offline — ${queuedCount} event${queuedCount !== 1 ? 's' : ''} queued`;
    indicator.style.background = '#EF4444';
    indicator.style.display = 'block';
  }

  function showSyncing() {
    if (!indicator) indicator = buildIndicator();
    indicator.textContent = 'Back online — syncing…';
    indicator.style.background = '#F59E0B';
    indicator.style.display = 'block';
  }

  function hideIndicator() {
    if (indicator) {
      indicator.style.opacity = '0';
      setTimeout(() => {
        if (indicator) indicator.style.display = 'none';
        if (indicator) indicator.style.opacity = '1';
      }, 800);
    }
  }

  // ── Queue helpers ─────────────────────────────────────────────────────────
  function loadQueue() {
    try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); }
    catch (e) { return []; }
  }

  function saveQueue(q) {
    try { localStorage.setItem(QUEUE_KEY, JSON.stringify(q)); }
    catch (e) { /* storage full — drop silently */ }
  }

  function enqueue(url, options) {
    const q = loadQueue();
    q.push({ url, options, ts: Date.now() });
    saveQueue(q);
    showOffline(q.length);
  }

  // ── Replay ────────────────────────────────────────────────────────────────
  async function replayQueue() {
    // Simple tab-level lock to avoid double-replay
    if (localStorage.getItem(REPLAY_FLAG) === '1') return;
    const q = loadQueue();
    if (q.length === 0) return;

    localStorage.setItem(REPLAY_FLAG, '1');
    showSyncing();

    const remaining = [];
    for (const item of q) {
      try {
        const resp = await fetch(item.url, item.options);
        if (!resp.ok) {
          console.warn('[OfflineQueue] Replay request failed (', resp.status, '), dropping:', item.url);
        } else {
          console.log('[OfflineQueue] Replayed:', item.url);
        }
        // On success or permanent failure, do NOT re-queue the item.
      } catch (e) {
        // Still offline — keep the item for next attempt
        remaining.push(item);
      }
    }

    saveQueue(remaining);
    localStorage.removeItem(REPLAY_FLAG);

    if (remaining.length === 0) {
      hideIndicator();
    } else {
      showOffline(remaining.length);
    }
  }

  // ── Network event listeners ───────────────────────────────────────────────
  window.addEventListener('online',  () => replayQueue());
  window.addEventListener('offline', () => {
    const q = loadQueue();
    showOffline(q.length);
  });

  // On page load, if we're online and have queued items, replay immediately
  document.addEventListener('DOMContentLoaded', () => {
    if (navigator.onLine) replayQueue();
    else {
      const q = loadQueue();
      if (q.length > 0) showOffline(q.length);
    }
  });

  // ── Public API ────────────────────────────────────────────────────────────
  /**
   * Drop-in replacement for fetch() that queues the request when offline.
   * Returns a Promise that resolves with the parsed JSON response (or rejects
   * on a server-side error).  Returns null when the request is queued (offline).
   */
  async function queuedFetch(url, options = {}) {
    if (!navigator.onLine) {
      enqueue(url, options);
      return null;  // Caller should handle null as "queued, will sync later"
    }

    try {
      const resp = await fetch(url, options);
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || `Server error ${resp.status}`);
      }
      return await resp.json();
    } catch (e) {
      // Network error (not a server error) → queue for later
      if (e instanceof TypeError && e.message.toLowerCase().includes('fetch')) {
        enqueue(url, options);
        return null;
      }
      throw e;  // Re-throw server errors
    }
  }

  global.OfflineQueue = { fetch: queuedFetch, replayQueue };

}(window));
