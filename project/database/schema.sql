-- ============================================================================
-- Payment Verification & Reconciliation Automation
-- Database Schema (PostgreSQL 14+)
-- Sesuai ERD di Technical Design Document, Bagian 12
-- ============================================================================
-- Cara pakai (dari Git Bash, setelah docker compose up -d jalan):
--   docker exec -i reconciliation_postgres psql -U reconciliation_user -d reconciliation_db < database/schema.sql
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- untuk gen_random_uuid()

-- ============================================================================
-- 1. customers -- data nasabah/pengirim
-- ============================================================================
CREATE TABLE customers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number        VARCHAR(20) UNIQUE NOT NULL,      -- format E.164, contoh: +60123456789
    full_name           VARCHAR(255) NOT NULL,
    kyc_status          VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                            CHECK (kyc_status IN ('PENDING', 'VERIFIED', 'REJECTED')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE customers IS 'Data nasabah yang berinteraksi dengan bot/teller';

-- ============================================================================
-- 2. bot_transactions -- transaksi yang diinisiasi customer (via bot atau teller)
-- ============================================================================
CREATE TABLE bot_transactions (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_code            VARCHAR(30) UNIQUE NOT NULL,   -- contoh: MIR-20260908-00123
    customer_id                 UUID REFERENCES customers(id) ON DELETE SET NULL,
    sender_name                 VARCHAR(255) NOT NULL,
    sender_phone                VARCHAR(20),
    recipient_name               VARCHAR(255),
    recipient_bank               VARCHAR(50),                  -- kode kanonik, contoh: 'BANK_MANDIRI'
    recipient_account            VARCHAR(50),
    destination_country          VARCHAR(50),                  -- contoh: 'INDONESIA'
    purpose                      VARCHAR(255),                 -- contoh: 'FAMILY_SUPPORT'
    exchange_rate                NUMERIC(14,6),                 -- contoh: 3512.500000 (MYR->IDR)
    amount_sent_minor            INTEGER NOT NULL,              -- dalam sen, contoh RM20.00 = 2000
    expected_amount_received_minor INTEGER,
    -- entry_source: dari mana data ini masuk -- penting sejak ADR-0008 (Microsoft Forms interim
    -- vs custom web form target vs bot)
    entry_source                VARCHAR(30) NOT NULL DEFAULT 'BOT'
                                    CHECK (entry_source IN ('BOT', 'MS_FORMS', 'CUSTOM_FORM', 'OCR')),
    status                       VARCHAR(30) NOT NULL DEFAULT 'RECEIVED'
                                    CHECK (status IN (
                                        'RECEIVED', 'PENDING_RECEIPT', 'OCR_PROCESSING', 'OCR_REVIEW',
                                        'PENDING_BANK', 'MATCHED', 'AUTO_VERIFIED', 'FINANCE_REVIEW',
                                        'UNMATCHED', 'REJECTED', 'COMPLETED', 'ERROR'
                                    )),
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bot_transactions_status ON bot_transactions(status);
CREATE INDEX idx_bot_transactions_created_at ON bot_transactions(created_at);

COMMENT ON TABLE bot_transactions IS 'Transaksi sisi customer -- diisi via bot WhatsApp, Microsoft Forms (interim), atau custom web form (target), lihat ADR-0008';
COMMENT ON COLUMN bot_transactions.amount_sent_minor IS 'Nominal dalam sen/minor unit, JANGAN pakai float untuk uang';

-- ============================================================================
-- 3. receipts -- foto/screenshot bukti bayar (dipakai mulai Phase 2, ADR-0007)
-- ============================================================================
CREATE TABLE receipts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_transaction_id  UUID NOT NULL REFERENCES bot_transactions(id) ON DELETE CASCADE,
    file_path           VARCHAR(500) NOT NULL,     -- object storage key, contoh: 'receipts/2026/09/uuid.jpg'
    file_hash           CHAR(64) NOT NULL,          -- SHA256 hex, untuk deteksi duplicate
    perceptual_hash      VARCHAR(64),               -- untuk deteksi duplicate visual (screenshot beda kompresi)
    uploaded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    status               VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN ('PENDING', 'PROCESSING', 'CLASSIFIED', 'OCR_DONE', 'REJECTED'))
);

