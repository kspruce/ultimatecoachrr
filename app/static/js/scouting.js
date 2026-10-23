// Scouting pages: the bits that make them work on a phone at the field.
(function () {
  'use strict';

  function store(fn, fallback) {
    // Storage can be off (private mode, full); everything here is a convenience
    try { return fn(); } catch (e) { return fallback; }
  }

  // ── Text boxes grow with what is typed ──────────────────────────────────
  function autoGrow(el) {
    el.style.height = 'auto';
    el.style.height = (el.scrollHeight + 2) + 'px';
  }
  function initAutoGrow(root) {
    root.querySelectorAll('textarea[data-autogrow]').forEach(function (el) {
      autoGrow(el);
      el.addEventListener('input', function () { autoGrow(el); });
    });
  }

  // ── Unsaved form drafts survive a dropped signal or a stray back-swipe ──
  function formValues(form) {
    var values = {};
    form.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (!el.name || el.type === 'hidden' || el.type === 'submit' || el.type === 'button') return;
      if (el.type === 'checkbox' || el.type === 'radio') {
        values[el.name + '=' + el.value] = el.checked;
      } else {
        values[el.name] = el.value;
      }
    });
    return values;
  }
  function applyValues(form, values) {
    form.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (!el.name || el.type === 'hidden') return;
      if (el.type === 'checkbox' || el.type === 'radio') {
        var key = el.name + '=' + el.value;
        if (key in values) el.checked = values[key];
      } else if (el.name in values) {
        el.value = values[el.name];
        if (el.tagName === 'TEXTAREA' && el.hasAttribute('data-autogrow')) autoGrow(el);
      }
    });
  }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  function initDrafts() {
    document.querySelectorAll('form[data-draft-key]').forEach(function (form) {
      var key = 'scout-draft:' + form.dataset.draftKey;
      var original = formValues(form);
      var saved = store(function () { return JSON.parse(localStorage.getItem(key) || 'null'); }, null);
      var banner = document.querySelector('[data-draft-banner="' + form.dataset.draftKey + '"]');

      if (saved && !same(saved.values, original) && banner) {
        var when = new Date(saved.at);
        banner.querySelector('[data-draft-when]').textContent =
          when.toLocaleDateString([], { day: 'numeric', month: 'short' }) + ' ' +
          when.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        banner.hidden = false;
        banner.querySelector('[data-draft-restore]').addEventListener('click', function () {
          applyValues(form, saved.values);
          banner.hidden = true;
        });
        banner.querySelector('[data-draft-discard]').addEventListener('click', function () {
          store(function () { localStorage.removeItem(key); });
          banner.hidden = true;
        });
      } else if (saved) {
        store(function () { localStorage.removeItem(key); });
      }

      var timer;
      function save() {
        var values = formValues(form);
        store(function () {
          if (same(values, original)) localStorage.removeItem(key);
          else localStorage.setItem(key, JSON.stringify({ at: Date.now(), values: values }));
        });
      }
      form.addEventListener('input', function () { clearTimeout(timer); timer = setTimeout(save, 400); });
      form.addEventListener('change', save);
      form.addEventListener('submit', function () {
        clearTimeout(timer);
        store(function () { localStorage.removeItem(key); });
      });
    });
  }

  // ── Long forms: one section open at a time on a phone ───────────────────
  function initSections() {
    var sections = Array.prototype.slice.call(document.querySelectorAll('details.form-fold'));
    if (!sections.length) return;
    var phone = window.matchMedia('(max-width: 767.98px)').matches;
    sections.forEach(function (d, i) {
      var hasError = d.querySelector('.text-danger');
      d.open = !phone || i === 0 || !!hasError;
      d.addEventListener('toggle', function () {
        if (d.open) initAutoGrow(d);  // sizes are 0 while closed
      });
    });
    if (location.hash) {
      var target = document.querySelector(location.hash);
      var fold = target && target.closest('details.form-fold');
      if (fold) { fold.open = true; target.focus(); }
    }
  }

  // ── Game card: keep the screen on, say how fresh it is, save it offline ──
  function initWakeLock() {
    var btn = document.querySelector('[data-wake-lock]');
    if (!btn) return;
    if (!('wakeLock' in navigator)) { btn.hidden = true; return; }
    var lock = null;
    var wanted = store(function () { return localStorage.getItem('scout-wake') !== 'off'; }, true);

    function show() {
      btn.classList.toggle('active', !!lock);
      btn.setAttribute('aria-pressed', lock ? 'true' : 'false');
      btn.querySelector('[data-wake-label]').textContent = lock ? 'Screen stays on' : 'Keep screen on';
    }
    function acquire() {
      navigator.wakeLock.request('screen').then(function (l) {
        lock = l;
        lock.addEventListener('release', function () { lock = null; show(); });
        show();
      }).catch(function () { lock = null; show(); });
    }
    btn.addEventListener('click', function () {
      wanted = !lock;
      store(function () { localStorage.setItem('scout-wake', wanted ? 'on' : 'off'); });
      if (lock) lock.release(); else acquire();
    });
    // The lock goes when the phone sleeps or the tab is hidden: take it back on return
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible' && wanted && !lock) acquire();
    });
    show();
    if (wanted) acquire();
  }

  function initFreshness() {
    var el = document.querySelector('[data-rendered-at]');
    if (!el) return;
    var at = new Date(el.dataset.renderedAt);
    var time = at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    function show() {
      var old = Date.now() - at.getTime() > 2 * 60 * 1000;
      if (!navigator.onLine || old) {
        el.textContent = (navigator.onLine ? 'Saved copy from ' : 'Offline · saved copy from ') + time;
        el.classList.add('stale');
      } else {
        el.textContent = 'Updated ' + time;
        el.classList.remove('stale');
      }
    }
    show();
    window.addEventListener('online', show);
    window.addEventListener('offline', show);
    // A page restored from the back/forward cache keeps its old time
    window.addEventListener('pageshow', show);
  }

  function registerOffline() {
    if (!document.querySelector('[data-offline-card]') || !('serviceWorker' in navigator)) return;
    navigator.serviceWorker.register('/scouting/sw.js', { scope: '/scouting/' }).then(function (reg) {
      // The first visit isn't saved by a worker that has only just started: save it now
      if (!navigator.serviceWorker.controller && 'caches' in window) {
        caches.open('scouting-cards-v1').then(function (cache) { cache.add(location.pathname); })
          .catch(function () {});
      }
      return reg;
    }).catch(function () {});
  }

  function initFolds() {
    // Card sections fold away on a phone; remember which ones the coach closed
    document.querySelectorAll('details[data-fold-key]').forEach(function (d) {
      var key = 'scout-fold:' + d.dataset.foldKey;
      if (store(function () { return localStorage.getItem(key); }) === 'closed') d.open = false;
      d.addEventListener('toggle', function () {
        if (printing) return;
        store(function () {
          if (d.open) localStorage.removeItem(key); else localStorage.setItem(key, 'closed');
        });
      });
    });
    // A printed card shows every section, then folds back as it was
    var printing = false, closed = [];
    window.addEventListener('beforeprint', function () {
      printing = true;
      closed = Array.prototype.filter.call(document.querySelectorAll('details'), function (d) { return !d.open; });
      closed.forEach(function (d) { d.open = true; });
    });
    window.addEventListener('afterprint', function () {
      closed.forEach(function (d) { d.open = false; });
      setTimeout(function () { printing = false; }, 0);
    });
  }

  // ── Quick note panel ────────────────────────────────────────────────────
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    var input = document.querySelector('input[name="csrf_token"]');
    return meta ? meta.content : (input ? input.value : '');
  }

  function post(url, data) {
    var body = new FormData();
    Object.keys(data).forEach(function (k) { body.append(k, data[k]); });
    body.append('csrf_token', csrfToken());
    return fetch(url, {
      method: 'POST', body: body, credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrfToken() }
    }).then(function (r) {
      return r.json().catch(function () { return { success: false, message: 'Not saved. Try again.' }; })
        .then(function (json) { json.success = r.ok && json.success; return json; });
    });
  }

  function initQuickNote() {
    var panel = document.getElementById('quickNote');
    if (!panel) return;
    var form = panel.querySelector('form');
    var text = form.querySelector('[name=text]');
    var status = panel.querySelector('[data-note-status]');
    var changed = false;

    panel.addEventListener('shown.bs.offcanvas', function () { text.focus(); });
    panel.addEventListener('hidden.bs.offcanvas', function () {
      if (changed) location.reload();  // show what was added
    });

    function say(message, ok) {
      status.textContent = message;
      status.className = 'small mt-2 ' + (ok ? 'text-success' : 'text-danger');
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      if (!text.value.trim()) { say('Type a note first.', false); return; }
      var now = new Date();
      var data = {
        text: text.value,
        section: form.querySelector('[name=section]:checked').value,
        time: String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0')
      };
      var button = form.querySelector('[type=submit]');
      button.disabled = true;
      post(form.action, data).then(function (res) {
        say(res.message, res.success);
        if (res.success) { text.value = ''; changed = true; text.focus(); }
      }).catch(function () {
        say('No signal: the note was not saved. It is still in the box, so try again in a moment.', false);
      }).then(function () { button.disabled = false; });
    });

    panel.querySelectorAll('[data-tag]').forEach(function (chip) {
      chip.addEventListener('click', function () {
        chip.disabled = true;
        post(panel.dataset.tagUrl, { tag: chip.dataset.tag }).then(function (res) {
          if (res.success) {
            chip.classList.toggle('on', res.on);
            chip.setAttribute('aria-pressed', res.on ? 'true' : 'false');
            say((res.on ? 'Added ' : 'Removed ') + res.label + '.', true);
            changed = true;
          } else {
            say(res.message || 'Not saved. Try again.', false);
          }
        }).catch(function () { say('No signal: try again in a moment.', false); })
          .then(function () { chip.disabled = false; });
      });
    });
  }

  // ── Clips: grid or compact list, remembered per device ──────────────────
  function initClipView() {
    var grid = document.getElementById('clipsGrid');
    var buttons = document.querySelectorAll('[data-clip-view]');
    if (!grid || !buttons.length) return;
    function set(view) {
      grid.classList.toggle('clips-list', view === 'list');
      buttons.forEach(function (b) {
        var on = b.dataset.clipView === view;
        b.classList.toggle('active', on);
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
    }
    var phone = window.matchMedia('(max-width: 575.98px)').matches;
    set(store(function () { return localStorage.getItem('scout-clip-view'); }) || (phone ? 'list' : 'grid'));
    buttons.forEach(function (b) {
      b.addEventListener('click', function () {
        set(b.dataset.clipView);
        store(function () { localStorage.setItem('scout-clip-view', b.dataset.clipView); });
      });
    });
  }

  // ── Report page: the section bar sits under the sticky navbar ──────────
  function initSectionBar() {
    var bar = document.querySelector('.section-bar');
    if (!bar) return;
    var nav = document.querySelector('.uc-navbar');
    function measure() {
      document.documentElement.style.setProperty('--nav-h', (nav ? nav.offsetHeight : 0) + 'px');
    }
    measure();
    window.addEventListener('resize', measure);
    if (!('IntersectionObserver' in window)) return;
    var links = Array.prototype.slice.call(bar.querySelectorAll('a[href^="#"]'));
    var visible = {};
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting; });
      var current = links.filter(function (a) { return visible[a.getAttribute('href').slice(1)]; })[0];
      links.forEach(function (a) { a.classList.toggle('active', a === current); });
    }, { rootMargin: '-120px 0px -50% 0px' });
    links.forEach(function (a) {
      var target = document.getElementById(a.getAttribute('href').slice(1));
      if (target) observer.observe(target);
    });
  }

  // ── Key player panel: best markers float up as their threats are picked ──
  function initKeyPlayer() {
    var panel = document.getElementById('keyPlayer');
    var dataEl = document.getElementById('kp-data');
    if (!panel || !dataEl) return;
    var data = JSON.parse(dataEl.textContent);
    var form = panel.querySelector('form');
    var list = panel.querySelector('.kp-markers');
    var hint = panel.querySelector('[data-kp-hint]');
    var defenders = {};
    data.defenders.forEach(function (d) { defenders[d.id] = d; });
    var original = Array.prototype.slice.call(list.querySelectorAll('label[data-defender]'));

    function threats() {
      var picked = Array.prototype.map.call(form.querySelectorAll('[name=threat_roles]:checked'), function (el) { return el.value; });
      if (picked.length) return picked;
      var pos = form.querySelector('[name=position]:checked');
      return pos ? (data.positionThreats[pos.value] || []) : [];
    }

    function update() {
      var wanted = threats();
      var gender = (form.querySelector('[name=gender]:checked') || {}).value;
      var scored = original.map(function (label, i) {
        var d = defenders[label.dataset.defender];
        var score = 0, why = [];
        wanted.forEach(function (t) {
          var answers = data.counters[t] || [];
          var hit = answers.filter(function (r) { return d.roles.indexOf(r) !== -1; })[0];
          if (hit) {
            score += hit === answers[0] ? 2 : 1;
            why.push(data.labels[hit] + ' vs ' + data.labels[t].toLowerCase());
          }
        });
        var clash = gender && d.gender && d.gender !== gender;
        return { label: label, score: clash ? -1 : score, why: why, clash: clash, i: i };
      });
      scored.sort(function (a, b) { return (b.score - a.score) || (a.i - b.i); });
      var good = 0;
      scored.forEach(function (x) {
        var input = document.getElementById(x.label.getAttribute('for'));
        var fit = x.label.querySelector('.kp-fit');
        fit.hidden = !(x.score > 0);
        fit.textContent = x.score > 0 ? 'Good fit: ' + x.why.join(', ') : '';
        x.label.classList.toggle('good', x.score > 0);
        x.label.classList.toggle('off', x.clash);
        input.disabled = x.clash;
        if (x.clash && input.checked) form.querySelector('#kp-m-0').checked = true;
        if (x.score > 0) good++;
        list.appendChild(input);
        list.appendChild(x.label);
      });
      hint.textContent = wanted.length ? (good ? '(best fits first)' : '(no one tagged for this yet)') : '';
    }

    form.addEventListener('change', function (e) {
      if (['threat_roles', 'position', 'gender'].indexOf(e.target.name) !== -1) update();
    });
    panel.addEventListener('shown.bs.offcanvas', function () { form.querySelector('#kp-number').focus(); });
    if (/[?&]add=key/.test(location.search) && window.bootstrap) {
      bootstrap.Offcanvas.getOrCreateInstance(panel).show();
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    initKeyPlayer();
    initSectionBar();
    initAutoGrow(document);
    initDrafts();
    initSections();
    initWakeLock();
    initFreshness();
    initFolds();
    registerOffline();
    initQuickNote();
    initClipView();
  });
})();
