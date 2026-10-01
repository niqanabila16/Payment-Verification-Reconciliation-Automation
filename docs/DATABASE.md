# Database notes

The Django models in `apps/*/models.py` implement **DBML v4** (`payment_reconciliation`). Migrations are in `apps/*/migrations/`.
Run `python manage.py makemigrations` after changing a model, never edit applied migrations.

| DBML table | Django model | Notes |
|---|---|---|
| `branches` | `accounts.Branch` | Lives in `accounts` to avoid a circular dependency with `User` |
| `banks` | `core.Bank` | |
| `users` | `accounts.User` | Custom user, e-mail sign-in; Django adds `password`, `last_login`, `is_superuser`, groups and permissions |
| `teller_submissions` | `receipts.TellerSubmission` | `reference_normalized` is recalculated on every save |
| `bank_statement_imports` | `reconciliation.StatementImport` | See "Additions" |
| `bank_statement_entries` | `reconciliation.StatementEntry` | `reference_normalized` holds the primary reference (ref 1, else ref 2, else bank ref no) |
| `reconciliation_matches` | `reconciliation.ReconciliationMatch` | `OneToOne` on submission and on the final entry; the suggestion is a separate FK |
| `match_comments` | `reconciliation.MatchComment` | |
| `notifications` | `core.Notification` | |
| `audit_logs` | `core.AuditLog` | Append-only in code (NFR-010) |

## Additions to DBML v4 (columns marked "(added)" in the code)

| Table | Column | Reason |
|---|---|---|
| `bank_statement_imports` | `uploaded_by`, `progress_percent`, `error_message`, `result_summary` (JSON) | Progress bar, upload summary (Match / Typo / Not found), audit |
| `bank_statement_imports` | `status` values `processing`, `processed`, `failed` | DBML only had the default `processed`; the progress bar needs the other two |
| `bank_statement_entries` | `source_row` | Points Finance to the exact row of the uploaded file |

## Deviations to be aware of

* Primary keys are `BigAutoField` (DBML shows `integer`).
* `teller_submissions.sync_status`: a row that reaches the server is stored as `synced`. The *pending* state lives in the Teller's browser queue, not in the database.
* `payment_method_code` accepts `CASH`, `CDM`, `TRANSFER` (requirement sheet) instead of the DBML examples `CHK, QR, CASH`. Change `receipts/constants.py` if QR/cheque are needed.
* `relationship` stores English codes (`SELF`, `SIBLING`, ...).
* `bank_statement_entries.reference_normalized` is 150 characters (DBML 50) because it can be derived from a long reference field.
* Overlapping statement periods (BR-1) are handled in code by skipping Bank Ref Nos already stored for the same bank and account, because the DBML unique index is per import only.
