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
| 1 | A bank changes its statement layout, or a file is not read | Upload says which required columns are missing | `python manage.py inspect_statement <file> <bank>` shows what was understood; add the file as a test | Add aliases / header rules in `reconciliation/services/bank_profiles.py`; re-run tests |
| 1a | The wrong bank was chosen in the upload form | Message names the bank the file looks like and preselects it | `bank_profiles.detect_bank`, `BankMismatchError` tests | Press upload again with the suggested bank |
| 1b | Bank rows with no teller receipt | Items in the **Open Item** tab | `EngineTests` (open item) | Normal: they match when the teller's receipt arrives, or Finance handles them |
| 1c | Reset e-mail does not arrive | User waits, nothing in the mailbox | Server log shows an SMTP error | Check the `EMAIL_*` and `SITE_BASE_URL` lines in `.env` (README 6a); Admin uses Users > Reset password meanwhile |
| 2 | Row 1 text changes so account/date cannot be read | "Row 1 of the file could not be read..." | `ParserTests.test_unreadable_row1_asks_for_manual_details` | Finance enters account and date in the form; developer extends `_parse_metadata` |
| 3 | Excel turns long references into numbers (`6.11E+08`) or drops leading zeros | Receipts that look identical do not match | `NormalizeTests.test_excel_float_reference` | Download **CSV** from the bank (the real flow), or format the column as text. Scientific notation cannot be repaired automatically |
| 4 | The same statement is uploaded again | A warning asks "Upload again?"; the result shows 0 new rows | `EngineTests.test_br1_same_file_uploaded_again_adds_no_rows_and_no_duplicates` | Expected behaviour (BR-1): nothing is stored twice |
| 5 | Import stuck at "Processing" after a restart | Progress bar never completes | `recover_imports` command | `python manage.py recover_imports`, then upload again (stored rows are not duplicated) |
| 6 | SQLite "database is locked" | Import shows Failed, log has `OperationalError` | Log file / console; WAL and a 20 s timeout are already on | Retry once; if it recurs with many users, switch to PostgreSQL (`DB_ENGINE=postgres`) |
| 7 | Name check too strict or too lenient | Many receipts stay Not found because of name spelling, or wrong receipts are verified | Collect 50 real cases into a test in `MatchingTests` | Tune `NAME_WORD_MIN_SCORE` / `NAME_MATCH_MIN_WORDS`. Amount tolerance is never configurable (BR-8). `REVIEW_REASONS` lists what may go to Review (now only `amount`) |
| 8 | A bank row is claimed by the wrong receipt (two receipts, same amount and reference) | One shows Verified, the other Not found | `MatchingTests.test_one_bank_row_serves_one_receipt` | Finance presses Reject on the wrong one (with a Note); the same bank row is never suggested again for it |
| 9 | Receipts reported for the wrong branch | Branch shows the wrong code | `ReviewTests.test_reassign_branch_notifies_new_branch` | Finance > receipt > Move to another branch |
| 10 | Teller device clock is wrong | Offline receipts show odd times | `ReceiptViewTests.test_old_offline_timestamp_is_trusted_but_future_is_not` | The server ignores future times and anything older than 31 days (`OFFLINE_TIMESTAMP_MAX_AGE_DAYS`); fix the device clock |
| 11 | Desktop notifications never appear | No pop-ups, bell still counts | Browser site settings; address bar must be `https://` or `localhost` | Enable HTTPS (README section 7), click "Enable desktop alerts", allow notifications. Enable the e-mail digest as a fallback |
| 12 | Offline queue does not empty | Yellow "Waiting to sync" card stays | Open the card: rejected items show the reason | Fix the cause (duplicate, wrong length) and re-enter, then use **Remove**. If the page was never opened while online, open it once online |
| 13 | Everyone is signed out suddenly | Sign-in page after a restart | `DJANGO_SECRET_KEY` changed or `.env` missing | Keep the key stable; restore `.env` |
| 14 | Someone guesses passwords | Many `user.login_failed` rows in the audit trail | `AccessControlTests.test_no_lockout_after_repeated_failures` documents that there is NO lockout (requirement) | Keep the site on the office network or VPN; Admin resets the password of a compromised account |
| 15 | New user cannot sign in | "email address or password is incorrect" | `UserManagementTests` | Admin > Users: check the email, reset the password, confirm the account is Active |
| 15a | A dropdown lacks a value (new bank, payment method, branch, relationship) | Teller cannot pick it | `MasterDataTests` | Admin > Master data > add it (or activate it again) |
| 15b | A user forgot the password | User clicks Forgot password | `ForgotPasswordTests` | The e-mailed link does it; if the mail server is down the Admin presses Reset password |
| 16 | Old service worker serves a stale page | UI looks old after an upgrade | DevTools > Application > Service Workers | Bump `STATIC_CACHE` / `PAGES_CACHE` names in `static/js/sw.js`; users press Ctrl+F5 |
| 17 | Disk fills up | Server slows or fails | Check `db.sqlite3` and `backups\` size | Backups keep 30 copies automatically; archive old statements by exporting the database; never delete audit rows |
| 18 | Slow matching with very large histories | Import takes minutes | Time an import with 50,000 rows | The engine loads all credit rows in memory (fine to roughly 100,000) and re-checks every unmatched receipt on each upload. Beyond that add date filters and move to Redis + RQ |
| 18a | Receipts stay "Not found" forever | The Not found tab grows | `EngineTests` (old receipts keep matching) | Expected: they match as soon as the right statement arrives. Ask the teller to check the reference; the teller corrects it (Finance sends a request) |
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

## Daily purge of bank data (revision 2)

Bank statement data older than 31 days is deleted automatically before every upload and (at most hourly) when Finance opens Reconciliation. To also run it when nobody uses the system, schedule it daily (Windows Task Scheduler, action `python manage.py purge_bank_data`). `--dry-run` only counts. Receipts, notes and the audit trail are kept; verified (GFP) receipts keep a snapshot of their bank row.

## Forgot password and e-mail

* Flow: **Forgot password?** > enter e-mail > "Check your email" page (masked address, **Send the link again** after 60 s) > open the e-mailed link > type the new password twice.
* Real e-mail needs `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` in `.env` (Gmail: `smtp.gmail.com`, 587, TLS, a 16-character **app password**; the account needs 2-step verification). `DEFAULT_FROM_EMAIL` should be the same address as `EMAIL_HOST_USER`. Restart the server after editing `.env`.
* With `EMAIL_HOST` empty the message is only **printed in the server window** (development): that is why nothing arrives in a mailbox.
* A mail-server error never shows on the page (it must not reveal which addresses exist); look in the server log for "Password reset email".
