// The sessions list: filters apply as soon as one is picked, and one delete
// dialog serves every row.
document.addEventListener('DOMContentLoaded', function () {
  var filters = document.getElementById('sessionFilters');
  if (filters) {
    filters.querySelectorAll('select').forEach(function (select) {
      select.addEventListener('change', function () { filters.submit(); });
    });
  }

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
