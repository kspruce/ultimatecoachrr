/* Theory hub: reading pages. Lightbox (pinch / double-tap zoom, swipe down
   to close), contents built from the article's headings, the compact header
   and progress bar while reading, marking a topic read without leaving the
   page, and confirm prompts on delete buttons. */
(function () {
  'use strict';

  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content;

  function navHeight() {
    var nav = document.querySelector('.uc-navbar');
    document.documentElement.style.setProperty('--uc-nav-h', (nav ? nav.offsetHeight : 0) + 'px');
  }
  navHeight();
  window.addEventListener('resize', navHeight);

  // Just saved in the editor: forget the copy it kept on this device
  var saved = document.querySelector('[data-clear-drafts]');
  if (saved) {
    try {
      saved.getAttribute('data-clear-drafts').split(' ').forEach(function (k) { localStorage.removeItem(k); });
    } catch (e) { /* ignore */ }
    if (window.history.replaceState) history.replaceState(null, '', location.pathname + location.hash);
  }

  // Forms that ask first (delete buttons and the like)
  document.addEventListener('submit', function (e) {
    var msg = e.target.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) e.preventDefault();
  }, true);

  /* ── Lightbox ──────────────────────────────────────────────── */
  var box, img, caption, scale = 1, x = 0, y = 0;
  var pointers = new Map(), start = null, lastTap = 0;

  function apply() {
    img.style.transform = 'translate(calc(-50% + ' + x + 'px), calc(-50% + ' + y + 'px)) scale(' + scale + ')';
  }
  function reset() { scale = 1; x = 0; y = 0; apply(); box.style.background = ''; }

  function build() {
    box = document.createElement('div');
    box.id = 'th-lightbox';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-label', 'Photo');
    box.innerHTML = '<button type="button" class="th-lb-close" aria-label="Close"><i class="bi bi-x-lg"></i></button>' +
                    '<img alt=""><div class="th-lb-caption"></div>';
    document.body.appendChild(box);
    img = box.querySelector('img');
    caption = box.querySelector('.th-lb-caption');
    box.querySelector('.th-lb-close').addEventListener('click', close);

    box.addEventListener('pointerdown', function (e) {
      if (e.target.closest('.th-lb-close')) return;
      box.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      box.classList.add('dragging');
      start = snapshot();
    });
    box.addEventListener('pointermove', function (e) {
      if (!pointers.has(e.pointerId)) return;
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      var now = snapshot();
      if (pointers.size === 2 && start.dist) {
        scale = Math.min(5, Math.max(1, start.scale * now.dist / start.dist));
        x = start.x + (now.cx - start.cx);
        y = start.y + (now.cy - start.cy);
      } else if (pointers.size === 1) {
        x = start.x + (now.cx - start.cx);
        y = start.y + (now.cy - start.cy);
        if (scale === 1) {           // swiping down closes it
          x = 0;
          box.style.background = 'rgba(0,0,0,' + Math.max(.3, .94 - Math.abs(y) / 600) + ')';
        }
      }
      apply();
    });
    function up(e) {
      if (!pointers.has(e.pointerId)) return;
      var moved = Math.abs(x - start.x) + Math.abs(y - start.y);
      pointers.delete(e.pointerId);
      box.classList.remove('dragging');
      if (pointers.size) { start = snapshot(); return; }
      if (scale === 1 && Math.abs(y) > 110) return close();
      if (scale === 1) { x = 0; y = 0; box.style.background = ''; apply(); }
      if (moved < 8) {                                   // a tap
        var t = Date.now();
        if (t - lastTap < 300) {                         // double tap: zoom in / out
          if (scale > 1) reset(); else { scale = 2.5; apply(); }
          lastTap = 0;
        } else {
          lastTap = t;
          if (e.target !== img && scale === 1) {
            setTimeout(function () { if (lastTap === t) close(); }, 300);
          }
        }
      }
    }
    box.addEventListener('pointerup', up);
    box.addEventListener('pointercancel', up);
    box.addEventListener('wheel', function (e) {
      e.preventDefault();
      scale = Math.min(5, Math.max(1, scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15)));
      if (scale === 1) { x = 0; y = 0; }
      apply();
    }, { passive: false });
  }

  function snapshot() {
    var pts = Array.from(pointers.values());
    var cx = pts.reduce(function (s, p) { return s + p.x; }, 0) / (pts.length || 1);
    var cy = pts.reduce(function (s, p) { return s + p.y; }, 0) / (pts.length || 1);
    var dist = pts.length === 2 ? Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y) : 0;
    return { cx: cx, cy: cy, dist: dist, scale: scale, x: x, y: y };
  }

  var opener = null;
  function open(src, alt) {
    if (!box) build();
    opener = document.activeElement;
    img.src = src;
    img.alt = alt || '';
    caption.textContent = alt || '';
    reset();
    box.classList.add('open');
    document.body.style.overflow = 'hidden';
    box.querySelector('.th-lb-close').focus();
  }
  function close() {
    if (!box || !box.classList.contains('open')) return;
    box.classList.remove('open');
    img.removeAttribute('src');
    pointers.clear();
    document.body.style.overflow = '';
    if (opener && opener.focus) opener.focus();
  }
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest('[data-lightbox]');
    if (trigger) {
      e.preventDefault();
      return open(trigger.getAttribute('data-lightbox'), trigger.getAttribute('data-caption'));
    }
    var pic = e.target.closest('.topic-content img');
    if (pic && !pic.closest('a')) open(pic.currentSrc || pic.src, pic.alt);
  });

  /* ── Reading a topic ───────────────────────────────────────── */
  var content = document.querySelector('.topic-content');
  var article = document.getElementById('th-article');
  if (content) {
    // Contents: the article's headings, in the sidebar and the phone sheet
    var headings = Array.from(content.querySelectorAll('h1, h2, h3'));
    var lists = document.querySelectorAll('[data-toc-list]');
    if (headings.length >= 2 && lists.length) {
      headings.forEach(function (h, i) {
        if (!h.id) h.id = 'section-' + (i + 1);
      });
      lists.forEach(function (list) {
        headings.forEach(function (h) {
          var a = document.createElement('a');
          a.href = '#' + h.id;
          a.textContent = h.textContent;
          a.className = 'toc-link' + (h.tagName === 'H3' ? ' h3' : '');
          a.dataset.id = h.id;
          list.appendChild(a);
        });
      });
      document.querySelectorAll('[data-toc]').forEach(function (el) { el.hidden = false; });
      var links = document.querySelectorAll('.toc-link');
      if ('IntersectionObserver' in window) {
        var observer = new IntersectionObserver(function (entries) {
          entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            links.forEach(function (l) { l.classList.toggle('active', l.dataset.id === entry.target.id); });
          });
        }, { rootMargin: '0px 0px -65% 0px' });
        headings.forEach(function (h) { observer.observe(h); });
      }
      // Tapping a heading in the sheet closes it first, then jumps
      document.querySelectorAll('.th-sheet [data-toc-list]').forEach(function (list) {
        list.addEventListener('click', function (e) {
          var a = e.target.closest('a.toc-link');
          if (!a) return;
          e.preventDefault();
          var sheet = list.closest('.offcanvas');
          var go = function () {
            document.getElementById(a.dataset.id).scrollIntoView({ behavior: 'smooth' });
            history.replaceState(null, '', '#' + a.dataset.id);
          };
          if (window.bootstrap && sheet) {
            sheet.addEventListener('hidden.bs.offcanvas', go, { once: true });
            bootstrap.Offcanvas.getOrCreateInstance(sheet).hide();
          } else go();
        });
      });
    }

    // Progress bar, and the compact header once the title has scrolled away
    var bar = document.getElementById('th-progress-bar');
    var head = document.querySelector('.th-sticky-head');
    var title = document.getElementById('th-title');
    var ticking = false;
    function onScroll() {
      ticking = false;
      if (bar && article) {
        var rect = article.getBoundingClientRect();
        var total = article.offsetHeight - window.innerHeight;
        bar.style.width = Math.min(100, total > 0 ? Math.max(0, -rect.top) / total * 100 : 100) + '%';
      }
      if (head && title) head.classList.toggle('shown', title.getBoundingClientRect().bottom < 40);
    }
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; requestAnimationFrame(onScroll); }
    }, { passive: true });
    onScroll();
  }

  // Mark as read without leaving the page (the form still works without JS)
  document.querySelectorAll('form[data-read-form]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var input = form.querySelector('input[name="read"]');
      var btn = form.querySelector('button');
      btn.disabled = true;
      fetch(form.action, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
        body: new FormData(form)
      }).then(function (r) { return r.ok ? r.json() : Promise.reject(r); })
        .then(function (data) {
          document.querySelectorAll('form[data-read-form]').forEach(function (f) {
            f.querySelector('input[name="read"]').value = data.read ? '0' : '1';
            var b = f.querySelector('button');
            b.classList.toggle('is-read', data.read);
            b.classList.toggle('btn-primary', !data.read);
            b.classList.toggle('btn-outline-secondary', data.read);
            // (the playbook's "learned" button says so with data-done / data-todo)
            var done = f.getAttribute('data-done') || 'Read', todo = f.getAttribute('data-todo') || 'Mark as read';
            b.innerHTML = data.read ? '<i class="bi bi-check-circle-fill"></i> ' + done
                                    : '<i class="bi bi-check-circle"></i> ' + todo;
            b.setAttribute('aria-pressed', data.read ? 'true' : 'false');
          });
          var next = document.querySelector('[data-next-topic]');
          if (data.read && next) next.classList.add('btn-primary');
        })
        .catch(function () { input.form.submit(); })
        .finally(function () { btn.disabled = false; });
    });
  });
})();
