/* Card tables: checkbox selection with Shift+click range, select-all, selected counter; status dialog for CS requests (Reject asks for a type and a reason). */
(() => {
  const init = () => document.querySelectorAll('[data-card-table]').forEach((table) => {
    const boxes = () => Array.from(table.querySelectorAll('[data-row-check]'));
    const form = document.querySelector('[data-card-actions]');
    const counter = form && form.querySelector('[data-selected-count]');
    const submit = form && form.querySelector('[data-needs-selection]');
    let last = null;
    const refresh = () => {
      const n = boxes().filter((b) => b.checked).length;
      if (counter) counter.textContent = n + ' selected';
      if (submit) submit.disabled = n === 0;
      const all = table.querySelector('[data-select-all]');
      if (all) { all.checked = n > 0 && n === boxes().length; all.indeterminate = n > 0 && n < boxes().length; }
    };
    table.addEventListener('click', (event) => {
      const box = event.target.closest('[data-row-check]');
      if (!box) return;
      const list = boxes();
      if (event.shiftKey && last && last !== box) {
        const [a, b] = [list.indexOf(last), list.indexOf(box)].sort((x, y) => x - y);
        for (let i = a; i <= b; i += 1) list[i].checked = box.checked;
      }
      last = box;
      refresh();
    });
    table.addEventListener('change', (event) => {
      if (event.target.matches('[data-select-all]')) { boxes().forEach((b) => { b.checked = event.target.checked; }); refresh(); }
    });
    refresh();
  });
  init();
  document.addEventListener('region:updated', init);      // the table was replaced without a page load: bind the new one

  const dialog = document.getElementById('status-dialog');
  if (dialog) {
    const form = dialog.querySelector('[data-status-form]');
    const select = dialog.querySelector('[data-status-select]');
    const reject = dialog.querySelector('[data-reject-fields]');
    const REJECT = '3';
    // Reject needs a type and a reason (both drop-downs); the other statuses do not.
    const syncReject = () => {
      const on = select.value === REJECT;
      reject.hidden = !on;
      reject.querySelectorAll('select').forEach((el) => { el.required = on; if (!on) el.value = ''; });
    };
    select.addEventListener('change', syncReject);
    document.addEventListener('click', (event) => {
      const open = event.target.closest('[data-status-open]');
      if (!open) return;
      form.action = open.dataset.action;
      dialog.querySelector('[data-status-name]').textContent = open.dataset.name;
      Array.from(select.options).forEach((o) => { o.hidden = o.disabled = Boolean(o.dataset.from) && o.dataset.from !== open.dataset.current; });
      select.value = Array.from(select.options).find((o) => !o.disabled).value;
      syncReject();
      dialog.showModal();
    });
  }
})();
