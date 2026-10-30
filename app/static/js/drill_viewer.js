// Plays a drill's or play's stages (templates/partials/diagram_animation.html),
// using drill_diagram.js. Not editable. On a play, picking a role fades
// everything but that role's player and the arrows they run. The defence
// can be faded or hidden, and the animation saved as a video to send on.
document.addEventListener('DOMContentLoaded', function () {
    const DD = window.DrillDiagram;
    const root = document.getElementById('drill-animation');
    const dataEl = document.getElementById('drill-animation-data');
    if (!root || !dataEl) return;
    const saved = DD.normaliseState(JSON.parse(dataEl.textContent || 'null'),
                                    () => Math.random().toString(36).slice(2, 10));
    const field = saved.field;
    const stages = saved.stages;
    const rolePick = root.querySelector('[data-animation="role"]');
    const defencePick = root.querySelector('[data-animation="defence"]');
    const showDefence = defencePick && DD.hasDefence(stages);
    if (stages.length < 2 && !rolePick && !showDefence) return;
    if (showDefence) defencePick.closest('label').hidden = false;

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

    function view(objects) {
        return DD.viewObjects(objects, {role: rolePick ? rolePick.value : '',
                                        defence: showDefence ? defencePick.value : 'show'});
    }

    const player = DD.createPlayer(canvas, () => stages, {
        mapObjects: view,
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

    function redraw() {
        player.reset();
        player.seek(player.position);
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
    if (rolePick) {
        rolePick.addEventListener('change', () => {
            redraw();
            const url = new URL(window.location.href);
            if (rolePick.value) url.searchParams.set('role', rolePick.value);
            else url.searchParams.delete('role');
            window.history.replaceState({}, '', url);
        });
    }
    if (showDefence) defencePick.addEventListener('change', redraw);

    // Save as video: what's on screen (role picked, defence faded...), at the
    // chosen speed. Phones get the share sheet, others a download.
    const videoBtn = root.querySelector('[data-animation="video"]');
    if (videoBtn && stages.length > 1 && DD.videoType() && HTMLCanvasElement.prototype.captureStream) {
        videoBtn.hidden = false;
        const label = videoBtn.innerHTML;
        videoBtn.addEventListener('click', async () => {
            player.pause();
            videoBtn.disabled = true;
            const shown = stages.map(s => Object.assign({}, s, {objects: view(s.objects)}));
            try {
                const {blob, extension} = await DD.recordVideo(field, shown, {
                    speed: player.speed,
                    onUpdate: position => {
                        videoBtn.textContent = `Recording… ${Math.round(100 * position / (stages.length - 1))}%`;
                    },
                });
                const name = `${(videoBtn.dataset.name || 'animation').replace(/[^\w-]+/g, '_')}.${extension}`;
                const file = new File([blob], name, {type: blob.type});
                if (navigator.canShare && navigator.canShare({files: [file]})) {
                    try {
                        await navigator.share({files: [file], title: videoBtn.dataset.name || ''});
                    } catch (e) {
                        if (e.name !== 'AbortError') throw e;
                    }
                } else {
                    const link = document.createElement('a');
                    link.href = URL.createObjectURL(blob);
                    link.download = name;
                    document.body.appendChild(link);
                    link.click();
                    link.remove();
                    setTimeout(() => URL.revokeObjectURL(link.href), 10000);
                }
            } catch (e) {
                window.alert(e.message || 'The video could not be made.');
            } finally {
                videoBtn.disabled = false;
                videoBtn.innerHTML = label;
            }
        });
    }

    if (window.ResizeObserver) new ResizeObserver(fit).observe(holder);
    else window.addEventListener('resize', fit);
    fit();
    player.seek(0);
});
