// The demo team's drawn plays and drills (see build_diagrams.py), written
// the way the drill editor draws them. Positions are in yards on a 70 x 40
// field with 20-yard endzones, attacking the right-hand endzone (its line is
// at x = 90).
//
// Each drawing: start = [[type, label, x, y]] (type o, d, disc or cone; the
// disc's label names who holds it), then stages, each moving players with
// `cuts` ([label, [x, y], ...]: where they run, through any bends) and the
// disc with `throw` ([x, y]: where it's caught).
window.DEMO_DRAWINGS = [
    {
        key: 'ho-centre', kind: 'play', field: {force: 'none'},
        start: [
            ['o', 'H1', 50, 20], ['o', 'H2', 47, 8], ['o', 'H3', 47, 32],
            ['o', 'C1', 65, 5], ['o', 'C2', 65, 15], ['o', 'C3', 65, 25], ['o', 'C4', 65, 35],
            ['disc', 'H1'],
        ],
        stages: [
            {name: 'Set up', notes: 'Three handlers, four cutters level across the field 15 yards ahead.',
             cuts: [['C2', [80, 13], [86, 12]], ['C3', [62, 24], [58, 22]]]},
            {name: 'Hit the under', notes: 'C3 checks under into the lane C2 has cleared; H1 hits them.',
             throw: [58, 22],
             cuts: [['C1', [72, 5]], ['C4', [72, 35]]]},
            {name: 'Go to space', notes: 'C2 has kept going deep: C3 puts it into the space for the score.',
             throw: [94, 14], cuts: [['C2', [94, 14]]]},
        ],
    },
    {
        key: 'vert-under-deep', kind: 'play', field: {force: 'down'},
        start: [
            ['o', 'H1', 40, 20], ['o', 'H2', 36, 27],
            ['o', 'C1', 50, 20], ['o', 'C2', 54, 20], ['o', 'C3', 58, 20], ['o', 'C4', 62, 20], ['o', 'C5', 66, 20],
            ['disc', 'H1'],
        ],
        stages: [
            {name: 'Set up', notes: 'Vertical stack in the middle, force to the bottom sideline (open side down).',
             cuts: [['C1', [48, 28], [44, 33]]]},
            {name: 'Under on the open side', notes: 'Front of the stack checks under to the open side.',
             throw: [44, 33], cuts: [['C5', [72, 26], [84, 32]]]},
            {name: 'Back of the stack goes deep', notes: 'Back of the stack times the deep cut off the catch.',
             throw: [86, 33], cuts: [['C5', [86, 33]], ['H1', [38, 26]]]},
        ],
    },
    {
        key: 'endzone-split', kind: 'play', field: {view: 'endzone', force: 'none'},
        start: [
            ['o', 'H1', 84, 20], ['o', 'H2', 80, 10], ['o', 'H3', 80, 30],
            ['o', 'C1', 93, 20], ['o', 'C2', 97, 20], ['o', 'C3', 101, 20], ['o', 'C4', 105, 20],
            ['disc', 'H1'],
        ],
        stages: [
            {name: 'Set up', notes: 'Disc stopped on the brick. Stack in the endzone, handlers wide.',
             cuts: [['C1', [92, 8]], ['C4', [105, 33]]]},
            {name: 'Split', notes: 'Front and back split to opposite corners; H1 hits whichever is open.',
             throw: [105, 33], cuts: [['C2', [97, 30]]]},
        ],
    },
    {
        key: 'cup-zone', kind: 'play', field: {force: 'middle'},
        start: [
            ['o', 'H1', 45, 20], ['o', 'H2', 42, 10], ['o', 'H3', 42, 30],
            ['o', 'P1', 54, 15], ['o', 'P2', 54, 25], ['o', 'W1', 67, 6], ['o', 'W2', 67, 34],
            ['d', 'M', 46.5, 20], ['d', 'C1', 48, 16.5], ['d', 'C2', 48, 23.5],
            ['d', 'W1', 58, 8], ['d', 'W2', 58, 32], ['d', 'MM', 59, 20], ['d', 'DD', 73, 20],
            ['disc', 'H1'],
        ],
        stages: [
            {name: 'Set up', notes: 'The cup of three around the disc; mid-mid takes the poppers, deep-deep sits back.',
             throw: [42, 10]},
            {name: 'Swing: the cup slides', notes: 'Disc swings to H2: the cup slides across with it, the far wing pinches.',
             cuts: [['M', [43.5, 10.5]], ['C1', [45, 7]], ['C2', [45.5, 13.5]],
                    ['d:W1', [55, 5]], ['d:W2', [56, 26]], ['MM', [55, 15]], ['DD', [70, 14]]]},
            {name: 'Trap on the line', notes: 'Close the gaps through the cup and wait for the high-risk throw.'},
        ],
    },
    {
        key: 'box-drill', kind: 'drill', field: {view: 'blank'},
        start: [
            ['cone', '', 46, 13], ['cone', '', 64, 13], ['cone', '', 64, 27], ['cone', '', 46, 27],
            ['o', 'A', 44.5, 14.5], ['o', 'B', 65.5, 14.5], ['o', 'C', 65.5, 25.5], ['o', 'D', 44.5, 25.5],
            ['disc', 'A'],
        ],
        stages: [
            {name: 'Throw and follow', notes: 'A throws to B cutting into the box and follows the throw.',
             throw: [60, 16.5], cuts: [['B', [60, 16.5]], ['A', [55, 12], [64, 11.5]]]},
            {name: 'Next corner', notes: 'B turns and hits C, who cuts in from the next cone. Keep it moving round.',
             throw: [60, 23.5], cuts: [['C', [60, 23.5]], ['B', [66.5, 20], [66, 27.5]]]},
        ],
    },
    {
        key: 'under-deep-drill', kind: 'drill', field: {view: 'half'},
        start: [
            ['cone', '', 60, 20], ['cone', '', 75, 30],
            ['o', 'T', 60, 21.5], ['o', 'R', 75, 32], ['o', 'R2', 77.5, 33.5],
            ['disc', 'T'],
        ],
        stages: [
            {name: 'Under', notes: 'Receiver drives in under; thrower hits them on the hip.',
             throw: [67, 26], cuts: [['R', [69, 27], [67, 26]]]},
            {name: 'Then deep', notes: 'Plant, turn and go deep; the next thrower leads them into space.',
             throw: [89, 30], cuts: [['R', [74, 26], [89, 30]]]},
        ],
    },
];

