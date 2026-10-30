/* Playbook: "Download as PDF". Starts the export on the server, shows its
   progress, then downloads the file. */
(function () {
  'use strict';
  var status = document.getElementById('pb-export-status');
  var busy = false;

  function show(text) {
    if (!status) return;
    status.hidden = !text;
    status.textContent = text || '';
  }

  document.addEventListener('click', function (e) {
    var link = e.target.closest('[data-export-pdf]');
    if (!link) return;
    e.preventDefault();
    if (busy) return;
    busy = true;
    show('Making the PDF…');
    fetch(link.getAttribute('data-start-url'), { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json(); })
      .then(function (job) { return poll(job.job_id); })
      .catch(function () { finish('The PDF could not be made. Try again in a minute.'); });
  });

  function poll(jobId) {
    return fetch('/playbook/export/status/' + jobId, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (s) {
        if (s.state === 'ready') {
          finish('');
          window.location.href = s.download_url;
        } else if (s.state === 'running') {
          show((s.label || 'Making the PDF…') + (s.pct ? ' ' + s.pct + '%' : ''));
          setTimeout(function () { poll(jobId); }, 1000);
        } else {
          finish(s.label || 'The PDF could not be made.');
        }
      });
  }

  function finish(text) {
    busy = false;
    show(text);
  }
})();
