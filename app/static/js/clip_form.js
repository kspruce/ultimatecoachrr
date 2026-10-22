/* Add/edit clip form: tag pickers, game -> points and video link, a live
   check of the link with a preview player, and "Set start/end" from it.
   The page sets window.CLIP_FORM (endpoint URLs) first. */
let previewPlayer = null;

function formatClipTime(total) {
  total = Math.max(0, Math.floor(total));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const pad = n => String(n).padStart(2, '0');
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}

function attachPreviewPlayer() {
  const iframe = document.getElementById('preview-player');
  if (!window.YT || !YT.Player || !iframe || !iframe.src) return;
  previewPlayer = new YT.Player(iframe, {
    events: {
      onReady: () => document.querySelectorAll('.set-from-video').forEach(b => b.classList.remove('d-none'))
    }
  });
}

// Called by the YouTube API script once it has loaded
function onYouTubeIframeAPIReady() { attachPreviewPlayer(); }

$(document).ready(function () {
  $('#tags-select').select2({ theme: 'bootstrap-5', placeholder: 'Select tags', allowClear: true });
  $('#players-select').select2({ theme: 'bootstrap-5', placeholder: 'Select players', allowClear: true });

  const linkInput = $('#youtube-link');
  const sourceSelect = $('#video-source');
  const startInput = $('#start-time');
  const preview = $('#clip-preview');
  const previewFrame = document.getElementById('preview-player');
  const linkError = $('#link-check-error');
  let linkAutoFilled = false;
  let checkTimer = null;
  let lastChecked = null;

  function setPreview(embedUrl) {
    const src = embedUrl ? `${embedUrl}?enablejsapi=1&origin=${encodeURIComponent(location.origin)}` : '';
    if (previewFrame.getAttribute('src') === src) return;
    if (previewPlayer && previewPlayer.destroy) {
      // destroy() removes the iframe; put a fresh one back for the next link
      const fresh = previewFrame.cloneNode(false);
      previewPlayer.destroy();
      preview.find('.ratio').append(fresh);
    }
    previewPlayer = null;
    $('.set-from-video').addClass('d-none');
    const frame = document.getElementById('preview-player');
    frame.setAttribute('src', src);
    preview.toggleClass('d-none', !src);
    if (src) attachPreviewPlayer();
  }

  function checkLink() {
    const url = linkInput.val().trim();
    const source = sourceSelect.val();
    const key = source + ' ' + url;
    if (key === lastChecked) return;
    lastChecked = key;
    if (!url) { linkError.addClass('d-none'); setPreview(null); return; }
    $.getJSON(CLIP_FORM.checkLinkUrl, { url, source }, function (data) {
      if (key !== lastChecked) return;  // a newer check is on its way
      linkError.text(data.error || '').toggleClass('d-none', !data.error);
      setPreview(data.embed_url);
      if (data.start && !startInput.val()) startInput.val(formatClipTime(data.start));
    });
  }

  function scheduleCheck() {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(checkLink, 400);
  }

  linkInput.on('input', function () {
    linkAutoFilled = false;
    $('#link-auto-populated').addClass('d-none');
    scheduleCheck();
  });
  sourceSelect.on('change', checkLink);

  $('.set-from-video').on('click', function () {
    if (!previewPlayer || !previewPlayer.getCurrentTime) return;
    $('#' + this.dataset.target).val(formatClipTime(previewPlayer.getCurrentTime())).trigger('change');
  });

  // When the game changes: reload its points, and fill in the game's video
  // link unless one has been typed in already.
  $('#game-select').change(function () {
    const gameId = $(this).val();
    const pointSelect = $('#point-select');
    pointSelect.empty();
    pointSelect.append(new Option('Select Point', 0));
    if (!(gameId > 0)) return;

    $.getJSON(CLIP_FORM.pointsUrl.replace('__ID__', gameId), function (data) {
      $.each(data, function (index, point) {
        pointSelect.append(new Option(point.name, point.id));
      });
    });

    if (!linkInput.val() || linkAutoFilled) {
      $.getJSON(CLIP_FORM.gameLinkUrl.replace('__ID__', gameId), function (data) {
        if (data.youtube_link) {
          linkInput.val(data.youtube_link);
          linkAutoFilled = true;
          $('#link-auto-populated').removeClass('d-none');
          checkLink();
        }
      });
    }
  });

  checkLink();  // an existing clip's link previews straight away
});