// Turns a spec into editor stages, then a PNG and SVG of each stage.
window.buildDrawing = async function (spec) {
    const DD = window.DrillDiagram;
    const Y = DD.PX_PER_YARD;
    const field = DD.withDefaults(spec.field);
    let n = 0;
    const newId = () => `${spec.key}-${++n}`;
    const at = (x, y) => ({x: x * Y, y: y * Y});

    function player(type, label, x, y) {
        const fill = type === 'player-o' ? field.colours.offense : field.colours.defense;
        const circle = new fabric.Circle({radius: 12, fill, stroke: '#ffffff', strokeWidth: 2,
            originX: 'center', originY: 'center'});
        const text = new fabric.Text(label, {fontSize: 11, fontWeight: 'bold', fill: DD.textOn(fill),
            fontFamily: 'Arial', originX: 'center', originY: 'center'});
        return new fabric.Group([circle, text], {left: x, top: y, originX: 'center', originY: 'center',
            herdType: type, herdLabel: label, herdId: newId()});
    }
    const plain = o => JSON.parse(JSON.stringify(o.toObject(DD.EXTRA_PROPS)));

    // Stage one's things
    let objects = [];
    const byLabel = {};
    spec.start.forEach(([type, label, x, y]) => {
        let o;
        if (type === 'disc') return;
        if (type === 'cone') {
            const p = at(x, y);
            o = new fabric.Triangle({left: p.x, top: p.y, width: 14, height: 14, fill: DD.COLOURS.cone,
                stroke: '#7a3e00', strokeWidth: 1, originX: 'center', originY: 'center',
                herdType: 'cone', herdId: newId()});
        } else {
            const p = at(x, y);
            o = player(type === 'o' ? 'player-o' : 'player-d', label, p.x, p.y);
        }
        objects.push(plain(o));
        if (label) byLabel[(type === 'd' ? 'd:' : '') + label] = objects[objects.length - 1].herdId;
    });
    const holder = spec.start.find(s => s[0] === 'disc');
    if (holder) {
        const h = objects.find(o => o.herdId === byLabel[holder[1]]);
        const disc = new fabric.Circle({left: h.left + 10, top: h.top - 10, radius: 7, fill: DD.COLOURS.disc,
            stroke: '#000', strokeWidth: 2, originX: 'center', originY: 'center', herdType: 'disc',
            herdId: newId()});
        objects.push(plain(disc));
        byLabel.disc = objects[objects.length - 1].herdId;
    }

    const find = label => {
        // Defenders' labels can match attackers' (W1): a defender's is d:W1,
        // and a cut by a label only a defender has goes to the defender
        const id = byLabel[label] || byLabel['d:' + label];
        return objects.find(o => o.herdId === id);
    };
    const line = (from, points, style) => {
        const l = new DD.HerdLine({points: [], lineStyle: style, smooth: points.length > 2, arrow: true,
            herdFrom: from.herdId, delay: style === 'throw' ? 0.5 : 0, herdId: newId()});
        l.setAbsolutePoints(points.map(p => new fabric.Point(p.x, p.y)));
        return plain(l);
    };

    const stages = [];
    for (const s of spec.stages) {
        const arrows = [];
        (s.cuts || []).forEach(([label, ...pts]) => {
            const o = find(label);
            if (!o) throw new Error(`${spec.key}: no ${label}`);
            arrows.push(line(o, [{x: o.left, y: o.top}, ...pts.map(([x, y]) => at(x, y))], 'cut'));
        });
        if (s.throw) {
            const disc = objects.find(o => o.herdType === 'disc');
            arrows.push(line(disc, [{x: disc.left, y: disc.top}, at(...s.throw)], 'throw'));
        }
        const stageObjects = [...objects, ...arrows];
        stages.push({name: s.name, notes: s.notes || '', objects: stageObjects});
        objects = DD.nextStageObjects(stageObjects);
    }
    const editor = {version: 2, field, stages};
    const images = [];
    for (const st of stages) images.push(await DD.exportStage(field, st.objects));
    return {editor, images: images.map(i => ({png: i.png.split(',')[1], svg: i.svg}))};
};
