/* "Send the link again": the button unlocks after the countdown (the server enforces the same 60 s). */
(() => {
  const form = document.querySelector('[data-resend-form]');
  if (!form) return;
  const button = form.querySelector('[data-resend-button]');
  const label = form.querySelector('[data-resend-count]');
  let left = parseInt(form.dataset.resendIn, 10) || 0;
  if (left <= 0) return;
  const timer = setInterval(() => {
    left -= 1;
    if (left <= 0) { clearInterval(timer); button.disabled = false; label.textContent = ''; } else { label.textContent = ' (' + left + 's)'; }
  }, 1000);
})();
