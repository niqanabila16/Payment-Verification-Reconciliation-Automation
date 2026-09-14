# ERD -- Entity Relationship Diagram (Quick Reference)

The full schema lives in `schema.sql`. This document is a visual summary plus an explanation of each entity, for quick reference without opening the database.

## Relationship Diagram

```
customers
    |
    | 1---N
    v
bot_transactions -------------------------+
    |                                     |
    | 1---N (Phase 2)                     | N---1
    v                                     v
receipts                          reconciliations
    |                                     ^
    | 1---N (Phase 2)                     | N---1
    v                                     |
ocr_results                       bank_transactions
                                          ^
                                          | N---1
                                   bank_file_batches
                                          ^
                                          | N---1
                                   bank_format_configs

finance_users   (stands alone, referenced by reconciliations.matched_by as an email string)
audit_logs      (stands alone, references other entities via entity_type + entity_id)
processing_jobs (stands alone, tracks the OCR/parse/match/notify job queue)
```

## Explanation of Each Entity

| Entity | Purpose | When It Gets Populated |
|---|---|---|
| `customers` | Customer identity (phone number as the unique key) | From the first interaction with the bot/teller |
| `bot_transactions` | Customer-side transaction data (sender, recipient, amount, purpose) | Every time there's a new transaction -- `entry_source` marks where it came from (BOT/MS_FORMS/CUSTOM_FORM/OCR), see ADR-0008 |
| `receipts` | Pointer to the payment-proof photo/screenshot file in object storage | From Phase 2 onward (OCR), see ADR-0007 |
| `ocr_results` | Classification & field-extraction results from a receipt | From Phase 2 onward |
| `bank_format_configs` | XLSX column mapping per bank (data-driven) | Filled in manually once per new bank, before that bank's files can be processed |
| `bank_file_batches` | One row per XLSX file dropped into the folder | Every time the file watcher detects a new file |
| `bank_transactions` | One row per transaction line parsed out of an XLSX file | After the corresponding `bank_file_batches` row finishes processing |
| `reconciliations` | Matching results between `bot_transactions` and `bank_transactions` | After the matching engine runs |
| `finance_users` | Finance staff (2 roles in the MVP-Solo: FINANCE_VIEWER, ADMIN) | Initial setup |
| `audit_logs` | Append-only log of every significant state change | Continuously, never UPDATEd/DELETEd |
| `processing_jobs` | Job queue tracking (OCR, XLSX parsing, matching, notifications) | Continuously, for as long as the system runs |

## Important Notes

- **`reconciliations` is deliberately many-to-many capable**: one `bot_transaction` can have several `reconciliations` rows (different match candidates) before one is chosen as final -- see the many-to-one/one-to-many cases in Technical Design Document Section 15.4.
- **All monetary amounts are stored as INTEGER minor units (cents)**, not `NUMERIC`/`FLOAT`, for any field used in calculations/matching -- see `amount_sent_minor`, `amount_minor_units`. This prevents floating-point error on money.
- **`dedup_hash` on `bank_transactions` has a UNIQUE constraint** -- this is the primary idempotency mechanism ensuring that reprocessing the same file does not produce duplicate data (see ADR-0005 and Technical Design Document Section 14).
- **`entry_source` on `bot_transactions`** was added specifically to support the transition from Microsoft Forms (interim) to the custom web form (target) per ADR-0008 -- it makes it easy to query "how many transactions are still coming in through the interim path" during the migration window.
