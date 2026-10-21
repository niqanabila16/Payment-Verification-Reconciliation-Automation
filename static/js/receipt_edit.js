/* Correction screen: when the Teller saves values that were already entered (another receipt with the same reference and
   amount, or exactly the values this receipt had before), the server sends the details and this opens the red pop-up. */
(() => {
  'use strict';
  const dialog = document.getElementById('duplicate-dialog');
  if (!dialog || !dialog.dataset.popup) return;
  let info;
  try { info = JSON.parse(dialog.dataset.popup); } catch { return; }
  const esc = (text) => String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const rows = [['Branch', info.branch + (info.branch_name ? ' - ' + info.branch_name : '')], ['Account holder', info.account_holder],
                ['Sender', info.sender || 'Unknown'], ['Amount', info.amount], ['Reference', info.reference],
                ['Entered', info.entered], ['Status', info.status]];
  dialog.querySelector('[data-duplicate-title]').textContent = info.title;
  dialog.querySelector('[data-duplicate-message]').textContent = info.message;
  dialog.querySelector('[data-duplicate-details]').innerHTML = rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  if (typeof dialog.showModal === 'function') dialog.showModal();
})();
