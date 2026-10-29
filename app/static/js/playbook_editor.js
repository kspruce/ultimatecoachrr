/* Playbook: writing a play's details on a phone. Boxes that grow, roles
   added and removed, a photo from the camera or library, tags, the theory /
   drill / clip pickers, and a copy kept on this device until it's saved. */
(function () {
  'use strict';

  var form = document.getElementById('pb-play-form');
  if (!form) return;
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content;
  var dirty = false;

  /* ── Boxes that grow with their text ────────────────────────── */
  function grow(ta) {
    ta.style.height = 'auto';
    ta.style.height = (ta.scrollHeight + 2) + 'px';
  }
  form.addEventListener('input', function (e) {
    if (e.target.tagName === 'TEXTAREA') grow(e.target);
  });
  form.querySelectorAll('textarea').forEach(grow);

  /* ── Roles ──────────────────────────────────────────────────── */
  var roles = document.getElementById('pb-roles');
  if (roles) {
    form.querySelector('[data-add-role]').addEventListener('click', function () {
      roles.appendChild(document.getElementById('pb-role-row').content.cloneNode(true));
      roles.lastElementChild.querySelector('select').focus();
    });
    roles.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-remove-role]');
      if (btn) { btn.closest('.pb-role-row').remove(); changed(); }
    });
  }

  /* ── Photo ──────────────────────────────────────────────────── */
  var coverFile = document.getElementById('th-cover-file');
  if (coverFile) {
    var coverImg = document.getElementById('th-cover-img');
    var coverInput = document.getElementById('image_url');
    var coverRemove = document.getElementById('th-cover-remove');
    var coverStatus = document.getElementById('th-cover-status');
    var coverLabel = form.querySelector('[data-cover-label]');
    var showCover = function (url) {
      coverInput.value = url || '';
      coverImg.hidden = !url;
      if (url) coverImg.src = url; else coverImg.removeAttribute('src');
      coverRemove.hidden = !url;
      coverLabel.textContent = url ? 'Change photo' : 'Or add a photo of it';
      changed();
    };
    coverFile.addEventListener('change', function () {
      var file = this.files[0];
      this.value = '';
      if (!file) return;
      coverStatus.textContent = 'Uploading…';
      var body = new FormData();
      body.append('image', file);
      fetch(form.getAttribute('data-upload-url'), {
        method: 'POST', credentials: 'same-origin', body: body,
        headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }
      }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (data) {
          if (!r.ok) throw new Error(data.error || data.message || 'That photo could not be uploaded.');
          return data;
        });
      }).then(function (data) {
        coverStatus.textContent = '';
        showCover(data.url);
      }).catch(function (err) { coverStatus.textContent = err.message; });
    });
    coverRemove.addEventListener('click', function () { showCover(''); });
    coverInput.addEventListener('change', function () { showCover(coverInput.value.trim()); });
  }

  /* ── Tags ───────────────────────────────────────────────────── */
  var tagsInput = document.getElementById('tags');
  form.querySelectorAll('[data-add-tag]').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var name = chip.getAttribute('data-add-tag');
      var have = tagsInput.value.split(',').map(function (t) { return t.trim().toLowerCase(); }).filter(Boolean);
      if (have.indexOf(name.toLowerCase()) === -1) {
        tagsInput.value = (have.length ? tagsInput.value.replace(/[\s,]*$/, '') + ', ' : '') + name;
        changed();
      }
      chip.hidden = true;
    });
  });

  /* ── Pickers: the sheet's checkboxes are the form field ─────── */
  function showPicked(field) {
    var box = form.querySelector('[data-picked-for="' + field + '"]');
    if (!box) return;
    box.innerHTML = '';
    form.querySelectorAll('input[name="' + field + '"]:checked').forEach(function (input) {
      var chip = document.createElement('span');
      chip.className = 'th-badge';
      chip.textContent = input.getAttribute('data-pick-title');
      box.appendChild(chip);
    });
    if (!box.children.length) box.innerHTML = '<span class="small text-muted">None linked</span>';
  }
  ['topics', 'drills', 'clips'].forEach(showPicked);
  form.addEventListener('change', function (e) {
    if (['topics', 'drills', 'clips'].indexOf(e.target.name) !== -1) { showPicked(e.target.name); changed(); }
  });
  form.querySelectorAll('[data-pick-search]').forEach(function (search) {
    search.addEventListener('input', function () {
      var q = search.value.trim().toLowerCase();
      search.closest('.offcanvas').querySelectorAll('[data-pick-name]').forEach(function (row) {
        row.hidden = q && row.getAttribute('data-pick-name').indexOf(q) === -1;
      });
    });
  });

  /* ── A copy kept on this device until it's saved ────────────── */
  var key = form.getAttribute('data-autosave-key');
  var fields = ['name', 'call', 'signal', 'description', 'notes', 'tags'];
  function snapshot() {
    var data = {};
    fields.forEach(function (f) { var el = document.getElementById(f); if (el) data[f] = el.value; });
    data.roles = roles ? Array.from(roles.querySelectorAll('.pb-role-row')).map(function (row) {
      return [row.querySelector('[name="role_id"]').value, row.querySelector('[name="role_text"]').value];
    }) : [];
    return data;
  }
  var initial = JSON.stringify(snapshot());
  var timer = null;
  function changed() {
    dirty = true;
    clearTimeout(timer);
    timer = setTimeout(function () {
      var data = snapshot();
      try {
        if (JSON.stringify(data) === initial) localStorage.removeItem(key);
        else localStorage.setItem(key, JSON.stringify({ at: Date.now(), data: data }));
      } catch (e) { /* private browsing: nothing to keep */ }
    }, 600);
  }
  form.addEventListener('input', changed);

  var saved = null;
  try { saved = JSON.parse(localStorage.getItem(key) || 'null'); } catch (e) { saved = null; }
  if (saved && saved.data && JSON.stringify(saved.data) !== initial) {
    var banner = document.getElementById('th-restore');
    banner.hidden = false;
    banner.querySelector('[data-restore-when]').textContent =
      new Date(saved.at).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
    banner.querySelector('[data-restore]').addEventListener('click', function () {
      fields.forEach(function (f) {
        var el = document.getElementById(f);
        if (el && saved.data[f] !== undefined) el.value = saved.data[f];
      });
      if (saved.data.roles && roles) {
        roles.innerHTML = '';
        saved.data.roles.forEach(function (pair) {
          roles.appendChild(document.getElementById('pb-role-row').content.cloneNode(true));
          var row = roles.lastElementChild;
          row.querySelector('[name="role_id"]').value = pair[0];
          row.querySelector('[name="role_text"]').value = pair[1];
        });
      }
      form.querySelectorAll('textarea').forEach(grow);
      banner.hidden = true;
    });
    banner.querySelector('[data-discard]').addEventListener('click', function () {
      try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
      banner.hidden = true;
    });
  }

  // The copy is cleared once the play's page confirms the save
  form.addEventListener('submit', function () { dirty = false; });
  window.addEventListener('beforeunload', function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });
})();
