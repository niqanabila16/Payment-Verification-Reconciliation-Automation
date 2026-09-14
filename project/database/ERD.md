# ERD -- Entity Relationship Diagram (Referensi Cepat)

Skema lengkap ada di `schema.sql`. Dokumen ini ringkasan visual + penjelasan tiap entity untuk referensi cepat tanpa perlu buka database.

## Diagram Relasi

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

finance_users  (berdiri sendiri, direferensikan reconciliations.matched_by sebagai teks email)
audit_logs     (berdiri sendiri, mereferensikan entity lain via entity_type + entity_id)
processing_jobs (berdiri sendiri, tracking job queue OCR/parse/match/notify)
```

## Penjelasan Tiap Entity

| Entity | Fungsi | Kapan Terisi |
|---|---|---|
| `customers` | Identitas nasabah (nomor HP sebagai key unik) | Sejak interaksi pertama dengan bot/teller |
| `bot_transactions` | Data transaksi sisi customer (sender, recipient, amount, purpose) | Setiap kali ada transaksi baru -- `entry_source` menandai asalnya (BOT/MS_FORMS/CUSTOM_FORM/OCR), lihat ADR-0008 |
| `receipts` | Pointer ke file foto/screenshot bukti bayar di object storage | Mulai Phase 2 (OCR), lihat ADR-0007 |
| `ocr_results` | Hasil klasifikasi & ekstraksi field dari receipt | Mulai Phase 2 |
| `bank_format_configs` | Mapping kolom XLSX per bank (data-driven) | Diisi manual sekali per bank baru, sebelum bank itu bisa diproses |
| `bank_file_batches` | 1 baris per file XLSX yang di-drop ke folder | Setiap kali file baru terdeteksi file watcher |
| `bank_transactions` | 1 baris per baris transaksi hasil parsing XLSX | Setelah `bank_file_batches` selesai diproses |
| `reconciliations` | Hasil matching antara `bot_transactions` dan `bank_transactions` | Setelah matching engine jalan |
| `finance_users` | Staf finance (2 role di MVP-Solo: FINANCE_VIEWER, ADMIN) | Setup awal |
| `audit_logs` | Log append-only setiap perubahan state penting | Terus-menerus, tidak pernah di-UPDATE/DELETE |
| `processing_jobs` | Tracking job queue (OCR, parse XLSX, matching, notifikasi) | Terus-menerus selama sistem berjalan |

## Catatan Penting

- **`reconciliations` sengaja many-to-many capable**: satu `bot_transaction` bisa punya beberapa baris `reconciliations` (kandidat match berbeda) sebelum satu dipilih sebagai final -- lihat kasus many-to-one/one-to-many di Technical Design Document Bagian 15.4.
- **Semua nominal uang disimpan sebagai INTEGER minor units (sen)**, bukan `NUMERIC`/`FLOAT` biasa untuk field yang dipakai kalkulasi/matching -- lihat `amount_sent_minor`, `amount_minor_units`. Ini mencegah floating point error pada uang.
- **`dedup_hash` di `bank_transactions` punya UNIQUE constraint** -- ini mekanisme idempotency utama supaya file yang sama diproses 2x tidak menghasilkan data ganda (lihat ADR-0005 dan Technical Design Document Bagian 14).
- **`entry_source` di `bot_transactions`** ditambahkan khusus untuk mendukung transisi dari Microsoft Forms (interim) ke custom web form (target) sesuai ADR-0008 -- memudahkan query "berapa banyak transaksi masih masuk lewat jalur interim" selama masa migrasi.
