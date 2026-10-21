# Database notes

The Django models in `apps/*/models.py` implement **DBML v4** (`payment_reconciliation`). Migrations are in `apps/*/migrations/`.
Run `python manage.py makemigrations` after changing a model, never edit applied migrations.

| DBML table | Django model | Notes |
|---|---|---|
| `branches` | `accounts.Branch` | Lives in `accounts` to avoid a circular dependency with `User`; `is_active` added |
| `banks` | `core.Bank` | `is_active` added |
| `users` | `accounts.User` | Custom user, e-mail sign-in; Django adds `password`, `last_login`, `is_superuser`, groups and permissions |
| `teller_submissions` | `receipts.TellerSubmission` | `reference_normalized` is recalculated on every save |
| `bank_statement_imports` | `reconciliation.StatementImport` | See "Additions" |
| `bank_statement_entries` | `reconciliation.StatementEntry` | `reference_normalized` holds the primary reference (ref 1, else ref 2, else bank ref no) |
| `reconciliation_matches` | `reconciliation.ReconciliationMatch` | `OneToOne` on submission and on the final entry; the suggestion is a separate FK |
| `notifications` | `core.Notification` | |
| `audit_logs` | `core.AuditLog` | Append-only in code (NFR-010) |

## Added in this revision

| Table / model | Purpose |
|---|---|
| `core.PaymentMethod`, `core.Relationship` | Value lists behind the Teller dropdowns, managed by Admin (Master data). `teller_submissions.payment_method_code` and `relationship` still store only the code |
| `is_active` on `Branch`, `Bank`, `PaymentMethod`, `Relationship` | Deactivate instead of delete |

## Revision v3: database changes

Apply with `python manage.py migrate` (backs up nothing by itself: run `.\scripts\backup.ps1` first). The migrations convert existing data.

| Model | Change | Migration |
|---|---|---|
| `core.Bank` | `statement_format` (`""`, `rhb`, `alb`, `pbb`, `mbb`) picks the file reader. Four bank categories RHB, ALB, PBB, MBB are seeded; MAYBANK becomes MBB; MANDIRI is removed if unused | `core.0004`, `core.0005` |
| `receipts.TellerSubmission` | `transaction_at` (date and time printed on the receipt, copied from the entry time for old rows); `sender_name` column now allows blank (the form still requires it); new indexes | `receipts.0003` |
| `reconciliation.StatementEntry` | `bank` (required), `amount` (Credit or Debit, whichever is filled), `transaction_date`, `references` (all reference columns), `raw_columns` (every column of the file, shown to Finance); back-filled from existing rows | `reconciliation.0004` |
| `reconciliation.ReconciliationMatch` | `status_changed_at` (newest first), `finance_note` (the single Note), `rejected_entry_ids` (never suggested again) | `reconciliation.0004` |
| `accounts.PasswordResetRequest` | removed (reset is by e-mailed link, nothing to store) | `accounts.0003` |

## Search analysis: which lookups are most frequent, and the indexes they need

Collected from the screens and services (the same lookups run on every page load, upload or save):

| # | Lookup (who, how often) | Columns | Index |
|---|---|---|---|
| 1 | Finance tabs and counters on every page view: matches by status, newest first | `match_status`, `status_changed_at` | `match_status_recent_idx` |
| 2 | Matching on every upload and every new receipt: bank rows of the same bank with the same amount | `bank`, `amount` | `entry_bank_amount_idx` |
| 3 | Matching and live search by reference (normalised) | `reference_normalized` | existing index on `reference_normalized` (entries and submissions) |
| 4 | Duplicate receipt check on every save, across all branches | `reference_normalized`, `amount` | `sub_ref_amount_idx` |
| 5 | Re-upload and overlap check: skip rows already stored | `bank_ref_no` | `entry_bankref_idx` |
| 6 | Teller list of the own branch, newest first | `branch`, `entered_at` | `sub_branch_entered_idx` |
| 7 | Finance bank filter | `bank`, `entered_at` | `sub_bank_entered_idx` |
| 8 | Weekly / monthly report periods | `transaction_at`, `transaction_date` | `sub_txn_at_idx`, `entry_txn_date_idx` |
| 9 | Notification bell (every few seconds per user) | `recipient`, `status` | existing index on notifications |

Free-text live search (name, reference, amount) uses `LIKE` over a few thousand rows per bank and is fast on SQLite and PostgreSQL. If it becomes slow with years of data, add a PostgreSQL `pg_trgm` index on `reference_normalized` and the name columns.

## Removed in this revision

* `match_comments` (no discussion thread for Tellers) and the `closed` status with `closed_reason` / `closed_at`. Existing closed items are converted to `not_found` by migration `reconciliation.0002`.
* Unique constraints on `bank_statement_imports.file_sha256` and on (bank, account, statement date): the same file may be uploaded again after a warning. Duplicate transactions are still prevented row by row (see below).

## Additions to DBML v4 (columns marked "(added)" in the code)

| Table | Column | Reason |
|---|---|---|
| `bank_statement_imports` | `uploaded_by`, `progress_percent`, `error_message`, `result_summary` (JSON) | Progress bar, upload summary (Match / Review / Not found / Open item), audit |
| `bank_statement_imports` | `status` values `processing`, `processed`, `failed` | DBML only had the default `processed`; the progress bar needs the other two |
| `bank_statement_entries` | `source_row` | Points Finance to the exact row of the uploaded file |

## Deviations to be aware of

* Primary keys are `BigAutoField` (DBML shows `integer`).
* `teller_submissions.sync_status`: a row that reaches the server is stored as `synced`. The *pending* state lives in the Teller's browser queue, not in the database.
* `payment_method_code` and `relationship` accept the codes in the Master data lists. The starting values are `CASH`, `CDM`, `TRANSFER` (requirement sheet) and `SELF`, `SIBLING`, ... Add `QR` or `CHK` in Master data if needed.
* `bank_statement_entries.reference_normalized` is 150 characters (DBML 50) because it can be derived from a long reference field.
* Duplicate transactions (BR-1), including re-uploads and overlapping periods, are handled in code by skipping Bank Ref Nos already stored for the same bank and account.
