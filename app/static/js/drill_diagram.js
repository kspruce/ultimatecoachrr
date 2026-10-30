// Drill diagrams: the parts shared by the drill editor (drill_editor.js) and
// the animation on the drill page (drill_viewer.js). Exposes
// window.DrillDiagram.
//
// A drawing is {version, field, stages: [{name, notes, objects}]}, where the
// objects are fabric.js objects as plain data, in field units (PX_PER_YARD
// per yard). Players, discs and cones are centred on their position. Arrows
// are HerdLine objects; one that starts on a player or disc (herdFrom) moves
// it to the arrow's end in the next stage.
(function () {
    const PX_PER_YARD = 10;
    const COLOURS = {offense: '#e03131', defense: '#1c7ed6', disc: '#ffffff',
                     cone: '#fd7e14', line: '#212529', field: '#5a9e4b',
                     apron: '#7f9f72'};
    const LINE_STYLES = {
        cut: {dash: null, width: 3},
        throw: {dash: [8, 6], width: 2.5},
        move: {dash: [2, 5], width: 2.5},
    };
    const MOVERS = ['player-o', 'player-d', 'disc'];
    // herdRole: in a playbook play, the team role (its id) a player is
    const EXTRA_PROPS = ['herdType', 'herdLabel', 'herdId', 'herdColour', 'herdRole'];
    const FORCES = {up: 'Force ↑', down: 'Force ↓', middle: 'Force middle', straight: 'Straight up'};
    const DEFAULT_FIELD = {length: 70, width: 40, endzone: 20, grid: false, markers: true,
                           view: 'full', force: 'none',
                           colours: {offense: COLOURS.offense, defense: COLOURS.defense}};
    const STAGE_MS = 1600;  // one stage's movement at normal speed
    const HOLD_MS = 600;    // pause on each stage

    // ---- geometry -----------------------------------------------------------

    const fmt = n => Math.round(n * 100) / 100;

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

    function pathLength(path) {
        let total = 0;
        for (let i = 1; i < path.length; i++) {
            total += Math.hypot(path[i].x - path[i - 1].x, path[i].y - path[i - 1].y);
        }
        return total;
    }

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

    // ---- arrows -------------------------------------------------------------

    // An arrow is a polyline (or a smooth curve through its points) with an
    // optional arrowhead. Points are kept relative to the object's centre.
    // `delay` is how far through the stage it starts when animated (0-0.75).
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
                herdFrom: options.herdFrom || '',
                delay: Number(options.delay) || 0,
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

        // The editor supplies point handles (DrillDiagram.lineControls)
        setControls: function () {
            this.controls = api.lineControls ? api.lineControls(this) : {};
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
                ['points', 'lineStyle', 'lineColour', 'smooth', 'arrow', 'herdFrom', 'delay'].concat(props || []));
        },
    });
    HerdLine.fromObject = function (object, callback) {
        callback && callback(new HerdLine(object));
    };
    fabric.HerdLine = HerdLine;

    // ---- field --------------------------------------------------------------

    function withDefaults(field) {
        return {...DEFAULT_FIELD, ...(field || {}),
                colours: {...DEFAULT_FIELD.colours, ...((field && field.colours) || {})}};
    }

    // `rotated` is the portrait view used on phones: the field runs up the
    // screen, attacking the top. Drawings are always saved the landscape way
    // round (see toDisplay/toSaved).
    function logicalSize(field, rotated) {
        const w = (field.length + 2 * field.endzone) * PX_PER_YARD, h = field.width * PX_PER_YARD;
        return rotated ? {w: h, h: w} : {w, h};
    }

    // The part of the field shown: all of it, the attacking half, the
    // attacking endzone and 25 yards in front of it, the attacking endzone
    // alone, a stretch of the near sideline (with the ground beyond it), or a
    // small patch of plain grass with no lines, for footwork and the like.
    // `anchor` 'end' keeps the attacking end at the edge of the screen.
    const SIDELINE_APRON = 6;  // yards of ground shown beyond the sideline
    function viewRect(field, rotated) {
        const Y = PX_PER_YARD;
        const {w, h} = logicalSize(field);
        const goal = (field.endzone + field.length) * Y;
        const mid = (field.endzone + field.length / 2) * Y;
        let r = {x: 0, y: 0, w, h};
        if (field.view === 'half') r = {x: mid, y: 0, w: w - mid, h, anchor: 'end'};
        if (field.view === 'endzone') {
            const x = Math.max(0, goal - 25 * Y);
            r = {x, y: 0, w: w - x, h, anchor: 'end'};
        }
        if (field.view === 'endzone-only') {
            const x = Math.max(0, goal - 3 * Y);
            r = {x, y: 0, w: w - x, h, anchor: 'end'};
        }
        if (field.view === 'sideline') {
            const long = Math.min(40 * Y, w), deep = Math.min(15 * Y, h);
            r = {x: mid - long / 2, y: h - deep, w: long, h: deep + SIDELINE_APRON * Y};
        }
        if (field.view === 'blank') {
            const long = Math.min(30 * Y, w), deep = Math.min(20 * Y, h);
            r = {x: (w - long) / 2, y: (h - deep) / 2, w: long, h: deep};
        }
        if (!rotated) return r;
        // Turned with the field (see rotation): x across, attacking the top
        return {x: r.y, y: w - (r.x + r.w), w: r.h, h: r.w, anchor: r.anchor};
    }

    const noLines = field => field.view === 'blank';
    // Views that frame a small area: what's outside the frame is dimmed in
    // the editor (pictures and the drill page show the frame alone)
    const FRAMED = ['endzone-only', 'sideline', 'blank'];

    // Landscape (saved) to portrait (shown) and back
    function rotation(field, back) {
        const L = (field.length + 2 * field.endzone) * PX_PER_YARD;
        return back ? {pt: p => ({x: L - p.y, y: p.x}), vec: v => ({x: -v.y, y: v.x}), angle: 90}
                    : {pt: p => ({x: p.y, y: L - p.x}), vec: v => ({x: v.y, y: -v.x}), angle: -90};
    }

    // Players, discs, cones and text stay upright when the field turns
    const UPRIGHT = ['player-o', 'player-d', 'disc', 'cone', 'text', 'ghost'];

    function rotateObjects(objects, field, back) {
        const r = rotation(field, back);
        return objects.map(o => {
            const copy = JSON.parse(JSON.stringify(o));
            const p = r.pt({x: o.left, y: o.top});
            copy.left = fmt(p.x);
            copy.top = fmt(p.y);
            if (o.type === 'herdLine') {
                copy.points = o.points.map(v => {
                    const q = r.vec(v);
                    return {x: fmt(q.x), y: fmt(q.y)};
                });
            } else if (!(UPRIGHT.includes(o.herdType) && centred(o))) {
                copy.angle = ((o.angle || 0) + r.angle + 360) % 360;
            }
            return copy;
        });
    }

    const toDisplay = (objects, field, rotated) => (rotated ? rotateObjects(objects, field, false) : objects);
    const toSaved = (objects, field, rotated) => (rotated ? rotateObjects(objects, field, true) : objects);
    const pointToDisplay = (p, field, rotated) => (rotated ? rotation(field, false).pt(p) : p);
    const pointToSaved = (p, field, rotated) => (rotated ? rotation(field, true).pt(p) : p);

    function fieldObject(obj) {
        obj.set({selectable: false, evented: false, herdType: 'field'});
        return obj;
    }

    // Drawn the landscape way round, then turned for the portrait view
    function fieldParts(field, rotated) {
        const {w, h} = logicalSize(field);
        const P = p => pointToDisplay(p, field, rotated);
        const rect = (x, y, rw, rh, opts) => {
            const a = P({x, y}), b = P({x: x + rw, y: y + rh});
            return fieldObject(new fabric.Rect({left: Math.min(a.x, b.x), top: Math.min(a.y, b.y),
                width: Math.abs(b.x - a.x), height: Math.abs(b.y - a.y), ...opts}));
        };
        const line = (x1, y1, x2, y2, opts) => {
            const a = P({x: x1, y: y1}), b = P({x: x2, y: y2});
            return fieldObject(new fabric.Line([a.x, a.y, b.x, b.y], opts));
        };
        const text = (str, x, y, opts) => {
            const a = P({x, y});
            return fieldObject(new fabric.Text(str, {left: a.x, top: a.y, originX: 'center', originY: 'center', ...opts}));
        };
        const y = PX_PER_YARD;
        const ez = field.endzone * y;
        const parts = [];
        // The ground beyond the sideline, a little duller than the field
        if (field.view === 'sideline') {
            const a = SIDELINE_APRON * y;
            parts.push(rect(-a, -a, w + 2 * a, h + 2 * a, {fill: COLOURS.apron, strokeWidth: 0}));
        }
        parts.push(rect(0, 0, w, h, {fill: COLOURS.field, strokeWidth: 0}));
        if (field.grid) {
            const grid = {stroke: 'rgba(255,255,255,0.18)', strokeWidth: 1};
            for (let x = 5 * y; x < w; x += 5 * y) parts.push(line(x, 0, x, h, grid));
            for (let gy = 5 * y; gy < h; gy += 5 * y) parts.push(line(0, gy, w, gy, grid));
        }
        const white = {stroke: '#ffffff', strokeWidth: 2};
        if (!noLines(field)) {
            parts.push(rect(1, 1, w - 2, h - 2, {fill: '', ...white}));
            parts.push(line(ez, 0, ez, h, white));
            parts.push(line(w - ez, 0, w - ez, h, white));
            // Brick marks, 20 yards out from each endzone line
            [ez + 20 * y, w - ez - 20 * y].forEach(bx => {
                if (bx > ez && bx < w - ez) parts.push(text('×', bx, h / 2, {fontSize: 18, fill: '#ffffff'}));
            });
        }
        if (field.markers && !noLines(field)) {
            for (let yd = 10; yd < field.length; yd += 10) {
                parts.push(text(String(yd), ez + yd * y, 10, {fontSize: 11, fill: 'rgba(255,255,255,0.8)'}));
            }
        }
        if (FRAMED.includes(field.view)) {
            const v = viewRect(field), far = 10000;
            const dim = {fill: 'rgba(255,255,255,0.75)', strokeWidth: 0};
            parts.push(rect(-far, -far, 2 * far + w, far + v.y, dim));
            parts.push(rect(-far, v.y + v.h, 2 * far + w, far, dim));
            parts.push(rect(-far, v.y, far + v.x, v.h, dim));
            parts.push(rect(v.x + v.w, v.y, far, v.h, dim));
        }
        if (FORCES[field.force]) {
            // Bottom left of what's shown, on the field and clear of the
            // defending endzone
            const view = viewRect(field, rotated);
            const at = rotated ? {left: Math.max(view.x, 0) + 8, top: Math.min(view.y + view.h, w - ez) - 8}
                               : {left: Math.max(view.x, noLines(field) ? 0 : ez) + 8,
                                  top: Math.min(view.y + view.h, h) - 8};
            parts.push(fieldObject(new fabric.Text(FORCES[field.force], {
                ...at, fontSize: 13, fontWeight: 'bold', originY: 'bottom',
                fontFamily: 'Arial', fill: '#ffffff', backgroundColor: 'rgba(0,0,0,0.35)',
            })));
        }
        return parts;
    }

    // White or near-black, whichever reads better on the colour
    function textOn(colour) {
        const hex = (colour || '#000000').replace('#', '');
        const [r, g, b] = [0, 2, 4].map(i => parseInt(hex.substr(i, 2), 16) || 0);
        return (0.299 * r + 0.587 * g + 0.114 * b) > 170 ? '#212529' : '#ffffff';
    }

    // Recolour the players in stage objects (plain data) to the team colours
    function recolourPlayers(objects, field) {
        objects.forEach(o => {
            if (!(o.herdType === 'player-o' || o.herdType === 'player-d') || !o.objects) return;
            const fill = o.herdType === 'player-o' ? field.colours.offense : field.colours.defense;
            o.objects[0].fill = fill;
            if (o.objects[1]) o.objects[1].fill = textOn(fill);
        });
    }

    // ---- stages -------------------------------------------------------------

    function centred(o) {
        return o.originX === 'center' && o.originY === 'center';
    }

    function serialisedLinePoints(o) {
        const m = fabric.util.composeMatrix({translateX: o.left, translateY: o.top, angle: o.angle || 0,
            scaleX: o.scaleX || 1, scaleY: o.scaleY || 1, flipX: !!o.flipX, flipY: !!o.flipY});
        return o.points.map(p => fabric.util.transformPoint(new fabric.Point(p.x, p.y), m));
    }

    function isArrow(o) {
        return o.type === 'herdLine' || o.herdType === 'cut' || o.herdType === 'throw';
    }

    // Where each arrow takes a player or disc, as {herdId: [{pts, delay}]}.
    // An arrow belongs to the player or disc it was drawn from (herdFrom);
    // otherwise to whichever one it starts on (the disc, for a throw).
    // Arrows that start where another one ends carry on from there.
    function movements(objects) {
        return assignArrows(objects).legs;
    }

    // Whose each arrow is, the way playback decides it: {object index: herdId}
    function arrowOwners(objects) {
        return assignArrows(objects).owners;
    }

    function assignArrows(objects) {
        const pos = {};
        const legs = {};
        const owners = {};
        objects.forEach(o => {
            if (MOVERS.includes(o.herdType) && o.herdId && centred(o)) {
                pos[o.herdId] = {x: o.left, y: o.top, type: o.herdType};
            }
        });
        let lines = objects.map((o, index) => ({o, index}))
            .filter(({o}) => o.type === 'herdLine' && o.points && o.points.length > 1)
            .map(({o, index}) => ({index, style: o.lineStyle, from: o.herdFrom, delay: Number(o.delay) || 0,
                                   pts: samplePoints(serialisedLinePoints(o), o.smooth)}));
        const assign = (id, line) => {
            owners[line.index] = id;
            const end = line.pts[line.pts.length - 1];
            (legs[id] = legs[id] || []).push({pts: line.pts, delay: line.delay});
            pos[id] = {...pos[id], x: end.x, y: end.y};
        };
        lines = lines.filter(line => {
            if (!line.from || !pos[line.from]) return true;
            assign(line.from, line);
            return false;
        });
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
                assign(best, line);
                progress = true;
                return false;
            });
        }
        return {legs, owners};
    }

    // How a viewer sees a stage: picking a role fades everything but that
    // role's player and the arrows they run; the defence (defenders and
    // their arrows) can be shown, faded or hidden. Returns new objects.
    function viewObjects(objects, options) {
        const role = options && options.role ? String(options.role) : '';
        const defence = (options && options.defence) || 'show';
        if (!role && defence === 'show') return objects;
        const owners = arrowOwners(objects);
        const byId = {};
        objects.forEach(o => { if (o.herdId) byId[o.herdId] = o; });
        const ownerOf = (o, i) => byId[o.herdFrom || owners[i]];
        const isDefence = (o, i) => o.herdType === 'player-d'
            || (isArrow(o) && (ownerOf(o, i) || {}).herdType === 'player-d');
        const roleIds = role ? new Set(objects.filter(o => String(o.herdRole || '') === role).map(o => o.herdId))
                             : null;
        const shown = [];
        objects.forEach((o, i) => {
            const d = defence !== 'show' && isDefence(o, i);
            if (d && defence === 'hidden') return;
            let opacity = o.opacity === undefined ? 1 : o.opacity;
            if (roleIds) {
                const mine = roleIds.has(o.herdId) || roleIds.has(owners[i]) || (o.herdFrom && roleIds.has(o.herdFrom));
                opacity = mine ? 1 : (o.herdType === 'disc' ? 0.6 : 0.18);
            }
            if (d) opacity = Math.min(opacity, 0.25);
            shown.push(Object.assign({}, o, {opacity}));
        });
        return shown;
    }

    function hasDefence(stages) {
        return stages.some(s => (s.objects || []).some(o => o.herdType === 'player-d'));
    }

    // The next stage: the same things, with players and the disc at the ends
    // of their arrows, and no arrows
    function nextStageObjects(objects) {
        const legs = movements(objects);
        const next = objects.filter(o => !isArrow(o)).map(o => {
            const copy = JSON.parse(JSON.stringify(o));
            const mine = legs[o.herdId];
            if (mine) {
                const last = mine[mine.length - 1].pts;
                copy.left = last[last.length - 1].x;
                copy.top = last[last.length - 1].y;
            }
            return copy;
        });
        // A disc caught by a player sits at their shoulder, not over their label
        const players = next.filter(o => o.herdType && o.herdType.startsWith('player'));
        next.filter(o => o.herdType === 'disc' && legs[o.herdId]).forEach(disc => {
            if (players.some(p => Math.hypot(p.left - disc.left, p.top - disc.top) < 6)) {
                disc.left += 10;
                disc.top -= 10;
            }
        });
        return next;
    }

    // ---- playback -----------------------------------------------------------

    // How each thing moves from one stage to the next: legs with start and
    // end times (0-1). A leg starts at its arrow's delay or when the previous
    // one ends, and the time left is shared out by length.
    function transitionPlan(fromObjects, toObjects) {
        const legs = movements(fromObjects);
        const target = {};
        toObjects.forEach(o => { if (o.herdId && centred(o)) target[o.herdId] = {x: o.left, y: o.top}; });
        const tracks = {};
        fromObjects.forEach(o => {
            if (isArrow(o) || !o.herdId) return;
            const end = target[o.herdId];
            if (!end) {
                tracks[o.herdId] = {fade: true};
                return;
            }
            if (!centred(o)) return;
            const mine = (legs[o.herdId] || []).map(l => ({pts: l.pts.slice(), delay: l.delay}));
            const here = mine.length ? mine[mine.length - 1].pts : [{x: o.left, y: o.top}];
            const last = here[here.length - 1];
            if (Math.hypot(last.x - end.x, last.y - end.y) > 1) {
                if (mine.length) here.push(end);
                else mine.push({pts: [last, end], delay: 0});
            }
            if (!mine.length) return;
            let prevEnd = 0;
            const lengths = mine.map(l => pathLength(l.pts) || 1);
            mine.forEach((leg, j) => {
                const start = Math.min(0.95, Math.max(leg.delay, prevEnd));
                const remaining = lengths.slice(j).reduce((a, b) => a + b, 0);
                leg.t0 = start;
                leg.t1 = start + (1 - start) * lengths[j] / remaining;
                prevEnd = leg.t1;
            });
            tracks[o.herdId] = {legs: mine};
        });
        return tracks;
    }

    function trackPoint(track, t) {
        const legs = track.legs;
        if (t <= legs[0].t0) return legs[0].pts[0];
        for (const leg of legs) {
            if (t <= leg.t1) return pointAlong(leg.pts, ease((t - leg.t0) / ((leg.t1 - leg.t0) || 1)));
        }
        const last = legs[legs.length - 1].pts;
        return last[last.length - 1];
    }

    // Put the objects on a canvas where they are `t` (0-1) of the way to the
    // next stage
    function applyFrame(canvas, plan, t) {
        canvas.getObjects().forEach(o => {
            if (!o.herdType || o.herdType === 'field') return;
            const base = o.herdBaseOpacity === undefined ? 1 : o.herdBaseOpacity;
            if (isArrow(o)) {
                o.set('opacity', base * (1 - 0.85 * ease(t)));
                return;
            }
            const track = plan[o.herdId];
            if (!track) return;
            if (track.fade) {
                o.set('opacity', base * (1 - ease(t)));
            } else {
                const p = trackPoint(track, t);
                o.setPositionByOrigin(new fabric.Point(p.x, p.y), 'center', 'center');
            }
        });
        canvas.requestRenderAll();
    }

    function enliven(objects) {
        return new Promise(resolve => fabric.util.enlivenObjects(
            JSON.parse(JSON.stringify(objects || [])), resolve));
    }

    // Replace what's drawn on the canvas (keeping the field) with a stage's
    // objects, not selectable
    async function showStage(canvas, objects) {
        const enlivened = await enliven(objects);
        canvas.getObjects().filter(o => o.herdType !== 'field').forEach(o => canvas.remove(o));
        enlivened.forEach(o => {
            o.set({selectable: false, evented: false});
            o.herdBaseOpacity = o.opacity;  // playback fades from here (a picked-out role dims the rest)
            canvas.add(o);
        });
        canvas.requestRenderAll();
    }

    // Plays a drawing's stages on a canvas. The position runs from 0 (the
    // first stage) to stages.length - 1 (the last); 1.5 is halfway from the
    // second stage to the third. onUpdate(position, playing) is called as it
    // changes.
    function createPlayer(canvas, getStages, options) {
        options = options || {};
        const player = {position: 0, playing: false, speed: 1};
        let shown = -1;
        let plan = null;
        let queue = Promise.resolve();
        let frameRequest = null;

        const count = () => getStages().length;
        const update = () => options.onUpdate && options.onUpdate(player.position, player.playing);

        async function render(position) {
            const stages = getStages();
            const last = stages.length - 1;
            const i = Math.min(Math.floor(position), last);
            if (i !== shown) {
                const map = options.mapObjects || (objects => objects);
                const here = map(stages[i].objects);
                await showStage(canvas, here);
                plan = i < last ? transitionPlan(here, map(stages[i + 1].objects)) : null;
                shown = i;
                if (options.afterShow) options.afterShow(i);
            }
            applyFrame(canvas, plan || {}, plan ? position - i : 0);
        }

        // Renders run one after another; a seek only waits for the one before
        player.seek = function (position) {
            player.position = Math.max(0, Math.min(count() - 1, position));
            const wanted = player.position;
            queue = queue.then(() => (player.position === wanted ? render(wanted) : null));
            update();
            return queue;
        };

        player.reset = function () {
            shown = -1;
        };

        player.pause = function () {
            player.playing = false;
            if (frameRequest) cancelAnimationFrame(frameRequest);
            frameRequest = null;
            update();
        };

        // Resolves when it reaches the end (or is paused)
        player.play = function () {
            if (player.position >= count() - 1) player.position = 0;
            player.playing = true;
            update();
            return new Promise(resolve => {
                let last = null;
                let hold = HOLD_MS;
                const tick = now => {
                    if (!player.playing) return resolve();
                    const dt = last === null ? 0 : (now - last) * player.speed;
                    last = now;
                    if (hold > 0) {
                        hold -= dt;
                    } else {
                        const before = player.position;
                        let next = before + dt / STAGE_MS;
                        if (Math.floor(next) > Math.floor(before) || next >= count() - 1) {
                            next = Math.min(Math.floor(before) + 1, count() - 1);
                            hold = HOLD_MS;
                        }
                        player.seek(next);
                        if (next >= count() - 1) {
                            queue.then(() => setTimeout(() => {
                                player.playing = false;
                                update();
                                resolve();
                            }, HOLD_MS / player.speed));
                            return;
                        }
                    }
                    frameRequest = requestAnimationFrame(tick);
                };
                player.seek(player.position).then(() => { frameRequest = requestAnimationFrame(tick); });
            });
        };

        return player;
    }

    // ---- export -------------------------------------------------------------

    function exportCanvas(field, scale) {
        const view = viewRect(field);
        const el = document.createElement('canvas');
        const sc = new fabric.StaticCanvas(el, {width: Math.round(view.w * scale), height: Math.round(view.h * scale),
                                               backgroundColor: '#ffffff', renderOnAddRemove: false});
        sc.setViewportTransform([scale, 0, 0, scale, -view.x * scale, -view.y * scale]);
        fieldParts(field).forEach(p => sc.add(p));
        return {sc, el, view};
    }

    // A PNG (data URL) and SVG of one stage, at field size
    async function exportStage(field, objects) {
        const {sc, view} = exportCanvas(field, 1);
        (await enliven(objects)).forEach(o => sc.add(o));
        sc.renderAll();
        const png = sc.toDataURL({format: 'png', multiplier: 2});
        const svg = sc.toSVG({width: view.w, height: view.h,
                              viewBox: {x: view.x, y: view.y, width: view.w, height: view.h}});
        sc.dispose();
        return {png, svg};
    }

    function videoType() {
        if (!window.MediaRecorder) return null;
        const types = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'];
        return types.find(t => MediaRecorder.isTypeSupported(t)) || null;
    }

    // Record the stages playing as a video. Resolves to {blob, extension}.
    async function recordVideo(field, stages, options) {
        options = options || {};
        const type = videoType();
        if (!type || !HTMLCanvasElement.prototype.captureStream) {
            throw new Error('This browser cannot record video.');
        }
        const {sc, el} = exportCanvas(field, 1.5);
        // Off screen, but attached so the browser keeps painting it
        const box = document.createElement('div');
        box.style.cssText = 'position:fixed;left:-10000px;top:0;';
        box.appendChild(el);
        document.body.appendChild(box);
        const player = createPlayer(sc, () => stages, {onUpdate: options.onUpdate});
        player.speed = options.speed || 1;
        await player.seek(0);
        const stream = el.captureStream(30);
        const recorder = new MediaRecorder(stream, {mimeType: type, videoBitsPerSecond: 4000000});
        const chunks = [];
        recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
        const stopped = new Promise(resolve => { recorder.onstop = resolve; });
        recorder.start(250);
        // Keep frames coming while it holds still
        const keepAlive = setInterval(() => sc.requestRenderAll(), 100);
        try {
            await player.play();
        } finally {
            clearInterval(keepAlive);
            recorder.stop();
            await stopped;
            stream.getTracks().forEach(track => track.stop());
            sc.dispose();
            box.remove();
        }
        return {blob: new Blob(chunks, {type: type.split(';')[0]}),
                extension: type.startsWith('video/mp4') ? 'mp4' : 'webm'};
    }

    // Drawings saved before stages (version 1) had one list of objects
    function normaliseState(saved, newId) {
        const state = {field: withDefaults(saved && saved.field), stages: []};
        if (saved && Array.isArray(saved.stages) && saved.stages.length) {
            state.stages = saved.stages.map((s, i) => ({name: s.name || `Stage ${i + 1}`, notes: s.notes || '',
                                                        objects: s.objects || []}));
        } else {
            state.stages = [{name: 'Stage 1', notes: '', objects: (saved && saved.objects) || []}];
        }
        state.stages.forEach(s => s.objects.forEach(o => { if (!o.herdId) o.herdId = newId(); }));
        return state;
    }

    const api = {
        PX_PER_YARD, COLOURS, LINE_STYLES, MOVERS, EXTRA_PROPS, FORCES, DEFAULT_FIELD, STAGE_MS,
        HerdLine, lineControls: null,
        mid, lineSegments, segmentMiddle, samplePoints,
        withDefaults, logicalSize, viewRect, fieldParts, textOn, recolourPlayers,
        toDisplay, toSaved, pointToDisplay, pointToSaved,
        centred, isArrow, movements, arrowOwners, viewObjects, hasDefence, nextStageObjects,
        transitionPlan, applyFrame, enliven, showStage, createPlayer,
        exportStage, videoType, recordVideo, normaliseState,
    };
    window.DrillDiagram = api;
})();
