/* Playlist player: plays each clip from its start to its end, then moves on.
   The page sets window.PLAYLIST = { tracks, startIndex } first. */
let plPlayer = null;
let plReady = false;
let plIndex = 0;
let plAdvancedFrom = null;  // the track we already moved on from (ENDED and the end-time check can both fire)

function plFormat(total) {
  total = Math.max(0, Math.floor(total));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const pad = n => String(n).padStart(2, '0');
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function plShow(index, play) {
  const tracks = PLAYLIST.tracks;
  plIndex = index;
  plAdvancedFrom = null;
  const track = tracks[index];

  document.querySelectorAll('.pl-track').forEach(li =>
    li.classList.toggle('is-current', Number(li.dataset.index) === index));
  document.getElementById('pl-position').textContent = `${index + 1} of ${tracks.length} ·`;
  document.getElementById('pl-title').textContent = track.title;
  document.getElementById('pl-note').textContent = track.note;
  document.getElementById('pl-clip-link').href = track.clip_url;
  document.getElementById('pl-prev').disabled = index === 0;
  document.getElementById('pl-next').disabled = index === tracks.length - 1;
  document.getElementById('pl-done').classList.add('d-none');

  const isVideo = Boolean(track.video_id);
  document.getElementById('pl-player-wrap').classList.toggle('d-none', !isVideo);
  document.getElementById('pl-veo').classList.toggle('d-none', isVideo);

  if (!isVideo) {
    if (plReady) plPlayer.pauseVideo();
    const link = document.getElementById('pl-veo-link');
    link.href = track.veo_link || track.clip_url;
    link.textContent = track.veo_link ? 'Watch on Veo' : 'Open the clip';
    const times = track.end ? ` from ${plFormat(track.start)} to ${plFormat(track.end)}` : (track.start ? ` from ${plFormat(track.start)}` : '');
    document.getElementById('pl-veo-text').textContent =
      track.veo_link ? `This clip is on Veo${times}.` : "This clip's video can't be played here.";
    return;
  }
  if (!plReady) return;  // onReady shows the current track
  const opts = { videoId: track.video_id, startSeconds: track.start || 0 };
  if (track.end) opts.endSeconds = track.end;
  play ? plPlayer.loadVideoById(opts) : plPlayer.cueVideoById(opts);
}

function plAdvance() {
  if (plAdvancedFrom === plIndex) return;
  plAdvancedFrom = plIndex;
  if (plIndex >= PLAYLIST.tracks.length - 1) {
    document.getElementById('pl-player-wrap').classList.add('d-none');
    document.getElementById('pl-done').classList.remove('d-none');
    return;
  }
  if (document.getElementById('pl-autoplay').checked) plShow(plIndex + 1, true);
}

// Called by the YouTube API script once it has loaded
function onYouTubeIframeAPIReady() {
  plPlayer = new YT.Player('pl-player', {
    playerVars: { rel: 0, playsinline: 1 },
    events: {
      onReady: () => { plReady = true; plShow(plIndex, false); },
      onStateChange: e => { if (e.data === YT.PlayerState.ENDED) plAdvance(); }
    }
  });
}

document.addEventListener('DOMContentLoaded', function () {
  plShow(PLAYLIST.startIndex || 0, false);

  document.getElementById('pl-prev').addEventListener('click', () => plIndex > 0 && plShow(plIndex - 1, true));
  document.getElementById('pl-next').addEventListener('click', () =>
    plIndex < PLAYLIST.tracks.length - 1 && plShow(plIndex + 1, true));
  document.getElementById('pl-restart').addEventListener('click', () => plShow(0, true));
  document.querySelectorAll('.pl-track').forEach(li => {
    const go = () => plShow(Number(li.dataset.index), true);
    li.addEventListener('click', go);
    li.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
  });

  // Not every embed reports ENDED at endSeconds, so also watch the clock
  setInterval(() => {
    const track = PLAYLIST.tracks[plIndex];
    if (!plReady || !track.video_id || !track.end || !plPlayer.getCurrentTime) return;
    if (plPlayer.getPlayerState() === YT.PlayerState.PLAYING && plPlayer.getCurrentTime() >= track.end - 0.25) {
      plPlayer.pauseVideo();
      plAdvance();
    }
  }, 500);
});
