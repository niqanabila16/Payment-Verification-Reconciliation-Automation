# Software Architecture

The picture below is the same diagram that the site shows under **Architecture** (`static/img/architecture.svg`).

![Architecture](../static/img/architecture.svg)

```mermaid
flowchart LR
  T[Teller browser] -->|HTTPS| FE
  F[Finance browser] -->|HTTPS| FE
  A[Admin browser] -->|HTTPS| FE
  subgraph FE[Frontend]
    TPL[Django templates] --- JS[Vanilla JS] --- SW[Service worker]
  end
  FE <-->|HTTP| BE
  subgraph BE[Backend - Python 3.12 + Django 5.2]
    AUTH[Auth + roles] --- PARSE[Statement parser] --- ENG[Matching engine]
    ENG --- THR[Import thread] --- NOTI[Notifications] --- AUD[Audit log]
  end
  BE <--> DB[(SQLite / PostgreSQL)]
  BE <--> CACHE[(Local memory cache)]
  BE -.optional.-> SMTP[SMTP e-mail digest]
  BANK[Bank website] -. manual CSV/XLSX download .-> F
```

## Request flows

1. **Teller reports a payment.** `receipts.js` validates length rules in the browser, posts the form as JSON.
   If the server is unreachable the receipt is stored in `localStorage` with a client-generated UUID and re-sent later.
   `create_submission()` is idempotent on that UUID, takes the branch from the session and creates a *pending* match row (BR-6).
2. **Finance uploads a statement.** `start_import()` checks size, SHA-256 (BR-1), parses rows (header on row 4, rows 1 and 3 ignored)
   and starts a background thread. The thread stores new rows, calls `run_matching()` and reports progress to the progress bar.
3. **Matching engine.** For each open receipt, only credit rows of the same bank are considered (company branch is never a filter):

   | Condition | Result |
   |---|---|
   | Reference equal/contained after normalisation **and** amount equal to the sen | `gfp` (score 100) |
   | Reference matches but amount differs | `manual_review` (BR-8), only a *suggestion* |
   | Amount equal and RapidFuzz similarity of references >= `MATCH_TYPO_MIN_SCORE` | `typo`, only a *suggestion* |
   | Otherwise | `not_found`, retried on every new statement until `RECHECK_WINDOW_DAYS` (BR-10) |

4. **Finance reviews.** Approve (final link), send feedback (comment + notification, Teller corrects, receipt re-matches),
   reject suggestion, link manually, close with mandatory reason, or move the receipt to another branch.
5. **Notifications.** Stored in the database, shown by the bell, raised as browser notifications by polling, optionally e-mailed as a digest.

## Decisions (ADR summary)

| # | Decision | Why | Revisit when |
|---|---|---|---|
| 1 | Django templates + vanilla JS instead of a React SPA | No build tooling on Windows, fast pages on weak branch PCs, requirement NFR-PERF-2 names HTML/JS and Django ORM | The UI needs heavy client-side state |
| 2 | SQLite default, PostgreSQL supported | Zero setup for the central PC; schema stays portable | More than ~20 concurrent users or multiple servers |
| 3 | Deterministic rules + RapidFuzz, no ML | Finance must be able to explain every result; zero tolerance on amounts | Real data shows systematic misses |
| 4 | Background thread for imports | Progress bar without extra infrastructure | Imports > a few minutes: Redis + RQ |
| 5 | Suggestions are separate from final links | A typo is never final without a human (DBML v3) | - |
| 6 | Service worker + localStorage queue | Central PC is off at night (constraint) | Branches need guaranteed delivery: add Web Push + server-side queue |
| 7 | Strict CSP, no inline JS/CSS | Defence in depth for a finance tool | - |
| 8 | No Django admin site | It would offer a password-change path that BR forbids | - |

## Where would automation plug in?

The sheet asks: *if the bank import should be automated, where must the integration happen, an API?*
The bank gives no Open API access (NFR-PERF-1), so the integration point is **not** an API call from this system into the bank.
Everything funnels through one function, `apps.reconciliation.services.importer.start_import()`, which only needs
*the file bytes, the bank and a user*. Any future source simply calls it:

| Option | Where it lives | Needs from the bank | Risk |
|---|---|---|---|
| Keep manual download (today) | Finance browser | nothing | Human step |
| Scheduled statement e-mail or SFTP drop, if the bank offers one for corporate accounts | A small watcher script/management command that reads a mailbox or folder and calls `start_import()` | A corporate channel and approval from the bank | Low: still file based |
| Browser automation (RPA) of the bank website | Separate script on the central PC | Allowed by bank terms of use | High: breaks on page changes, may violate terms and security policy |

Recommended first step: ask the bank whether a scheduled file delivery exists. It keeps the matching code untouched.

## Security notes

* Roles enforced server-side on every view (`role_required`); tested in `AccessControlTests.test_role_matrix`.
* CSRF on all POSTs, `HttpOnly` + `SameSite=Lax` cookies, secure cookies when `DJANGO_DEBUG=False`.
* Sign-in lockout (5 failures / 15 min), generic error for unknown e-mail or wrong password.
* Temporary passwords are shown once on a `no-store` page, never put in messages or cookies.
* Append-only audit log (updates and deletes raise errors); admins can read, not change.
* Uploaded files are parsed in memory and never stored or executed; only the hash and the parsed rows are kept.
