/* Theory hub: writing a topic, built for phones. Formatting buttons, a box
   that grows as you type, Write / Preview that keeps your place, photos
   from the camera or library (cover and inline), a draft kept on this
   device until it's saved, videos, tags and the drill and clip pickers. */
(function () {
  'use strict';

  var form = document.getElementById('th-topic-form');
  if (!form) return;
  var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content;
  var ta = document.getElementById('content');
  var dirty = false;

  function post(url, body) {
    return fetch(url, {
      method: 'POST', credentials: 'same-origin', body: body,
      headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' }
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(data.error || data.message || 'Something went wrong. Try again.');
        return data;
      });
    });
  }

  /* ── Grow the box with its text ─────────────────────────────── */
  function grow() {
    var y = window.scrollY;
    ta.style.height = 'auto';
    ta.style.height = (ta.scrollHeight + 2) + 'px';
    window.scrollTo(0, y);
  }
  ta.addEventListener('input', grow);
  window.addEventListener('resize', grow);
  grow();

  /* ── Formatting buttons ─────────────────────────────────────── */
  function wrap(before, after, placeholder) {
    var s = ta.selectionStart, e = ta.selectionEnd;
    var picked = ta.value.slice(s, e) || placeholder || '';
    ta.setRangeText(before + picked + after, s, e, 'end');
    ta.setSelectionRange(s + before.length, s + before.length + picked.length);
    changed();
  }
  function linePrefix(prefix, numbered) {
    var v = ta.value, s = ta.selectionStart, e = ta.selectionEnd;
    var lineStart = v.lastIndexOf('\n', s - 1) + 1;
    var lineEnd = v.indexOf('\n', e);
    if (lineEnd === -1) lineEnd = v.length;
    var lines = v.slice(lineStart, lineEnd).split('\n');
    var out = lines.map(function (line, i) {
      var p = numbered ? (i + 1) + '. ' : prefix;
      return line.indexOf(p) === 0 ? line.slice(p.length) : p + line.replace(/^(#{1,6} |> |- |\d+\. )/, '');
    }).join('\n');
    ta.setRangeText(out, lineStart, lineEnd, 'end');
    changed();
  }
  function insertBlock(text) {
    var s = ta.selectionStart, v = ta.value;
    var before = s > 0 && v[s - 1] !== '\n' ? '\n\n' : (s > 1 && v[s - 2] !== '\n' ? '\n' : '');
    var after = v[s] && v[s] !== '\n' ? '\n\n' : '\n';
    ta.setRangeText(before + text + after, s, ta.selectionEnd, 'end');
    changed();
  }

  form.querySelectorAll('[data-md]').forEach(function (btn) {
    // Keep the keyboard up and the selection where it was
    btn.addEventListener('mousedown', function (e) { e.preventDefault(); });
    btn.addEventListener('click', function () {
      var kind = btn.getAttribute('data-md');
      ta.focus();
      if (kind === 'bold') wrap('**', '**', 'bold text');
      else if (kind === 'italic') wrap('*', '*', 'italic text');
      else if (kind === 'h2') linePrefix('## ');
      else if (kind === 'h3') linePrefix('### ');
      else if (kind === 'ul') linePrefix('- ');
      else if (kind === 'ol') linePrefix('', true);
      else if (kind === 'quote') linePrefix('> ');
      else if (kind === 'hr') insertBlock('---');
      else if (kind === 'link') {
        var url = window.prompt('Link to (https://…)', 'https://');
        if (url && url !== 'https://') wrap('[', '](' + url.trim() + ')', 'link text');
      } else if (kind === 'photo') {
        document.getElementById('th-inline-file').click();
      }
    });
  });

  /* ── Photos ─────────────────────────────────────────────────── */
  function upload(file) {
    var body = new FormData();
    body.append('image', file);
    return post(form.getAttribute('data-upload-url'), body);
  }

  document.getElementById('th-inline-file').addEventListener('change', function () {
    var file = this.files[0];
    this.value = '';
    if (!file) return;
    var marker = '![Uploading ' + (file.name || 'photo').replace(/[\[\]]/g, '') + '…]()';
    insertBlock(marker);
    upload(file).then(function (data) {
      ta.value = ta.value.replace(marker, '![](' + data.url + ')');
      changed();
    }).catch(function (err) {
      ta.value = ta.value.replace(marker + '\n', '').replace(marker, '');
      changed();
      window.alert(err.message);
    });
  });

  var coverFile = document.getElementById('th-cover-file');
  var coverImg = document.getElementById('th-cover-img');
  var coverInput = document.getElementById('image_url');
  var coverRemove = document.getElementById('th-cover-remove');
  var coverStatus = document.getElementById('th-cover-status');
  var coverLabel = form.querySelector('[data-cover-label]');
  function showCover(url) {
    coverInput.value = url || '';
    coverImg.hidden = !url;
    if (url) coverImg.src = url; else coverImg.removeAttribute('src');
    coverRemove.hidden = !url;
    coverLabel.textContent = url ? 'Change photo' : 'Add a photo';
    changed();
  }
  coverFile.addEventListener('change', function () {
    var file = this.files[0];
    this.value = '';
    if (!file) return;
    coverStatus.textContent = 'Uploading…';
    upload(file).then(function (data) {
      coverStatus.textContent = '';
      showCover(data.url);
    }).catch(function (err) { coverStatus.textContent = err.message; });
  });
  coverRemove.addEventListener('click', function () { showCover(''); });
  coverInput.addEventListener('change', function () { showCover(coverInput.value.trim()); });
  coverImg.addEventListener('error', function () {
    if (coverInput.value) coverStatus.textContent = "That link didn't load a photo. Check it's a link to the image itself.";
  });
  coverImg.addEventListener('load', function () { coverStatus.textContent = ''; });

  /* ── Write / Preview, keeping your place ────────────────────── */
  var writePane = form.querySelector('[data-pane="write"]');
  var previewPane = form.querySelector('[data-pane="preview"]');
  var preview = document.getElementById('th-preview');
  var place = null;
  form.querySelectorAll('[data-tab]').forEach(function (tab) {
    tab.addEventListener('click', function () {
      var showPreview = tab.getAttribute('data-tab') === 'preview';
      if (showPreview === !previewPane.hidden) return;
      form.querySelectorAll('[data-tab]').forEach(function (t) {
        var on = t === tab;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      if (showPreview) {
        place = { start: ta.selectionStart, end: ta.selectionEnd, y: window.scrollY };
        preview.innerHTML = '<p class="text-muted">Loading preview…</p>';
        writePane.hidden = true;
        previewPane.hidden = false;
        var body = new FormData();
        body.append('content', ta.value);
        post(form.getAttribute('data-preview-url'), body).then(function (data) {
          preview.innerHTML = data.html || '<p class="text-muted">Nothing written yet.</p>';
        }).catch(function (err) { preview.textContent = err.message; });
      } else {
        previewPane.hidden = true;
        writePane.hidden = false;
        grow();
        if (place) {
          window.scrollTo(0, place.y);
          ta.focus({ preventScroll: true });
          ta.setSelectionRange(place.start, place.end);
        }
      }
    });
  });

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

  /* ── Videos ─────────────────────────────────────────────────── */
  var videos = document.getElementById('th-videos');
  form.querySelector('[data-add-video]').addEventListener('click', function () {
    var row = document.getElementById('th-video-row').content.cloneNode(true);
    videos.appendChild(row);
    videos.lastElementChild.querySelector('input').focus();
  });
  videos.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-remove-video]');
    if (btn) { btn.closest('.th-video-row').remove(); changed(); }
  });

  /* ── Drill and clip pickers ─────────────────────────────────── */
  function picker(field, kind) {
    var picked = document.getElementById('th-' + kind + 's-picked');
    function showPicked() {
      if (!picked) return;
      picked.innerHTML = '';
      form.querySelectorAll('input[name="' + field + '"]:checked').forEach(function (box) {
        var chip = document.createElement('span');
        chip.className = 'th-badge';
        chip.textContent = box.getAttribute('data-' + kind + '-title');
        picked.appendChild(chip);
      });
      if (!picked.children.length) {
        picked.innerHTML = '<span class="small text-muted">None linked</span>';
      }
    }
    form.addEventListener('change', function (e) {
      if (e.target.name === field) showPicked();
    });
    var search = form.querySelector('[data-' + kind + '-search]');
    if (search) {
      search.addEventListener('input', function () {
        var q = search.value.trim().toLowerCase();
        form.querySelectorAll('[data-' + kind + '-name]').forEach(function (row) {
          row.hidden = q && row.getAttribute('data-' + kind + '-name').indexOf(q) === -1;
        });
      });
    }
    showPicked();
  }
  picker('related_drills', 'drill');
  picker('clips', 'clip');
  picker('plays', 'play');

  /* ── A play from the playbook inside the text: [[play:<id>]] ──── */
  var playAt = null;
  var playButton = form.querySelector('[data-md="play"]');
  if (playButton) {
    playButton.addEventListener('click', function () { playAt = [ta.selectionStart, ta.selectionEnd]; });
    document.querySelectorAll('[data-insert-play]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sheet = btn.closest('.offcanvas');
        if (window.bootstrap && sheet) bootstrap.Offcanvas.getOrCreateInstance(sheet).hide();
        ta.focus();
        if (playAt) ta.setSelectionRange(playAt[0], playAt[1]);
        insertBlock('[[play:' + btn.getAttribute('data-insert-play') + ']]');
      });
    });
  }

  /* ── Draft kept on this device until saved ──────────────────── */
  var key = form.getAttribute('data-autosave-key');
  var fields = ['name', 'section_id', 'content', 'image_url', 'tags'];
  function snapshot() {
    var data = {};
    fields.forEach(function (f) { var el = document.getElementById(f); if (el) data[f] = el.value; });
    return data;
  }
  var initial = JSON.stringify(snapshot());
  var timer = null;
  function changed() {
    dirty = true;
    grow();
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
    var when = new Date(saved.at);
    banner.querySelector('[data-restore-when]').textContent =
      when.toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' });
    banner.querySelector('[data-restore]').addEventListener('click', function () {
      fields.forEach(function (f) {
        var el = document.getElementById(f);
        if (el && saved.data[f] !== undefined) el.value = saved.data[f];
      });
      showCover((saved.data.image_url || '').trim());
      banner.hidden = true;
      grow();
    });
    banner.querySelector('[data-discard]').addEventListener('click', function () {
      try { localStorage.removeItem(key); } catch (e) { /* ignore */ }
      banner.hidden = true;
    });
  }

  // The copy on this device is cleared once the topic page confirms the save
  // (a lost connection mid-save keeps it)
  form.addEventListener('submit', function () { dirty = false; });
  window.addEventListener('beforeunload', function (e) {
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });
})();
