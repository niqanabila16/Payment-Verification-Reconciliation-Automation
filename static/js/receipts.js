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

  /* ---- red pop-up when the same transaction was already entered (possibly by another branch) ---- */
  function showDuplicate(info) {
    const dialog = document.getElementById('duplicate-dialog');
    const rows = [['Branch', info.branch + (info.branch_name ? ' - ' + info.branch_name : '')], ['Account holder', info.account_holder],
                  ['Sender', info.sender || 'Unknown'], ['Amount', info.amount], ['Reference', info.reference],
                  ['Entered', info.entered], ['Status', info.status]];
    if (info.title) dialog.querySelector('[data-duplicate-title]').textContent = info.title;
    if (info.message) dialog.querySelector('[data-duplicate-message]').textContent = info.message;
    dialog.querySelector('[data-duplicate-details]').innerHTML = rows.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd>`).join('');
    dialog.showModal();
  }

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
          stored.errors = Array.from(doc.querySelectorAll('.error-summary li, .field__error')).map((li) => li.textContent.trim());
          saveQueue(items);
        }
        renderQueue();
      }
    } finally { syncing = false; }
  }

  /* ---- inline validation: live while typing, full check on blur, message under the field ---- */
  const FIELD_SELECTOR = 'input:not([type=hidden]), select, textarea';
  const isField = (el) => el && el.matches && el.matches(FIELD_SELECTOR) && !el.disabled;
  const labelOf = (field) => {
    const label = field.id && card.querySelector(`label[for="${field.id}"]`);
    return label ? label.textContent.replace('*', '').replace(/\s*\(required\)\s*$/, '').trim() : 'This field';
  };

  // Returns an error message, or '' when the value is fine. final=false only reports errors that are
  // already certain while the user is still typing (e.g. a second comma), never "required" or "too short".
  function messageFor(field, final) {
    const value = field.value;
    if (field.name === 'amount' && value) {
      const clean = value.replace(/\s/g, '');
      if (/[^0-9RMrm.,]/.test(clean)) return 'The amount can only contain digits and one comma, e.g. 150,50.';
      if ((clean.match(/[.,]/g) || []).length > 1) return 'Use only one comma for sen, e.g. 150,50.';
      if (/[.,][0-9]{3,}/.test(clean)) return 'Sen can have at most 2 digits, e.g. 150,50.';
      if (final && field.validity.patternMismatch) return 'Enter a valid amount, e.g. 150,50.';
    }
    if (field.name === 'bank_reference_no' && value && /[^A-Za-z0-9]/.test(value)) {
      return 'Use only letters and digits (no spaces or symbols).';
    }
    if ((field.name === 'sender_name' || field.name === 'account_holder_name') && value && /[^\p{L} ]/u.test(value)) {
      return 'Use letters only (no digits or symbols).';
    }
    if (field.validity.tooLong) return `${labelOf(field)} is too long (maximum ${field.maxLength} characters).`;
    if (!final) return '';
    const v = field.validity;
    if (v.valueMissing) {
      if (field.name === 'transaction_at') return 'Enter the date and time on the receipt.';
      return field.tagName === 'SELECT' ? 'Please select an option.' : `${labelOf(field)} is required.`;
    }
    if (v.tooShort) return `${labelOf(field)} must be at least ${field.minLength} characters (you entered ${field.value.length}).`;
    if (v.rangeOverflow) return 'The transaction time cannot be in the future.';
    if (v.badInput) return 'Enter a valid date and time.';
    if (v.patternMismatch) return field.title || `Enter a valid ${labelOf(field).toLowerCase()}.`;
    return field.checkValidity() ? '' : `Enter a valid ${labelOf(field).toLowerCase()}.`;
  }

  function setError(field, message) {
    const wrap = field.closest('.field') || field.parentElement;
    let box = wrap.querySelector('[data-client-error]');
    const describedBy = (field.getAttribute('aria-describedby') || '').split(' ').filter(Boolean);
    if (message) {
      if (!box) {
        box = document.createElement('p');
        box.className = 'field__error';
        box.setAttribute('data-client-error', '');
        box.setAttribute('aria-live', 'polite');
        box.id = `${field.id || field.name}-client-error`;
        box.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x-circle"></use></svg><span></span>';
        wrap.appendChild(box);
      }
      const text = box.lastElementChild;
      if (text.textContent !== message) text.textContent = message;   // no re-render on every keystroke
      field.setAttribute('data-client-invalid', '');
      field.setAttribute('aria-invalid', 'true');
      if (!describedBy.includes(box.id)) field.setAttribute('aria-describedby', [...describedBy, box.id].join(' '));
    } else {
      if (box) {
        const rest = describedBy.filter((id) => id !== box.id);
        rest.length ? field.setAttribute('aria-describedby', rest.join(' ')) : field.removeAttribute('aria-describedby');
        box.removeAttribute('data-client-error');   // a new error on this field creates a fresh box
        box.removeAttribute('id');
        box.classList.add('is-leaving');             // fade out, then remove
        box.addEventListener('animationend', () => box.remove(), { once: true });
        setTimeout(() => box.remove(), 400);         // fallback if animations are disabled
      }
      field.removeAttribute('data-client-invalid');
      field.removeAttribute('aria-invalid');
    }
  }

  function validateField(field, final = true) {
    if (!isField(field)) return;
    setError(field, messageFor(field, final));
  }

  card.addEventListener('input', (event) => {
    const field = event.target;
    if (!isField(field)) return;
    // The user is editing, so an old error rendered by the server for this field is stale.
    (field.closest('.field') || field.parentElement).querySelectorAll('.field__error:not([data-client-error])').forEach((el) => el.remove());
    const final = field.dataset.touched === '1' || field.hasAttribute('data-client-invalid');
    validateField(field, final);
  });
  card.addEventListener('focusout', (event) => {
    if (!isField(event.target)) return;
    event.target.dataset.touched = '1';
    validateField(event.target, true);
  });
  card.addEventListener('change', (event) => validateField(event.target, true));   // selects and date picker

  /* ---- form handling ----------------------------------------------------- */
  function bind() {
    const form = card.querySelector('[data-receipt-form]');
    if (!form) return;
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (form.dataset.submitting) return;
      // Frontend validation: mark every wrong field with its message, then focus the first one.
      Array.from(form.elements).forEach((el) => validateField(el, true));
      const firstInvalid = form.querySelector('[data-client-invalid]');
      if (firstInvalid || !form.checkValidity()) {
        (firstInvalid || form.querySelector(':invalid')).focus();
        return;
      }
      form.querySelector('[name="entered_at"]').value = new Date().toISOString();
      const fields = Object.fromEntries(Array.from(new FormData(form)).filter(([key]) => key !== 'csrfmiddlewaretoken'));
      const button = form.querySelector('[data-submit-btn]');
      form.dataset.submitting = '1'; button.classList.add('is-loading'); button.setAttribute('aria-disabled', 'true');
      try {
        const response = await send(fields);
        if (response.ok && isJson(response)) { window.location.assign(postUrl); return; }   // reload: shows the saved message
        if ((response.status === 400 || response.status === 409) && isJson(response)) {   // server found field errors: show them
          const result = await response.json();
          card.innerHTML = result.html;
          bind();
          if (result.duplicate) {
            // A duplicate is not something the teller can fix, so it gets the pop-up only.
            // Server already leaves out the summary when the duplicate is the only error; if some other
            // error is shown too, keep everything as rendered.
            const summary = card.querySelector('#error-summary');
            const items = summary ? summary.querySelectorAll('li') : [];
            const onlyDuplicate = !summary || (items.length === 1 && items[0].querySelector('a[href$="#id_bank_reference_no"]'));
            if (onlyDuplicate) {
              if (summary) summary.remove();
              const refField = card.querySelector('#id_bank_reference_no');
              if (refField) {
                (refField.closest('.field') || card).querySelectorAll('.field__error').forEach((el) => el.remove());
                refField.removeAttribute('aria-invalid');
                const ids = (refField.getAttribute('aria-describedby') || '').split(' ')
                  .filter((id) => id && document.getElementById(id));
                ids.length ? refField.setAttribute('aria-describedby', ids.join(' ')) : refField.removeAttribute('aria-describedby');
              }
            }
            showDuplicate(result.duplicate);
            return;
          }
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
