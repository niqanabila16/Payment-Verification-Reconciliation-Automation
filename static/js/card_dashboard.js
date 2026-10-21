/* Card dashboard: the numbers refresh by themselves (every 15 s while the page is visible, and when the tab comes back),
   so a new batch, a delivery, a card request or a block shows up without reloading. Server renders the first values; no JS = still correct. */
(() => {
  const root = document.querySelector('[data-dash]');
  if (!root) return;
  const url = root.dataset.dashUrl;
  const EVERY = 15000;

  const apply = (data) => {
    const values = {};
    Object.entries(data.total).forEach(([k, v]) => { values['total.' + k] = v; });
    data.branches.forEach((b) => {
      ['disbursed', 'collected', 'remaining', 'blocked'].forEach((k) => { values['b' + b.id + '.' + k] = b.empty ? '-' : b[k]; });
    });
    root.querySelectorAll('[data-m]').forEach((el) => {
      const next = values[el.dataset.m];
      if (next !== undefined && el.textContent !== String(next)) {
        el.textContent = next;
        el.toggleAttribute('data-zero', !(Number(next) > 0));
        el.classList.remove('metric--flash'); void el.offsetWidth; el.classList.add('metric--flash');   // brief highlight of a changed number
      }
    });
  };

  const refresh = async () => {
    if (document.hidden) return;
    try {
      const response = await fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin', cache: 'no-store' });
      if (response.ok) apply(await response.json());
    } catch (e) { /* offline or signed out: keep the numbers that are shown */ }
  };

  setInterval(refresh, EVERY);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
})();