CREATE INDEX idx_receipts_bot_transaction_id ON receipts(bot_transaction_id);
CREATE INDEX idx_receipts_file_hash ON receipts(file_hash);

-- ============================================================================
-- 4. ocr_results -- hasil klasifikasi & ekstraksi OCR (Phase 2)
-- ============================================================================
CREATE TABLE ocr_results (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    receipt_id                  UUID NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
    raw_text                    TEXT,
    provider                    VARCHAR(30) CHECK (provider IN ('AZURE', 'GOOGLE', 'AWS', 'SELF_HOSTED')),
    classification_result       JSONB,     -- {"is_receipt": true, "bank": "RHB"}
    classification_confidence   NUMERIC(4,3),  -- 0.000 - 1.000
    extracted_fields             JSONB,     -- {"sender_name": "...", "amount": 70850, "reference": "1055889", ...}
    field_confidences            JSONB,     -- {"sender_name": 0.95, "amount": 0.99, ...}
    overall_confidence           NUMERIC(4,3),
    sanitization_applied         BOOLEAN NOT NULL DEFAULT false,  -- lihat Technical Design Doc Bagian 11.3
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ocr_results_receipt_id ON ocr_results(receipt_id);

-- ============================================================================
-- 5. bank_format_configs -- mapping kolom XLSX per bank (data-driven, bukan hardcode)
-- ============================================================================
CREATE TABLE bank_format_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_code       VARCHAR(20) UNIQUE NOT NULL,   -- contoh: 'RHB', 'MAYBANK', 'CIMB'
    sheet_name      VARCHAR(100) NOT NULL DEFAULT 'Sheet1',
    header_row      INTEGER NOT NULL DEFAULT 1,
    column_map      JSONB NOT NULL,                -- {"Date": "transaction_date", "Amount": "amount_raw", ...}
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 6. bank_file_batches -- 1 baris per file XLSX yang diproses
-- ============================================================================
CREATE TABLE bank_file_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name       VARCHAR(255) NOT NULL,
    file_hash       CHAR(64) UNIQUE NOT NULL,       -- SHA256, cegah file yang sama diproses 2x
    source_bank     VARCHAR(20) NOT NULL REFERENCES bank_format_configs(bank_code),
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ,
    status          VARCHAR(30) NOT NULL DEFAULT 'RECEIVED'
                        CHECK (status IN ('RECEIVED', 'PROCESSING', 'PROCESSED', 'QUARANTINED', 'ERROR')),
    row_count       INTEGER
);

-- ============================================================================
-- 7. bank_transactions -- 1 baris per transaksi hasil parsing XLSX bank
-- ============================================================================
CREATE TABLE bank_transactions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_file_batch_id      UUID NOT NULL REFERENCES bank_file_batches(id) ON DELETE CASCADE,
    transaction_date        DATE NOT NULL,
    transaction_type        VARCHAR(100),           -- raw dari bank, contoh: 'DUITNOW QR POS CR'
    amount_minor_units      INTEGER NOT NULL,       -- dalam sen
    raw_name                VARCHAR(255),
    account_or_ref          VARCHAR(100),
    description             TEXT,
    bank_reference          VARCHAR(100),           -- boleh NULL, tidak semua channel menyediakan
    source_bank             VARCHAR(20) NOT NULL REFERENCES bank_format_configs(bank_code),
    normalized_name         VARCHAR(255),           -- uppercase, trim, standarisasi BIN/BINTI/dst
    normalized_amount       INTEGER,
    dedup_hash              CHAR(64) UNIQUE NOT NULL,  -- hash(bank+date+amount+reference+raw_name)
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_bank_transactions_date ON bank_transactions(transaction_date);
CREATE INDEX idx_bank_transactions_amount ON bank_transactions(amount_minor_units);
CREATE INDEX idx_bank_transactions_reference ON bank_transactions(bank_reference);
CREATE INDEX idx_bank_transactions_batch_id ON bank_transactions(bank_file_batch_id);

