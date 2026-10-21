# Requirements traceability

Source: the SRS spreadsheet (functional requirements, business rules, NFR, constraints). Status below describes this code base (revision 2: no Closed status, no discussion thread, no access locking).
"Test" names refer to `python manage.py test`. **Done** = implemented and covered by an automated test; **Partial** = implemented with a stated limit.

## Functional requirements

| Code | Acceptance criterion | Implementation | Test | Status |
|---|---|---|---|---|
| REQ-F-1.1 | Matching runs automatically after every CSV/XLSX upload | `services/importer.py` > `engine.run_matching` | `EngineTests.test_full_demo_scenario` | Done |
| REQ-F-1.1 | 100% match becomes AUTO_VERIFIED (GFP) | `engine.decide` | `test_exact_match_is_gfp_and_teller_is_notified` | Done |
| REQ-F-1.1 | Teller is notified when the result is GFP (the only result a Teller hears about) | `services/notify.py` | `test_exact_match_is_gfp_and_teller_is_notified`, `test_teller_is_not_told_about_review_or_not_found` | Done |
| REQ-F-1.1 | Progress bar / loading status while processing | `import_progress.js`, `import_status` view | `PageSmokeTests.test_progress_endpoint` | Done |
| REQ-F-1.1 | Identical fields green, different fields red | `reconciliation/detail.html` (`is-same` / `is-diff`), plus icon + text | `test_detail_shows_green_for_identical_and_red_for_different` | Done |
| REQ-F-1.1 | Same name but a different amount becomes REVIEW (reasons configurable) | status `manual_review`, `review_reasons` | `MatchingTests.test_amount_difference_goes_to_review_with_reason` | Done |
| REQ-F-1.1 | Teller and bank data side by side | `reconciliation/detail.html`, `views._comparison` | `PageSmokeTests.test_finance_pages` | Done |
| REQ-F-1.1 | Finance approves (GFP) or Rejects with a note; Teller corrects | `review.confirm_suggestion`, `reject_receipt`, `correct_submission`, `receipts:edit` | `ReviewTests.*` | Done |
| REQ-F-1.1 | Summary after upload shows Match and Not Found (plus Review / Open Item) | `reconciliation/import_detail.html` | `MatchingTests` | Done |
| REQ-F-1.1 | Receipt with no similarity anywhere becomes NOT_FOUND | `engine.decide` step 4 | `test_br6_every_receipt_gets_a_definite_outcome` | Done |
| REQ-F-1.2 | Tabs for REVIEW and UNMATCHED | `views.TABS` (Pending, Review, Not found, Open Item, Verified, All) | `PageSmokeTests.test_finance_pages` | Done |
| REQ-F-1.2 | Newest teller data / newest match first (v3) | `ReconciliationMatch.Meta.ordering = -status_changed_at`, index `match_status_recent_idx` | `test_a_newly_matched_receipt_moves_to_the_top` | Done |
| REQ-F-1.2 | Red warning on the specific differing field | same as REQ-F-1.1 colours; reference shows character-level diff | `test_detail_shows_green...` | Done |
| REQ-F-1.3 | Upload accepts CSV and XLSX; box sits on the Reconciliation page, bank chosen next to it (RHB, ALB, PBB, MBB), wrong choice detected | `queue` view, `forms.StatementUploadForm`, `parser.py` | `ParserTests.test_sample_csv_and_xlsx_parse_identically`, `FinanceScreenTests.test_upload_box_is_on_the_main_page...` | Done |
| REQ-F-1.3 | Columns mapped without manual work | `bank_profiles.py` (aliases per bank) | same test | Done |
| REQ-F-1.3 note | Ignore row 1 and row 3, read header from row 4 | `parser.parse_statement` + RHB profile (`STATEMENT_HEADER_ROW`) | `test_br3_br4_br5_rows_1_and_3_ignored_header_on_row_4`, `test_wrong_header_row_gives_actionable_error` | Done |
| Users | Admin CRUD (create, read, update, deactivate) | `accounts/views.py` | `UserManagementTests` | Done (deactivate instead of delete, keeps history) |
| Users | Admin changes roles | `user_edit` | `test_change_role_teller_to_finance_clears_branch` | Done |
| Users | Admin resets passwords | `user_reset_password` | `PasswordPolicyTests` | Done |
| Users | Forgot password: unique expiring link e-mailed, user sets new password twice, no Admin request | `ForgotPasswordView`, `NewPasswordView` | `ForgotPasswordTests` | Done (needs SMTP in `.env`) |
| Users | Admin can delete a user (blocked if the user reported receipts) | `accounts.views.user_delete` | `UserManagementTests` | Done |
| Master data | Nothing locked; code editable (receipts follow), Delete when unused | `core/master.py` | `MasterDataTests` | Done |
| Receipt | Amount accepts a comma for the sen (MYR, no thousands separator) | `normalize.parse_teller_amount` | `ReceiptFormTests` | Done |
| Receipt | Transaction date and time as printed on the receipt | `TellerSubmission.transaction_at` | `ReceiptFormTests` | Done |
| Receipt | Teller form unchanged except the new transaction date and time | `receipts/forms.py` | `ReceiptFormTests.test_valid_receipt_has_the_same_fields_as_before_plus_the_transaction_time` | Done |
| Receipt | Same transaction already entered by another branch: red pop-up with name, amount, reference | `ReceiptForm.duplicate_info`, `receipts.js` | `ReceiptViewTests` | Done |
| Finance | Bank filter, live search without a button, Open Item category | `views.queue`, `app.js` | `PageSmokeTests.test_finance_filters_and_report` | Done |
| Finance | Generate report (Excel, weekly/monthly, Open Item or GFP) | `services/report.py` | `ReportTests` | Done |
| Finance | GFP + Reject buttons in Actions and one Note field | `queue.html`, `review.confirm/reject` | `ReviewTests` | Done |
| Users | Branch cannot be chosen for Finance/Admin | `app.js` disables the field; `UserForm.clean` clears it | `UserManagementTests.test_branch_field_is_disabled_by_script...` | Done |
| Master data | Admin adds values for branch, bank, payment method, relationship | `core/master.py` | `MasterDataTests` | Done |
| Receipt | Method (CASH/CDM/TRANSFER) and bank are mandatory dropdowns | `receipts/forms.py` | `test_dropdowns_are_mandatory`, `test_payment_method_must_be_one_of_the_three` | Done |
| Receipt | Branch set from the login session | `submissions.create_submission` | `test_branch_comes_from_the_login_session_not_the_form` | Done |
| Receipt | Reference length limits, submit rejected outside them | `forms.clean_bank_reference_no` + HTML attributes | `test_reference_length_is_validated_on_the_server`, `test_browser_side_length_rules_are_rendered` | Done |
| Receipt note | Same transaction entered twice returns "already saved at [time] with status [x]" | `forms.ReceiptForm.clean` | `test_duplicate_entry_reports_time_and_status` | Done |

