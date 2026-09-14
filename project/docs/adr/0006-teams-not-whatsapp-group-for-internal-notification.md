# ADR-0006: Notifikasi Internal Finance via Microsoft Teams, Bukan Otomasi Grup WhatsApp

## Status

Accepted

## Context

Proses saat ini memposting string transaksi hasil ketikan teller ke grup WhatsApp yang dipakai finance. WhatsApp Business Platform API resmi dirancang untuk komunikasi bisnis-ke-customer (1:1 atau broadcast dengan template), bukan untuk memposting ke grup WhatsApp internal yang sudah ada -- melakukannya membutuhkan tooling tidak resmi yang melanggar ToS, yang tidak dapat diterima untuk sistem yang menangani data finansial. Perusahaan sudah beroperasi di dalam ekosistem Microsoft 365.

## Decision

Komunikasi dengan customer tetap menggunakan WhatsApp Business Platform (sesuai use case yang memang dirancang untuknya). Notifikasi internal finance (exception baru, alert antrian review, dsb.) akan menggunakan Microsoft Teams, bukan grup WhatsApp, karena Teams secara native diatur oleh kontrol keamanan tenant Microsoft perusahaan (Conditional Access, audit log).

## Consequences

Tidak ada lagi ketergantungan pada otomasi WhatsApp yang tidak resmi/tidak didukung; audit trail notifikasi menjadi native di dalam tenant Microsoft yang memang sudah diatur oleh tim security. Di sisi lain, staf finance harus beradaptasi ke channel notifikasi baru (Teams) menggantikan grup WhatsApp yang selama ini mereka pakai untuk koordinasi internal; perlu setup dan governance channel/webhook Teams sebagai bagian dari scope delivery.
