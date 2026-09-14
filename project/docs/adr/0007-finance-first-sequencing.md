# ADR-0007: Otomasi Sisi Finance Dulu Sebelum Receipt OCR

## Status

Accepted (menggantikan urutan OCR-dulu pada Solo Delivery Plan awal)

## Context

Rencana delivery solo awal mengurutkan Receipt OCR Pipeline sebagai epic pertama yang dibangun, mengikuti alur natural customer -> bank. Namun untuk delivery oleh satu orang, OCR adalah komponen dengan ketidakpastian dan learning curve tertinggi (klasifikasi gambar, tuning akurasi ekstraksi, lead time eksternal onboarding OCR provider/WhatsApp Business API), sementara pain point AS-IS yang paling banyak menyita tenaga kerja saat ini justru ada di sisi finance (download dan pencocokan manual data bank), bukan di sisi teller.

## Decision

Kami akan membangun dan merilis otomasi sisi finance (bank file ingestion, matching engine, exception handling) terlebih dahulu, menggunakan mekanisme penangkapan data non-OCR yang ringan untuk sisi customer/teller (lihat ADR-0008), dan menunda epic Receipt OCR Pipeline ke Phase 2.

## Consequences

Menghapus risiko teknis OCR dan lead time verifikasi WhatsApp Business API dari jalur kritis rilis pertama; memberikan nilai tercepat terhadap pain point terbesar saat ini (kerja manual finance); alur kerja teller/customer tidak berubah di Phase 1 sehingga risiko change management lebih rendah. Di sisi lain, akar masalah kesalahan transkripsi manual oleh teller belum teratasi sampai Phase 2; ada risiko urgensi organisasi untuk mendanai Phase 2 (OCR) menurun setelah pain point Phase 1 sudah selesai -- dimitigasi dengan mengunci komitmen scope dan budget Phase 2 bersamaan dengan persetujuan Phase 1, bukan dinegosiasikan ulang setelahnya.
