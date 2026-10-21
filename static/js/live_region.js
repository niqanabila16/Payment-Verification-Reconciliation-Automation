/* Live regions: tables, tabs, search and row actions update in place (no page reload, no jump to the top).
   [data-region]       the part of the page that is replaced (same name in the new page = same region)
   form[data-ajax]     POST in the background, then show the new state of the regions and the message
   form[data-ajax-get] search / filter: same, and the address is kept in the browser history
   tabs and pager links inside a region behave the same way.
   Without JavaScript every form and link still works as a normal page load. */
(() => {
  'use strict';
  const FLASH = '[data-flash]';

  const swap = (html, url, push) => {
    const next = new DOMParser().parseFromString(html, 'text/html');
    const regions = Array.from(document.querySelectorAll('[data-region]'));
    const found = regions.filter((r) => next.querySelector('[data-region="' + r.dataset.region + '"]'));
    if (!found.length) { window.location.assign(url); return false; }      // an error page or another screen: show it normally
    found.forEach((r) => { r.innerHTML = next.querySelector('[data-region="' + r.dataset.region + '"]').innerHTML; });
    const flash = document.querySelector(FLASH);
    const newFlash = next.querySelector(FLASH);
    if (flash && newFlash) flash.innerHTML = newFlash.innerHTML;
    if (push) history.pushState({ live: true }, '', url);
    document.dispatchEvent(new Event('region:updated'));
    return true;
  };

  const request = async (url, options, push) => {
    try {
      const response = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' }, ...options });
      swap(await response.text(), response.url || url, push);
    } catch (e) {
      window.location.assign(url);                                       // offline or interrupted: fall back to a normal load
    }
  };

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (event.defaultPrevented) return;
    if (form.matches('form[data-ajax]')) {
      event.preventDefault();
      const dialog = form.closest('dialog');
      request(form.action, { method: 'POST', body: new FormData(form, event.submitter) }, false);
      if (dialog) dialog.close();
    } else if (form.matches('form[data-ajax-get]')) {
      event.preventDefault();
      const url = new URL(form.action || window.location.href, window.location.href);
      url.search = new URLSearchParams(new FormData(form)).toString();
      request(url.toString(), {}, true);
    }
  });

  document.addEventListener('click', (event) => {
    const link = event.target.closest('[data-region] .tabs a, [data-region] .pager a');
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    request(link.href, {}, true);
  });

  window.addEventListener('popstate', () => window.location.reload());
})();
