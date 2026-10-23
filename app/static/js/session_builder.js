// The session builder (templates/training/plan.html): blocks you can add,
// drag or nudge into order and time, saved as you go.
(() => {
  const data = JSON.parse(document.getElementById('pb-data').textContent);
  const list = document.getElementById('pb-blocks');
  const tpl = document.getElementById('pb-block-tpl');
  const statusEl = document.getElementById('pb-status');
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const FIELDS = ['title', 'component_type', 'duration_minutes', 'description', 'coach_cue', 'focus_area', 'notes'];
  const drills = Object.fromEntries(data.drills.map((d) => [d.id, d]));
  let published = data.published;
  let timer = null;
  let saving = false;
  let dirtyAgain = false;

  // ── Blocks ──────────────────────────────────────────────────────────────
  function addBlock(block, before = null) {
    const el = tpl.content.firstElementChild.cloneNode(true);
    el.dataset.id = block.id || '';
    el.dataset.drill = block.drill_id || '';
    FIELDS.forEach((f) => {
      const input = el.querySelector(`[name=${f}]`);
      if (input) input.value = block[f] ?? '';
    });
    if (!block.component_type) el.querySelector('[name=component_type]').value = 'drill';
    const drill = block.drill_id && drills[block.drill_id];
    if (drill || block.drill_title) {
      const tag = el.querySelector('[data-drill]');
      tag.hidden = false;
      tag.textContent = `Drill: ${(drill && drill.title) || block.drill_title}`;
    }
    if (block.description || block.coach_cue || block.notes) el.classList.add('open');
    list.insertBefore(el, before);
    return el;
  }

  function readBlocks() {
    return [...list.children].map((el) => {
      const block = {id: el.dataset.id ? Number(el.dataset.id) : null,
                     drill_id: el.dataset.drill ? Number(el.dataset.drill) : null};
      FIELDS.forEach((f) => { block[f] = el.querySelector(`[name=${f}]`).value; });
      return block;
    });
  }

  function setBlocks(blocks) {
    list.innerHTML = '';
    blocks.forEach((b) => addBlock(b));
    refresh();
  }

  // Clock times from the session's start, the total against its length
  function refresh() {
    let minutes = 0;
    const [h, m] = (data.start || '').split(':').map(Number);
    [...list.children].forEach((el) => {
      el.dataset.type = el.querySelector('[name=component_type]').value;
      const mins = Number(el.querySelector('[name=duration_minutes]').value) || 0;
      const clock = el.querySelector('[data-clock]');
      if (data.start) {
        const t = h * 60 + m + minutes;
        clock.textContent = `${String(Math.floor(t / 60) % 24).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
      } else {
        clock.textContent = `+${minutes}`;
      }
      el.querySelector('[data-mins]').textContent = mins ? `${mins} min` : '';
      minutes += mins;
    });
    document.getElementById('pb-empty').hidden = list.children.length > 0;
    const total = document.getElementById('pb-total');
    const over = data.length && minutes > data.length;
    total.classList.toggle('over', Boolean(over));
    total.lastElementChild.textContent = data.length
      ? `${minutes} of ${data.length} min${over ? ` – ${minutes - data.length} over` : minutes < data.length ? ` – ${data.length - minutes} free` : ''}`
      : `${minutes} min`;
  }

  // ── Saving ──────────────────────────────────────────────────────────────
  function setStatus(text, kind) {
    statusEl.textContent = text;
    statusEl.className = `pb-status ${kind || ''}`;
  }

  function changed() {
    refresh();
    setStatus('Unsaved changes', 'dirty');
    clearTimeout(timer);
    timer = setTimeout(save, 1500);
  }

  async function save(extra = {}) {
    clearTimeout(timer);
    if (saving) { dirtyAgain = true; return false; }
    saving = true;
    setStatus('Saving…');
    const blocks = readBlocks();
    try {
      const response = await fetch(data.saveUrl, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'Accept': 'application/json'},
        body: JSON.stringify({
          blocks, title: document.getElementById('pb-title').value,
          focus_area: document.getElementById('pb-focus').value,
          notes: document.getElementById('pb-notes').value, ...extra,
        }),
      });
      const result = await response.json();
      if (!result.ok) throw new Error(result.message || 'Could not save');
      // New blocks get their ids, in the same order
      [...list.children].forEach((el, i) => { if (result.blocks[i]) el.dataset.id = result.blocks[i].id; });
      published = result.published;
      setStatus('All saved', 'saved');
      return true;
    } catch (error) {
      setStatus(error.message, 'dirty');
      return false;
    } finally {
      saving = false;
      if (dirtyAgain) { dirtyAgain = false; changed(); }
    }
  }

  window.addEventListener('beforeunload', (event) => {
    if (statusEl.classList.contains('dirty')) event.preventDefault();
  });

  // ── Editing ─────────────────────────────────────────────────────────────
  list.addEventListener('input', changed);
  ['pb-title', 'pb-focus', 'pb-notes'].forEach((id) => document.getElementById(id).addEventListener('input', changed));

  list.addEventListener('click', (event) => {
    const button = event.target.closest('[data-act]');
    if (!button) return;
    const el = button.closest('.pb-block');
    const act = button.dataset.act;
    if (act === 'remove') {
      if (el.querySelector('[name=title]').value && !confirm('Remove this block?')) return;
      el.remove();
    } else if (act === 'up' && el.previousElementSibling) {
      list.insertBefore(el, el.previousElementSibling);
    } else if (act === 'down' && el.nextElementSibling) {
      list.insertBefore(el.nextElementSibling, el);
    } else if (act === 'more') {
      el.classList.toggle('open');
      return;
    } else {
      return;
    }
    button.focus();
    changed();
  });

  document.querySelectorAll('[data-add]').forEach((b) => b.addEventListener('click', () => {
    const el = addBlock({component_type: b.dataset.add, title: ''});
    changed();
    el.querySelector('[name=title]').focus();
  }));

  // Drag by the grip
  let dragged = null;
  list.addEventListener('mousedown', (event) => {
    const grip = event.target.closest('[data-grip]');
    if (grip) grip.closest('.pb-block').draggable = true;
  });
  list.addEventListener('dragstart', (event) => {
    dragged = event.target.closest('.pb-block');
    dragged.classList.add('dragging');
    event.dataTransfer.effectAllowed = 'move';
  });
  list.addEventListener('dragover', (event) => {
    event.preventDefault();
    const over = event.target.closest('.pb-block');
    list.querySelectorAll('.over').forEach((e) => e.classList.remove('over'));
    if (over && over !== dragged) over.classList.add('over');
  });
  list.addEventListener('drop', (event) => {
    event.preventDefault();
    const over = event.target.closest('.pb-block');
    if (dragged && over && over !== dragged) list.insertBefore(dragged, over);
    else if (dragged && !over) list.appendChild(dragged);
  });
  list.addEventListener('dragend', () => {
    list.querySelectorAll('.over').forEach((e) => e.classList.remove('over'));
    if (dragged) { dragged.classList.remove('dragging'); dragged.draggable = false; dragged = null; changed(); }
  });

  // ── Drill library ───────────────────────────────────────────────────────
  const lib = document.getElementById('pb-lib');
  function showDrills(query = '') {
    const q = query.trim().toLowerCase();
    const matches = data.drills.filter((d) => !q || d.title.toLowerCase().includes(q) || d.focus_area.toLowerCase().includes(q));
    lib.innerHTML = '';
    if (!matches.length) {
      lib.innerHTML = `<div class="tr-muted small">${data.drills.length ? 'No drills match.' : 'No drills saved yet.'}</div>`;
      return;
    }
    matches.slice(0, 80).forEach((d) => {
      const row = document.createElement('div');
      row.className = 'pb-lib-item';
      const name = document.createElement('span');
      name.textContent = d.title + (d.duration_minutes ? ` · ${d.duration_minutes} min` : '');
      name.title = d.description;
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'btn btn-sm btn-outline-primary';
      add.textContent = 'Add';
      add.setAttribute('aria-label', `Add ${d.title}`);
      add.addEventListener('click', () => {
        addBlock({title: d.title.slice(0, 100), component_type: 'drill', duration_minutes: d.duration_minutes,
                  description: d.description, focus_area: d.focus_area, drill_id: d.id});
        changed();
      });
      row.append(name, add);
      lib.appendChild(row);
    });
  }
  document.getElementById('pb-search').addEventListener('input', (e) => showDrills(e.target.value));

  // ── Starting points ─────────────────────────────────────────────────────
  function useBlocks(blocks) {
    const copies = blocks.map((b) => ({...b, id: null}));
    if (list.children.length && !confirm('Replace the blocks you have? OK replaces them; Cancel adds these to the end.')) {
      copies.forEach((b) => addBlock(b));
    } else {
      list.innerHTML = '';
      copies.forEach((b) => addBlock(b));
    }
    changed();
  }

  async function copySession(id) {
    const response = await fetch(data.copyUrl.replace('/0/', `/${id}/`), {headers: {'Accept': 'application/json'}});
    if (!response.ok) { alert('Could not load that session.'); return; }
    useBlocks((await response.json()).blocks);
  }

  document.querySelectorAll('[data-copy]').forEach((b) => b.addEventListener('click', () => copySession(b.dataset.copy)));
  document.getElementById('pb-start-from').addEventListener('change', (event) => {
    const value = event.target.value;
    event.target.value = '';
    if (value.startsWith('t')) {
      const i = data.templateIds.indexOf(Number(value.slice(1)));
      if (i >= 0) useBlocks(data.templates[i]);
    } else if (value.startsWith('s')) {
      copySession(value.slice(1));
    }
  });

  document.getElementById('pb-template').addEventListener('click', async () => {
    const blocks = readBlocks();
    if (!blocks.length) { alert('Add some blocks first.'); return; }
    const name = prompt('Name this template (e.g. "Standard warm-up + scrimmage"):');
    if (!name) return;
    const response = await fetch(data.templateUrl, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf, 'Accept': 'application/json'},
      body: JSON.stringify({name, blocks}),
    });
    const result = await response.json();
    if (!result.ok) { alert(result.message); return; }
    const i = data.templateIds.indexOf(result.id);
    if (i >= 0) { data.templates[i] = result.blocks; } else {
      data.templateIds.push(result.id);
      data.templates.push(result.blocks);
      const option = new Option(result.name, `t${result.id}`);
      const select = document.getElementById('pb-start-from');
      (select.querySelector('optgroup[label=Templates]') || select).appendChild(option);
    }
    setStatus(`Saved template "${result.name}"`, 'saved');
  });

  // ── Saving and publishing ───────────────────────────────────────────────
  document.getElementById('pb-save').addEventListener('click', () => save());
  const publishButton = document.getElementById('pb-publish');
  publishButton.addEventListener('click', async () => {
    const ok = await save({publish: !published});
    if (ok) {
      publishButton.textContent = published ? 'Unpublish' : 'Publish to players';
      publishButton.className = `btn ${published ? 'btn-outline-secondary' : 'btn-primary'}`;
      setStatus(published ? 'Published – players can see it' : 'Now a draft', 'saved');
    }
  });

  setBlocks(data.blocks);
  showDrills();
})();
