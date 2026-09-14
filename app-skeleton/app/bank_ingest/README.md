# app/bank_ingest

File watcher, readiness check, per-bank XLSX parser (using `bank_format_configs` from the database, see `database/schema.sql` and `samples/sample_bank_format_config_RHB.json`), normalization, and dedup check. See Technical Design Document Sections 13-14.

Sample files for testing the parser are in `samples/sample_bank_statement_RHB.xlsx` and `samples/sample_bank_statement_MAYBANK.xlsx` (two different column formats, deliberately provided to test whether the parser is genuinely data-driven rather than hardcoded to one format).
