// Drill diagram editor (templates/session/drills/editor.html).
//
// Everything is drawn in field units: PX_PER_YARD logical pixels per yard,
// with the canvas zoomed to fit the screen. A drill has one or more stages
// (like the frames of an animation); only the current stage is on the
// canvas, the others are kept as plain objects. Saving posts the drill
// details, a PNG and an SVG of every stage, and the drawing itself (so it can
// be edited again) to the session blueprint's /api/drills routes.
document.addEventListener('DOMContentLoaded', function () {
    const PX_PER_YARD = 10;
    const COLOURS = {offense: '#e03131', defense: '#1c7ed6', disc: '#ffffff',
                     cone: '#fd7e14', line: '#212529', field: '#5a9e4b'};
    const PLACE_TOOLS = ['player-o', 'player-d', 'disc', 'cone', 'text'];
    const LINE_TOOLS = {cut: 'cut', throw: 'throw', move: 'move'};  // tool -> line style
    const TOOL_KEYS = {v: 'select', o: 'player-o', d: 'player-d', f: 'disc', c: 'cone',
                       l: 'cut', r: 'throw', m: 'move', p: 'path', t: 'text'};
    const LINE_STYLES = {
        cut: {dash: null, width: 3},
        throw: {dash: [8, 6], width: 2.5},
        move: {dash: [2, 5], width: 2.5},
    };
    const TOOL_HINTS = {
        select: 'Drag to move. Select an arrow to drag its points; double-click a point to remove it.',
        cut: 'Drag for a straight arrow, or click to add points and double-click (or Enter) to finish. Hold Shift for straight angles.',
        throw: 'Drag from the disc for a straight throw, or click points for a longer one. Tick Curved, then drag the middle handle to bend it.',
        move: 'Dotted arrow for a defender or a jog. Drag, or click points and double-click to finish.',
        path: 'Draw freehand; an arrowhead is added at the end.',
    };
    const MOVERS = ['player-o', 'player-d', 'disc'];
    const EXTRA_PROPS = ['herdType', 'herdLabel', 'herdId'];
    const MAX_STAGES = 20;
    const STAGE_MS = 1400;   // one stage's movement when playing
    const HOLD_MS = 500;

    const dataEl = document.getElementById('drill-data');
    const createUrl = dataEl.dataset.createUrl;
    let drillId = dataEl.dataset.drillId || null;
    let updateUrl = dataEl.dataset.updateUrl || null;
    const holder = document.querySelector('.canvas-holder');

    let field = {length: 70, width: 40, endzone: 20, grid: false, markers: true};
    let stages = [{name: 'Stage 1', notes: '', objects: []}];
    let current = 0;
    let currentTool = 'select';
    let lineOptions = {colour: COLOURS.line, smooth: false, arrow: true};
    let snapToGrid = false;
    let dirty = false;
    let loading = false;
    let playing = null;
    let history = [];
    let future = [];
    let clipboard = null;
    let draft = null;  // the arrow being drawn: {points, preview, dragged}

    // ---- arrows -------------------------------------------------------------

    // An arrow is a polyline (or a smooth curve through its points) with an
    // optional arrowhead. Points are kept relative to the object's centre;
    // dragging its handles moves them.

    function mid(a, b) {
        return {x: (a.x + b.x) / 2, y: (a.y + b.y) / 2};
    }

    // One segment per pair of points, from points[0]: straight, or (when
    // smooth) a curve through every point (Catmull-Rom, as cubic Béziers).
    function lineSegments(points, smooth) {
        const segs = [];
        for (let i = 1; i < points.length; i++) {
            if (!smooth || points.length < 3) {
                segs.push({to: points[i]});
                continue;
            }
            const p0 = points[i - 2] || points[i - 1], p1 = points[i - 1];
            const p2 = points[i], p3 = points[i + 1] || points[i];
            segs.push({c1: {x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6},
                       c2: {x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6},
                       to: p2});
        }
        return segs;
    }

    function segmentPoint(from, seg, t) {
        if (!seg.c1) return {x: from.x + (seg.to.x - from.x) * t, y: from.y + (seg.to.y - from.y) * t};
        const u = 1 - t;
        const a = u * u * u, b = 3 * u * u * t, c = 3 * u * t * t, d = t * t * t;
        return {x: a * from.x + b * seg.c1.x + c * seg.c2.x + d * seg.to.x,
                y: a * from.y + b * seg.c1.y + c * seg.c2.y + d * seg.to.y};
    }

    // The middle of the segment from points[i], on the line itself
    function segmentMiddle(points, smooth, i) {
        return segmentPoint(points[i], lineSegments(points, smooth)[i], 0.5);
    }

    function endDirection(points, segs) {
        const last = segs[segs.length - 1];
        let from = segs.length > 1 ? segs[segs.length - 2].to : points[0];
        if (last.c2 && Math.hypot(last.to.x - last.c2.x, last.to.y - last.c2.y) > 0.5) from = last.c2;
        const dx = last.to.x - from.x, dy = last.to.y - from.y;
        const len = Math.hypot(dx, dy) || 1;
        return {x: dx / len, y: dy / len};
    }

    // Shorten the last segment so the shaft stops inside the arrowhead.
    function shaftSegments(points, smooth, arrow) {
        const segs = lineSegments(points, smooth);
        if (!arrow || !segs.length) return {segs, dir: segs.length ? endDirection(points, segs) : null};
        const dir = endDirection(points, segs);
        const last = segs[segs.length - 1];
        const shortened = segs.slice(0, -1);
        shortened.push({...last, to: {x: last.to.x - dir.x * 8, y: last.to.y - dir.y * 8}});
        return {segs: shortened, dir};
    }

    function headPoints(tip, dir, size) {
        const back = {x: tip.x - dir.x * size * 1.2, y: tip.y - dir.y * size * 1.2};
        const side = {x: -dir.y * size * 0.55, y: dir.x * size * 0.55};
        return [tip, {x: back.x + side.x, y: back.y + side.y}, {x: back.x - side.x, y: back.y - side.y}];
    }

    // Points along the arrow, for animating a player along it.
    function samplePoints(points, smooth) {
        const out = [points[0]];
        let prev = points[0];
        lineSegments(points, smooth).forEach(seg => {
            if (!seg.c1) {
                out.push(seg.to);
            } else {
                for (let k = 1; k <= 10; k++) out.push(segmentPoint(prev, seg, k / 10));
            }
            prev = seg.to;
        });
        return out;
    }

    const fmt = n => Math.round(n * 100) / 100;

    const HerdLine = fabric.util.createClass(fabric.Object, {
        type: 'herdLine',

        initialize: function (options) {
            options = options || {};
            this.callSuper('initialize', options);
            this.set({
                points: (options.points || []).map(p => ({x: p.x, y: p.y})),
                lineStyle: options.lineStyle || 'cut',
                lineColour: options.lineColour || COLOURS.line,
                smooth: !!options.smooth,
                arrow: options.arrow !== false,
                originX: 'center', originY: 'center',
                fill: '', stroke: null,
                perPixelTargetFind: true,
                hasBorders: false,
                objectCaching: false,
                herdType: 'line',
            });
            this._updateSize();
            this.setControls();
        },

        // Points are centred, so the box is twice the furthest reach (curves
        // can bulge past their points)
        _updateSize: function () {
            const reach = this.points.length > 1 ? samplePoints(this.points, this.smooth) : this.points;
            const xs = reach.map(p => Math.abs(p.x));
            const ys = reach.map(p => Math.abs(p.y));
            this.width = 2 * Math.max(0, ...xs) + 20;
            this.height = 2 * Math.max(0, ...ys) + 20;
        },

        absolutePoints: function () {
            const m = this.calcTransformMatrix();
            return this.points.map(p => fabric.util.transformPoint(new fabric.Point(p.x, p.y), m));
        },

        // Re-centre on the given canvas points (also drops any scale/rotation)
        setAbsolutePoints: function (abs) {
            const xs = abs.map(p => p.x), ys = abs.map(p => p.y);
            const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
            const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
            this.set({points: abs.map(p => ({x: fmt(p.x - cx), y: fmt(p.y - cy)})),
                      left: cx, top: cy, angle: 0, scaleX: 1, scaleY: 1,
                      flipX: false, flipY: false, skewX: 0, skewY: 0});
            this._updateSize();
            this.setCoords();
        },

        setControls: function () {
            const controls = {};
            const n = this.points.length;
            this.points.forEach((p, i) => {
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
            this.controls = controls;
        },

        _render: function (ctx) {
            if (this.points.length < 2) return;
            const style = LINE_STYLES[this.lineStyle] || LINE_STYLES.cut;
            const {segs, dir} = shaftSegments(this.points, this.smooth, this.arrow);
            ctx.save();
            ctx.lineWidth = style.width;
            ctx.strokeStyle = this.lineColour;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.setLineDash(style.dash || []);
            ctx.beginPath();
            ctx.moveTo(this.points[0].x, this.points[0].y);
            segs.forEach(s => s.c1 ? ctx.bezierCurveTo(s.c1.x, s.c1.y, s.c2.x, s.c2.y, s.to.x, s.to.y)
                                   : ctx.lineTo(s.to.x, s.to.y));
            ctx.stroke();
            if (this.arrow) {
                const head = headPoints(this.points[this.points.length - 1], dir, 9);
                ctx.setLineDash([]);
                ctx.fillStyle = this.lineColour;
                ctx.beginPath();
                ctx.moveTo(head[0].x, head[0].y);
                ctx.lineTo(head[1].x, head[1].y);
                ctx.lineTo(head[2].x, head[2].y);
                ctx.closePath();
                ctx.fill();
            }
            ctx.restore();
        },

        _toSVG: function () {
            if (this.points.length < 2) return [];
            const style = LINE_STYLES[this.lineStyle] || LINE_STYLES.cut;
            const {segs, dir} = shaftSegments(this.points, this.smooth, this.arrow);
            let d = `M ${fmt(this.points[0].x)} ${fmt(this.points[0].y)}`;
            segs.forEach(s => {
                d += s.c1 ? ` C ${fmt(s.c1.x)} ${fmt(s.c1.y)} ${fmt(s.c2.x)} ${fmt(s.c2.y)} ${fmt(s.to.x)} ${fmt(s.to.y)}`
                          : ` L ${fmt(s.to.x)} ${fmt(s.to.y)}`;
            });
            const dash = style.dash ? ` stroke-dasharray="${style.dash.join(' ')}"` : '';
            const markup = [`<path d="${d}" fill="none" stroke="${this.lineColour}" stroke-width="${style.width}"` +
                            ` stroke-linecap="round" stroke-linejoin="round"${dash} />\n`];
            if (this.arrow) {
                const head = headPoints(this.points[this.points.length - 1], dir, 9);
                markup.push(`<polygon points="${head.map(p => fmt(p.x) + ',' + fmt(p.y)).join(' ')}"` +
                            ` fill="${this.lineColour}" />\n`);
            }
            return markup;
        },

        toSVG: function (reviver) {
            return this._createBaseSVGMarkup(this._toSVG(), {reviver: reviver, noStyle: true});
        },

        toObject: function (props) {
            return this.callSuper('toObject',
                ['points', 'lineStyle', 'lineColour', 'smooth', 'arrow'].concat(props || []));
        },
    });
    HerdLine.fromObject = function (object, callback) {
        callback && callback(new HerdLine(object));
    };
    fabric.HerdLine = HerdLine;

    function linePointPosition(dim, finalMatrix, obj) {
        const p = this.midpoint ? segmentMiddle(obj.points, obj.smooth, this.pointIndex)
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

    function dragPointTo(line, index, x, y, e) {
        const abs = line.absolutePoints();
        const neighbour = abs[index - 1] || abs[index + 1];
        abs[index] = snapPoint({x, y}, e && e.shiftKey ? neighbour : null, line);
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
            abs.splice(i + 1, 0, segmentMiddle(abs, line.smooth, i));
            line.setAbsolutePoints(abs);
            line.setControls();
            transform.herdIndex = i + 1;
        }
        return dragPointTo(line, transform.herdIndex, x, y, e);
    }

    // ---- canvas, field ------------------------------------------------------

    const canvas = new fabric.Canvas('drill-canvas', {
        backgroundColor: '#ffffff',
        selection: true,
        preserveObjectStacking: true,
        targetFindTolerance: 6,
    });
    canvas.freeDrawingBrush = new fabric.PencilBrush(canvas);
    canvas.freeDrawingBrush.color = COLOURS.line;
    canvas.freeDrawingBrush.width = 3;

    function logicalSize() {
        return {w: (field.length + 2 * field.endzone) * PX_PER_YARD,
                h: field.width * PX_PER_YARD};
    }

    function fieldObject(obj) {
        obj.set({selectable: false, evented: false, herdType: 'field'});
        return obj;
    }

    function fieldParts() {
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
        return parts;
    }

    function drawField() {
        canvas.getObjects().filter(o => o.herdType === 'field').forEach(o => canvas.remove(o));
        fieldParts().forEach((p, i) => canvas.insertAt(p, i));
        document.getElementById('field-size').textContent = `${field.length}×${field.width} yards`;
        document.getElementById('endzone-size').textContent = `${field.endzone} yards`;
        fitToScreen();
    }

    function fieldCount() {
        return canvas.getObjects().filter(o => o.herdType === 'field').length;
    }

    function fitToScreen() {
        const {w, h} = logicalSize();
        const cw = holder.clientWidth;
        const ch = holder.clientHeight || cw * h / w;
        const zoom = Math.min(cw / w, ch / h);
        canvas.setDimensions({width: cw, height: ch});
        canvas.setViewportTransform([zoom, 0, 0, zoom, (cw - w * zoom) / 2, (ch - h * zoom) / 2]);
        canvas.getObjects().forEach(o => o.setCoords());
        canvas.requestRenderAll();
    }

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
        let obj = null;
        if (tool === 'player-o' || tool === 'player-d') obj = makePlayer(tool, x, y);
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

    function makeLine(points, style) {
        const line = new HerdLine({points: [], lineStyle: style, lineColour: lineOptions.colour,
                                   smooth: lineOptions.smooth, arrow: lineOptions.arrow,
                                   herdId: newId()});
        line.setAbsolutePoints(points);
        line.setControls();
        return line;
    }

    // Arrows go under the players, so they come out from beneath them
    function addLine(line) {
        canvas.insertAt(line, fieldCount());
    }

    function arrowHead(x, y, angleRad, colour) {
        return new fabric.Triangle({left: x, top: y, width: 12, height: 14, fill: colour,
            originX: 'center', originY: 'center', angle: angleRad * 180 / Math.PI + 90});
    }

    // ---- snapping -----------------------------------------------------------

    function snapGrid(p) {
        if (!snapToGrid) return p;
        return {x: Math.round(p.x / PX_PER_YARD) * PX_PER_YARD,
                y: Math.round(p.y / PX_PER_YARD) * PX_PER_YARD};
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
            if (o === except || o.herdType === 'field' || o === (draft && draft.preview)) return;
            if (o.type === 'herdLine') {
                const abs = o.absolutePoints();
                targets.push({p: abs[0]}, {p: abs[abs.length - 1]});
            } else if (MOVERS.includes(o.herdType) || o.herdType === 'cone') {
                const c = o.getCenterPoint();
                targets.push({p: {x: c.x, y: c.y}, type: o.herdType});
            }
        });
        return targets;
    }

    function snapPoint(p, angleFrom, except, prefer) {
        if (angleFrom) return snapAngle(p, angleFrom);
        const radius = 12 / canvas.getZoom();
        let best = null, bestD = radius;
        snapTargets(except).forEach(t => {
            let d = Math.hypot(t.p.x - p.x, t.p.y - p.y);
            if (prefer && t.type === prefer) d -= radius / 2;
            if (d < bestD) { best = t.p; bestD = d; }
        });
        return best ? {x: best.x, y: best.y} : snapGrid(p);
    }

    // ---- tools --------------------------------------------------------------

    function isLineTool(tool) {
        return Object.prototype.hasOwnProperty.call(LINE_TOOLS, tool);
    }

    function setTool(tool) {
        finishDraft();
        currentTool = tool;
        document.querySelectorAll('.tool-btn[data-tool]').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.tool === tool));
        canvas.isDrawingMode = tool === 'path';
        canvas.selection = tool === 'select';
        canvas.skipTargetFind = tool !== 'select';
        canvas.defaultCursor = tool === 'select' ? 'default' : 'crosshair';
        if (tool !== 'select') canvas.discardActiveObject();
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

    function finishDraft() {
        if (!draft) return;
        const d = draft;
        draft = null;
        if (d.preview) {
            loading = true;
            canvas.remove(d.preview);
            loading = false;
        }
        // Drop repeated points (e.g. from the clicks of a double-click)
        const pts = d.points.filter((p, i, all) => i === 0 ||
            Math.hypot(p.x - all[i - 1].x, p.y - all[i - 1].y) > 3);
        const first = pts[0], last = pts[pts.length - 1];
        if (pts.length < 2 || Math.hypot(last.x - first.x, last.y - first.y) < 8) {
            canvas.requestRenderAll();
            return;
        }
        if (lineOptions.smooth && pts.length === 2) pts.splice(1, 0, mid(pts[0], pts[1]));
        addLine(makeLine(pts, LINE_TOOLS[d.tool]));
        canvas.requestRenderAll();
    }

    function linePointer(opt) {
        const p = canvas.getPointer(opt.e);
        const prev = draft && draft.points[draft.points.length - 1];
        const prefer = LINE_TOOLS[currentTool] === 'throw' ? 'disc' : null;
        return snapPoint({x: p.x, y: p.y}, opt.e.shiftKey ? prev : null, null, prefer);
    }

    canvas.on('mouse:down', function (opt) {
        if (playing) return;
        const p = canvas.getPointer(opt.e);
        if (PLACE_TOOLS.includes(currentTool)) {
            // Keep new things on the field
            const {w, h} = logicalSize();
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
        } else if (isLineTool(currentTool)) {
            const point = linePointer(opt);
            if (!draft) {
                draft = {tool: currentTool, points: [point], down: point, dragged: false};
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

    canvas.on('mouse:move', function (opt) {
        if (!draft) return;
        const point = linePointer(opt);
        if (draft.pressed && Math.hypot(point.x - draft.down.x, point.y - draft.down.y) > 6) {
            draft.dragged = true;
        }
        updateDraftPreview(point);
    });

    canvas.on('mouse:up', function (opt) {
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
        if (!snapToGrid || o.type === 'herdLine' || o.type === 'activeSelection') return;
        const c = snapGrid(o.getCenterPoint());
        o.setPositionByOrigin(new fabric.Point(c.x, c.y), 'center', 'center');
    });

    function deleteSelected() {
        const active = canvas.getActiveObjects();
        if (!active.length) return;
        canvas.discardActiveObject();
        active.forEach(o => canvas.remove(o));
        canvas.requestRenderAll();
    }

    function clearDrawing() {
        if (!userObjects().length || !confirm('Remove everything from this stage?')) return;
        userObjects().forEach(o => canvas.remove(o));
    }

    // ---- line options -------------------------------------------------------

    function selectedLines() {
        return canvas.getActiveObjects().filter(o => o.type === 'herdLine');
    }

    function updateLineOptions() {
        const lines = selectedLines();
        const show = isLineTool(currentTool) || currentTool === 'path' || lines.length > 0;
        document.getElementById('line-options').classList.toggle('invisible', !show);
        const source = lines[0] ? {colour: lines[0].lineColour, smooth: lines[0].smooth,
                                   arrow: lines[0].arrow} : lineOptions;
        document.querySelectorAll('.line-colour').forEach(btn =>
            btn.classList.toggle('active', btn.dataset.colour === source.colour));
        document.getElementById('line-smooth').checked = source.smooth;
        document.getElementById('line-arrow').checked = source.arrow;
        const styleGroup = document.getElementById('line-style-group');
        styleGroup.classList.toggle('invisible', !lines.length);
        if (lines.length) {
            styleGroup.querySelectorAll('[data-line-style]').forEach(btn =>
                btn.classList.toggle('active', btn.dataset.lineStyle === lines[0].lineStyle));
        }
    }

    function applyToLines(props) {
        const lines = selectedLines();
        if (!lines.length) return;
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
        changed();
    }

    document.querySelectorAll('.line-colour').forEach(btn => btn.addEventListener('click', () => {
        lineOptions.colour = btn.dataset.colour;
        canvas.freeDrawingBrush.color = lineOptions.colour;
        applyToLines({lineColour: btn.dataset.colour});
        updateLineOptions();
    }));
    document.getElementById('line-smooth').addEventListener('change', e => {
        lineOptions.smooth = e.target.checked;
        applyToLines({smooth: e.target.checked});
    });
    document.getElementById('line-arrow').addEventListener('change', e => {
        lineOptions.arrow = e.target.checked;
        applyToLines({arrow: e.target.checked});
    });
    document.querySelectorAll('[data-line-style]').forEach(btn => btn.addEventListener('click', () => {
        applyToLines({lineStyle: btn.dataset.lineStyle});
        updateLineOptions();
    }));
    document.getElementById('snap-grid').addEventListener('change', e => { snapToGrid = e.target.checked; });

    canvas.on('selection:created', updateLineOptions);
    canvas.on('selection:updated', updateLineOptions);
    canvas.on('selection:cleared', updateLineOptions);

    // ---- state, stages, undo ------------------------------------------------

    function userObjects() {
        return canvas.getObjects().filter(o => o.herdType && o.herdType !== 'field' &&
                                               o !== (draft && draft.preview));
    }

    // Serialise as plain data, as each object would be outside any
    // multi-selection
    function serialiseObject(o) {
        return JSON.parse(JSON.stringify(canvas._toObject(o, 'toObject', EXTRA_PROPS)));
    }

    // (Not while a stage is still being put on the canvas)
    function commitStage() {
        if (loading) return;
        stages[current].objects = userObjects().map(serialiseObject);
    }

    function editorState() {
        commitStage();
        return {version: 2, field: {...field},
                stages: stages.map(s => ({name: s.name, notes: s.notes, objects: s.objects}))};
    }

    function enliven(objects) {
        return new Promise(resolve => fabric.util.enlivenObjects(objects || [], resolve));
    }

    function showObjects(objects) {
        loading = true;
        canvas.discardActiveObject();
        userObjects().forEach(o => canvas.remove(o));
        return enliven(objects).then(enlivened => {
            enlivened.forEach(o => canvas.add(o));
            loading = false;
            canvas.requestRenderAll();
        });
    }

    function snapshot() {
        return JSON.stringify({stages, current});
    }

    function changed() {
        if (loading) return;
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

    // Only finished drawing objects count (not the field, or an arrow while
    // it is being drawn)
    const isDrawing = o => o.herdType && o.herdType !== 'field';
    canvas.on('object:added', e => { if (isDrawing(e.target)) changed(); });
    canvas.on('object:removed', e => { if (isDrawing(e.target)) changed(); });
    canvas.on('object:modified', function (e) {
        const o = e.target;
        if (o && o.type === 'herdLine') {
            o.setAbsolutePoints(o.absolutePoints());  // bake in any move
            o.setControls();
        }
        changed();
    });
    canvas.on('text:editing:exited', changed);

    function switchStage(index) {
        if (index === current || index < 0 || index >= stages.length || playing || loading) return;
        finishDraft();
        commitStage();
        current = index;
        renderStageBar();
        showObjects(stages[current].objects);
    }

    // Where each arrow takes a player or disc: an arrow that starts on a
    // player (or, for a throw, on the disc) moves it to the arrow's end.
    // Arrows that start where another one ends carry on from there.
    function serialisedLinePoints(o) {
        const m = fabric.util.composeMatrix({translateX: o.left, translateY: o.top, angle: o.angle || 0,
            scaleX: o.scaleX || 1, scaleY: o.scaleY || 1, flipX: !!o.flipX, flipY: !!o.flipY});
        return o.points.map(p => fabric.util.transformPoint(new fabric.Point(p.x, p.y), m));
    }

    function centred(o) {
        return o.originX === 'center' && o.originY === 'center';
    }

    function movements(objects) {
        const pos = {};
        const paths = {};
        objects.forEach(o => {
            if (MOVERS.includes(o.herdType) && o.herdId && centred(o)) pos[o.herdId] = {x: o.left, y: o.top, type: o.herdType};
        });
        let lines = objects.filter(o => o.type === 'herdLine' && o.points && o.points.length > 1)
            .map(o => ({style: o.lineStyle, pts: samplePoints(serialisedLinePoints(o), o.smooth)}));
        const reach = 2.5 * PX_PER_YARD;
        let progress = true;
        while (lines.length && progress) {
            progress = false;
            lines = lines.filter(line => {
                const start = line.pts[0];
                let best = null, bestD = reach;
                Object.entries(pos).forEach(([id, p]) => {
                    const wanted = line.style === 'throw' ? p.type === 'disc' : p.type !== 'disc';
                    const d = Math.hypot(p.x - start.x, p.y - start.y);
                    if (wanted && d < bestD) { best = id; bestD = d; }
                });
                if (!best) return true;
                const end = line.pts[line.pts.length - 1];
                paths[best] = (paths[best] || [{x: pos[best].x, y: pos[best].y}]).concat(line.pts);
                pos[best] = {...pos[best], x: end.x, y: end.y};
                progress = true;
                return false;
            });
        }
        return paths;
    }

    function nextStageObjects(objects) {
        const paths = movements(objects);
        const next = objects.filter(o => o.type !== 'herdLine' && o.herdType !== 'cut' && o.herdType !== 'throw')
            .map(o => {
                const copy = JSON.parse(JSON.stringify(o));
                const path = paths[o.herdId];
                if (path) {
                    copy.left = path[path.length - 1].x;
                    copy.top = path[path.length - 1].y;
                }
                return copy;
            });
        // A disc caught by a player sits at their shoulder, not over their label
        const players = next.filter(o => o.herdType && o.herdType.startsWith('player'));
        next.filter(o => o.herdType === 'disc' && paths[o.herdId]).forEach(disc => {
            if (players.some(p => Math.hypot(p.left - disc.left, p.top - disc.top) < 6)) {
                disc.left += 10;
                disc.top -= 10;
            }
        });
        return next;
    }

    function addStage(copyExactly) {
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
            objects: copyExactly ? JSON.parse(JSON.stringify(objects)) : nextStageObjects(objects),
        });
        current += 1;
        renderStageBar();
        showObjects(stages[current].objects).then(changed);
    }

    function deleteStage() {
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
        const to = current + delta;
        if (to < 0 || to >= stages.length) return;
        commitStage();
        const [stage] = stages.splice(current, 1);
        stages.splice(to, 0, stage);
        current = to;
        renderStageBar();
        changed();
    }

    function renderStageBar() {
        const tabs = document.getElementById('stage-tabs');
        tabs.innerHTML = '';
        stages.forEach((stage, i) => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-sm stage-tab ' + (i === current ? 'btn-primary' : 'btn-outline-secondary');
            btn.textContent = stage.name;
            btn.title = 'Double-click to rename';
            btn.addEventListener('click', () => switchStage(i));
            btn.addEventListener('dblclick', () => { switchStage(i); renameStage(); });
            tabs.appendChild(btn);
        });
        document.getElementById('stage-notes').value = stages[current].notes || '';
        document.getElementById('stage-count').textContent = `${current + 1} / ${stages.length}`;
        document.getElementById('play-stages').disabled = stages.length < 2 && !playing;
    }

    document.getElementById('stage-notes').addEventListener('change', e => {
        stages[current].notes = e.target.value.slice(0, 255);
        changed();
    });

    // ---- playback -----------------------------------------------------------

    function pointAlong(path, t) {
        if (path.length === 1) return path[0];
        const lengths = [0];
        for (let i = 1; i < path.length; i++) {
            lengths.push(lengths[i - 1] + Math.hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y));
        }
        const total = lengths[lengths.length - 1];
        if (!total) return path[path.length - 1];
        const target = t * total;
        let i = 1;
        while (i < lengths.length - 1 && lengths[i] < target) i++;
        const seg = lengths[i] - lengths[i - 1] || 1;
        const f = (target - lengths[i - 1]) / seg;
        return {x: path[i - 1].x + (path[i].x - path[i - 1].x) * f,
                y: path[i - 1].y + (path[i].y - path[i - 1].y) * f};
    }

    const ease = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

    // Move the stage's players along their arrows to where they stand in the
    // next stage
    function animateStage(from, to, run) {
        const paths = movements(from.objects);
        const target = {};
        to.objects.forEach(o => { if (o.herdId && centred(o)) target[o.herdId] = {x: o.left, y: o.top}; });
        const tracks = [];
        userObjects().forEach(o => {
            if (o.type === 'herdLine' || o.herdType === 'cut' || o.herdType === 'throw') {
                tracks.push({obj: o, fade: true});
                return;
            }
            const end = target[o.herdId];
            if (!end) {
                tracks.push({obj: o, fade: true});
                return;
            }
            const c = o.getCenterPoint();
            let path = paths[o.herdId] ? paths[o.herdId].slice() : [{x: c.x, y: c.y}];
            const last = path[path.length - 1];
            if (Math.hypot(last.x - end.x, last.y - end.y) > 1) path.push(end);
            if (path.length > 1) tracks.push({obj: o, path});
        });
        return new Promise(resolve => {
            const start = performance.now();
            function frame(now) {
                if (run.stopped) return resolve();
                const t = Math.min(1, (now - start) / STAGE_MS);
                const e = ease(t);
                tracks.forEach(track => {
                    if (track.fade) {
                        track.obj.set('opacity', 1 - e);
                    } else {
                        const p = pointAlong(track.path, e);
                        track.obj.setPositionByOrigin(new fabric.Point(p.x, p.y), 'center', 'center');
                    }
                });
                canvas.requestRenderAll();
                if (t < 1) requestAnimationFrame(frame);
                else resolve();
            }
            requestAnimationFrame(frame);
        });
    }

    function setPlaying(run) {
        playing = run;
        const btn = document.getElementById('play-stages');
        btn.innerHTML = run ? '<i class="bi bi-stop-fill"></i> Stop' : '<i class="bi bi-play-fill"></i> Play';
        btn.classList.toggle('btn-success', !run);
        btn.classList.toggle('btn-danger', !!run);
        document.querySelector('.editor-main').classList.toggle('is-playing', !!run);
        canvas.skipTargetFind = !!run || currentTool !== 'select';
        canvas.selection = !run && currentTool === 'select';
        renderStageBar();
    }

    async function play() {
        if (playing) {
            playing.stopped = true;
            return;
        }
        finishDraft();
        setTool('select');
        commitStage();
        const run = {stopped: false};
        const returnTo = current;
        const first = current === stages.length - 1 ? 0 : current;
        setPlaying(run);
        for (let i = first; i < stages.length && !run.stopped; i++) {
            current = i;
            renderStageBar();
            await showObjects(stages[i].objects);
            await wait(i === first ? HOLD_MS : HOLD_MS / 2);
            if (i + 1 < stages.length && !run.stopped) await animateStage(stages[i], stages[i + 1], run);
        }
        if (!run.stopped) await wait(HOLD_MS * 2);
        current = run.stopped ? current : returnTo;
        setPlaying(null);
        renderStageBar();
        await showObjects(stages[current].objects);
    }

    // ---- export, save -------------------------------------------------------

    // Render each stage at field size (not screen size) for the PNG and SVG
    async function exportStage(objects) {
        const {w, h} = logicalSize();
        const el = document.createElement('canvas');
        const sc = new fabric.StaticCanvas(el, {width: w, height: h, backgroundColor: '#ffffff',
                                               renderOnAddRemove: false});
        fieldParts().forEach(p => sc.add(p));
        (await enliven(objects)).forEach(o => sc.add(o));
        sc.renderAll();
        const png = sc.toDataURL({format: 'png', multiplier: 2});
        const svg = sc.toSVG({width: w, height: h, viewBox: {x: 0, y: 0, width: w, height: h}});
        sc.dispose();
        return {png, svg};
    }

    async function exportAll() {
        finishDraft();
        commitStage();
        const out = [];
        for (const stage of stages) out.push(await exportStage(stage.objects));
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
        if (saving || playing) return;
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
    // already in this stage
    async function paste() {
        if (!clipboard) return;
        const here = new Set(userObjects().map(o => o.herdId));
        const offset = here.size ? 2 * PX_PER_YARD : 0;
        const enlivened = await enliven(clipboard.map(o => ({...o})));
        canvas.discardActiveObject();
        enlivened.forEach(o => {
            if (here.has(o.herdId)) {
                o.set({herdId: newId(), left: o.left + offset, top: o.top + offset});
            }
            o.type === 'herdLine' ? addLine(o) : canvas.add(o);
            o.setCoords();
        });
        if (enlivened.length > 1) {
            canvas.setActiveObject(new fabric.ActiveSelection(enlivened, {canvas}));
        } else if (enlivened.length) {
            canvas.setActiveObject(enlivened[0]);
        }
        canvas.requestRenderAll();
    }

    function nudge(dx, dy) {
        const active = canvas.getActiveObject();
        if (!active) return;
        active.set({left: active.left + dx, top: active.top + dy});
        active.setCoords();
        canvas.requestRenderAll();
        canvas.fire('object:modified', {target: active});
    }

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
    document.getElementById('play-stages').addEventListener('click', play);

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
        const mod = e.ctrlKey || e.metaKey;
        const key = e.key.toLowerCase();
        if (mod && key === 's') {
            e.preventDefault();
            saveDrill();
            return;
        }
        if (typing) return;
        if (playing) {
            if (e.key === ' ' || e.key === 'Escape') {
                e.preventDefault();
                play();  // stops it
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
            const step = (e.shiftKey ? 5 : 1) * PX_PER_YARD;
            nudge({ArrowLeft: -step, ArrowRight: step}[e.key] || 0,
                  {ArrowUp: -step, ArrowDown: step}[e.key] || 0);
        } else if (e.key === 'PageDown' || e.key === ']') {
            switchStage(current + 1);
        } else if (e.key === 'PageUp' || e.key === '[') {
            switchStage(current - 1);
        } else if (e.key === ' ' && stages.length > 1) {
            e.preventDefault();
            play();
        } else if (!mod && !e.altKey && TOOL_KEYS[key]) {
            setTool(TOOL_KEYS[key]);
        }
    });

    // Refit whenever the space for the field changes (window, option rows)
    if (window.ResizeObserver) new ResizeObserver(fitToScreen).observe(holder);
    else window.addEventListener('resize', fitToScreen);
    window.addEventListener('beforeunload', function (e) {
        if (dirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });

    // ---- start --------------------------------------------------------------

    // Version 1 drawings had a single list of objects
    function loadState(saved) {
        if (!saved) return;
        if (saved.field) field = {...field, ...saved.field};
        if (Array.isArray(saved.stages) && saved.stages.length) {
            stages = saved.stages.map((s, i) => ({name: s.name || `Stage ${i + 1}`, notes: s.notes || '',
                                                  objects: s.objects || []}));
        } else {
            stages = [{name: 'Stage 1', notes: '', objects: saved.objects || []}];
        }
        stages.forEach(s => s.objects.forEach(o => { if (!o.herdId) o.herdId = newId(); }));
    }

    loadState(JSON.parse(document.getElementById('editor-state').textContent || 'null'));
    fillFieldSettings();
    drawField();
    setTool('select');
    renderStageBar();
    showObjects(stages[current].objects).then(function () {
        history = [snapshot()];
        dirty = false;
    });
});
