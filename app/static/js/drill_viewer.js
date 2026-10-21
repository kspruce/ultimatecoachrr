// Plays a drill's stages on the drill page (templates/session/drills/detail.html),
// using drill_diagram.js. Not editable.
document.addEventListener('DOMContentLoaded', function () {
    const DD = window.DrillDiagram;
    const root = document.getElementById('drill-animation');
    const dataEl = document.getElementById('drill-animation-data');
    if (!root || !dataEl) return;
    const saved = DD.normaliseState(JSON.parse(dataEl.textContent || 'null'),
                                    () => Math.random().toString(36).slice(2, 10));
    const field = saved.field;
    const stages = saved.stages;
    if (stages.length < 2) return;

    const holder = root.querySelector('.animation-canvas');
    const el = document.createElement('canvas');
    holder.appendChild(el);
    const canvas = new fabric.StaticCanvas(el, {backgroundColor: '#ffffff', renderOnAddRemove: false});
    DD.fieldParts(field).forEach(p => canvas.add(p));

    const playBtn = root.querySelector('[data-animation="play"]');
    const scrubber = root.querySelector('[data-animation="scrubber"]');
    const caption = root.querySelector('.animation-caption');
    scrubber.max = String((stages.length - 1) * 1000);

    function showCaption(index) {
        const stage = stages[index];
        caption.querySelector('strong').textContent = `${index + 1}/${stages.length} · ${stage.name}`;
        caption.querySelector('span').textContent = stage.notes ? ' – ' + stage.notes : '';
    }

    const player = DD.createPlayer(canvas, () => stages, {
        onUpdate: function (position, playing) {
            scrubber.value = String(Math.round(position * 1000));
            showCaption(Math.min(Math.floor(position + 0.001), stages.length - 1));
            playBtn.innerHTML = playing ? '<i class="bi bi-pause-fill"></i> Pause' : '<i class="bi bi-play-fill"></i> Play';
        },
    });

    function fit() {
        const view = DD.viewRect(field);
        const width = holder.clientWidth;
        const zoom = width / view.w;
        canvas.setDimensions({width, height: Math.round(view.h * zoom)});
        canvas.setViewportTransform([zoom, 0, 0, zoom, -view.x * zoom, -view.y * zoom]);
        canvas.requestRenderAll();
    }

    playBtn.addEventListener('click', () => (player.playing ? player.pause() : player.play()));
    scrubber.addEventListener('input', () => {
        const position = parseInt(scrubber.value, 10) / 1000;
        player.pause();
        player.seek(position);
    });
    root.querySelector('[data-animation="prev"]').addEventListener('click', () => {
        player.pause();
        player.seek(Math.ceil(player.position - 1.001));
    });
    root.querySelector('[data-animation="next"]').addEventListener('click', () => {
        player.pause();
        player.seek(Math.floor(player.position + 1.001));
    });
    root.querySelector('[data-animation="speed"]').addEventListener('change', e => {
        player.speed = parseFloat(e.target.value) || 1;
    });

    if (window.ResizeObserver) new ResizeObserver(fit).observe(holder);
    else window.addEventListener('resize', fit);
    fit();
    player.seek(0);
});
