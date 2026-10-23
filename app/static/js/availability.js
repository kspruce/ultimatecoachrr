// Yes / Maybe / No buttons (templates/training/_macros.html): save in place
// instead of reloading the page. Without JavaScript the form still posts.
document.addEventListener('submit', async (event) => {
  const form = event.target.closest('.ans-form');
  if (!form) return;
  event.preventDefault();
  const button = event.submitter;
  if (!button) return;
  const saved = form.querySelector('.av-saved');
  const body = new FormData(form);
  body.set('status', button.value);
  try {
    const response = await fetch(form.action, {
      method: 'POST', body, headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.message || 'Could not save');
    form.querySelector('.ans').classList.remove('is-usual');
    form.querySelectorAll('.ans button').forEach((b) => {
      const on = b.value === data.status;
      b.className = on ? `on-${b.value}` : '';
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if (saved) { saved.textContent = 'Saved'; saved.style.color = ''; }
    form.dispatchEvent(new CustomEvent('answer-saved', {bubbles: true, detail: data}));
  } catch (error) {
    if (saved) { saved.textContent = error.message; saved.style.color = 'var(--bad)'; }
  }
});
