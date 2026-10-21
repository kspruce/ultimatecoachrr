// Drill diagram editor (templates/session/drills/editor.html).
//
// Drawing, arrows, stage movement and playback come from drill_diagram.js
// (DrillDiagram). Everything is drawn in field units, with the canvas zoomed
// to fit the screen. A drill has one or more stages (like the frames of an
// animation); only the current stage is on the canvas, the others are kept
// as plain objects. Saving posts the drill details, a PNG and an SVG of
// every stage, and the drawing itself (so it can be edited again) to the
// session blueprint's /api/drills routes.
document.addEventListener('DOMContentLoaded', function () {
    const DD = window.DrillDiagram;
    const {PX_PER_YARD, COLOURS, MOVERS, EXTRA_PROPS, mid} = DD;
    const YD = PX_PER_YARD;
    const PLACE_TOOLS = ['player-o', 'player-d', 'disc', 'cone', 'text'];
    const LINE_TOOLS = {cut: 'cut', throw: 'throw', move: 'move'};  // tool -> line style
    const TOOL_KEYS = {v: 'select', o: 'player-o', d: 'player-d', f: 'disc', c: 'cone',
                       l: 'cut', r: 'throw', m: 'move', p: 'path', a: 'area', t: 'text'};
    const TOOL_HINTS = {
        select: 'Drag to move; arrows drawn from a player follow them. Select an arrow to drag its points; double-click a point to remove it. Scroll to zoom, middle-drag or Alt-drag to pan.',
        cut: 'Start on a player and drag for a straight arrow, or click points and double-click (or Enter) to finish. Hold Shift for straight angles.',
        throw: 'Start on the disc and drag, or click points for a longer throw. Tick Curved, then drag the middle handle to bend it.',
        move: 'Dotted arrow for a defender or a jog. Drag, or click points and double-click to finish.',
        path: 'Draw freehand; an arrowhead is added at the end.',
        area: 'Drag to shade an area, such as a lane or the space a defender covers.',
    };
    const DELAYS = [0, 0.25, 0.5, 0.75];
    const MAX_STAGES = 20;
    const NON_USER = ['field', 'ghost'];

    const dataEl = document.getElementById('drill-data');
    const createUrl = dataEl.dataset.createUrl;
    let drillId = dataEl.dataset.drillId || null;
    let updateUrl = dataEl.dataset.updateUrl || null;
    const holder = document.querySelector('.canvas-holder');

    let field = DD.withDefaults(null);
    let stages = [{name: 'Stage 1', notes: '', objects: []}];
    let current = 0;
    let currentTool = 'select';
    let lineOptions = {colour: COLOURS.line, smooth: false, arrow: true, shape: 'rect'};
    let snapToGrid = false;
    let showGhosts = false;
    let dirty = false;
    let loading = false;
    let playback = false;   // the canvas is showing the animation, not the stage being edited
    let history = [];
    let future = [];
    let clipboard = null;
    let draft = null;       // the arrow being drawn: {points, from, preview, dragged}
    let areaDraft = null;   // the area being drawn: {start, shape}
    let panning = null;
    let baseZoom = 1;

    // ---- canvas -------------------------------------------------------------

    const canvas = new fabric.Canvas('drill-canvas', {
        backgroundColor: '#ffffff',
        selection: true,
        preserveObjectStacking: true,
        targetFindTolerance: 6,
        fireMiddleClick: true,
    });
    canvas.freeDrawingBrush = new fabric.PencilBrush(canvas);
    canvas.freeDrawingBrush.color = COLOURS.line;
    canvas.freeDrawingBrush.width = 3;

    const isUser = o => o.herdType && !NON_USER.includes(o.herdType);

    function userObjects() {
        return canvas.getObjects().filter(o => isUser(o) && o !== (draft && draft.preview) &&
                                               o !== (areaDraft && areaDraft.obj));
    }

    function drawField() {
        canvas.getObjects().filter(o => o.herdType === 'field').forEach(o => canvas.remove(o));
        DD.fieldParts(field).forEach((p, i) => canvas.insertAt(p, i));
        document.getElementById('field-size').textContent = `${field.length}×${field.width} yards`;
        document.getElementById('endzone-size').textContent = `${field.endzone} yards`;
        document.getElementById('field-view').value = field.view;
        fitToScreen();
    }

    // Layers, bottom up: field, ghosts of the last stage, areas, arrows, the rest
    function layerIndex(kind) {
        const below = {ghost: ['field'], area: ['field', 'ghost'], line: ['field', 'ghost', 'area']}[kind];
        return canvas.getObjects().filter(o => below.includes(o.herdType)).length;
    }

    function fitToScreen() {
        const view = DD.viewRect(field);
        const cw = holder.clientWidth;
        const ch = holder.clientHeight || cw * view.h / view.w;
        baseZoom = Math.min(cw / view.w, ch / view.h);
        canvas.setDimensions({width: cw, height: ch});
        // Part of the field: keep its far end on the right, so any spare
        // width shows more field rather than blank space
        const left = view.x ? cw - (view.x + view.w) * baseZoom
                            : (cw - view.w * baseZoom) / 2;
        canvas.setViewportTransform([baseZoom, 0, 0, baseZoom,
            left, (ch - view.h * baseZoom) / 2 - view.y * baseZoom]);
        canvas.getObjects().forEach(o => o.setCoords());
        canvas.requestRenderAll();
    }

    function zoomBy(factor, point) {
        const zoom = Math.min(baseZoom * 8, Math.max(baseZoom * 0.6, canvas.getZoom() * factor));
        const at = point || {x: canvas.getWidth() / 2, y: canvas.getHeight() / 2};
        canvas.zoomToPoint(new fabric.Point(at.x, at.y), zoom);
        canvas.getObjects().forEach(o => o.setCoords());
        canvas.requestRenderAll();
    }

    canvas.on('mouse:wheel', function (opt) {
        zoomBy(Math.pow(0.999, opt.e.deltaY), {x: opt.e.offsetX, y: opt.e.offsetY});
        opt.e.preventDefault();
        opt.e.stopPropagation();
    });

    // ---- objects ------------------------------------------------------------

    function newId() {
        return Math.random().toString(36).slice(2, 10);
    }

    function nextLabel(type, prefix) {
        const used = new Set(canvas.getObjects().filter(o => o.herdType === type).map(o => o.herdLabel));
        let n = 1;
        while (used.has(prefix + n)) n++;
        return prefix + n;
    }

    function makePlayer(type, x, y, label) {
        const offense = type === 'player-o';
        const fill = offense ? field.colours.offense : field.colours.defense;
        label = label || nextLabel(type, offense ? 'O' : 'D');
        const circle = new fabric.Circle({radius: 12, fill, stroke: '#ffffff', strokeWidth: 2,
            originX: 'center', originY: 'center'});
        const text = new fabric.Text(label, {fontSize: 11, fontWeight: 'bold', fill: DD.textOn(fill),
            fontFamily: 'Arial', originX: 'center', originY: 'center'});
        return new fabric.Group([circle, text], {left: x, top: y, originX: 'center',
            originY: 'center', herdType: type, herdLabel: label});
    }

    function makeObject(tool, x, y, label) {
        let obj = null;
        if (tool === 'player-o' || tool === 'player-d') obj = makePlayer(tool, x, y, label);
        if (tool === 'disc') {
            obj = new fabric.Circle({left: x, top: y, radius: 7, fill: COLOURS.disc, stroke: '#000',
                strokeWidth: 2, originX: 'center', originY: 'center', herdType: 'disc'});
        }
        if (tool === 'cone') {
            obj = new fabric.Triangle({left: x, top: y, width: 14, height: 14, fill: COLOURS.cone,
                stroke: '#7a3e00', strokeWidth: 1, originX: 'center', originY: 'center', herdType: 'cone'});
        }
        if (tool === 'text') {
            obj = new fabric.IText('Text', {left: x, top: y, fontSize: 16, fill: '#ffffff',
                fontFamily: 'Arial', fontWeight: 'bold', originX: 'center', originY: 'center',
                herdType: 'text', shadow: 'rgba(0,0,0,0.6) 1px 1px 2px'});
        }
        if (obj) obj.set('herdId', newId());
        return obj;
    }

    function makeLine(points, style, from) {
        const line = new DD.HerdLine({points: [], lineStyle: style, lineColour: lineOptions.colour,
                                      smooth: lineOptions.smooth, arrow: lineOptions.arrow,
                                      herdFrom: from || '', delay: style === 'throw' ? 0.5 : 0,
                                      herdId: newId()});
        line.setAbsolutePoints(points);
        line.setControls();
        return line;
    }

    // Arrows go under the players, so they come out from beneath them
    function addLine(line) {
        canvas.insertAt(line, layerIndex('line'));
    }

    function arrowHead(x, y, angleRad, colour) {
        return new fabric.Triangle({left: x, top: y, width: 12, height: 14, fill: colour,
            originX: 'center', originY: 'center', angle: angleRad * 180 / Math.PI + 90});
    }

    function rgba(hex, alpha) {
        const h = hex.replace('#', '');
        const [r, g, b] = [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16));
        return `rgba(${r},${g},${b},${alpha})`;
    }

    function areaStyle(colour) {
        return {fill: rgba(colour, 0.25), stroke: rgba(colour, 0.8), herdColour: colour};
    }

    function makeArea(shape, x, y, w, h, colour) {
        const common = {left: x, top: y, strokeWidth: 1.5, strokeUniform: true, herdType: 'area',
                        herdId: newId(), ...areaStyle(colour)};
        return shape === 'ellipse' ? new fabric.Ellipse({...common, rx: w / 2, ry: h / 2})
                                   : new fabric.Rect({...common, width: w, height: h, rx: 4, ry: 4});
    }

    // ---- point handles ------------------------------------------------------

    function linePointPosition(dim, finalMatrix, obj) {
        const p = this.midpoint ? DD.segmentMiddle(obj.points, obj.smooth, this.pointIndex)
                                : obj.points[this.pointIndex];
        const m = fabric.util.multiplyTransformMatrices(obj.canvas.viewportTransform,
                                                        obj.calcTransformMatrix());
        return fabric.util.transformPoint(new fabric.Point(p.x, p.y), m);
    }

    function renderPointControl(ctx, left, top) {
        ctx.save();
        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = '#0d6efd';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(left, top, 6, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
    }

    function renderMidControl(ctx, left, top) {
        ctx.save();
        ctx.fillStyle = 'rgba(13,110,253,0.35)';
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(left, top, 4.5, 0, 2 * Math.PI);
        ctx.fill();
        ctx.stroke();
        ctx.restore();
    }

    // Which player or disc an arrow starting on `target` belongs to: a throw
    // belongs to the disc, anything else to a player
    function ownerFor(style, target) {
        if (!target || !target.id) return '';
        return (style === 'throw') === (target.type === 'disc') ? target.id : '';
    }

    function dragPointTo(line, index, x, y, e) {
        const abs = line.absolutePoints();
        const neighbour = abs[index - 1] || abs[index + 1];
        const p = snapPoint({x, y}, e && e.shiftKey ? neighbour : null, line,
                            line.lineStyle === 'throw' ? 'disc' : null);
        abs[index] = {x: p.x, y: p.y};
        if (index === 0) line.herdFrom = ownerFor(line.lineStyle, p);
        line.setAbsolutePoints(abs);
        return true;
    }

    function movePoint(e, transform, x, y) {
        return dragPointTo(transform.target, transform.target.controls[transform.corner].pointIndex, x, y, e);
    }

    // Dragging a midpoint handle adds a point there (to bend a curve, or make
    // a corner), then moves it.
    function insertPoint(e, transform, x, y) {
        const line = transform.target;
        if (transform.herdIndex === undefined) {
            const i = line.controls[transform.corner].pointIndex;
            const abs = line.absolutePoints();
            abs.splice(i + 1, 0, DD.segmentMiddle(abs, line.smooth, i));
            line.setAbsolutePoints(abs);
            line.setControls();
            transform.herdIndex = i + 1;
        }
        return dragPointTo(line, transform.herdIndex, x, y, e);
    }

    DD.lineControls = function (line) {
        const controls = {};
        const n = line.points.length;
        line.points.forEach((p, i) => {
            controls['p' + i] = new fabric.Control({
                pointIndex: i, positionHandler: linePointPosition, actionHandler: movePoint,
                actionName: 'modifyLine', render: renderPointControl, cursorStyle: 'move',
            });
            if (i < n - 1) {
                controls['m' + i] = new fabric.Control({
                    pointIndex: i, midpoint: true, positionHandler: linePointPosition,
                    actionHandler: insertPoint, actionName: 'modifyLine',
                    render: renderMidControl, cursorStyle: 'copy',
                });
            }
        });
        return controls;
    };

    // ---- arrows follow their players ----------------------------------------

    function centreOf(o) {
        const c = o.getCenterPoint();
        return o.group ? fabric.util.transformPoint(c, o.group.calcTransformMatrix()) : c;
    }

    function moverById(id) {
        return id ? canvas.getObjects().find(o => o.herdId === id && MOVERS.includes(o.herdType)) : null;
    }

    // Keep each arrow's start on the player or disc it belongs to
    function followOwners() {
        canvas.getObjects().forEach(line => {
            if (line.type !== 'herdLine' || !line.herdFrom || line.group || line === (draft && draft.preview)) return;
            const owner = moverById(line.herdFrom);
            if (!owner) return;
            const c = centreOf(owner);
            const abs = line.absolutePoints();
            if (Math.hypot(abs[0].x - c.x, abs[0].y - c.y) < 0.5) return;
            abs[0] = {x: c.x, y: c.y};
            line.setAbsolutePoints(abs);
        });
    }

    // After an arrow is moved: it belongs to whatever it now starts on
    function relinkLine(line) {
        const start = line.absolutePoints()[0];
        let best = null, bestD = 1.2 * YD;
        canvas.getObjects().forEach(o => {
            if (!MOVERS.includes(o.herdType) || o.group) return;
            const c = o.getCenterPoint();
            const d = Math.hypot(c.x - start.x, c.y - start.y);
            if (d < bestD) { best = o; bestD = d; }
        });
        line.herdFrom = ownerFor(line.lineStyle, best && {id: best.herdId, type: best.herdType});
    }

    // ---- snapping -----------------------------------------------------------

    function snapGrid(p) {
        if (!snapToGrid) return p;
        return {x: Math.round(p.x / YD) * YD, y: Math.round(p.y / YD) * YD};
    }

    // Lock the angle from `from` to the nearest 15 degrees
    function snapAngle(p, from) {
        const dx = p.x - from.x, dy = p.y - from.y;
        const len = Math.hypot(dx, dy);
        const step = Math.PI / 12;
        const angle = Math.round(Math.atan2(dy, dx) / step) * step;
        return {x: from.x + Math.cos(angle) * len, y: from.y + Math.sin(angle) * len};
    }

    // Things an arrow end can snap to: players, discs, cones and the ends of
    // other arrows
    function snapTargets(except) {
        const targets = [];
        canvas.getObjects().forEach(o => {
            if (o === except || !isUser(o) || o === (draft && draft.preview)) return;
            if (o.type === 'herdLine') {
                const abs = o.absolutePoints();
                targets.push({p: abs[0]}, {p: abs[abs.length - 1]});
            } else if (MOVERS.includes(o.herdType) || o.herdType === 'cone') {
                const c = centreOf(o);
                targets.push({p: {x: c.x, y: c.y}, type: o.herdType,
                              id: MOVERS.includes(o.herdType) ? o.herdId : null});
            }
        });
        return targets;
    }

    // Returns {x, y}, plus the id and type of the player or disc it snapped to
    function snapPoint(p, angleFrom, except, prefer) {
        if (angleFrom) return snapAngle(p, angleFrom);
        const radius = 12 / canvas.getZoom();
        let best = null, bestD = radius;
        snapTargets(except).forEach(t => {
            let d = Math.hypot(t.p.x - p.x, t.p.y - p.y);
            if (prefer && t.type === prefer) d -= radius / 2;
            if (d < bestD) { best = t; bestD = d; }
        });
        return best ? {x: best.p.x, y: best.p.y, id: best.id, type: best.type} : snapGrid(p);
    }

    // ---- tools --------------------------------------------------------------

    function isLineTool(tool) {
        return Object.prototype.hasOwnProperty.call(LINE_TOOLS, tool);
    }

    function setTool(tool) {
        if (playback) exitPlayback();
        finishDraft();
        currentTool = tool;
        document.querySelectorAll('.tool-btn[data-tool]').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.tool === tool));
        canvas.isDrawingMode = tool === 'path';
        canvas.selection = tool === 'select';
        canvas.skipTargetFind = tool !== 'select';
        canvas.defaultCursor = tool === 'select' ? 'default' : 'crosshair';
        if (tool !== 'select') canvas.discardActiveObject();
        // Black shading looks muddy on the grass
        if (tool === 'area' && lineOptions.colour === COLOURS.line) lineOptions.colour = '#fab005';
        updateLineOptions();
        document.getElementById('tool-hint').textContent = TOOL_HINTS[tool] || '';
        canvas.requestRenderAll();
    }

    function updateDraftPreview(cursor) {
        const pts = cursor ? draft.points.concat([cursor]) : draft.points;
        if (pts.length < 2) return;
        if (!draft.preview) {
            loading = true;  // not an undo step until finished
            draft.preview = makeLine(pts, LINE_TOOLS[currentTool]);
            draft.preview.set({selectable: false, evented: false, opacity: 0.8});
            addLine(draft.preview);
            loading = false;
        } else {
            draft.preview.setAbsolutePoints(pts);
        }
        canvas.requestRenderAll();
    }

    function setDrafting(on) {
        document.getElementById('finish-arrow').classList.toggle('d-none', !on);
    }

    function finishDraft() {
        if (!draft) return;
        const d = draft;
        draft = null;
        setDrafting(false);
        if (d.preview) {
            loading = true;
            canvas.remove(d.preview);
            loading = false;
        }
        // Drop repeated points (e.g. from the clicks of a double-click)
        const pts = d.points.filter((p, i, all) => i === 0 ||
            Math.hypot(p.x - all[i - 1].x, p.y - all[i - 1].y) > 3).map(p => ({x: p.x, y: p.y}));
        const first = pts[0], last = pts[pts.length - 1];
        if (pts.length < 2 || Math.hypot(last.x - first.x, last.y - first.y) < 8) {
            canvas.requestRenderAll();
            return;
        }
        if (lineOptions.smooth && pts.length === 2) pts.splice(1, 0, mid(pts[0], pts[1]));
        const style = LINE_TOOLS[d.tool];
        addLine(makeLine(pts, style, ownerFor(style, d.points[0])));
        canvas.requestRenderAll();
    }

    function linePointer(opt) {
        const p = canvas.getPointer(opt.e);
        const prev = draft && draft.points[draft.points.length - 1];
        const prefer = LINE_TOOLS[currentTool] === 'throw' ? 'disc' : null;
        return snapPoint({x: p.x, y: p.y}, opt.e.shiftKey ? prev : null, null, prefer);
    }

    function startPan(opt) {
        panning = {x: opt.e.clientX, y: opt.e.clientY, selection: canvas.selection};
        canvas.selection = false;
        canvas.setCursor('grabbing');
    }

    canvas.on('mouse:down', function (opt) {
        if (opt.e.button === 1 || (opt.e.altKey && !opt.target && !canvas.isDrawingMode)) {
            startPan(opt);
            return;
        }
        if (playback) return;
        const p = canvas.getPointer(opt.e);
        if (PLACE_TOOLS.includes(currentTool)) {
            // Keep new things on the field
            const {w, h} = DD.logicalSize(field);
            const s = snapGrid(p);
            const x = Math.min(w - 8, Math.max(8, s.x));
            const y = Math.min(h - 8, Math.max(8, s.y));
            const obj = makeObject(currentTool, x, y);
            canvas.add(obj);
            if (currentTool === 'text') {
                setTool('select');
                canvas.setActiveObject(obj);
                obj.enterEditing();
                obj.selectAll();
            }
        } else if (currentTool === 'area') {
            const start = snapGrid(p);
            loading = true;
            const obj = makeArea(lineOptions.shape, start.x, start.y, 1, 1, lineOptions.colour);
            obj.set({selectable: false, evented: false});
            canvas.insertAt(obj, layerIndex('area'));
            loading = false;
            areaDraft = {start, obj};
        } else if (isLineTool(currentTool)) {
            const point = linePointer(opt);
            if (!draft) {
                draft = {tool: currentTool, points: [point], down: point, dragged: false};
                setDrafting(true);
            } else {
                const last = draft.points[draft.points.length - 1];
                // Clicking the last point again finishes the arrow
                if (Math.hypot(point.x - last.x, point.y - last.y) < 6 / canvas.getZoom()) {
                    finishDraft();
                    return;
                }
                draft.points.push(point);
                draft.down = point;
                updateDraftPreview(null);
            }
            draft.pressed = true;
        }
    });

    function areaBox(start, p) {
        const end = snapGrid(p);
        return {x: Math.min(start.x, end.x), y: Math.min(start.y, end.y),
                w: Math.abs(end.x - start.x), h: Math.abs(end.y - start.y)};
    }

    canvas.on('mouse:move', function (opt) {
        if (panning) {
            canvas.relativePan(new fabric.Point(opt.e.clientX - panning.x, opt.e.clientY - panning.y));
            panning.x = opt.e.clientX;
            panning.y = opt.e.clientY;
            return;
        }
        if (areaDraft) {
            const b = areaBox(areaDraft.start, canvas.getPointer(opt.e));
            const o = areaDraft.obj;
            o.set({left: b.x, top: b.y});
            o.type === 'ellipse' ? o.set({rx: b.w / 2, ry: b.h / 2}) : o.set({width: b.w, height: b.h});
            canvas.requestRenderAll();
            return;
        }
        if (!draft) return;
        const point = linePointer(opt);
        if (draft.pressed && Math.hypot(point.x - draft.down.x, point.y - draft.down.y) > 6) {
            draft.dragged = true;
        }
        updateDraftPreview(point);
    });

    canvas.on('mouse:up', function (opt) {
        if (panning) {
            canvas.selection = panning.selection;
            panning = null;
            canvas.getObjects().forEach(o => o.setCoords());
            canvas.setCursor(canvas.defaultCursor);
            return;
        }
        if (areaDraft) {
            const d = areaDraft;
            areaDraft = null;
            const b = areaBox(d.start, canvas.getPointer(opt.e));
            loading = true;
            canvas.remove(d.obj);
            loading = false;
            if (b.w > YD && b.h > YD) {
                canvas.insertAt(makeArea(lineOptions.shape, b.x, b.y, b.w, b.h, lineOptions.colour),
                                layerIndex('area'));
            }
            canvas.requestRenderAll();
            return;
        }
        if (!draft || !draft.pressed) return;
        draft.pressed = false;
        // A press-drag-release draws a straight arrow in one go
        if (draft.dragged && draft.points.length === 1) {
            draft.points.push(linePointer(opt));
            finishDraft();
        }
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
        path.set({fill: '', stroke: lineOptions.colour, strokeWidth: 3});
        canvas.add(new fabric.Group([path, arrowHead(end[0], end[1], angle, lineOptions.colour)],
            {herdType: 'cut', herdId: newId()}));
    });

    canvas.on('mouse:dblclick', function (opt) {
        if (playback) return;
        if (draft) {
            finishDraft();
            return;
        }
        const target = opt.target;
        if (!target) return;
        if (target.type === 'herdLine') {
            // Double-click a point to remove it
            const p = canvas.getPointer(opt.e);
            const abs = target.absolutePoints();
            const i = abs.findIndex(a => Math.hypot(a.x - p.x, a.y - p.y) < 8 / canvas.getZoom());
            if (i >= 0 && abs.length > 2) {
                abs.splice(i, 1);
                target.setAbsolutePoints(abs);
                target.setControls();
                if (i === 0) relinkLine(target);
                canvas.requestRenderAll();
                changed();
            }
            return;
        }
        // Double-click a player to rename them (e.g. "H1", "C2")
        if (!target.herdType || !target.herdType.startsWith('player')) return;
        const label = prompt('Player label', target.herdLabel || '');
        if (label === null) return;
        const text = target.getObjects().find(o => o.type === 'text');
        text.set('text', label.slice(0, 4));
        target.set('herdLabel', label.slice(0, 4));
        canvas.requestRenderAll();
        changed();
    });

    canvas.on('object:moving', function (e) {
        const o = e.target;
        if (snapToGrid && o.type !== 'herdLine' && o.type !== 'activeSelection' && o.herdType !== 'area') {
            const c = snapGrid(o.getCenterPoint());
            o.setPositionByOrigin(new fabric.Point(c.x, c.y), 'center', 'center');
        }
        if (o.type !== 'herdLine') followOwners();
    });

    function deleteSelected() {
        const active = canvas.getActiveObjects();
        if (!active.length) return;
        canvas.discardActiveObject();
        loading = true;
        active.forEach(o => canvas.remove(o));
        loading = false;
        canvas.requestRenderAll();
        changed();
    }

    function clearDrawing() {
        if (!userObjects().length || !confirm('Remove everything from this stage?')) return;
        loading = true;
        userObjects().forEach(o => canvas.remove(o));
        loading = false;
        changed();
    }

    // ---- set up: formations, defenders --------------------------------------

    // Positions in yards, attacking the right-hand endzone. Each is
    // [type, x, y, label]; the first player has the disc.
    const FORMATIONS = {
        vertical: (f, xd, cy) => [
            ['player-o', xd, cy, 'H1'], ['player-o', xd - 4, cy + 7, 'H2'],
            ...[0, 1, 2, 3, 4].map(k => ['player-o', xd + 10 + 4 * k, cy, 'C' + (k + 1)]),
        ],
        horizontal: (f, xd, cy) => [
            ['player-o', xd, cy, 'H1'], ['player-o', xd - 2, cy - 12, 'H2'], ['player-o', xd - 2, cy + 12, 'H3'],
            ...[-15, -5, 5, 15].map((dy, k) => ['player-o', xd + 15, cy + dy, 'C' + (k + 1)]),
        ],
        zone: (f, xd, cy) => [
            ['player-o', xd, cy, 'H1'], ['player-o', xd - 3, cy - 9, 'H2'], ['player-o', xd - 3, cy + 9, 'H3'],
            ['player-o', xd + 9, cy - 5, 'P1'], ['player-o', xd + 9, cy + 5, 'P2'],
            ['player-o', xd + 22, cy - 13, 'W1'], ['player-o', xd + 22, cy + 13, 'W2'],
            ['player-d', xd + 1.5, cy + 1.5, 'M'], ['player-d', xd + 3, cy - 3.5, 'C1'],
            ['player-d', xd + 3.5, cy + 4.5, 'C2'], ['player-d', xd + 13, cy - 12, 'W1'],
            ['player-d', xd + 13, cy + 12, 'W2'], ['player-d', xd + 14, cy, 'MM'],
            ['player-d', xd + 28, cy, 'DD'],
        ],
        endzone: (f, xd, cy) => {
            const goal = f.endzone + f.length;
            return [
                ['player-o', goal - 6, cy - 8, 'H1'], ['player-o', goal - 9, cy + 2, 'H2'],
                ['player-o', goal - 5, cy + 12, 'H3'],
                ...[0, 1, 2, 3].map(k => ['player-o', goal + 2 + 4 * k, cy, 'C' + (k + 1)]),
            ];
        },
    };

    function applyFormation(name) {
        const existing = userObjects().filter(o => MOVERS.includes(o.herdType) || o.type === 'herdLine');
        if (existing.length && !confirm('Replace the players, disc and arrows on this stage?')) return;
        exitPlaybackIfNeeded();
        const total = field.length + 2 * field.endzone;
        const xd = Math.max(field.endzone + 5, field.endzone + field.length - 35);
        const clampX = x => Math.min(total - 1, Math.max(1, x)) * YD;
        const clampY = y => Math.min(field.width - 1, Math.max(1, y)) * YD;
        const spots = FORMATIONS[name](field, xd, field.width / 2);
        canvas.discardActiveObject();
        loading = true;
        existing.forEach(o => canvas.remove(o));
        spots.forEach(([type, x, y, label]) => canvas.add(makeObject(type, clampX(x), clampY(y), label)));
        const [, x, y] = spots[0];
        canvas.add(makeObject('disc', clampX(x) + YD, clampY(y) - YD));
        loading = false;
        canvas.requestRenderAll();
        changed();
        if (name !== 'zone' && confirm('Add a defender on each player?')) matchDefenders();
    }

    // Put a defender on each offensive player that hasn't got one, on the
    // break side (away from the force) and a step towards the endzone they
    // attack; the player with the disc gets a mark.
    function matchDefenders() {
        exitPlaybackIfNeeded();
        const objects = canvas.getObjects();
        const offence = objects.filter(o => o.herdType === 'player-o');
        const defence = objects.filter(o => o.herdType === 'player-d').map(centreOf);
        const disc = objects.find(o => o.herdType === 'disc');
        const discAt = disc && centreOf(disc);
        let thrower = null;
        if (discAt) {
            let bestD = 3 * YD;
            offence.forEach(o => {
                const c = centreOf(o);
                const d = Math.hypot(c.x - discAt.x, c.y - discAt.y);
                if (d < bestD) { thrower = o; bestD = d; }
            });
        }
        const h = field.width * YD;
        let added = 0;
        loading = true;
        offence.forEach(o => {
            const c = centreOf(o);
            if (defence.some(d => Math.hypot(d.x - c.x, d.y - c.y) < 3 * YD)) return;
            let side = 0;   // -1: towards the top sideline, 1: towards the bottom
            if (field.force === 'down') side = -1;
            if (field.force === 'up') side = 1;
            if (field.force === 'middle') side = c.y < h / 2 ? -1 : 1;
            // Beside them (not on top of them): the mark goes downfield of the
            // thrower when there's no force
            const mark = o === thrower;
            const x = c.x + (mark && !side ? 2 : 0.8) * YD;
            const y = c.y + (mark && !side ? 0 : (side || -1) * 2) * YD;
            canvas.add(makeObject('player-d', x, y));
            added++;
        });
        loading = false;
        canvas.requestRenderAll();
        if (added) changed();
        else showNotification('Every offensive player already has a defender.', 'info');
    }

    // ---- line and area options ----------------------------------------------

    function selectedLines() {
        return canvas.getActiveObjects().filter(o => o.type === 'herdLine');
    }

    function selectedAreas() {
        return canvas.getActiveObjects().filter(o => o.herdType === 'area');
    }

    function toggleShown(id, shown) {
        document.getElementById(id).classList.toggle('d-none', !shown);
    }

    function updateLineOptions() {
        const lines = selectedLines();
        const areas = selectedAreas();
        const forLines = isLineTool(currentTool) || currentTool === 'path' || lines.length > 0;
        const forAreas = currentTool === 'area' || areas.length > 0;
        document.getElementById('line-options').classList.toggle('invisible', !forLines && !forAreas);
        const colour = lines[0] ? lines[0].lineColour : areas[0] ? areas[0].herdColour : lineOptions.colour;
        document.querySelectorAll('.line-colour').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.colour === colour));
        const source = lines[0] || lineOptions;
        document.getElementById('line-smooth').checked = source.smooth;
        document.getElementById('line-arrow').checked = source.arrow;
        toggleShown('line-shape-options', forLines);
        toggleShown('area-shape-group', forAreas && !lines.length);
        toggleShown('line-style-group', lines.length > 0);
        toggleShown('line-delay-group', lines.length > 0);
        if (lines.length) {
            document.querySelectorAll('[data-line-style]').forEach(btn =>
                btn.classList.toggle('active', btn.dataset.lineStyle === lines[0].lineStyle));
            const delay = DELAYS.reduce((a, b) => Math.abs(b - lines[0].delay) < Math.abs(a - lines[0].delay) ? b : a);
            document.getElementById('line-delay').value = String(delay);
        }
        const shape = areas[0] ? (areas[0].type === 'ellipse' ? 'ellipse' : 'rect') : lineOptions.shape;
        document.querySelectorAll('[data-area-shape]').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.areaShape === shape));
    }

    function applyToLines(props) {
        const lines = selectedLines();
        if (!lines.length) return false;
        lines.forEach(l => {
            if (props.smooth && !l.smooth && l.points.length === 2) {
                const abs = l.absolutePoints();
                abs.splice(1, 0, mid(abs[0], abs[1]));
                l.setAbsolutePoints(abs);
                l.setControls();
            }
            l.set(props);
            l._updateSize();
            l.setCoords();
        });
        canvas.requestRenderAll();
        return true;
    }

    document.querySelectorAll('.line-colour').forEach(btn => btn.addEventListener('click', () => {
        const colour = btn.dataset.colour;
        lineOptions.colour = colour;
        canvas.freeDrawingBrush.color = colour;
        const lines = applyToLines({lineColour: colour});
        const areas = selectedAreas();
        areas.forEach(a => a.set(areaStyle(colour)));
        canvas.requestRenderAll();
        if (lines || areas.length) changed();
        updateLineOptions();
    }));
    document.getElementById('line-smooth').addEventListener('change', e => {
        lineOptions.smooth = e.target.checked;
        if (applyToLines({smooth: e.target.checked})) changed();
    });
    document.getElementById('line-arrow').addEventListener('change', e => {
        lineOptions.arrow = e.target.checked;
        if (applyToLines({arrow: e.target.checked})) changed();
    });
    document.getElementById('line-delay').addEventListener('change', e => {
        if (applyToLines({delay: parseFloat(e.target.value)})) changed();
    });
    document.querySelectorAll('[data-line-style]').forEach(btn => btn.addEventListener('click', () => {
        if (applyToLines({lineStyle: btn.dataset.lineStyle})) {
            selectedLines().forEach(relinkLine);
            changed();
        }
        updateLineOptions();
    }));
    // Changing a selected area's shape swaps it for the other kind
    document.querySelectorAll('[data-area-shape]').forEach(btn => btn.addEventListener('click', () => {
        lineOptions.shape = btn.dataset.areaShape;
        const areas = selectedAreas();
        if (areas.length) {
            canvas.discardActiveObject();
            loading = true;
            areas.forEach(a => {
                const b = a.getBoundingRect(true, true);
                const index = canvas.getObjects().indexOf(a);
                canvas.remove(a);
                const swapped = makeArea(lineOptions.shape, b.left, b.top, b.width, b.height, a.herdColour);
                swapped.set('herdId', a.herdId);
                canvas.insertAt(swapped, index);
            });
            loading = false;
            changed();
        }
        updateLineOptions();
    }));
    document.getElementById('finish-arrow').addEventListener('click', finishDraft);
    document.getElementById('snap-grid').addEventListener('change', e => { snapToGrid = e.target.checked; });

    canvas.on('selection:created', updateLineOptions);
    canvas.on('selection:updated', updateLineOptions);
    canvas.on('selection:cleared', updateLineOptions);

    // ---- state, stages, undo ------------------------------------------------

    // Serialise as plain data, as each object would be outside any
    // multi-selection
    function serialiseObject(o) {
        return JSON.parse(JSON.stringify(canvas._toObject(o, 'toObject', EXTRA_PROPS)));
    }

    // (Not while a stage is still being put on the canvas, or playing)
    function commitStage() {
        if (loading || playback) return;
        stages[current].objects = userObjects().map(serialiseObject);
    }

    function editorState() {
        commitStage();
        return {version: 2, field: {...field},
                stages: stages.map(s => ({name: s.name, notes: s.notes, objects: s.objects}))};
    }

    function showObjects(objects) {
        loading = true;
        canvas.discardActiveObject();
        canvas.getObjects().filter(o => o.herdType && o.herdType !== 'field').forEach(o => canvas.remove(o));
        return DD.enliven(objects).then(enlivened => {
            enlivened.forEach(o => canvas.add(o));
            return addGhosts();
        }).then(() => {
            loading = false;
            canvas.requestRenderAll();
        });
    }

    // Faded copies of the last stage's players and disc
    async function addGhosts() {
        canvas.getObjects().filter(o => o.herdType === 'ghost').forEach(o => canvas.remove(o));
        if (!showGhosts || current === 0 || playback) return;
        const previous = stages[current - 1].objects.filter(o => MOVERS.includes(o.herdType));
        const ghosts = await DD.enliven(previous);
        ghosts.forEach(g => {
            g.set({opacity: 0.3, selectable: false, evented: false, herdType: 'ghost'});
            canvas.insertAt(g, layerIndex('ghost'));
        });
    }

    function snapshot() {
        return JSON.stringify({stages, current});
    }

    function changed() {
        if (loading || playback) return;
        dirty = true;
        commitStage();
        history.push(snapshot());
        if (history.length > 80) history.shift();
        future = [];
    }

    function restore(snap) {
        const s = JSON.parse(snap);
        stages = s.stages;
        current = Math.min(s.current, stages.length - 1);
        renderStageBar();
        return showObjects(stages[current].objects).then(() => { dirty = true; });
    }

    function undo() {
        if (history.length < 2) return;
        future.push(history.pop());
        restore(history[history.length - 1]);
    }

    function redo() {
        if (!future.length) return;
        const snap = future.pop();
        history.push(snap);
        restore(snap);
    }

    // Only finished drawing objects count (not the field, ghosts, or an arrow
    // while it is being drawn)
    canvas.on('object:added', e => { if (isUser(e.target)) changed(); });
    canvas.on('object:removed', e => { if (isUser(e.target)) changed(); });
    canvas.on('object:modified', function (e) {
        const o = e.target;
        if (o && o.type === 'herdLine') {
            o.setAbsolutePoints(o.absolutePoints());  // bake in any move
            o.setControls();
            if (!e.transform || e.transform.action === 'drag') relinkLine(o);
        } else if (o && o.type === 'activeSelection') {
            // Arrows moved without their player no longer belong to them
            o.getObjects().forEach(line => {
                if (line.type !== 'herdLine') return;
                const owner = moverById(line.herdFrom);
                if (!owner || owner.group !== o) line.herdFrom = '';
            });
        }
        followOwners();
        canvas.requestRenderAll();
        changed();
    });
    canvas.on('text:editing:exited', changed);

    function switchStage(index) {
        if (playback) {
            exitPlayback(index);
            return;
        }
        if (index === current || index < 0 || index >= stages.length || loading) return;
        finishDraft();
        commitStage();
        current = index;
        renderStageBar();
        showObjects(stages[current].objects);
    }

    function addStage(copyExactly) {
        exitPlaybackIfNeeded();
        if (stages.length >= MAX_STAGES) {
            showNotification(`A drill can have up to ${MAX_STAGES} stages.`, 'warning');
            return;
        }
        finishDraft();
        commitStage();
        const objects = stages[current].objects;
        stages.splice(current + 1, 0, {
            name: `Stage ${stages.length + 1}`,
            notes: '',
            objects: copyExactly ? JSON.parse(JSON.stringify(objects)) : DD.nextStageObjects(objects),
        });
        current += 1;
        renderStageBar();
        showObjects(stages[current].objects).then(changed);
    }

    function deleteStage() {
        exitPlaybackIfNeeded();
        if (stages.length < 2) {
            showNotification('A drill needs at least one stage. Use Clear to empty it.', 'warning');
            return;
        }
        if (!confirm(`Delete "${stages[current].name}"?`)) return;
        stages.splice(current, 1);
        current = Math.max(0, current - 1);
        renderStageBar();
        showObjects(stages[current].objects).then(changed);
    }

    function renameStage() {
        const name = prompt('Stage name', stages[current].name);
        if (name === null || !name.trim()) return;
        stages[current].name = name.trim().slice(0, 100);
        renderStageBar();
        changed();
    }

    function moveStage(delta) {
        exitPlaybackIfNeeded();
        const to = current + delta;
        if (to < 0 || to >= stages.length) return;
        commitStage();
        const [stage] = stages.splice(current, 1);
        stages.splice(to, 0, stage);
        current = to;
        renderStageBar();
        showObjects(stages[current].objects).then(changed);
    }

    function renderStageBar() {
        const tabs = document.getElementById('stage-tabs');
        tabs.innerHTML = '';
        stages.forEach((stage, i) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-sm stage-tab btn-outline-secondary';
            btn.textContent = stage.name;
            btn.title = 'Double-click to rename';
            btn.addEventListener('click', () => switchStage(i));
            btn.addEventListener('dblclick', () => { switchStage(i); renameStage(); });
            tabs.appendChild(btn);
        });
        highlightStage(current);
        document.getElementById('stage-notes').value = stages[current].notes || '';
        const scrubber = document.getElementById('stage-scrubber');
        scrubber.max = String(Math.max(1, stages.length - 1) * 1000);
        if (!playback) scrubber.value = String(current * 1000);
        const single = stages.length < 2;
        document.getElementById('play-stages').disabled = single;
        scrubber.disabled = single;
        document.getElementById('download-video').disabled = single;
    }

    function highlightStage(index) {
        document.querySelectorAll('#stage-tabs .stage-tab').forEach((btn, i) => {
            btn.classList.toggle('btn-primary', i === index);
            btn.classList.toggle('btn-outline-secondary', i !== index);
        });
        document.getElementById('stage-count').textContent = `${index + 1} / ${stages.length}`;
    }

    document.getElementById('stage-notes').addEventListener('change', e => {
        stages[current].notes = e.target.value.slice(0, 255);
        changed();
    });

    document.getElementById('show-ghosts').addEventListener('change', e => {
        showGhosts = e.target.checked;
        loading = true;
        addGhosts().then(() => {
            loading = false;
            canvas.requestRenderAll();
        });
    });

    // ---- playback -----------------------------------------------------------

    // While playing (or scrubbing), the canvas shows the animation; editing
    // comes back on the stage you choose (or the one you were on).
    const player = DD.createPlayer(canvas, () => stages, {
        onUpdate: function (position, playing) {
            const scrubber = document.getElementById('stage-scrubber');
            scrubber.value = String(Math.round(position * 1000));
            highlightStage(Math.min(Math.floor(position + 0.001), stages.length - 1));
            const btn = document.getElementById('play-stages');
            btn.innerHTML = playing ? '<i class="bi bi-pause-fill"></i> Pause' : '<i class="bi bi-play-fill"></i> Play';
            btn.classList.toggle('btn-success', !playing);
            btn.classList.toggle('btn-warning', playing);
        },
    });
    let playbackFrom = 0;

    function enterPlayback() {
        if (playback) return;
        finishDraft();
        if (currentTool !== 'select') setTool('select');
        canvas.discardActiveObject();
        commitStage();
        playbackFrom = current;
        playback = true;
        player.reset();
        canvas.skipTargetFind = true;
        canvas.selection = false;
        document.querySelector('.editor-main').classList.add('is-playing');
        toggleShown('exit-playback', true);
    }

    function exitPlayback(index) {
        if (!playback) return;
        player.pause();
        playback = false;
        current = index === undefined ? Math.min(Math.round(player.position), stages.length - 1) : index;
        document.querySelector('.editor-main').classList.remove('is-playing');
        toggleShown('exit-playback', false);
        canvas.skipTargetFind = currentTool !== 'select';
        canvas.selection = currentTool === 'select';
        renderStageBar();
        showObjects(stages[current].objects);
    }

    function exitPlaybackIfNeeded() {
        if (playback) exitPlayback();
    }

    async function togglePlay() {
        if (player.playing) {
            player.pause();
            return;
        }
        const fresh = !playback;
        enterPlayback();
        if (fresh) await player.seek(current === stages.length - 1 ? 0 : current);
        const finished = await player.play().then(() => player.position >= stages.length - 1);
        // Played to the end: back to editing where you started
        if (finished && playback && !player.playing) exitPlayback(playbackFrom);
    }

    document.getElementById('play-stages').addEventListener('click', togglePlay);
    document.getElementById('exit-playback').addEventListener('click', () => exitPlayback());
    document.getElementById('stage-scrubber').addEventListener('input', e => {
        const position = parseInt(e.target.value, 10) / 1000;
        enterPlayback();
        player.pause();
        player.seek(position);
    });
    document.getElementById('play-speed').addEventListener('change', e => {
        player.speed = parseFloat(e.target.value) || 1;
    });

    // ---- video --------------------------------------------------------------

    async function downloadVideo() {
        if (stages.length < 2) return;
        exitPlaybackIfNeeded();
        finishDraft();
        commitStage();
        if (!DD.videoType()) {
            showNotification('This browser cannot record video. Try Chrome, Edge or Safari.', 'warning');
            return;
        }
        const modal = videoModal();
        const status = modal.querySelector('.video-status');
        const result = modal.querySelector('.video-result');
        result.innerHTML = '';
        status.textContent = 'Recording… the video plays in real time.';
        bootstrap.Modal.getOrCreateInstance(modal).show();
        try {
            const speed = parseFloat(document.getElementById('play-speed').value) || 1;
            const {blob, extension} = await DD.recordVideo(field, stages, {
                speed,
                onUpdate: position => {
                    status.textContent = `Recording… stage ${Math.min(Math.floor(position) + 1, stages.length)} of ${stages.length}`;
                },
            });
            const url = URL.createObjectURL(blob);
            const name = (val('drill-title').trim() || 'drill').replace(/[^\w-]+/g, '_') + '.' + extension;
            status.textContent = 'Done.';
            const video = document.createElement('video');
            video.src = url;
            video.controls = true;
            video.className = 'w-100 border rounded mb-2';
            const link = document.createElement('a');
            link.href = url;
            link.download = name;
            link.className = 'btn btn-primary';
            link.innerHTML = '<i class="bi bi-download"></i> Download ' + extension.toUpperCase();
            result.append(video, link);
        } catch (err) {
            status.textContent = 'Could not record the video: ' + err.message;
        }
    }

    function videoModal() {
        let modal = document.getElementById('videoModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'modal fade';
            modal.id = 'videoModal';
            modal.tabIndex = -1;
            modal.innerHTML = `
                <div class="modal-dialog modal-lg modal-dialog-centered"><div class="modal-content">
                  <div class="modal-header"><h5 class="modal-title">Animation video</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
                  <div class="modal-body"><p class="video-status mb-2"></p><div class="video-result"></div></div>
                </div></div>`;
            document.body.appendChild(modal);
        }
        return modal;
    }

    document.getElementById('download-video').addEventListener('click', downloadVideo);

    // ---- export, save -------------------------------------------------------

    async function exportAll() {
        exitPlaybackIfNeeded();
        finishDraft();
        commitStage();
        const out = [];
        for (const stage of stages) out.push(await DD.exportStage(field, stage.objects));
        return out;
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
    async function saveDrill() {
        if (saving) return;
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (!csrfToken) {
            showNotification('Security token not found. Please refresh the page.', 'danger');
            return;
        }
        saving = true;
        try {
            const images = await exportAll();
            const form = new FormData();
            form.append('data', JSON.stringify(drillDetails()));
            images.forEach((img, i) => {
                form.append('diagram', dataUrlToBlob(img.png), `stage-${i + 1}.png`);
                form.append('svg', img.svg);
                form.append('stage_name', stages[i].name);
                form.append('stage_notes', stages[i].notes || '');
            });
            form.append('editor', JSON.stringify(editorState()));

            const r = await fetch(drillId ? updateUrl : createUrl, {
                method: drillId ? 'PUT' : 'POST',
                headers: {'X-CSRFToken': csrfToken},
                body: form,
            });
            const body = await r.json().catch(() => ({}));
            if (!r.ok || !body.success) throw new Error(body.message || `HTTP ${r.status}`);
            if (!drillId) {
                drillId = body.drill_id;
                updateUrl = `${createUrl}/${drillId}`;
                window.history.replaceState({}, '', body.editor_url);
            }
            dirty = false;
            showNotification('Drill saved.', 'success', body.detail_url);
        } catch (err) {
            showNotification('Could not save the drill: ' + err.message, 'danger');
        } finally {
            saving = false;
        }
    }

    async function showPreview() {
        const images = await exportAll();
        let modal = document.getElementById('previewModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'modal fade';
            modal.id = 'previewModal';
            modal.tabIndex = -1;
            modal.innerHTML = `
                <div class="modal-dialog modal-xl modal-dialog-centered modal-dialog-scrollable"><div class="modal-content">
                  <div class="modal-header"><h5 class="modal-title">Preview</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
                  <div class="modal-body"><div class="row g-3 preview-stages"></div></div>
                </div></div>`;
            document.body.appendChild(modal);
        }
        const list = modal.querySelector('.preview-stages');
        list.innerHTML = '';
        const base = (val('drill-title').trim() || 'drill').replace(/[^\w-]+/g, '_');
        images.forEach((img, i) => {
            const col = document.createElement('div');
            col.className = images.length > 1 ? 'col-lg-6' : 'col-12';
            const heading = document.createElement('div');
            heading.className = 'd-flex justify-content-between align-items-center mb-1';
            const name = document.createElement('strong');
            name.textContent = stages[i].name;
            const link = document.createElement('a');
            link.className = 'btn btn-sm btn-outline-secondary';
            link.href = img.png;
            link.download = images.length > 1 ? `${base}_${i + 1}.png` : `${base}.png`;
            link.textContent = 'Download PNG';
            heading.append(name, link);
            const image = document.createElement('img');
            image.className = 'img-fluid border rounded';
            image.alt = stages[i].name;
            image.src = img.png;
            col.append(heading, image);
            if (stages[i].notes) {
                const notes = document.createElement('div');
                notes.className = 'small text-muted mt-1';
                notes.textContent = stages[i].notes;
                col.appendChild(notes);
            }
            list.appendChild(col);
        });
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

    // ---- copy, paste, nudge -------------------------------------------------

    function copySelection() {
        const active = canvas.getActiveObjects();
        if (active.length) clipboard = active.map(serialiseObject);
    }

    // Pasted things keep their identity (so they animate) unless they're
    // already in this stage. One paste is one undo step.
    async function paste() {
        if (!clipboard) return;
        const here = new Set(userObjects().map(o => o.herdId));
        const offset = here.size ? 2 * YD : 0;
        const enlivened = await DD.enliven(clipboard);
        canvas.discardActiveObject();
        loading = true;
        enlivened.forEach(o => {
            if (here.has(o.herdId)) {
                o.set({herdId: newId(), left: o.left + offset, top: o.top + offset});
            }
            if (o.type === 'herdLine') addLine(o);
            else if (o.herdType === 'area') canvas.insertAt(o, layerIndex('area'));
            else canvas.add(o);
            o.setCoords();
        });
        enlivened.filter(o => o.type === 'herdLine').forEach(relinkLine);
        loading = false;
        if (enlivened.length > 1) {
            canvas.setActiveObject(new fabric.ActiveSelection(enlivened, {canvas}));
        } else if (enlivened.length) {
            canvas.setActiveObject(enlivened[0]);
        }
        canvas.requestRenderAll();
        changed();
    }

    function nudge(dx, dy) {
        const active = canvas.getActiveObject();
        if (!active) return;
        active.set({left: active.left + dx, top: active.top + dy});
        active.setCoords();
        canvas.requestRenderAll();
        canvas.fire('object:modified', {target: active});
    }

    // ---- field settings -----------------------------------------------------

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
        document.getElementById('field-force').value = field.force;
        document.getElementById('colour-offense').value = field.colours.offense;
        document.getElementById('colour-defense').value = field.colours.defense;
    }

    document.getElementById('apply-field-settings').addEventListener('click', function () {
        exitPlaybackIfNeeded();
        commitStage();
        const colours = {offense: val('colour-offense') || COLOURS.offense,
                         defense: val('colour-defense') || COLOURS.defense};
        const recolour = colours.offense !== field.colours.offense || colours.defense !== field.colours.defense;
        field = {
            ...field,
            length: clampInput('field-length', 40, 120, field.length),
            width: clampInput('field-width', 20, 60, field.width),
            endzone: clampInput('endzone-depth', 10, 40, field.endzone),
            grid: document.getElementById('show-grid').checked,
            markers: document.getElementById('show-yard-markers').checked,
            force: val('field-force') || 'none',
            colours,
        };
        fillFieldSettings();
        drawField();
        if (recolour) {
            stages.forEach(s => DD.recolourPlayers(s.objects, field));
            showObjects(stages[current].objects).then(changed);
        }
        dirty = true;
        bootstrap.Modal.getOrCreateInstance(document.getElementById('fieldSettingsModal')).hide();
    });

    document.getElementById('field-view').addEventListener('change', e => {
        field = {...field, view: e.target.value};
        drawField();
        dirty = true;
    });

    // ---- wiring -------------------------------------------------------------

    document.querySelectorAll('.tool-btn[data-tool]').forEach(btn =>
        btn.addEventListener('click', () => setTool(btn.dataset.tool)));
    document.querySelector('[data-action="delete"]').addEventListener('click', deleteSelected);
    document.querySelector('[data-action="clear"]').addEventListener('click', clearDrawing);
    document.querySelector('[data-action="undo"]').addEventListener('click', undo);
    document.querySelector('[data-action="redo"]').addEventListener('click', redo);
    document.getElementById('save-drill').addEventListener('click', saveDrill);
    document.getElementById('preview-drill').addEventListener('click', showPreview);
    document.getElementById('drill-title').addEventListener('input', () => { dirty = true; });
    document.getElementById('add-stage').addEventListener('click', () => addStage(false));
    document.getElementById('duplicate-stage').addEventListener('click', () => addStage(true));
    document.getElementById('rename-stage').addEventListener('click', renameStage);
    document.getElementById('delete-stage').addEventListener('click', deleteStage);
    document.getElementById('stage-left').addEventListener('click', () => moveStage(-1));
    document.getElementById('stage-right').addEventListener('click', () => moveStage(1));
    document.getElementById('zoom-in').addEventListener('click', () => zoomBy(1.25));
    document.getElementById('zoom-out').addEventListener('click', () => zoomBy(0.8));
    document.getElementById('zoom-fit').addEventListener('click', fitToScreen);
    document.querySelectorAll('[data-formation]').forEach(btn =>
        btn.addEventListener('click', () => applyFormation(btn.dataset.formation)));
    document.getElementById('match-defenders').addEventListener('click', matchDefenders);

    document.getElementById('save-properties').addEventListener('click', function () {
        dirty = true;
        bootstrap.Modal.getOrCreateInstance(document.getElementById('drillPropertiesModal')).hide();
    });

    document.addEventListener('keydown', function (e) {
        const active = canvas.getActiveObject();
        const el = document.activeElement;
        const typing = ['TEXTAREA', 'SELECT'].includes(el.tagName) || (active && active.isEditing) ||
            (el.tagName === 'INPUT' && !['range', 'checkbox', 'radio', 'button', 'color'].includes(el.type));
        const mod = e.ctrlKey || e.metaKey;
        const key = e.key.toLowerCase();
        if (mod && key === 's') {
            e.preventDefault();
            saveDrill();
            return;
        }
        if (typing) return;
        if (playback) {
            if (e.key === ' ') {
                e.preventDefault();
                togglePlay();
            } else if (e.key === 'Escape') {
                exitPlayback();
            }
            return;
        }
        if (mod && key === 'z') {
            e.preventDefault();
            e.shiftKey ? redo() : undo();
        } else if (mod && key === 'y') {
            e.preventDefault();
            redo();
        } else if (mod && key === 'c') {
            copySelection();
        } else if (mod && key === 'v') {
            e.preventDefault();
            paste();
        } else if (mod && key === 'd') {
            e.preventDefault();
            copySelection();
            paste();
        } else if (e.key === 'Enter' && draft) {
            finishDraft();
        } else if (e.key === 'Delete' || e.key === 'Backspace') {
            e.preventDefault();
            deleteSelected();
        } else if (e.key === 'Escape') {
            if (draft) finishDraft();
            else setTool('select');
        } else if (e.key.startsWith('Arrow') && active) {
            e.preventDefault();
            const step = (e.shiftKey ? 5 : 1) * YD;
            nudge({ArrowLeft: -step, ArrowRight: step}[e.key] || 0,
                  {ArrowUp: -step, ArrowDown: step}[e.key] || 0);
        } else if (e.key === 'PageDown' || e.key === ']') {
            switchStage(current + 1);
        } else if (e.key === 'PageUp' || e.key === '[') {
            switchStage(current - 1);
        } else if (e.key === ' ' && stages.length > 1) {
            e.preventDefault();
            togglePlay();
        } else if (key === '=' || key === '+') {
            zoomBy(1.25);
        } else if (key === '-') {
            zoomBy(0.8);
        } else if (key === '0') {
            fitToScreen();
        } else if (!mod && !e.altKey && TOOL_KEYS[key]) {
            setTool(TOOL_KEYS[key]);
        }
    });

    // Refit whenever the space for the field changes
    if (window.ResizeObserver) new ResizeObserver(fitToScreen).observe(holder);
    else window.addEventListener('resize', fitToScreen);
    window.addEventListener('beforeunload', function (e) {
        if (dirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    // ---- start --------------------------------------------------------------

    const saved = DD.normaliseState(JSON.parse(document.getElementById('editor-state').textContent || 'null'), newId);
    field = saved.field;
    stages = saved.stages;
    fillFieldSettings();
    drawField();
    setTool('select');
    renderStageBar();
    showObjects(stages[current].objects).then(function () {
        history = [snapshot()];
        dirty = false;
    });
});
