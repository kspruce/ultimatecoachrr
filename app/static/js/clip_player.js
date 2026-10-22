/* Clip page: YouTube player, annotation panel, point segments and share links.
   The page sets window.CLIP_PAGE (embed URL, endpoint URLs, CSRF token) first. */
/* ── YouTube player ─────────────────────────────────────── */
let ytPlayer = null;
const CLIP_EMBED_URL = CLIP_PAGE.embedUrl;

function onYouTubeIframeAPIReady() {
  const iframe = document.getElementById('video-player');
  if (!iframe || !iframe.src.includes('youtube.com')) return;
  ytPlayer = new YT.Player('video-player', { events: {} });
}

function getCurrentTimeSeconds() {
  if (ytPlayer && ytPlayer.getCurrentTime) return Math.floor(ytPlayer.getCurrentTime());
  return 0;
}

function seekToTime(seconds) {
  const iframe = document.getElementById('video-player');
  if (!iframe) return;

  const rect = iframe.getBoundingClientRect();
  const isVisible = rect.top >= 0 && rect.bottom <= window.innerHeight;
  if (!isVisible) {
    (iframe.closest('.video-card') || iframe).scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  if (iframe.src.includes('youtube.com')) {
    if (ytPlayer && ytPlayer.seekTo) {
      ytPlayer.seekTo(seconds, true);
      ytPlayer.playVideo && ytPlayer.playVideo();
      return;
    }
    const m = iframe.src.match(/embed\/([^?]+)/);
    if (m) iframe.src = `https://www.youtube.com/embed/${m[1]}?start=${seconds}&autoplay=1&enablejsapi=1`;
  }
}

/* ── mm:ss ↔ seconds helpers ───────────────────────────── */
function secondsToMmSs(total) {
  return { m: Math.floor(total / 60), s: total % 60 };
}
function mmSsToSeconds(m, s) {
  return (parseInt(m) || 0) * 60 + (parseInt(s) || 0);
}

/* ── Annotation offcanvas ───────────────────────────────── */
let quillEditor = null;

function initOffcanvas() {
  // Initialise Quill once
  if (!quillEditor) {
    quillEditor = new Quill('#quill-ann-editor', {
      theme: 'snow',
      placeholder: 'Write your notes here…',
      modules: {
        toolbar: [
          ['bold', 'italic', 'underline'],
          [{ list: 'ordered' }, { list: 'bullet' }],
          ['clean']
        ]
      }
    });
  }

  // Stamp current playback time into the mm:ss fields
  const t = getCurrentTimeSeconds();
  const { m, s } = secondsToMmSs(t);
  document.getElementById('ann-min').value = m;
  document.getElementById('ann-sec').value = String(s).padStart(2, '0');
  document.getElementById('ann-timestamp-hidden').value = t;

  // Load offcanvas video at the right timestamp
  const videoIframe = document.getElementById('offcanvas-video-player');
  if (videoIframe && CLIP_EMBED_URL) {
    const sep = CLIP_EMBED_URL.includes('?') ? '&' : '?';
    videoIframe.src = `${CLIP_EMBED_URL}${sep}start=${t}`;
  }

  // Update visibility hint
  updateVisibilityHint();

  // Clear any previous error
  const errBox = document.getElementById('ann-form-error');
  if (errBox) errBox.style.display = 'none';
}

// Wire the offcanvas "show" event to stamp the current time
const offcanvasEl = document.getElementById('annotationOffcanvas');
if (offcanvasEl) {
  offcanvasEl.addEventListener('show.bs.offcanvas', initOffcanvas);

  // Stop the offcanvas video when panel is closed
  offcanvasEl.addEventListener('hide.bs.offcanvas', () => {
    const videoIframe = document.getElementById('offcanvas-video-player');
    if (videoIframe) videoIframe.src = '';
  });
}

// Visibility hint + target player show/hide
const visibilityHints = {
  'team':     'Visible to all team members.',
  'coaches':  '🔒 Only coaches and admins will see this — hidden from players.',
  'specific': '🔒 Only the selected player (and coaches) will see this.',
  'private':  '🔒 Only you will see this annotation.'
};
function updateVisibilityHint() {
  const sel  = document.getElementById('ann-visibility');
  const hint = document.getElementById('ann-visibility-hint');
  const wrap = document.getElementById('ann-target-user-wrap');
  if (!sel) return;
  if (hint) {
    hint.textContent = visibilityHints[sel.value] || '';
    hint.style.color = (sel.value === 'team') ? 'var(--uc-gray-500)' : '#7c3aed';
  }
  if (wrap) {
    wrap.style.display = (sel.value === 'specific') ? '' : 'none';
    // Reset target select when hidden so it doesn't accidentally submit a stale value
    if (sel.value !== 'specific') {
      const targetSel = document.getElementById('ann-target-user');
      if (targetSel) targetSel.value = '0';
    }
  }
}
document.getElementById('ann-visibility')?.addEventListener('change', updateVisibilityHint);

// Sync mm:ss inputs → hidden seconds field
['ann-min', 'ann-sec'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', () => {
    const m = document.getElementById('ann-min').value;
    const s = document.getElementById('ann-sec').value;
    document.getElementById('ann-timestamp-hidden').value = mmSsToSeconds(m, s);
  });
});

