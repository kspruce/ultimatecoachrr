// Drill diagram editor (templates/session/drills/editor.html).
//
// Everything is drawn in field units: PX_PER_YARD logical pixels per yard,
// with the canvas zoomed to fit the screen. Saving posts the drill details,
// a PNG and an SVG of the diagram, and the drawing itself (so it can be
// edited again) to the session blueprint's /api/drills routes.
document.addEventListener('DOMContentLoaded', function () {
    const PX_PER_YARD = 10;
    const COLOURS = {offense: '#e03131', defense: '#1c7ed6', disc: '#ffffff',
                     cone: '#fd7e14', line: '#212529', field: '#5a9e4b'};
    const PLACE_TOOLS = ['player-o', 'player-d', 'disc', 'cone', 'text'];
    const TOOL_KEYS = {v: 'select', o: 'player-o', d: 'player-d', f: 'disc', c: 'cone',
                       p: 'path', r: 'throw', t: 'text'};
    const EXTRA_PROPS = ['herdType', 'herdLabel'];

    const dataEl = document.getElementById('drill-data');
    const createUrl = dataEl.dataset.createUrl;
    let drillId = dataEl.dataset.drillId || null;
    let updateUrl = dataEl.dataset.updateUrl || null;
    const holder = document.querySelector('.canvas-holder');

    let field = {length: 70, width: 40, endzone: 20, grid: false, markers: true};
    let currentTool = 'select';
    let dirty = false;
    let loading = false;
    let history = [];
    let throwLine = null;

    const canvas = new fabric.Canvas('drill-canvas', {
        backgroundColor: '#ffffff',
        selection: true,
        preserveObjectStacking: true,
    });
    canvas.freeDrawingBrush = new fabric.PencilBrush(canvas);
    canvas.freeDrawingBrush.color = COLOURS.line;
    canvas.freeDrawingBrush.width = 3;

    // ---- field --------------------------------------------------------------

    function logicalSize() {
        return {w: (field.length + 2 * field.endzone) * PX_PER_YARD,
                h: field.width * PX_PER_YARD};
    }

    function fieldObject(obj) {
        obj.set({selectable: false, evented: false, herdType: 'field'});
        return obj;
    }

    function drawField() {
        canvas.getObjects().filter(o => o.herdType === 'field').forEach(o => canvas.remove(o));
        const {w, h} = logicalSize();
        const y = PX_PER_YARD;
        const ez = field.endzone * y;
        const parts = [fieldObject(new fabric.Rect({left: 0, top: 0, width: w, height: h,
                                                     fill: COLOURS.field, strokeWidth: 0}))];
        if (field.grid) {
            for (let x = 5 * y; x < w; x += 5 * y) {
                parts.push(fieldObject(new fabric.Line([x, 0, x, h],
                    {stroke: 'rgba(255,255,255,0.18)', strokeWidth: 1})));
            }
            for (let gy = 5 * y; gy < h; gy += 5 * y) {
                parts.push(fieldObject(new fabric.Line([0, gy, w, gy],
                    {stroke: 'rgba(255,255,255,0.18)', strokeWidth: 1})));
            }
        }
        const line = {stroke: '#ffffff', strokeWidth: 2};
        parts.push(fieldObject(new fabric.Rect({left: 1, top: 1, width: w - 2, height: h - 2,
                                                 fill: '', ...line})));
        parts.push(fieldObject(new fabric.Line([ez, 0, ez, h], line)));
        parts.push(fieldObject(new fabric.Line([w - ez, 0, w - ez, h], line)));
        // Brick marks, 20 yards out from each endzone line
        [ez + 20 * y, w - ez - 20 * y].forEach(bx => {
            if (bx > ez && bx < w - ez) {
                parts.push(fieldObject(new fabric.Text('×', {left: bx, top: h / 2, fontSize: 18,
                    fill: '#ffffff', originX: 'center', originY: 'center'})));
            }
        });
        if (field.markers) {
            for (let yd = 10; yd < field.length; yd += 10) {
                parts.push(fieldObject(new fabric.Text(String(yd), {left: ez + yd * y, top: 4,
                    fontSize: 11, fill: 'rgba(255,255,255,0.8)', originX: 'center'})));
            }
        }
        parts.forEach((p, i) => canvas.insertAt(p, i));
        document.getElementById('field-size').textContent = `${field.length}×${field.width} yards`;
        document.getElementById('endzone-size').textContent = `${field.endzone} yards`;
        fitToScreen();
    }

    function fitToScreen() {
        const {w, h} = logicalSize();
        const cw = holder.clientWidth;
        const ch = holder.clientHeight || cw * h / w;
        const zoom = Math.min(cw / w, ch / h);
        canvas.setDimensions({width: cw, height: ch});
        canvas.setViewportTransform([zoom, 0, 0, zoom, (cw - w * zoom) / 2, (ch - h * zoom) / 2]);
        canvas.requestRenderAll();
    }

    // ---- objects ------------------------------------------------------------

    function nextLabel(type, prefix) {
        const used = canvas.getObjects().filter(o => o.herdType === type).length;
        return prefix + (used + 1);
    }

    function makePlayer(type, x, y) {
        const offense = type === 'player-o';
        const label = nextLabel(type, offense ? 'O' : 'D');
        const circle = new fabric.Circle({radius: 12, fill: offense ? COLOURS.offense : COLOURS.defense,
            stroke: '#ffffff', strokeWidth: 2, originX: 'center', originY: 'center'});
        const text = new fabric.Text(label, {fontSize: 11, fontWeight: 'bold', fill: '#ffffff',
            fontFamily: 'Arial', originX: 'center', originY: 'center'});
        return new fabric.Group([circle, text], {left: x, top: y, originX: 'center',
            originY: 'center', herdType: type, herdLabel: label});
    }

    function makeObject(tool, x, y) {
        if (tool === 'player-o' || tool === 'player-d') return makePlayer(tool, x, y);
        if (tool === 'disc') {
            return new fabric.Circle({left: x, top: y, radius: 7, fill: COLOURS.disc, stroke: '#000',
                strokeWidth: 2, originX: 'center', originY: 'center', herdType: 'disc'});
        }
        if (tool === 'cone') {
            return new fabric.Triangle({left: x, top: y, width: 14, height: 14, fill: COLOURS.cone,
                stroke: '#7a3e00', strokeWidth: 1, originX: 'center', originY: 'center', herdType: 'cone'});
        }
        if (tool === 'text') {
            return new fabric.IText('Text', {left: x, top: y, fontSize: 16, fill: '#ffffff',
                fontFamily: 'Arial', fontWeight: 'bold', originX: 'center', originY: 'center',
                herdType: 'text', shadow: 'rgba(0,0,0,0.6) 1px 1px 2px'});
        }
        return null;
    }

    function arrowHead(x, y, angleRad, colour) {
        return new fabric.Triangle({left: x, top: y, width: 12, height: 14, fill: colour,
            originX: 'center', originY: 'center', angle: angleRad * 180 / Math.PI + 90});
    }

    // ---- tools --------------------------------------------------------------

    function setTool(tool) {
        currentTool = tool;
        document.querySelectorAll('.tool-btn[data-tool]').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.tool === tool));
        canvas.isDrawingMode = tool === 'path';
        canvas.selection = tool === 'select';
        canvas.skipTargetFind = tool !== 'select';
        canvas.defaultCursor = tool === 'select' ? 'default' : 'crosshair';
        if (tool !== 'select') canvas.discardActiveObject();
        canvas.requestRenderAll();
    }

    canvas.on('mouse:down', function (opt) {
        const p = canvas.getPointer(opt.e);
        if (PLACE_TOOLS.includes(currentTool)) {
            // Keep new things on the field
            const {w, h} = logicalSize();
            const x = Math.min(w - 8, Math.max(8, p.x));
            const y = Math.min(h - 8, Math.max(8, p.y));
            const obj = makeObject(currentTool, x, y);
            canvas.add(obj);
            if (currentTool === 'text') {
                setTool('select');
                canvas.setActiveObject(obj);
                obj.enterEditing();
                obj.selectAll();
            }
        } else if (currentTool === 'throw') {
            throwLine = new fabric.Line([p.x, p.y, p.x, p.y], {stroke: COLOURS.line, strokeWidth: 2.5,
                strokeDashArray: [8, 6], selectable: false, evented: false});
            loading = true;  // not an undo step until finished
            canvas.add(throwLine);
            loading = false;
        }
    });

    canvas.on('mouse:move', function (opt) {
        if (!throwLine) return;
        const p = canvas.getPointer(opt.e);
        throwLine.set({x2: p.x, y2: p.y});
        canvas.requestRenderAll();
    });

    canvas.on('mouse:up', function () {
        if (!throwLine) return;
        const line = throwLine;
        throwLine = null;
        loading = true;
        canvas.remove(line);
        loading = false;
        const dx = line.x2 - line.x1;
        const dy = line.y2 - line.y1;
        if (Math.hypot(dx, dy) < 8) return;
        const angle = Math.atan2(dy, dx);
        // Stop the dashes short of the arrowhead
        const shortX = line.x2 - Math.cos(angle) * 8;
        const shortY = line.y2 - Math.sin(angle) * 8;
        const shaft = new fabric.Line([line.x1, line.y1, shortX, shortY], {stroke: COLOURS.line,
            strokeWidth: 2.5, strokeDashArray: [8, 6]});
        canvas.add(new fabric.Group([shaft, arrowHead(line.x2, line.y2, angle, COLOURS.line)],
            {herdType: 'throw'}));
    });

    // Freehand cut: add an arrowhead at the end
    canvas.on('path:created', function (opt) {
        const path = opt.path;
        const points = path.path.map(cmd => [cmd[cmd.length - 2], cmd[cmd.length - 1]]);
        const end = points[points.length - 1];
        let i = points.length - 2;
        while (i > 0 && Math.hypot(end[0] - points[i][0], end[1] - points[i][1]) < 6) i--;
        const before = points[Math.max(i, 0)];
        loading = true;
        canvas.remove(path);
        loading = false;
        if (points.length < 2) return;
        const angle = Math.atan2(end[1] - before[1], end[0] - before[0]);
        path.set({fill: '', stroke: COLOURS.line, strokeWidth: 3});
        canvas.add(new fabric.Group([path, arrowHead(end[0], end[1], angle, COLOURS.line)],
            {herdType: 'cut'}));
    });

    // Double-click a player to rename them (e.g. "H1", "C2")
    canvas.on('mouse:dblclick', function (opt) {
        const target = opt.target;
        if (!target || !target.herdType || !target.herdType.startsWith('player')) return;
        const label = prompt('Player label', target.herdLabel || '');
        if (label === null) return;
        const text = target.getObjects().find(o => o.type === 'text');
        text.set('text', label.slice(0, 4));
        target.set('herdLabel', label.slice(0, 4));
        canvas.requestRenderAll();
        changed();
    });

    function deleteSelected() {
        const active = canvas.getActiveObjects();
        if (!active.length) return;
        active.forEach(o => canvas.remove(o));
        canvas.discardActiveObject();
        canvas.requestRenderAll();
    }

    function clearDrawing() {
        if (!userObjects().length || !confirm('Remove everything from the field?')) return;
        userObjects().forEach(o => canvas.remove(o));
    }

    // ---- state, undo --------------------------------------------------------

    function userObjects() {
        return canvas.getObjects().filter(o => o.herdType && o.herdType !== 'field');
    }

    function editorState() {
        return {version: 1, field: {...field},
                objects: userObjects().map(o => o.toObject(EXTRA_PROPS))};
    }

    function loadObjects(objects, done) {
        loading = true;
        userObjects().forEach(o => canvas.remove(o));
        fabric.util.enlivenObjects(objects || [], function (enlivened) {
            enlivened.forEach(o => canvas.add(o));
            loading = false;
            canvas.requestRenderAll();
            if (done) done();
        });
    }

    function changed() {
        if (loading) return;
        dirty = true;
        history.push(JSON.stringify(editorState().objects));
        if (history.length > 50) history.shift();
    }

    function undo() {
        if (history.length < 2) return;
        history.pop();
        loadObjects(JSON.parse(history[history.length - 1]), () => { dirty = true; });
    }

    // Only finished drawing objects count (not the field, or a cut or throw
    // while it is being drawn)
    const isDrawing = o => o.herdType && o.herdType !== 'field';
    canvas.on('object:added', e => { if (isDrawing(e.target)) changed(); });
    canvas.on('object:removed', e => { if (isDrawing(e.target)) changed(); });
    canvas.on('object:modified', changed);
    canvas.on('text:editing:exited', changed);

    // ---- export, save -------------------------------------------------------

    // Render at field size (not screen size) for the PNG and SVG
    function exportImages() {
        canvas.discardActiveObject();
        const vpt = canvas.viewportTransform.slice();
        const dims = {width: canvas.getWidth(), height: canvas.getHeight()};
        const {w, h} = logicalSize();
        canvas.setDimensions({width: w, height: h});
        canvas.setViewportTransform([1, 0, 0, 1, 0, 0]);
        const png = canvas.toDataURL({format: 'png', multiplier: 2});
        const svg = canvas.toSVG({width: w, height: h, viewBox: {x: 0, y: 0, width: w, height: h}});
        canvas.setDimensions(dims);
        canvas.setViewportTransform(vpt);
        canvas.requestRenderAll();
        return {png, svg};
    }

    function dataUrlToBlob(dataUrl) {
        const [meta, b64] = dataUrl.split(',');
        const bytes = atob(b64);
        const arr = new Uint8Array(bytes.length);
        for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
        return new Blob([arr], {type: meta.split(':')[1].split(';')[0]});
    }

    function val(id) {
        const el = document.getElementById(id);
        return el ? el.value : '';
    }

    function drillDetails() {
        return {
            title: val('drill-title').trim() || 'Untitled Drill',
            description: val('drill-description'),
            setup_instructions: val('setup-instructions'),
            skill_level: val('skill-level'),
            focus_area: val('focus-area'),
            recommended_duration: val('recommended-duration'),
            equipment_needed: val('equipment-needed'),
            min_players: val('min-players'),
            max_players: val('max-players'),
            is_public: document.getElementById('is-public').checked,
        };
    }

    let saving = false;
    function saveDrill() {
        if (saving) return;
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (!csrfToken) {
            showNotification('Security token not found. Please refresh the page.', 'danger');
            return;
        }
        saving = true;
        const {png, svg} = exportImages();
        const form = new FormData();
        form.append('data', JSON.stringify(drillDetails()));
        form.append('diagram', dataUrlToBlob(png), 'diagram.png');
        form.append('svg', svg);
        form.append('editor', JSON.stringify(editorState()));

        fetch(drillId ? updateUrl : createUrl, {
            method: drillId ? 'PUT' : 'POST',
            headers: {'X-CSRFToken': csrfToken},
            body: form,
        })
            .then(r => r.json().catch(() => ({})).then(body => {
                if (!r.ok || !body.success) throw new Error(body.message || `HTTP ${r.status}`);
                return body;
            }))
            .then(body => {
                if (!drillId) {
                    drillId = body.drill_id;
                    updateUrl = `${createUrl}/${drillId}`;
                    window.history.replaceState({}, '', body.editor_url);
                }
                dirty = false;
                showNotification('Drill saved.', 'success', body.detail_url);
            })
            .catch(err => showNotification('Could not save the drill: ' + err.message, 'danger'))
            .finally(() => { saving = false; });
    }

    function showPreview() {
        const {png} = exportImages();
        let modal = document.getElementById('previewModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'modal fade';
            modal.id = 'previewModal';
            modal.tabIndex = -1;
            modal.innerHTML = `
                <div class="modal-dialog modal-xl modal-dialog-centered"><div class="modal-content">
                  <div class="modal-header"><h5 class="modal-title">Preview</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
                  <div class="modal-body text-center"><img class="img-fluid border rounded" alt="Diagram preview"></div>
                  <div class="modal-footer"><a class="btn btn-outline-secondary" download="diagram.png">Download PNG</a></div>
                </div></div>`;
            document.body.appendChild(modal);
        }
        modal.querySelector('img').src = png;
        modal.querySelector('a[download]').href = png;
        modal.querySelector('a[download]').download =
            (val('drill-title').trim() || 'drill').replace(/[^\w-]+/g, '_') + '.png';
        bootstrap.Modal.getOrCreateInstance(modal).show();
    }

    function showNotification(message, type, link) {
        const note = document.createElement('div');
        note.className = `alert alert-${type} position-fixed top-0 end-0 m-3 shadow`;
        note.style.zIndex = '9999';
        note.textContent = message + ' ';
        if (link) {
            const a = document.createElement('a');
            a.href = link;
            a.className = 'alert-link';
            a.textContent = 'View drill';
            note.appendChild(a);
        }
        document.body.appendChild(note);
        setTimeout(() => note.remove(), 4000);
    }

    // ---- wiring -------------------------------------------------------------

    document.querySelectorAll('.tool-btn[data-tool]').forEach(btn =>
        btn.addEventListener('click', () => setTool(btn.dataset.tool)));
    document.querySelector('[data-action="delete"]').addEventListener('click', deleteSelected);
    document.querySelector('[data-action="clear"]').addEventListener('click', clearDrawing);
    document.getElementById('save-drill').addEventListener('click', saveDrill);
    document.getElementById('preview-drill').addEventListener('click', showPreview);
    document.getElementById('drill-title').addEventListener('input', () => { dirty = true; });

    document.getElementById('save-properties').addEventListener('click', function () {
        dirty = true;
        bootstrap.Modal.getOrCreateInstance(document.getElementById('drillPropertiesModal')).hide();
    });

    function clampInput(id, min, max, fallback) {
        const n = parseInt(val(id), 10);
        return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
    }

    function fillFieldSettings() {
        document.getElementById('field-length').value = field.length;
        document.getElementById('field-width').value = field.width;
        document.getElementById('endzone-depth').value = field.endzone;
        document.getElementById('show-grid').checked = field.grid;
        document.getElementById('show-yard-markers').checked = field.markers;
    }

    document.getElementById('apply-field-settings').addEventListener('click', function () {
        field = {
            length: clampInput('field-length', 40, 120, field.length),
            width: clampInput('field-width', 20, 60, field.width),
            endzone: clampInput('endzone-depth', 10, 40, field.endzone),
            grid: document.getElementById('show-grid').checked,
            markers: document.getElementById('show-yard-markers').checked,
        };
        fillFieldSettings();
        drawField();
        dirty = true;
        bootstrap.Modal.getOrCreateInstance(document.getElementById('fieldSettingsModal')).hide();
    });

    document.addEventListener('keydown', function (e) {
        const active = canvas.getActiveObject();
        const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) ||
            (active && active.isEditing);
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
            e.preventDefault();
            saveDrill();
            return;
        }
        if (typing) return;
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
            e.preventDefault();
            undo();
        } else if (e.key === 'Delete' || e.key === 'Backspace') {
            e.preventDefault();
            deleteSelected();
        } else if (e.key === 'Escape') {
            setTool('select');
        } else if (!e.ctrlKey && !e.metaKey && !e.altKey && TOOL_KEYS[e.key.toLowerCase()]) {
            setTool(TOOL_KEYS[e.key.toLowerCase()]);
        }
    });

    window.addEventListener('resize', fitToScreen);
    window.addEventListener('beforeunload', function (e) {
        if (dirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    // ---- start --------------------------------------------------------------

    const saved = JSON.parse(document.getElementById('editor-state').textContent || 'null');
    if (saved && saved.field) field = {...field, ...saved.field};
    fillFieldSettings();
    drawField();
    setTool('select');
    loadObjects(saved ? saved.objects : [], function () {
        history = [JSON.stringify(editorState().objects)];
        dirty = false;
    });
});
