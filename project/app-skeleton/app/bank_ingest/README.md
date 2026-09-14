# app/bank_ingest

File watcher, readiness check, parser XLSX per bank (pakai `bank_format_configs` dari database, lihat `database/schema.sql` dan `samples/sample_bank_format_config_RHB.json`), normalisasi, dan dedup check. Lihat Technical Design Document Bagian 13-14.

File sample untuk uji coba parser ada di `samples/sample_bank_statement_RHB.xlsx` dan `samples/sample_bank_statement_MAYBANK.xlsx` (dua format kolom yang berbeda, sengaja dibuat begitu untuk menguji apakah parser benar-benar data-driven, bukan hardcode 1 format).
