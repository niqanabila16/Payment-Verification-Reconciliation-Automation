/* "Request new card": the Card No field starts with the fixed BIN (shown as a prefix); the Teller types the rest and the cards of the
   own branch that are still free are suggested as in a search box (most similar first). The server checks the choice again. */
(() => {
  const form = document.querySelector('[data-card-request]');
  if (!form) return;
  const input = form.querySelector('[data-card-suggest]');
  const list = document.getElementById('card-options');
  if (!input || !list) return;
  let timer = null;
  let latest = 0;

  const load = async () => {
    const ticket = ++latest;
    try {
      const response = await fetch(form.dataset.suggestUrl + '?q=' + encodeURIComponent(input.value), { credentials: 'same-origin', cache: 'no-store' });
      if (!response.ok || ticket !== latest) return;
      const data = await response.json();
      list.replaceChildren(...data.suggestions.map((suffix) => { const o = document.createElement('option'); o.value = suffix; return o; }));
    } catch (e) { /* offline: the Teller can still type the whole number */ }
  };

  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 150); });
  input.addEventListener('focus', load);
})();
