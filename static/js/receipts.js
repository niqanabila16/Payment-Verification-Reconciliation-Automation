/* Teller receipt form: submit online, or queue on this computer when the central computer is unreachable.
   The server is idempotent on client_uuid, so syncing the same receipt twice never creates a duplicate.
   NFR-PERF-2: the browser also checks field lengths (HTML5 attributes) before anything is sent. */
(() => {
  'use strict';
  const card = document.querySelector('[data-receipt-card]');
  if (!card) return;

  const QUEUE_KEY = 'receipt-queue-v1';
  const owner = document.body.dataset.userId || '';
  const queueCard = document.querySelector('[data-queue-card]');
  const queueList = document.querySelector('[data-queue-list]');
  const queueTitle = document.querySelector('[data-queue-title]');
  const flash = document.querySelector('[data-flash]');
  const postUrl = card.dataset.postUrl;
  const pristine = card.innerHTML;          // clean copy of the form, used to reset after an offline save

  /* ---- helpers ----------------------------------------------------------- */
  const uuid = () => {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();   // needs HTTPS / localhost
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40; bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  };
  const csrf = () => (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || '';
  const loadQueue = () => { try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]'); } catch { return []; } };
  const saveQueue = (items) => { try { localStorage.setItem(QUEUE_KEY, JSON.stringify(items)); } catch { /* storage full or blocked */ } };
  const escapeHtml = (text) => String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function showFlash(tone, title, text) {
    const icon = { success: 'check-circle', warning: 'alert-triangle', danger: 'x-circle' }[tone] || 'info';
    flash.innerHTML = `<div class="alert alert--${tone}" role="${tone === 'success' ? 'status' : 'alert'}">
      <svg class="icon" aria-hidden="true"><use href="#i-${icon}"></use></svg>
      <div><span class="alert__title">${escapeHtml(title)}</span><p>${escapeHtml(text)}</p></div>
      <button type="button" class="alert__close" data-dismiss-alert aria-label="Dismiss message"><svg class="icon" aria-hidden="true"><use href="#i-x"></use></svg></button></div>`;
  }

  async function send(fields) {
    const data = new FormData();
    Object.entries(fields).forEach(([key, value]) => data.append(key, value));
    return fetch(postUrl, {
      method: 'POST', body: data, credentials: 'same-origin',
      headers: { Accept: 'application/json', 'X-CSRFToken': csrf() },
    });
  }
  const isJson = (response) => (response.headers.get('content-type') || '').includes('json');

  /* ---- offline queue UI -------------------------------------------------- */
  function renderQueue() {
    const items = loadQueue();
    queueCard.classList.toggle('hidden', items.length === 0);
    const rejected = items.some((i) => i.state === 'rejected');
    queueTitle.textContent = rejected ? 'Some receipts need your attention' : `Waiting to sync (${items.length})`;
    queueList.innerHTML = items.map((item) => {
      const mine = item.owner === owner;
      const status = item.state === 'rejected'
        ? `<strong>Rejected:</strong> ${escapeHtml((item.errors || []).join(' '))} <button type="button" class="btn btn--sm" data-remove="${item.id}">Remove</button>`
        : mine ? 'Waiting for connection' : 'Belongs to another account';
      return `<li><span><span class="ref">${escapeHtml(item.fields.bank_reference_no)}</span> - RM ${escapeHtml(item.fields.amount)}</span><span>${status}</span></li>`;
    }).join('');
  }
  queueList.addEventListener('click', (event) => {
    const button = event.target.closest('[data-remove]');
    if (!button) return;
    saveQueue(loadQueue().filter((i) => i.id !== button.dataset.remove));
    renderQueue();
  });

  function enqueue(fields) {
    const items = loadQueue();
    items.push({ id: fields.client_uuid, owner, fields, savedAt: new Date().toISOString(), state: 'queued', errors: [] });
    saveQueue(items);
    renderQueue();
  }

  let syncing = false;
  async function syncQueue() {
    if (syncing || !navigator.onLine) return;
    syncing = true;
    try {
      for (const item of loadQueue().filter((i) => i.owner === owner && i.state === 'queued')) {
        let response;
        try { response = await send(item.fields); } catch { break; }            // still offline: stop and retry later
        if (response.status >= 500 || !isJson(response)) break;                // server restarting or session expired
        const result = await response.json();
        const items = loadQueue();
        const stored = items.find((i) => i.id === item.id);
        if (response.ok) {
          saveQueue(items.filter((i) => i.id !== item.id));
        } else if (stored) {
          const doc = new DOMParser().parseFromString(result.html || '', 'text/html');
          stored.state = 'rejected';
          stored.errors = Array.from(doc.querySelectorAll('.error-summary li')).map((li) => li.textContent.trim());
          saveQueue(items);
        }
        renderQueue();
      }
    } finally { syncing = false; }
  }

  /* ---- form handling ----------------------------------------------------- */
  function bind() {
    const form = card.querySelector('[data-receipt-form]');
    if (!form) return;
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (form.dataset.submitting) return;
      if (!form.checkValidity()) { form.reportValidity(); return; }              // frontend length validation
      form.querySelector('[name="entered_at"]').value = new Date().toISOString();
      const fields = Object.fromEntries(Array.from(new FormData(form)).filter(([key]) => key !== 'csrfmiddlewaretoken'));
      const button = form.querySelector('[data-submit-btn]');
      form.dataset.submitting = '1'; button.classList.add('is-loading'); button.setAttribute('aria-disabled', 'true');
      try {
        const response = await send(fields);
        if (response.ok && isJson(response)) { window.location.assign(postUrl); return; }   // reload: shows the saved message
        if (response.status === 400 && isJson(response)) {                       // server found field errors: show them
          card.innerHTML = (await response.json()).html;
          bind();
          const summary = card.querySelector('#error-summary'); if (summary) summary.focus();
          return;
        }
        throw new Error('not-saved');                                              // 5xx, expired session, proxy page...
      } catch {
        enqueue(fields);                                                           // network down or server unreachable
        card.innerHTML = pristine; bind();
        card.querySelector('[name="client_uuid"]').value = uuid();
        showFlash('warning', 'Saved on this computer', 'It will be sent automatically when the connection returns.');
        card.querySelector('input:not([type=hidden])').focus();
      }
    });
    const reset = form.querySelector('[data-reset-form]');
    if (reset) reset.addEventListener('click', () => { setTimeout(() => { card.innerHTML = pristine; bind(); card.querySelector('[name="client_uuid"]').value = uuid(); }, 0); });
  }

  bind();
  renderQueue();
  syncQueue();
  window.addEventListener('online', syncQueue);
  setInterval(syncQueue, 30000);
})();
