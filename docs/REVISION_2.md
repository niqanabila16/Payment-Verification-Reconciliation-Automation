# Revision 2: what changed and where

| # | Revision point | Implemented in |
|---|---|---|
| 1 | Finance **Reject** makes the Teller status "Reject" | `review.reject_receipt`, `MatchStatus.REJECTED`, `ui.teller_badge` |
| 2 | Reject visible on the Finance side | Reject tab + red badge in `reconciliation/queue.html` |
| 3 | Teller: Reject always on top; after correction back to Pending | `receipts.views._rejected_first`, `review.correct_submission` |
| 4 | Name = bank name vs the Teller's **account holder** | `engine.name_overlap` / `names_match` |
| 5 | Review criteria configurable (name / amount / reference), for now amount only | `settings.REVIEW_REASONS`, `ReconciliationMatch.review_reasons` |
| 6 | Pop-up when already-entered data is re-entered (new receipt and correction) | `ReceiptForm.duplicate/repeat`, `receipts/_duplicate_dialog.html`, `receipt_edit.js` |
| 7 | RHB: name = Sender`s Name before "/", amount = credit/debit, reference = QR id (DUITNOW QR POS CR) or Bank Ref No. | `parser.rhb_sender_name`, `rhb_qr_reference`, `clean_bank_ref` |
| 8 | ALB: only "DuitNow CR Trf CA" matched, others Open Item; description filter managed in Admin; name/reference from Reference 2 | `bank_profiles.ALB`, `parser.split_alb_reference`, `TransactionDescription`, Master data > Transaction descriptions |
| 10 | PBB: only "DUITNOW TRSF CR" matched; name = Reference 1, reference = Cheque No/Ref No | `bank_profiles.PBB` |
| 11 | Matching limited to the bank selected on upload | `engine.run_matching(bank=...)` |
| 12 | No GFP/Reject in the table; Note + GFP + Reject in one row on Detail | `_queue_results.html`, `detail.html` |
| 13 | After Reject: one Teller-vs-bank comparison; decision card at the bottom right | `views.detail`, `rejected_bank_statement_entry` |
| 14 | Only the extracted columns are stored and shown | `StatementEntry` (no raw columns), `0005_revision2` |
| 15 | Bank data older than 31 days is deleted | `services/retention.py`, `purge_bank_data` command |
| 16 | Card activation (role CS) | `apps/cards`, templates `cards/`, `card_select.js`, `pdf_preview.js` |

Interpretations to confirm with the business owner
* Point 2: "new column with status Reject" is a **Reject tab** plus status badge/note columns.
* Point 15: the 31 days count from the **upload date** of the statement file, not the transaction date.
* Maybank (MBB) had no spec: its reader is unchanged (reference = Transaction Ref, name not required).
* The "Send to teller / feedback" action was removed: Reject (with note) replaces it.
* Typo/fuzzy reference suggestions were removed: Review is for amount differences only.

Migrations: `core.0006`, `accounts.0004`, `receipts.0004`, `reconciliation.0005/0006`, `cards.0001`. Run `python manage.py migrate`.
Old "typo" receipts go back to Pending and are matched again on the next upload.

## Revision 3 (follow-up)

* **Matching = name + amount only.** The Teller's reference number is no longer compared with the bank row (RHB/ALB/PBB). Name: account holder vs bank name, at least 2 shared words in any order. Review = same name, different amount. Maybank prints no name, so it still matches on amount + reference.
* **Duplicate pop-up = same person (2+ shared name words) + same amount + same reference number**, against receipts in any status (verified, pending, reject) from any branch. The same person paying the same amount again with a different reference number is a different transaction and does not trigger the pop-up. The reference number is kept for the report and for this check.
* **Input rules (blocked while typing, pasting and on the server):** names accept letters and spaces only; the reference number accepts letters and digits only (6 to 20). `static/js/input_rules.js`, `ReceiptForm`.
* **GFP button:** it appears when a bank row is compared (Review, or Reject with a row). A receipt with no compared bank row (Pending / Not found) has nothing to approve.
* **Removed:** "Move to another branch".
