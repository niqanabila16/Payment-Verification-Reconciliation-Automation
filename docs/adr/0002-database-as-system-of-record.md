# ADR-0002: Relational Database as System of Record, Not Spreadsheet Cell Color

## Status

Accepted

## Context

The AS-IS process marks verified transactions by coloring a row pink in an operational spreadsheet, done on a rotating basis by 3 finance staff. Cell color is not queryable data, stores no timestamp or identity of who verified it, and is prone to race conditions when more than one staff member edits the same spreadsheet. As transaction volume grows, this visual/manual approach cannot be audited for dispute investigation and does not scale.

## Decision

We will use a relational database (PostgreSQL) as the single system of record for all transaction and reconciliation state. Transaction status is represented as an explicit field within a state machine (RECEIVED, PENDING_BANK, MATCHED, FINANCE_REVIEW, etc.), not a color. Excel, WhatsApp/Teams, and any dashboard are outputs/views derived from the database -- never the primary store.

## Consequences

Transaction state can be queried, audited, and reported on programmatically; concurrent access by multiple finance staff becomes safe; dispute investigation has a complete history with clear timestamps and actors. On the other hand, finance staff must adapt from an "Excel-first" way of working to a state where Excel is just an export; the delivery team must build and operate a database plus backend service that did not previously exist; and a migration path is needed for historical data that currently only exists in old spreadsheets.
