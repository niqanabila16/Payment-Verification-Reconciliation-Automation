/* Site-wide behaviour: navigation, alerts, confirmation dialog, notifications, service worker.
   No framework and no build step. Everything degrades gracefully when JavaScript is off. */
(() => {
  'use strict';
  const body = document.body;
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  /* ---- Mobile navigation ------------------------------------------------ */
  const toggle = $('[data-menu-toggle]');
  const sidebar = $('#sidebar');
  if (toggle && sidebar) {
    toggle.addEventListener('click', () => {
      const open = sidebar.classList.toggle('is-open');
      toggle.setAttribute('aria-expanded', String(open));
    });
  }

  /* ---- Move focus to error summaries / alerts so screen readers announce them ---- */
  const focusTarget = $('[data-focus-on-load]');
  if (focusTarget) focusTarget.focus();

  /* ---- Dismissible alerts ----------------------------------------------- */
  document.addEventListener('click', (event) => {
    const close = event.target.closest('[data-dismiss-alert]');
    if (close) close.closest('.alert').remove();
  });

  /* ---- Confirmation dialog for risky actions (WCAG 3.3.4) --------------- */
  const dialog = $('#confirm-dialog');
  function askConfirm({ title, message, label = 'Confirm', tone = 'primary' }) {
    if (!dialog || typeof dialog.showModal !== 'function') return Promise.resolve(window.confirm(message));
    $('#confirm-title', dialog).textContent = title;
    $('#confirm-message', dialog).textContent = message;
    const ok = $('#confirm-ok', dialog);
    ok.textContent = label;
    ok.className = 'btn ' + (tone === 'danger' ? 'btn--danger' : 'btn--primary');
    return new Promise((resolve) => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
      dialog.showModal();
    });
  }
  window.askConfirm = askConfirm;

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-confirm-title]');
    if (!button) return;
    const form = button.form;
    if (form && !form.checkValidity()) return;         // let the browser show its own field errors first
    event.preventDefault();
    const yes = await askConfirm({
      title: button.dataset.confirmTitle, message: button.dataset.confirmMessage,
      label: button.dataset.confirmLabel, tone: button.dataset.confirmTone,
    });
    if (yes && form) form.requestSubmit(button);
  });

  /* ---- Copy to clipboard ------------------------------------------------- */
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy-target]');
    if (!button) return;
    const text = document.getElementById(button.dataset.copyTarget).textContent.trim();
    try { await navigator.clipboard.writeText(text); button.lastChild.textContent = ' Copied'; }
    catch { button.lastChild.textContent = ' Select and copy manually'; }
  });

  /* ---- Prevent double submits and show a loading state ------------------ */
  $$('form').forEach((form) => {
    if (form.hasAttribute('data-receipt-form')) return;  // receipts.js handles its own submit
    form.addEventListener('submit', () => {
      if (form.dataset.submitting) return;
      const button = $('[data-submit-btn]', form);
      if (!button) return;
      form.dataset.submitting = '1';
      button.classList.add('is-loading');
      button.setAttribute('aria-disabled', 'true');
      if (button.dataset.loadingText) button.lastChild.textContent = ' ' + button.dataset.loadingText;
    });
  });
  window.addEventListener('pageshow', (event) => {      // back button restores the page: reset the buttons
    if (!event.persisted) return;
    $$('form[data-submitting]').forEach((form) => {
      delete form.dataset.submitting;
      const button = $('[data-submit-btn]', form);
      if (button) { button.classList.remove('is-loading'); button.removeAttribute('aria-disabled'); }
    });
  });

  /* ---- Online / offline indicator --------------------------------------- */
  const net = $('[data-net-status]');
  function paintNetwork() {
    if (!net) return;
    const online = navigator.onLine;
    net.className = 'net-status ' + (online ? 'net-status--online' : 'net-status--offline');
    net.lastElementChild.textContent = online ? 'Online' : 'Offline';
    net.firstElementChild.firstElementChild.setAttribute('href', online ? '#i-wifi' : '#i-wifi-off');
  }
  window.addEventListener('online', paintNetwork);
  window.addEventListener('offline', paintNetwork);
  paintNetwork();

  /* ---- Service worker (offline Teller form + desktop notifications) ------ */
  let registration = null;
  if ('serviceWorker' in navigator && body.dataset.swUrl && body.dataset.userId) {
    navigator.serviceWorker.register(body.dataset.swUrl, { scope: '/' })
      .then((reg) => { registration = reg; })
      .catch(() => { /* needs HTTPS or localhost; the site still works without it */ });
  }

  /* ---- Sign out: warn about unsynced receipts, clear cached private pages --- */
  const logoutForm = $('[data-logout-form]');
  if (logoutForm) {
    logoutForm.addEventListener('submit', async (event) => {
      if (logoutForm.dataset.ready) return;
      event.preventDefault();
      let waiting = 0;
      try { waiting = JSON.parse(localStorage.getItem('receipt-queue-v1') || '[]').length; } catch { /* ignore */ }
      if (waiting) {
        const yes = await askConfirm({
          title: 'Receipts are still waiting to sync',
          message: `${waiting} receipt(s) are saved only on this computer. Signing out will not delete them, but they are sent only after you sign in again. Sign out anyway?`,
          label: 'Sign out', tone: 'danger',
        });
        if (!yes) return;
      }
      try { await caches.delete('pages-v1'); } catch { /* ignore */ }
      logoutForm.dataset.ready = '1';
      logoutForm.submit();
    });
  }

  /* ---- Notifications: bell counter + desktop alerts (BR-7) -------------- */
  const pollUrl = body.dataset.pollUrl;
  const bellCount = $('[data-bell-count]');
  const LAST_KEY = 'notif-last-id';
  async function pollNotifications() {
    if (!pollUrl || !body.dataset.userId || !navigator.onLine) return;
    const stored = localStorage.getItem(LAST_KEY);
    try {
      const response = await fetch(`${pollUrl}?after=${stored || 0}`, { headers: { Accept: 'application/json' }, credentials: 'same-origin' });
      if (!response.ok || !(response.headers.get('content-type') || '').includes('json')) return;
      const data = await response.json();
      if (bellCount) { bellCount.textContent = data.unread; bellCount.classList.toggle('hidden', !data.unread); }
      if (stored === null) { localStorage.setItem(LAST_KEY, String(data.latest_id)); return; }   // first visit: do not replay history
      for (const item of data.items) {
        if ('Notification' in window && Notification.permission === 'granted') {
          const options = { body: item.message, data: { url: item.url }, tag: 'recon-' + item.id };
          if (registration) registration.showNotification('Payment Reconciliation', options);
          else new Notification('Payment Reconciliation', options);
        }
      }
      if (data.items.length) localStorage.setItem(LAST_KEY, String(data.items[data.items.length - 1].id));
    } catch { /* offline or server restarting: try again next time */ }
  }
  if (pollUrl && body.dataset.userId) { pollNotifications(); setInterval(pollNotifications, 20000); }

  const enableButton = $('[data-enable-desktop-alerts]');
  if (enableButton) {
    enableButton.addEventListener('click', async () => {
      if (!('Notification' in window)) { $('[data-desktop-alert-help]').classList.remove('hidden'); return; }
      const result = await Notification.requestPermission();
      $('[data-desktop-alert-help]').classList.toggle('hidden', result !== 'denied');
      if (result === 'granted') enableButton.lastChild.textContent = ' Desktop alerts are on';
    });
  }
})();
