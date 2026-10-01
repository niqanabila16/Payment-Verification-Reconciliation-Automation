# UI standards (alerts, warnings, cards, fields)

Baseline: **WCAG 2.2 level AA** and the **WAI-ARIA Authoring Practices**, combined with patterns from the GOV.UK Design System
(error summary, field anatomy) and common severity conventions of design systems such as Carbon, Atlassian and Material.
Reference links are at the end. The CSS lives in `static/css/app.css`; reusable templates in `templates/components/`.

## 1. Feedback: which component for which situation

| Situation | Component | ARIA | Persists? | Example in this app |
|---|---|---|---|---|
| A field value is invalid | Inline field error under the label, red border + icon + text | `aria-invalid="true"`, `aria-describedby` to the error | Until fixed | "The reference must contain 6 to 20 letters or digits (you entered 3)..." |
| A form has one or more errors | **Error summary** at the top, links to each field, receives focus | `role="alert"`, `tabindex="-1"` | Until fixed | `components/error_summary.html` |
| An action succeeded | Success alert (dismissible) | `role="status"` | Until dismissed / next page | "Comment sent." |
| An action failed or a rule blocked it | Danger alert, not auto-hidden | `role="alert"` | Until the page changes | "That bank row is already linked to another receipt..." |
| Something needs the user's attention but nothing failed | Warning alert | `role="alert"` | Until dismissed | "Some rows were skipped" after an import |
| Neutral information | Info alert | `role="status"` | Dismissible | "Outside Finance working hours" |
| Risky or irreversible action (deactivate, close, link, reset password) | **Confirmation dialog** that names the consequence | native `<dialog>` modal, focus on Cancel | Until answered | `components/confirm_dialog.html` |
| Long operation | Progress bar with percentage text | `role="progressbar"`, `aria-valuenow`, `aria-live` | Until done | Statement import |
| Connection lost | Status pill in the top bar + local-save message | `role="status"` | While offline | Offline receipt queue |
| Nothing to show | Empty state with a next step | - | - | "Nothing needs attention" |

Severity vocabulary is fixed: **info, success, warning, danger**. Every alert has an **icon, a title and text**, so colour is never the only signal (WCAG 1.4.1).
Errors and warnings are never auto-dismissed (users need time to read them, WCAG 2.2.1).

## 2. Writing the messages

1. Say **what happened**, **why** if known, and **what to do next** ("Check the proof of payment and type the full reference").
2. Be specific with numbers and names ("you entered 3").
3. Never blame the user, never show codes or stack traces. Server errors say that the data was not changed.
4. Keep the user's input after an error (WCAG 3.3.7 Redundant Entry): the form is re-rendered with the posted values.
5. Destructive dialogs name the object and the consequence ("They will be signed out of new sessions...").
6. Wrong sign-in never says which part was wrong (security), but a deactivated account is explained after the correct password.

## 3. Form field anatomy (`components/field.html`)

```
Label *                      <- label above the control, asterisk + visually hidden "(required)"
Hint text (optional)         <- format help, linked with aria-describedby
x Error message              <- only when invalid: icon + "Error:" (screen readers) + text
[ control ............... ]  <- min height 42 px, visible focus ring, red border + left bar when invalid
```

* Every control has a visible `<label>`; placeholders are examples, never labels (WCAG 3.3.2).
* Required fields are marked and the form states it once: "Fields marked * are required."
* Dropdowns replace free text wherever the value set is known (payment method, bank, relationship).
* Validation happens on submit (not on every keystroke) to avoid premature errors. On the Teller form `receipts.js` checks the HTML5 attributes (`required`, `minlength`, `maxlength`, `pattern`) with `checkValidity()` before sending; the server always re-validates and answers with the error summary.
* Touch targets are at least 32 px (buttons 40 px), above the WCAG 2.2 minimum of 24 px (2.5.8).

## 4. Cards

| Card | Anatomy | Used for |
|---|---|---|
| Content card | Header (title + action), body, optional footer with actions | Forms, lists, details |
| KPI card | Label with icon, large number, one-line note | Reconciliation overview |
| Stat card | Icon + label + number, tinted by outcome | Upload summary |
| Comparison table | Field, Teller value, Bank value; row tint + flag | Review screen |

Row states in the comparison: **green = identical, red = different, neutral = for information**, always with the words "Identical" / "Differs".
The reference field adds a character-level diff (`<mark class="chardiff">`: bold, underlined, tinted) so a single wrong digit is visible.

## 5. Status badges

| Status | Badge | Icon |
|---|---|---|
| Pending | grey | clock |
| Verified (GFP) | green | check-circle |
| Typo suspected | amber | alert-triangle |
| Manual review | violet | search |
| Not found | red | x-circle |
| Closed | muted grey | lock |

## 6. Accessibility checklist for every new screen

- [ ] One `<h1>`, landmarks (`header`, `nav`, `main`), skip link works
- [ ] All controls reachable and operable by keyboard; focus ring visible
- [ ] Text contrast >= 4.5:1 (tokens in `:root` were chosen as foreground/background pairs)
- [ ] Meaning never depends on colour alone
- [ ] Errors identified in text, linked from a summary, suggestions given
- [ ] Status changes announced (`role="status"` / `alert`)
- [ ] Works at 200% zoom and at 360 px width (tables scroll inside their own container)
- [ ] No inline scripts or styles (the Content-Security-Policy would block them)
- [ ] `prefers-reduced-motion` respected

## References

* WCAG 2.2 Understanding: [1.4.1 Use of Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html),
  [3.3.1 Error Identification](https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html),
  [3.3.3 Error Suggestion](https://www.w3.org/WAI/WCAG22/Understanding/error-suggestion.html),
  [3.3.4 Error Prevention (Legal, Financial, Data)](https://www.w3.org/WAI/WCAG22/Understanding/error-prevention-legal-financial-data.html),
  [3.3.7 Redundant Entry](https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry.html),
  [4.1.3 Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html),
  [2.5.8 Target Size (Minimum)](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
* WAI-ARIA Authoring Practices: [Alert](https://www.w3.org/WAI/ARIA/apg/patterns/alert/), [Dialog (Modal)](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/)
* GOV.UK Design System: [Error summary](https://design-system.service.gov.uk/components/error-summary/), [Error message](https://design-system.service.gov.uk/components/error-message/)