// AJAX form submit
document.getElementById('annotation-offcanvas-form')?.addEventListener('submit', async function (e) {
  e.preventDefault();

  // Sync Quill HTML → hidden textarea
  if (quillEditor) {
    document.getElementById('ann-notes-hidden').value = quillEditor.root.innerHTML;
  }

  const btn = document.getElementById('ann-submit-btn');
  const errBox = document.getElementById('ann-form-error');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Saving…';
  errBox.style.display = 'none';

  try {
    const resp = await fetch(this.action, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: new FormData(this)
    });
    const data = await resp.json();
    if (data.success) {
      window.location.reload();
    } else {
      errBox.textContent = 'Please check the form and try again.';
      errBox.style.display = 'block';
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-check-circle me-1"></i>Save Annotation';
    }
  } catch {
    errBox.textContent = 'An error occurred. Please try again.';
    errBox.style.display = 'block';
    btn.disabled = false;
    btn.innerHTML = '<i class="bi bi-check-circle me-1"></i>Save Annotation';
  }
});

/* ── Point segments ─────────────────────────────────────── */
function formatTime(sec) {
  const s = Math.floor(sec % 60), m = Math.floor((sec / 60) % 60), h = Math.floor(sec / 3600);
  const pad = n => String(n).padStart(2, '0');
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function renderSegments(list) {
  const c = document.getElementById('segments-container');
  if (!list || !list.length) {
    c.innerHTML = '<div class="ann-empty"><i class="bi bi-flag"></i><p>No points recorded yet.</p></div>';
    return;
  }
  c.innerHTML = list.map(s => {
    const dur = (s.end_time !== null && s.end_time >= s.start_time) ? (s.end_time - s.start_time) : null;
    return `<div class="seg-item">
      <div>
        <strong>Point ${s.point_number}</strong>
        <div class="seg-time">
          ${formatTime(s.start_time)}${s.end_time !== null ? ' – ' + formatTime(s.end_time) : ' (open)'}
          ${dur !== null ? ' · ' + dur + 's' : ''}
        </div>
      </div>
      <div class="d-flex gap-1">
        <button class="btn btn-xs btn-outline-primary" style="padding:.15rem .4rem;font-size:.7rem"
                onclick="seekToTime(${s.start_time})"><i class="bi bi-play"></i></button>
        ${s.end_time !== null ? `<button class="btn btn-xs btn-outline-secondary" style="padding:.15rem .4rem;font-size:.7rem" onclick="seekToTime(${s.end_time})">End</button>` : ''}
        ${CLIP_PAGE.canManageSegments ? `<button class="btn btn-xs btn-outline-danger" style="padding:.15rem .4rem;font-size:.7rem"
                onclick="deleteSegment(${s.id})"><i class="bi bi-trash"></i></button>` : ''}
      </div>
    </div>`;
  }).join('');
}

async function fetchSegments() {
  const r = await fetch(CLIP_PAGE.segmentsUrl);
  if (r.ok) renderSegments(await r.json());
}

async function markPoint(action) {
  const t = getCurrentTimeSeconds();
  const r = await fetch(
    CLIP_PAGE.markSegmentUrl.replace('__ACTION__', action),
    { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CLIP_PAGE.csrfToken },
      body: JSON.stringify({ timestamp: t }) }
  );
  if (r.ok) fetchSegments(); else alert('Error: ' + await r.text());
}

async function deleteSegment(id) {
  if (!confirm('Delete this segment?')) return;
  const r = await fetch(
    CLIP_PAGE.deleteSegmentUrl.replace('__ID__', id),
    { method: 'DELETE', headers: { 'X-CSRFToken': CLIP_PAGE.csrfToken } }
  );
  if (r.ok) fetchSegments(); else alert('Error: ' + await r.text());
}

/* ── Init ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  const s = document.getElementById('btn-point-start');
  const e = document.getElementById('btn-point-end');
  const r = document.getElementById('btn-refresh-segments');
  s && s.addEventListener('click', () => markPoint('start'));
  e && e.addEventListener('click', () => markPoint('end'));
  r && r.addEventListener('click', fetchSegments);

  fetchSegments();

  // Share link
  const shareForm = document.getElementById('createShareForm');
  if (shareForm) {
    shareForm.addEventListener('submit', async ev => {
      ev.preventDefault();
      try {
        const resp = await fetch(shareForm.action, { method: 'POST', body: new FormData(shareForm) });
        const data = await resp.json();
        if (data.url) {
          try { await navigator.clipboard.writeText(data.url); } catch {}
          alert('Share link copied to clipboard:\n\n' + data.url + '\n\nExpires in ' + data.expires_days + ' day(s).');
        } else { alert(data.error || 'Failed to create share link.'); }
      } catch { alert('Failed to create share link.'); }
    });
  }
});