## Business rules

| Code | Rule | Where | Test | Status |
|---|---|---|---|---|
| BR-1 | Never process the same transaction twice. A same-name file asks "upload again?"; stored rows are skipped | `importer.py` (row skip by Bank Ref No.), `upload.js` | `test_br1_same_file_uploaded_again...`, `test_br1_overlapping_periods...`, `FinanceScreenTests.test_same_file_name_shows_warning...` | Done |
| BR-2 | Ignore spaces, case, hyphens, dots | `core/normalize.py` | `NormalizeTests` | Done |
| BR-6 | Every receipt ends as Verified, Review or Not found, never hanging | pending row at creation; engine; `ensure` for orphans | `test_br6...` | Done |
| BR-7 | Notifications reach users even outside the website; opening the list marks them read | in-app + desktop notification polling + optional e-mail digest | `NotificationApiTests` | Partial: desktop alerts need HTTPS and an open browser; closed browsers rely on e-mail |
| BR-8 | No tolerance on amount; mismatch must go to review | `engine.decide` | `test_br8...` | Done |
| BR-9 | All website text and code comments in English | whole code base | `MaintenanceTests.test_all_user_facing_text_is_english` | Done (automated check is a keyword guard, review copy manually) |
| BR-10 | Matching works on receipts reported long before the statement (about 1 month and more), no separate category | re-check of every `pending` / `not_found` on each upload | `test_br10_old_receipt_still_matches_a_later_statement`, `test_receipts_older_than_a_month_are_still_matched` | Done |
| (password) | Forgot password through an e-mailed link (v3); no change-password page while signed in | `ForgotPasswordView`, `NewPasswordView` | `PasswordPolicyTests`, `ForgotPasswordTests` | Done |

## Non-functional requirements

| Code | Requirement | Where | Status |
|---|---|---|---|
| NFR-PERF-1 | No direct connection to bank systems | No outbound bank code exists; statements are uploaded | Done by design |
| NFR-PERF-2 | Fixed length constraints at frontend (HTML/JS) and backend (Django) for the reference | `receipts/forms.py`, `receipts.js` | Done (`ReceiptFormTests`) |
| NFR-010 (DBML) | Audit log append-only | `core/models.AuditLog` | Done (`AuditTrailTests`) |

## Constraints

| Constraint | How it is respected |
|---|---|
| Zero-cost dependencies, no WhatsApp / Microsoft integrations | Only open-source libraries (`requirements.txt`); comments thread and notifications are built in |
| No direct bank API | See [Architecture > Where would automation plug in](ARCHITECTURE.md#where-would-automation-plug-in) |
| Scope: from receiving the Teller's proof (online or offline) up to the final verification mark | No payment, accounting or bank-posting features exist |
| Distributed branches to one central computer that is off at night | Offline queue in the browser + idempotent sync (`receipts.js`, `sw.js`, `create_submission`); see README limitations about HTTPS |
| A reporting branch may not be the right branch | The engine never filters by branch; Finance can move a receipt (`review.reassign_branch`, `test_reassign_branch_notifies_new_branch`) |
