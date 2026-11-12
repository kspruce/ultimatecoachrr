// Run mode: the session plan one block at a time, with a countdown that
// keeps the right time when the phone locks, and the screen kept awake.
(function () {
  const root = document.getElementById('run');
  if (!root) return;
  const blocks = JSON.parse(root.dataset.blocks || '[]');
  if (!blocks.length) return;
  const $ = function (id) { return document.getElementById(id); };
  const storeKey = 'run:' + location.pathname;

  // index: the block showing. endsAt: when its clock hits zero (running).
  // left: seconds left on a paused clock.
  let state = { index: 0, endsAt: null, left: null };
  try {
    const saved = JSON.parse(sessionStorage.getItem(storeKey) || 'null');
    if (saved && saved.index >= 0 && saved.index < blocks.length) state = saved;
  } catch (e) { /* start from the top */ }

  function save() {
    try { sessionStorage.setItem(storeKey, JSON.stringify(state)); } catch (e) { /* private window */ }
  }
  function seconds(block) { return block.duration_minutes ? block.duration_minutes * 60 : null; }
  function remaining() {
    if (state.endsAt !== null) return Math.round((state.endsAt - Date.now()) / 1000);
    if (state.left !== null) return state.left;
    return seconds(blocks[state.index]);
  }
  function clock(total) {
    const over = total < 0, t = Math.abs(total);
    return (over ? '+' : '') + Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0');
  }
  function text(el, value) {
    el.hidden = !value;
    (el.querySelector('div') || el).textContent = value || '';
  }

  function show() {
    const block = blocks[state.index];
    $('run-count').textContent = 'Block ' + (state.index + 1) + ' of ' + blocks.length;
    $('run-bar').style.width = ((state.index + 1) / blocks.length * 100) + '%';
    $('run-type').textContent = block.type_label + (block.focus_area ? ' · ' + block.focus_area : '');
    $('run-title').textContent = block.title;
    text($('run-cue'), block.coach_cue);
    text($('run-desc'), block.description);
    text($('run-notes'), block.notes);
    const drill = $('run-drill');
    drill.hidden = !block.drill_url;
    if (block.drill_url) drill.href = block.drill_url;
    $('run-prev').disabled = state.index === 0;
    $('run-next').disabled = state.index === blocks.length - 1;
    document.querySelectorAll('#run-list li').forEach(function (li, i) {
      li.classList.toggle('on', i === state.index);
      li.classList.toggle('done', i < state.index);
    });
    tick();
  }

  let buzzed = false;
  function tick() {
    const block = blocks[state.index], left = remaining();
    const el = $('run-clock'), note = $('run-clock-note'), go = $('run-go');
    if (left === null) {
      el.textContent = '–';
      el.classList.remove('over');
      note.textContent = 'No time set for this block';
      go.hidden = true;
      $('run-reset').hidden = true;
      return;
    }
    go.hidden = false;
    $('run-reset').hidden = false;
    el.textContent = clock(left);
    el.classList.toggle('over', left < 0);
    go.textContent = state.endsAt !== null ? 'Pause' : (state.left !== null ? 'Resume' : 'Start');
    note.textContent = left < 0 ? 'Over time: move on when you\'re ready'
      : block.duration_minutes + ' min block';
    if (left <= 0 && state.endsAt !== null && !buzzed) {
      buzzed = true;
      if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
    }
  }

  function go(index) {
    if (index < 0 || index >= blocks.length) return;
    const wasRunning = state.endsAt !== null;
    state = { index: index, endsAt: null, left: null };
    buzzed = false;
    // Carry straight on if the clock was running
    const total = seconds(blocks[index]);
    if (wasRunning && total) state.endsAt = Date.now() + total * 1000;
    save();
    show();
  }

  $('run-go').addEventListener('click', function () {
    if (state.endsAt !== null) {
      state.left = remaining();
      state.endsAt = null;
    } else {
      state.endsAt = Date.now() + remaining() * 1000;
      state.left = null;
    }
    save();
    tick();
  });
  $('run-reset').addEventListener('click', function () {
    state.endsAt = null;
    state.left = null;
    buzzed = false;
    save();
    tick();
  });
  $('run-prev').addEventListener('click', function () { go(state.index - 1); });
  $('run-next').addEventListener('click', function () { go(state.index + 1); });

  const list = $('run-list');
  let total = 0;
  blocks.forEach(function (block, i) {
    const li = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    const name = document.createElement('span');
    name.textContent = block.title;
    const mins = document.createElement('small');
    mins.textContent = block.duration_minutes ? block.duration_minutes + ' min' : '';
    button.append(name, mins);
    button.addEventListener('click', function () { go(i); window.scrollTo({ top: 0, behavior: 'smooth' }); });
    li.append(button);
    list.append(li);
    total += block.duration_minutes || 0;
  });
  if (total) $('run-total').textContent = total + ' minutes planned';

  setInterval(tick, 500);
  show();

  // Keep the screen on (where the browser can); ask again after a tab switch
  let lock = null;
  function stayAwake() {
    if (!('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
    navigator.wakeLock.request('screen').then(function (l) {
      lock = l;
      $('run-awake').hidden = false;
    }).catch(function () { /* battery saver, or not allowed */ });
  }
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') { stayAwake(); tick(); } else if (lock) { lock = null; }
  });
  stayAwake();
})();
