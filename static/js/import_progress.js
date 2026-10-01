/* Progress bar for a running bank statement import (REQ-F-1.1 AC6).
   Polls the status endpoint once per second and reloads the page when processing ends. */
(() => {
  'use strict';
  const box = document.querySelector('[data-import-progress]');
  if (!box) return;
  const bar = box.querySelector('[data-progress-bar]');
  const text = box.querySelector('[data-progress-text]');
  const track = box.querySelector('[role="progressbar"]');
  const paint = (value) => {
    bar.style.width = value + '%';
    track.setAttribute('aria-valuenow', String(value));
    text.textContent = value + '%';
  };
  paint(Number(bar.dataset.value || 0));

  async function tick() {
    try {
      const response = await fetch(box.dataset.statusUrl, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      const data = await response.json();
      paint(data.progress);
      if (data.status !== 'processing') { window.location.reload(); return; }
    } catch { /* temporary network problem: keep trying */ }
    setTimeout(tick, 1000);
  }
  setTimeout(tick, 800);
})();
