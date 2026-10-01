# Maintenance, testing and troubleshooting

> The requirement sheet asks for maintenance documentation listing potential problems, how to detect them with tests, and the fix.

## 1. Routine tasks

| Task | How often | Command |
|---|---|---|
| Run the automated tests | Before every change goes live and after every upgrade | `python manage.py test` |
| Security self-check | After changing `.env` for production | `python manage.py check --deploy` |
| Database backup | Daily (scheduled, see README section 7) | `.\scripts\backup.ps1` |
| Restore test | Monthly: copy a backup to a test folder, point `db.sqlite3` at it, sign in | manual |
| Recover interrupted imports | After every unexpected shutdown (the server script does it at start) | `python manage.py recover_imports --minutes 10` |
| Read the audit trail | Weekly by the Admin | Admin > Audit trail |
| Update dependencies | Quarterly, in a copy first | `pip list --outdated`, then run the tests |

## 2. Potential problems, detection and solution

| # | Problem | Symptom | How to detect (test / check) | Solution |
|---|---|---|---|---|
| 1 | The bank changes the statement layout (header no longer on row 4, renamed columns) | Upload says "Row 4 must contain the column headers, but these are missing: ..." | `ParserTests.test_wrong_header_row_gives_actionable_error`; add the new bank file to `sample_data/` and a parser test | Adjust `STATEMENT_HEADER_ROW` or add aliases in `parser.HEADER_ALIASES`; re-run tests |
| 2 | Row 1 text changes so account/date cannot be read | "Row 1 of the file could not be read..." | `ParserTests.test_unreadable_row1_asks_for_manual_details` | Finance enters account and date in the form; developer extends `_parse_metadata` |
| 3 | Excel turns long references into numbers (`6.11E+08`) or drops leading zeros | Receipts that look identical do not match | `NormalizeTests.test_excel_float_reference` | Download **CSV** from the bank (the real flow), or format the column as text. Scientific notation cannot be repaired automatically |
| 4 | Same file uploaded twice, or overlapping periods | "This exact file was already imported..." or skipped rows in the summary | `EngineTests.test_br1_*` | Expected behaviour (BR-1), nothing to fix |
| 5 | Import stuck at "Processing" after a restart | Progress bar never completes; re-upload says duplicate | `MaintenanceTests.test_recover_imports_marks_stuck_imports_failed_and_allows_retry` | `python manage.py recover_imports`, then upload again |
| 6 | SQLite "database is locked" | Import shows Failed, log has `OperationalError` | Log file / console; WAL and a 20 s timeout are already on | Retry once; if it recurs with many users, switch to PostgreSQL (`DB_ENGINE=postgres`) |
| 7 | Too many false "typo" suggestions, or typos missed | Finance rejects many suggestions, or many typos stay Not found | Collect 50 real cases into a test like `test_typo_is_only_a_suggestion` | Tune `MATCH_TYPO_MIN_SCORE` (higher = stricter). Amount tolerance is never configurable (BR-8) |
| 8 | A bank row is claimed by the wrong receipt (two receipts, same amount and reference) | One shows Verified, the other Not found | `EngineTests.test_one_bank_row_serves_only_one_receipt` | Finance closes the duplicate with a reason, or asks the teller which receipt is real |
| 9 | Receipts reported for the wrong branch | Branch shows the wrong code | `ReviewTests.test_reassign_branch_notifies_new_branch` | Finance > receipt > Other actions > Move to another branch |
| 10 | Teller device clock is wrong | Offline receipts show odd times | `ReceiptViewTests.test_old_offline_timestamp_is_trusted_but_future_is_not` | The server ignores future times and anything older than 31 days; fix the device clock |
| 11 | Desktop notifications never appear | No pop-ups, bell still counts | Browser site settings; address bar must be `https://` or `localhost` | Enable HTTPS (README section 7), click "Enable desktop alerts", allow notifications. Enable the e-mail digest as a fallback |
| 12 | Offline queue does not empty | Yellow "Waiting to sync" card stays | Open the card: rejected items show the reason | Fix the cause (duplicate, wrong length) and re-enter, then use **Remove**. If the page was never opened while online, open it once online |
| 13 | Everyone is signed out suddenly | Sign-in page after a restart | `DJANGO_SECRET_KEY` changed or `.env` missing | Keep the key stable; restore `.env` |
| 14 | Locked account | "Too many failed attempts" | `AccessControlTests.test_login_lockout_after_repeated_failures` | Wait 15 minutes, or restart the server (the counter is in memory), or Admin resets the password |
| 15 | New user cannot sign in | "email address or password is incorrect" | `UserManagementTests` | Admin > Users: check the email, reset the password, confirm the account is Active |
| 16 | Old service worker serves a stale page | UI looks old after an upgrade | DevTools > Application > Service Workers | Bump `STATIC_CACHE` / `PAGES_CACHE` names in `static/js/sw.js`; users press Ctrl+F5 |
| 17 | Disk fills up | Server slows or fails | Check `db.sqlite3` and `backups\` size | Backups keep 30 copies automatically; archive old statements by exporting the database; never delete audit rows |
| 18 | Slow matching with very large histories | Import takes minutes | Time an import with 50,000 rows | The engine loads all credit rows in memory (fine to roughly 100,000). Beyond that add database filters by date and move to Redis + RQ |
| 19 | Upgrade of Python/Django breaks something | Tests fail after upgrade | `python manage.py test` | Fix or pin the version in `requirements.txt` (ranges are pinned to Django 5.2) |
| 20 | Indonesian/Malay text slips into the UI | A screen is not English | `MaintenanceTests.test_all_user_facing_text_is_english` | Replace the text (BR-9) and extend the banned-word list if needed |

## 3. How to add a regression test for a new problem

1. Reproduce it with the smallest data possible. For statement problems use `csv_upload([...])` and `credit_row(...)` from `apps/core/testing.py`.
2. Write the test in the app it belongs to (`apps/reconciliation/tests.py` for parsing and matching).
3. Run `python manage.py test apps.reconciliation.tests.EngineTests.test_name` and watch it fail.
4. Fix the code, run the whole suite, commit both together.

## 4. Logs

Console output (the PowerShell window or the scheduled task). Look for lines with `ERROR` or `Import <id> failed`.
To keep a file: `.\scripts\serve.ps1 *>> logs\server.log` (create the `logs` folder first).

## 5. Restore from backup

```powershell
# Stop the server first (Ctrl+C or stop the scheduled task)
Copy-Item backups\db-20261001-180000.sqlite3 db.sqlite3 -Force
Remove-Item db.sqlite3-wal, db.sqlite3-shm -ErrorAction SilentlyContinue
.\scripts\serve.ps1
```
