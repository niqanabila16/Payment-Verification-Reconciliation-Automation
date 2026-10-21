/* PDF preview modal. Click a file name to open it; Left/Right arrow keys (or the arrow buttons) move to the previous/next file. */
(() => {
  const modal = document.getElementById('pdf-modal');
  if (!modal) return;
  const frame = modal.querySelector('[data-pdf-frame]');
  const title = modal.querySelector('[data-pdf-title]');
  const pos = modal.querySelector('[data-pdf-pos]');
  const items = () => Array.from(document.querySelectorAll('[data-pdf-url]'));
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let index = 0;

  const show = (i, direction) => {
    const list = items();
    if (!list.length) return;
    index = (i + list.length) % list.length;
    const item = list[index];
    title.textContent = item.dataset.pdfName;
    pos.textContent = (index + 1) + ' / ' + list.length;
    if (!reduce && direction) {
      frame.animate([{ opacity: 0, transform: 'translateX(' + (direction * 40) + 'px)' }, { opacity: 1, transform: 'none' }], { duration: 220, easing: 'ease-out' });
    }
    frame.src = item.dataset.pdfUrl + '#toolbar=1&navpanes=0';
  };
  const close = () => { modal.close(); frame.removeAttribute('src'); };

  document.addEventListener('click', (event) => {
    const item = event.target.closest('[data-pdf-url]');
    if (item) { event.preventDefault(); modal.showModal(); show(items().indexOf(item), 0); return; }
    if (event.target.closest('[data-pdf-next]')) show(index + 1, 1);
    else if (event.target.closest('[data-pdf-prev]')) show(index - 1, -1);
    else if (event.target.closest('[data-pdf-close]') || event.target === modal) close();
  });
  document.addEventListener('keydown', (event) => {
    if (!modal.open) return;
    if (event.key === 'ArrowRight') { event.preventDefault(); show(index + 1, 1); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); show(index - 1, -1); }
  });
  modal.addEventListener('cancel', () => frame.removeAttribute('src'));
})();
