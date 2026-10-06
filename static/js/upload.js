/* Bank statement upload box (Finance, reconciliation page).
   If a file with the same name was uploaded before, ask first and let the user upload it again on purpose. */
(() => {
  'use strict';
  const form = document.querySelector('[data-upload-form]');
  if (!form) return;
  const known = JSON.parse(form.dataset.knownFiles || '[]');
  const confirmed = form.querySelector('[data-confirm-duplicate]');
  const fileInput = form.querySelector('input[type="file"]');

  form.addEventListener('submit', async (event) => {
    if (form.dataset.checked) return;
    const file = fileInput.files[0];
    if (!file || confirmed.value === '1' || !known.includes(file.name.toLowerCase())) return;   // normal upload
    event.preventDefault();
    const yes = await window.askConfirm({
      title: 'This file was uploaded before',
      message: `A file named "${file.name}" was already uploaded. Upload it again? Transactions that are already stored are not counted twice.`,
      label: 'Upload again',
    });
    if (!yes) return;
    confirmed.value = '1';
    form.dataset.checked = '1';
    form.requestSubmit();
  });
})();
