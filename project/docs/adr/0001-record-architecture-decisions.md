# ADR-0001: Mencatat Keputusan Arsitektur dalam Bentuk ADR

## Status

Accepted

## Context

Sepanjang proses perencanaan sistem verifikasi & reconciliation pembayaran ini, sejumlah keputusan arsitektur signifikan sudah diambil (pemilihan database sebagai source of truth, pendekatan matching deterministic, urutan pengerjaan finance-first, mekanisme input data teller, dan lain-lain). Keputusan-keputusan ini tersebar di berbagai dokumen perencanaan dan percakapan, tanpa format baku yang membuatnya mudah ditemukan, dirujuk ulang, atau dipahami alasannya (bukan cuma hasil akhirnya) oleh siapa pun yang bergabung ke proyek ini di kemudian hari -- termasuk kemungkinan developer solo pengganti bila terjadi handover.

## Decision

Kami akan mencatat keputusan arsitektur menggunakan format Architecture Decision Record (ADR) sebagaimana didefinisikan oleh Michael Nygard, disimpan sebagai file markdown bernomor urut yang bersifat append-only di dalam folder `docs/adr/` pada repository proyek. Setiap ADR berisi empat bagian: Status, Context, Decision, dan Consequences.

## Consequences

Siapa pun yang bergabung ke proyek ini bisa melihat alasan di balik keputusan yang sudah diambil, dan tidak perlu membuka ulang diskusi yang sudah selesai tanpa adanya informasi baru. Keputusan yang di kemudian hari perlu diubah atau dibatalkan akan dicatat sebagai ADR baru yang men-supersede ADR lama -- bukan dengan mengedit atau menghapus riwayat yang sudah ada. Konsekuensi praktisnya, setiap keputusan besar berikutnya di proyek ini sebaiknya juga dituliskan sebagai ADR baru, bukan hanya didiskusikan lalu dilupakan formatnya.
