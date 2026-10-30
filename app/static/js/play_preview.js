// Plays a playbook play's animation in place: from the playbook list or a
// session (in a pop-up), or on a game-day card (in the card, instead of its
// stage pictures). Nothing loads until a play is tapped: then fabric,
// drill_diagram.js and the play's drawing (/playbook/plays/<id>/drawing.json).
//
//   <button data-play-preview="/playbook/plays/3/drawing.json">        pop-up
//   <button data-play-preview="…" data-inline=".gd-stages">            in the card
//
// The page loads this script with data-fabric and data-diagram (the two
// scripts' URLs).
(function () {
    'use strict';
    const me = document.currentScript;
    let ready = null;

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = () => reject(new Error('Could not load ' + src));
            document.head.appendChild(s);
        });
    }

    function libraries() {
        if (!ready) {
            ready = (window.fabric ? Promise.resolve() : loadScript(me.dataset.fabric))
                .then(() => (window.DrillDiagram ? null : loadScript(me.dataset.diagram)));
            ready.catch(() => { ready = null; });
        }
        return ready;
    }

    function addStyles() {
        if (document.getElementById('pb-preview-styles')) return;
        const style = document.createElement('style');
        style.id = 'pb-preview-styles';
        style.textContent = `
.pb-preview { background: #fff; border: 1px solid var(--rule, #dee2e6); border-radius: 10px; overflow: hidden; }
.pb-preview canvas { display: block; }
.pb-preview-bar { display: flex; align-items: center; gap: .6rem; padding: .45rem .6rem; font-size: .85rem;
                  background: var(--card, #fff); color: var(--ink, inherit); border-top: 1px solid var(--rule, #dee2e6); }
.pb-preview-bar button { min-height: 36px; }
.pb-preview-bar .cap { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pb-preview-in-card { margin: 0 1rem .5rem; }
[data-play-preview].pb-thumb-btn { position: relative; padding: 0; border: 0; background: none; flex-shrink: 0; line-height: 0; }
[data-play-preview].pb-thumb-btn .pb-thumb-play { position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; color: #fff; font-size: 1.1rem; text-shadow: 0 1px 3px rgba(0,0,0,.6); }`;
        document.head.appendChild(style);
    }

    // A player in `holder`: canvas, play/pause and the stage's name. Returns
    // a function that stops and removes it.
    function mount(holder, payload) {
        const DD = window.DrillDiagram;
        const saved = DD.normaliseState(payload.drawing, () => Math.random().toString(36).slice(2, 10));
        const field = saved.field;
        const stages = saved.stages;
        const box = document.createElement('div');
        box.className = 'pb-preview';
        const el = document.createElement('canvas');
        const bar = document.createElement('div');
        bar.className = 'pb-preview-bar';
        bar.innerHTML = '<button type="button" class="btn btn-sm btn-success"></button><span class="cap"></span>';
        box.append(el, bar);
        holder.appendChild(box);
        const btn = bar.querySelector('button');
        const cap = bar.querySelector('.cap');
        if (stages.length < 2) btn.hidden = true;

        const view = DD.viewRect(field);
        const width = box.clientWidth || holder.clientWidth || 320;
        const zoom = width / view.w;
        const canvas = new fabric.StaticCanvas(el, {width, height: Math.round(view.h * zoom),
                                                    backgroundColor: '#ffffff', renderOnAddRemove: false});
        canvas.setViewportTransform([zoom, 0, 0, zoom, -view.x * zoom, -view.y * zoom]);
        DD.fieldParts(field).forEach(p => canvas.add(p));
        const player = DD.createPlayer(canvas, () => stages, {
            mapObjects: objects => DD.viewObjects(objects, {defence: payload.defence}),
            onUpdate: (position, playing) => {
                const i = Math.min(Math.floor(position + 0.001), stages.length - 1);
                cap.textContent = stages.length > 1 ? `${i + 1}/${stages.length} · ${stages[i].name}` : '';
                btn.innerHTML = playing ? '<i class="bi bi-pause-fill"></i> Pause'
                    : (position >= stages.length - 1 ? '<i class="bi bi-arrow-counterclockwise"></i> Again'
                                                     : '<i class="bi bi-play-fill"></i> Play');
            },
        });
        btn.addEventListener('click', () => (player.playing ? player.pause() : player.play()));
        player.seek(0).then(() => { if (stages.length > 1) player.play(); });
        return function () {
            player.pause();
            canvas.dispose();
            box.remove();
        };
    }

    function fetchDrawing(url) {
        return fetch(url, {credentials: 'same-origin', headers: {'Accept': 'application/json'}})
            .then(r => { if (!r.ok) throw new Error('Could not load the play.'); return r.json(); });
    }

    // ── Pop-up ───────────────────────────────────────────────────
    let modal = null;
    let unmount = null;

    function popUp() {
        if (modal) return modal;
        modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.tabIndex = -1;
        modal.setAttribute('aria-hidden', 'true');
        modal.innerHTML = `
<div class="modal-dialog modal-dialog-centered modal-lg">
  <div class="modal-content">
    <div class="modal-header"><h5 class="modal-title"></h5>
      <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button></div>
    <div class="modal-body"><div class="pb-preview-holder"></div></div>
    <div class="modal-footer"><a class="btn btn-outline-primary" href="#">Open the play</a></div>
  </div>
</div>`;
        document.body.appendChild(modal);
        modal.addEventListener('hidden.bs.modal', () => { if (unmount) unmount(); unmount = null; });
        return modal;
    }

    function openPopUp(trigger) {
        const m = popUp();
        const holder = m.querySelector('.pb-preview-holder');
        m.querySelector('.modal-title').textContent = trigger.dataset.title || 'Play';
        holder.innerHTML = '<div class="text-center text-muted py-5">Loading…</div>';
        const link = m.querySelector('.modal-footer a');
        link.href = trigger.dataset.href || '#';
        const shown = new Promise(resolve => m.addEventListener('shown.bs.modal', resolve, {once: true}));
        bootstrap.Modal.getOrCreateInstance(m).show();
        Promise.all([libraries(), fetchDrawing(trigger.dataset.playPreview), shown]).then(([, payload]) => {
            if (!m.classList.contains('show')) return;  // closed while it loaded
            holder.innerHTML = '';
            m.querySelector('.modal-title').textContent = payload.name;
            link.href = payload.url;
            if (unmount) unmount();
            unmount = mount(holder, payload);
        }).catch(e => {
            holder.innerHTML = '';
            const p = document.createElement('p');
            p.className = 'text-danger mb-0';
            p.textContent = e.message;
            holder.appendChild(p);
        });
    }

    // ── In a card ────────────────────────────────────────────────
    function toggleInline(trigger) {
        const card = trigger.closest('[data-preview-card]') || document;
        const target = card.querySelector(trigger.dataset.inline);
        if (trigger._unmount) {
            trigger._unmount();
            trigger._unmount = null;
            if (target) target.hidden = false;
            trigger.innerHTML = trigger._label;
            return;
        }
        trigger._label = trigger._label || trigger.innerHTML;
        trigger.disabled = true;
        Promise.all([libraries(), fetchDrawing(trigger.dataset.playPreview)]).then(([, payload]) => {
            const holder = document.createElement('div');
            holder.className = 'pb-preview-in-card';
            (target || trigger).insertAdjacentElement(target ? 'beforebegin' : 'afterend', holder);
            if (target) target.hidden = true;
            const stop = mount(holder, payload);
            trigger._unmount = () => { stop(); holder.remove(); };
            trigger.innerHTML = '<i class="bi bi-images"></i> Stages';
        }).catch(e => window.alert(e.message)).finally(() => { trigger.disabled = false; });
    }

    addStyles();
    document.addEventListener('click', e => {
        const trigger = e.target.closest('[data-play-preview]');
        if (!trigger) return;
        e.preventDefault();
        e.stopPropagation();
        if (trigger.dataset.inline) toggleInline(trigger);
        else openPopUp(trigger);
    });
})();
