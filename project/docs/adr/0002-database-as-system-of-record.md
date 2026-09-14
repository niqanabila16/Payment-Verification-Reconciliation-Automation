# ADR-0002: Database Relasional sebagai Source of Truth, Bukan Warna Sel Spreadsheet

## Status

Accepted

## Context

Proses AS-IS menandai transaksi yang sudah diverifikasi dengan mewarnai baris spreadsheet operasional warna pink, dilakukan bergantian oleh 3 staf finance. Warna sel bukan data yang bisa di-query, tidak menyimpan timestamp atau identitas siapa yang memverifikasi, dan rawan race condition ketika lebih dari satu staf mengedit spreadsheet yang sama. Ketika volume transaksi bertambah, pendekatan visual/manual ini tidak dapat diaudit untuk investigasi dispute dan tidak scalable.

## Decision

Kami akan menggunakan database relasional (PostgreSQL) sebagai satu-satunya source of truth untuk seluruh state transaksi dan hasil reconciliation. Status transaksi direpresentasikan sebagai field eksplisit dalam sebuah state machine (RECEIVED, PENDING_BANK, MATCHED, FINANCE_REVIEW, dst), bukan warna. Excel, WhatsApp/Teams, dan dashboard apa pun hanyalah output/view yang diturunkan dari database -- tidak pernah menjadi tempat penyimpanan utama.

## Consequences

State transaksi dapat di-query, diaudit, dan dilaporkan secara terprogram; akses bersamaan oleh banyak staf finance menjadi aman; investigasi dispute punya riwayat lengkap dengan timestamp dan aktor yang jelas. Di sisi lain, staf finance harus beradaptasi dari kebiasaan kerja "Excel-first" ke kondisi di mana Excel hanyalah hasil export; tim delivery harus membangun dan mengoperasikan database beserta backend service yang sebelumnya tidak ada; dan diperlukan jalur migrasi untuk data historis yang saat ini hanya ada di spreadsheet lama.
