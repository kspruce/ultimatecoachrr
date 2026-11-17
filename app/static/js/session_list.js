// The sessions list: filters apply as soon as one is picked (search on
// Enter), weeks fold and open, "Go to week" opens and scrolls to a week,
// and one delete dialog serves every row.
document.addEventListener('DOMContentLoaded', function () {
  var filters = document.getElementById('sessionFilters');
  if (filters) {
    filters.querySelectorAll('select').forEach(function (select) {
      select.addEventListener('change', function () { filters.submit(); });
    });
  }

  function openWeek(id) {
    var week = id && document.getElementById(id);
    if (!week || week.tagName !== 'DETAILS') return;
    week.open = true;
    week.scrollIntoView({ block: 'start' });
  }

  var jump = document.getElementById('jumpToWeek');
  if (jump) {
    jump.addEventListener('change', function () {
      if (!jump.value) return;
      history.replaceState(null, '', '#' + jump.value);
      openWeek(jump.value);
      jump.value = '';
    });
  }
  // A link to /sessions/#week-2028-02-07 opens that week even when it starts
  // folded. All dates starts at this week rather than the season's first.
  if (location.hash) {
    openWeek(location.hash.slice(1));
  } else if ((document.querySelector('.sl-weeks-bar') || {dataset: {}}).dataset.show === 'all') {
    var current = document.querySelector('details.sl-week[open]');
    if (current && current.previousElementSibling && current.previousElementSibling.matches('details.sl-week')) {
      current.scrollIntoView({ block: 'start' });
    }
  }

  document.querySelectorAll('.js-fold').forEach(function (button) {
    button.addEventListener('click', function () {
      var open = button.dataset.open === '1';
      document.querySelectorAll('details.sl-week').forEach(function (week) { week.open = open; });
    });
  });

  var modalEl = document.getElementById('deleteSessionModal');
  if (!modalEl) return;
  var modal = new bootstrap.Modal(modalEl);
  document.querySelectorAll('.js-delete-session').forEach(function (button) {
    button.addEventListener('click', function () {
      document.getElementById('deleteSessionForm').action = button.dataset.url;
      document.getElementById('deleteSessionName').textContent = button.dataset.title;
      var parts = [];
      var components = Number(button.dataset.components), attendance = Number(button.dataset.attendance);
      if (components) parts.push(components + ' session component' + (components === 1 ? '' : 's'));
      if (attendance) parts.push(attendance + ' attendance record' + (attendance === 1 ? '' : 's'));
      var warning = document.getElementById('deleteSessionWarning');
      warning.hidden = !parts.length;
      warning.textContent = parts.length ? 'This will also delete ' + parts.join(' and ') + '.' : '';
      modal.show();
    });
  });
});
