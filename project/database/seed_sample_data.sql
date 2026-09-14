-- ============================================================================
-- Sample/Seed Data untuk Development Lokal
-- ============================================================================
-- Cara pakai (dari Git Bash, setelah schema.sql dijalankan):
--   docker exec -i reconciliation_postgres psql -U reconciliation_user -d reconciliation_db < database/seed_sample_data.sql
-- ============================================================================

-- 1. Bank format configs -- wajib diisi dulu sebelum bank_transactions bisa masuk
INSERT INTO bank_format_configs (bank_code, sheet_name, header_row, column_map) VALUES
('RHB', 'Sheet1', 1, '{
    "Date": "transaction_date",
    "Transaction Type": "transaction_type",
    "Amount": "amount_raw",
    "Name": "raw_name",
    "Account/Ref": "account_or_ref",
    "Description": "description",
    "Reference": "bank_reference"
}'::jsonb),
('MAYBANK', 'Transactions', 1, '{
    "Trans Date": "transaction_date",
    "Trans Description": "transaction_type",
    "Debit/Credit": "amount_raw",
    "Payer/Payee Name": "raw_name",
    "Ref No": "bank_reference"
}'::jsonb);

-- 2. Customers
INSERT INTO customers (id, phone_number, full_name, kyc_status) VALUES
('11111111-1111-1111-1111-111111111111', '+60123456789', 'MOHD IKHWAN BIN MOBIN', 'VERIFIED'),
('22222222-2222-2222-2222-222222222222', '+60198765432', 'JUNAEDI NURJANNAH', 'VERIFIED');

-- 3. Bot transactions (contoh data yang diisi via bot / Microsoft Forms interim, lihat ADR-0008)
INSERT INTO bot_transactions (
    id, transaction_code, customer_id, sender_name, sender_phone,
    recipient_name, recipient_bank, recipient_account,
    destination_country, purpose, exchange_rate,
    amount_sent_minor, expected_amount_received_minor,
    entry_source, status
) VALUES
(
    'aaaaaaaa-0000-0000-0000-000000000001', 'MIR-20260908-00123',
    '11111111-1111-1111-1111-111111111111', 'MOHD IKHWAN BIN MOBIN', '+60123456789',
    'IKMO NIAGA', 'BANK_MANDIRI', '1234567890',
    'INDONESIA', 'FAMILY_SUPPORT', 3512.500000,
    70850, 248932425,
    'MS_FORMS', 'PENDING_BANK'
),
(
    'aaaaaaaa-0000-0000-0000-000000000002', 'MIR-20260908-00124',
    '22222222-2222-2222-2222-222222222222', 'JUNAEDI NURJANNAH', '+60198765432',
    'BUDI SANTOSO', 'BANK_BCA', '9876543210',
    'INDONESIA', 'FAMILY_SHOPPING', 3512.500000,
    30000, 105375000,
    'MS_FORMS', 'PENDING_BANK'
);

-- 4. Bank file batch (contoh 1 file XLSX yang sudah "diproses")
INSERT INTO bank_file_batches (id, file_name, file_hash, source_bank, status, row_count, processed_at) VALUES
(
    'bbbbbbbb-0000-0000-0000-000000000001', 'RHB_20260908.xlsx',
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85' /* contoh hash, bukan hash asli */,
    'RHB', 'PROCESSED', 3, now()
);

-- 5. Bank transactions (contoh hasil parsing XLSX, cocok dengan format di Technical Design Document Bagian 5)
INSERT INTO bank_transactions (
    bank_file_batch_id, transaction_date, transaction_type, amount_minor_units,
    raw_name, account_or_ref, description, bank_reference, source_bank,
    normalized_name, normalized_amount, dedup_hash
) VALUES
(
    'bbbbbbbb-0000-0000-0000-000000000001', '2026-09-02', 'DUITNOW QR POS CR', 30000,
    'JUNAEDI NURJANNAH', 'QR20260902001', 'DuitNow QR Payment Received', NULL, 'RHB',
    'JUNAEDI NURJANNAH', 30000, 'hash_contoh_001'
),
(
    'bbbbbbbb-0000-0000-0000-000000000001', '2026-09-02', 'DUITNOW QR POS CR', 205000,
    'DINI', 'QR20260902002', 'DuitNow QR Payment Received', NULL, 'RHB',
    'DINI', 205000, 'hash_contoh_002'
),
(
    'bbbbbbbb-0000-0000-0000-000000000001', '2026-09-08', 'RPP INWARD INST TRF', 70850,
    'MOHD IKHWAN BIN MOBIN', 'RPP20260908123', 'Instant Transfer Received', '1055889', 'RHB',
    'MOHD IKHWAN BIN MOBIN', 70850, 'hash_contoh_003'
);

-- 6. Finance users (contoh, 2 role sesuai MVP-Solo -- lihat Solo Delivery Plan)
INSERT INTO finance_users (name, email, role) VALUES
('Siti Finance', 'siti.finance@company.com.my', 'FINANCE_VIEWER'),
('Ahmad Admin', 'ahmad.admin@company.com.my', 'ADMIN');

-- 7. Contoh hasil matching (Level 1, exact reference match -- lihat Technical Design Document Bagian 15)
INSERT INTO reconciliations (bot_transaction_id, bank_transaction_id, match_level, match_score, match_status, matched_by, matched_at)
SELECT
    'aaaaaaaa-0000-0000-0000-000000000001',
    bt.id,
    1, 99.00, 'AUTO_MATCH', 'SYSTEM', now()
FROM bank_transactions bt WHERE bt.bank_reference = '1055889';

-- Verifikasi cepat setelah seed:
--   SELECT transaction_code, status FROM bot_transactions;
--   SELECT bank_reference, amount_minor_units FROM bank_transactions;
--   SELECT match_level, match_score, match_status FROM reconciliations;
