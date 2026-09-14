# ADR-0004: Reconciliation Multi-Field Tanpa Virtual Account

## Status

Accepted

## Context

Sebagian platform pembayaran mengandalkan Virtual Account (VA) per customer yang diterbitkan bank untuk membuat reconciliation trivial (1 VA = 1 customer = match tanpa ambiguitas). Operasional perusahaan di Malaysia tidak memiliki infrastruktur VA, dan mengadakannya adalah proyek integrasi bank/partner tersendiri yang signifikan dan di luar scope saat ini.

## Decision

Reconciliation akan dilakukan menggunakan kombinasi transaction reference (bila tersedia), amount, nama pengirim, bank, dan kedekatan waktu, melalui matching engine hierarchical (ADR-0003) -- bukan bergantung pada identifikasi tanpa ambiguitas ala VA.

## Consequences

Sistem dapat dibangun dan dirilis tanpa perlu negosiasi kerja sama/integrasi bank baru, sehingga MVP tetap dapat dicapai dengan sumber daya yang ada. Di sisi lain, matching harus menangani ambiguitas yang inheren (amount sama dari beberapa customer berbeda, reference hilang, variasi penulisan nama) yang tidak akan muncul pada desain berbasis VA; harus diantisipasi ada tingkat manual review yang tidak nol, yang tidak akan dialami desain berbasis VA. Opsi VA dapat dipertimbangkan kembali di Phase 3 jika ada partner bank yang menawarkannya dan volume transaksi membenarkan investasinya.
