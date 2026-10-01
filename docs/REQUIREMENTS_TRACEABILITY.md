# Requirements traceability

Source: the SRS spreadsheet (functional requirements, business rules, NFR, constraints). Status below describes this code base.
"Test" names refer to `python manage.py test`. **Done** = implemented and covered by an automated test; **Partial** = implemented with a stated limit.

## Functional requirements

| Code | Acceptance criterion | Implementation | Test | Status |
|---|---|---|---|---|
| REQ-F-1.1 | Matching runs automatically after every CSV/XLSX upload | `services/importer.py` > `engine.run_matching` | `EngineTests.test_full_demo_scenario` | Done |
| REQ-F-1.1 | 100% match becomes AUTO_VERIFIED (GFP) | `engine.decide` | `test_exact_match_is_gfp_and_teller_is_notified` | Done |
| REQ-F-1.1 | Teller is notified when the result is GFP | `services/notify.py` | same test | Done |
| REQ-F-1.1 | Progress bar / loading status while processing | `import_progress.js`, `import_status` view | `PageSmokeTests.test_progress_endpoint` | Done |
| REQ-F-1.1 | Identical fields green, different fields red | `reconciliation/detail.html` (`is-same` / `is-diff`), plus icon + text | `test_detail_shows_green_for_identical_and_red_for_different` | Done |
| REQ-F-1.1 | Similar data with a difference becomes REVIEW | statuses `typo`, `manual_review` | `test_typo_is_only_a_suggestion`, `test_br8_amount_difference_never_auto_verified` | Done |
| REQ-F-1.1 | Teller and bank data side by side | `reconciliation/detail.html`, `views._comparison` | `PageSmokeTests.test_finance_pages` | Done |
| REQ-F-1.1 | Finance approves (-> GFP) or sends feedback so the Teller fixes the input | `review.confirm_suggestion`, `send_feedback`, `correct_submission`, `receipts:edit` | `ReviewTests.test_confirm_typo...`, `test_feedback_posts...`, `test_teller_correction_resets_and_rematches` | Done |
| REQ-F-1.1 | Summary after upload shows Match and Not Found (plus Typo / Manual review) | `reconciliation/import_detail.html` | `test_full_demo_scenario` | Done |
| REQ-F-1.1 | Receipt with no similarity anywhere becomes NOT_FOUND | `engine.decide` step 4 | `test_br6_every_receipt_gets_a_definite_outcome` | Done |
| REQ-F-1.2 | Tabs for REVIEW and UNMATCHED | `views.TABS` (Needs attention, Review, Unmatched, Pending, Verified, Closed, All) | `test_finance_pages` | Done |
| REQ-F-1.2 | Chronological, oldest first | `ReconciliationMatch.Meta.ordering`, queue `order_by` | `MaintenanceTests.test_queue_is_oldest_first` | Done |
| REQ-F-1.2 | Red warning on the specific differing field | same as REQ-F-1.1 colours; reference shows character-level diff | `test_detail_shows_green...` | Done |
| REQ-F-1.3 | Upload accepts CSV and XLSX | `forms.StatementUploadForm`, `parser.py` | `ParserTests.test_sample_csv_and_xlsx_parse_identically` | Done |
| REQ-F-1.3 | Columns mapped without manual work | `parser.HEADER_ALIASES` | same test | Done |
| REQ-F-1.3 note | Ignore row 1 and row 3, read header from row 4 | `parser.parse_statement`, `STATEMENT_HEADER_ROW` | `test_br3_br4_br5_rows_1_and_3_ignored_header_on_row_4`, `test_wrong_header_row_gives_actionable_error` | Done |
| Users | Admin CRUD (create, read, update, deactivate) | `accounts/views.py` | `UserManagementTests` | Done (deactivate instead of delete, keeps history) |
| Users | Admin changes roles | `user_edit` | `test_change_role_teller_to_finance_clears_branch` | Done |
| Users | Admin resets passwords | `user_reset_password` | `PasswordPolicyTests` | Done |
| Receipt | Method (CASH/CDM/TRANSFER) and bank are mandatory dropdowns | `receipts/forms.py` | `test_dropdowns_are_mandatory`, `test_payment_method_must_be_one_of_the_three` | Done |
| Receipt | Branch set from the login session | `submissions.create_submission` | `test_branch_comes_from_the_login_session_not_the_form` | Done |
| Receipt | Reference length limits, submit rejected outside them | `forms.clean_bank_reference_no` + HTML attributes | `test_reference_length_is_validated_on_the_server`, `test_browser_side_length_rules_are_rendered` | Done |
| Receipt note | Same transaction entered twice returns "already saved at [time] with status [x]" | `forms.ReceiptForm.clean` | `test_duplicate_entry_reports_time_and_status` | Done |

## Business rules

| Code | Rule | Where | Test | Status |
|---|---|---|---|---|
| BR-1 | Never process the same statement data twice (same file, same day, overlapping periods) | `importer.py` (SHA-256, unique index, overlap skip) | `test_br1_same_file...`, `test_br1_same_statement_date...`, `test_br1_overlapping_periods...` | Done |
| BR-2 | Ignore spaces, case, hyphens, dots | `core/normalize.py` | `NormalizeTests` | Done |
| BR-6 | Every receipt ends as Verified, Review or Not found, never hanging | pending row at creation; engine; `ensure` for orphans | `test_br6...` | Done |
| BR-7 | Notifications reach users even outside the website | in-app + desktop notification polling + optional e-mail digest | `NotificationApiTests` | Partial: desktop alerts need HTTPS and an open browser; closed browsers rely on e-mail |
| BR-8 | No tolerance on amount; mismatch must go to review | `engine.decide` | `test_br8...` | Done |
| BR-9 | All website text and code comments in English | whole code base | `MaintenanceTests.test_all_user_facing_text_is_english` | Done (automated check is a keyword guard, review copy manually) |
| BR-10 | Matching works on receipts reported long before the statement (about 1 month) | `RECHECK_WINDOW_DAYS`, re-check of `pending` / `not_found` | `test_br10_late_statement_still_matches_old_receipt`, `test_engine_stops_retrying_after_the_window` | Done |
| (password) | Teller/Finance cannot change or reset own password; admin only | no such routes exist | `PasswordPolicyTests.test_no_self_service_password_routes_exist` | Done |

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
