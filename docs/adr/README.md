# Architecture Decision Records

Architecture decision log for the Payment Verification & Reconciliation Automation project, written following the [Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) format (Title, Status, Context, Decision, Consequences).

Append-only: decisions that change are recorded as new ADRs that supersede old ones, not by editing existing history.

| # | Title | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record Architecture Decisions | Accepted |
| [0002](0002-database-as-system-of-record.md) | Relational Database as System of Record, Not Spreadsheet Cell Color | Accepted |
| [0003](0003-deterministic-matching-not-ml.md) | Deterministic Rule-Based Matching, Not Machine Learning | Accepted |
| [0004](0004-no-virtual-account.md) | Multi-Field Reconciliation Without a Virtual Account | Accepted |
| [0005](0005-bank-ingestion-via-xlsx-folder.md) | Bank Data Ingestion via XLSX + Folder Automation, Not a Direct Bank API | Accepted |
| [0006](0006-teams-not-whatsapp-group-for-internal-notification.md) | Internal Finance Notifications via Microsoft Teams, Not WhatsApp Group Automation | Accepted |
| [0007](0007-finance-first-sequencing.md) | Automate the Finance Side Before Receipt OCR | Accepted (supersedes original sequencing) |
| [0008](0008-teller-data-capture-mechanism.md) | Microsoft Forms + SharePoint (Interim), Migrating to a Custom Web Form (Target) | Accepted |

## How to Add a New ADR

1. Take the next sequential number (0009, etc.).
2. Use the template: Status / Context / Decision / Consequences.
3. If the new ADR cancels/changes an old one, write "Status: Accepted (supersedes ADR-000X)" and add a note on the old ADR that it has been superseded -- do not delete the old ADR.
4. Update the table in this README.
