/* Input rules: nothing is blocked while typing or pasting. Once a value is in the field, a rule that is broken shows a warning
   under the field (and the form cannot be sent until it is fixed). The server checks the same rules again.
   data-input-rule="letters": letters and spaces (names)      data-input-rule="alnum": letters and digits (reference numbers, ID)
   data-input-rule="digits": digits only (account, card numbers)   data-input-rule="phone": digits and a leading + (phone numbers) */
(() => {
  const RULES = {
    letters: { valid: /^[\p{L} ]*$/u, message: 'Only letters and spaces are allowed.' },
    alnum: { valid: /^[A-Za-z0-9]*$/, message: 'Only letters and digits are allowed.' },
    digits: { valid: /^[0-9]*$/, message: 'Only digits are allowed.' },
    phone: { valid: /^\+?[0-9]*$/, message: 'Only digits and a leading + are allowed.' },
  };
  const ICON = '<svg class="icon" aria-hidden="true" focusable="false"><use href="#i-x-circle"></use></svg>';

  const holder = (el) => el.closest('.bin-input') || el;
  const warningOf = (el) => {
    const next = holder(el).nextElementSibling;
    return next && next.matches('[data-rule-warning]') ? next : null;
  };

  const check = (el) => {
    const rule = RULES[el.dataset.inputRule];
    if (!rule) return;
    const broken = !rule.valid.test(el.value);
    let warning = warningOf(el);
    if (broken && !warning) {
      warning = document.createElement('div');
      warning.className = 'field__error';
      warning.dataset.ruleWarning = '';
      warning.setAttribute('role', 'alert');
      warning.innerHTML = ICON + '<span></span>';
      holder(el).after(warning);
    }
    if (broken) {
      warning.lastElementChild.textContent = rule.message;
      el.setCustomValidity(rule.message);
      el.setAttribute('aria-invalid', 'true');
    } else {
      if (warning) warning.remove();
      el.setCustomValidity('');
      if (el.hasAttribute('data-rule-warned')) el.removeAttribute('aria-invalid');
    }
    el.toggleAttribute('data-rule-warned', broken);
  };

  const apply = (event) => { if (event.target.matches && event.target.matches('[data-input-rule]')) check(event.target); };
  document.addEventListener('input', apply);       // typing, paste, drag and drop, autofill
  document.addEventListener('change', apply);
  document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('[data-input-rule]').forEach(check));
})();