-- ============================================================================
-- 8. reconciliations -- hasil matching antara bot_transactions & bank_transactions
-- ============================================================================
CREATE TABLE reconciliations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bot_transaction_id      UUID REFERENCES bot_transactions(id) ON DELETE SET NULL,
    bank_transaction_id     UUID REFERENCES bank_transactions(id) ON DELETE SET NULL,
    match_level             SMALLINT CHECK (match_level BETWEEN 1 AND 5),
    match_score             NUMERIC(5,2) CHECK (match_score BETWEEN 0 AND 100),
    match_status            VARCHAR(30) NOT NULL
                                CHECK (match_status IN (
                                    'AUTO_MATCH', 'REVIEW', 'UNMATCHED', 'REJECTED',
                                    'MULTIPLE_CANDIDATES', 'MATCHED_OVERPAID', 'MATCHED_UNDERPAID'
                                )),
    matched_by              VARCHAR(100),           -- 'SYSTEM' atau finance_users.id sebagai teks
    matched_at              TIMESTAMPTZ,
    review_notes            TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reconciliations_status ON reconciliations(match_status);
CREATE INDEX idx_reconciliations_bot_txn ON reconciliations(bot_transaction_id);
CREATE INDEX idx_reconciliations_bank_txn ON reconciliations(bank_transaction_id);

-- ============================================================================
-- 9. finance_users -- staf finance yang melakukan review
-- ============================================================================
CREATE TABLE finance_users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(255) NOT NULL,
    email               VARCHAR(255) UNIQUE NOT NULL,
    azure_ad_object_id  VARCHAR(100) UNIQUE,        -- untuk SSO Entra ID, lihat Technical Design Doc Bagian 21
    role                VARCHAR(30) NOT NULL DEFAULT 'FINANCE_VIEWER'
                            CHECK (role IN ('FINANCE_VIEWER', 'ADMIN', 'AUDITOR')), -- 2 role dulu di MVP-Solo
    active              BOOLEAN NOT NULL DEFAULT true,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- 10. audit_logs -- APPEND-ONLY, jangan pernah UPDATE/DELETE baris di sini
-- ============================================================================
CREATE TABLE audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(50) NOT NULL,       -- contoh: 'bot_transactions', 'reconciliations'
    entity_id       UUID NOT NULL,
    action          VARCHAR(50) NOT NULL,       -- contoh: 'STATUS_CHANGED', 'MATCH_DECIDED'
    actor           VARCHAR(100) NOT NULL,      -- 'SYSTEM' atau finance_users.email
    before_state    JSONB,
    after_state     JSONB,
    "timestamp"     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_source       VARCHAR(50)
);

CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_timestamp ON audit_logs("timestamp");

-- ============================================================================
-- 11. processing_jobs -- job queue tracking (OCR, parse XLSX, matching, notifikasi)
-- ============================================================================
CREATE TABLE processing_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type        VARCHAR(50) NOT NULL
                        CHECK (job_type IN ('OCR', 'PARSE_XLSX', 'MATCH', 'NOTIFY')),
    status          VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'RETRYING')),
    target_ref      VARCHAR(255),               -- transaction_code atau file_name terkait
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_processing_jobs_status ON processing_jobs(status, job_type);

-- ============================================================================
-- RELASI RINGKAS (lihat database/ERD.md untuk diagram lengkap)
-- ============================================================================
-- customers            1 --- N  bot_transactions
-- bot_transactions      1 --- N  receipts                 (mulai Phase 2)
-- receipts              1 --- N  ocr_results               (mulai Phase 2)
-- bank_format_configs   1 --- N  bank_file_batches
-- bank_format_configs   1 --- N  bank_transactions
-- bank_file_batches     1 --- N  bank_transactions
-- bot_transactions      1 --- N  reconciliations  (bisa N kandidat sebelum 1 dipilih, lihat Bagian 15.4)
-- bank_transactions     1 --- N  reconciliations
-- audit_logs & processing_jobs berdiri sendiri, mereferensikan entity lain via entity_type+entity_id
-- ============================================================================
