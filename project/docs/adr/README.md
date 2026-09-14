# Architecture Decision Records

Log keputusan arsitektur untuk proyek Payment Verification & Reconciliation Automation, ditulis mengikuti format [Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) (Title, Status, Context, Decision, Consequences).

Bersifat append-only: keputusan yang berubah dicatat sebagai ADR baru yang men-supersede ADR lama, bukan dengan mengedit riwayat yang sudah ada.

| # | Judul | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Mencatat Keputusan Arsitektur dalam Bentuk ADR | Accepted |
| [0002](0002-database-as-system-of-record.md) | Database Relasional sebagai Source of Truth, Bukan Warna Sel Spreadsheet | Accepted |
| [0003](0003-deterministic-matching-not-ml.md) | Matching Deterministic Berbasis Rule, Bukan Machine Learning | Accepted |
| [0004](0004-no-virtual-account.md) | Reconciliation Multi-Field Tanpa Virtual Account | Accepted |
| [0005](0005-bank-ingestion-via-xlsx-folder.md) | Ingestion Data Bank via XLSX Manual + Folder Automation, Bukan Direct Bank API | Accepted |
| [0006](0006-teams-not-whatsapp-group-for-internal-notification.md) | Notifikasi Internal Finance via Microsoft Teams, Bukan Otomasi Grup WhatsApp | Accepted |
| [0007](0007-finance-first-sequencing.md) | Otomasi Sisi Finance Dulu Sebelum Receipt OCR | Accepted (supersedes urutan awal) |
| [0008](0008-teller-data-capture-mechanism.md) | Microsoft Forms + SharePoint (Interim) Bermigrasi ke Custom Web Form (Target) | Accepted |

## Cara Menambah ADR Baru

1. Salin nomor urut berikutnya (0009, dst).
2. Gunakan template: Status / Context / Decision / Consequences.
3. Kalau ADR baru membatalkan/mengubah ADR lama, tulis "Status: Accepted (supersedes ADR-000X)" dan tambahkan catatan di ADR lama bahwa ia sudah di-supersede -- jangan menghapus ADR lama.
4. Update tabel di README ini.
