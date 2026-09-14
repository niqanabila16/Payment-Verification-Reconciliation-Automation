# ADR-0003: Matching Deterministic Berbasis Rule, Bukan Machine Learning

## Status

Accepted

## Context

Sistem harus mencocokkan klaim transaksi sisi customer dengan data bank. Pendekatan yang mungkin berkisar dari exact-match sederhana, fuzzy matching, sampai model machine learning penuh. Kesalahan reconciliation finansial punya konsekuensi uang dan kepercayaan secara langsung, dan stakeholder membutuhkan proses yang bisa dijelaskan dan diaudit. Organisasi juga tidak ingin model AI yang opaque mengambil keputusan pergerakan uang.

## Decision

Kami akan mengimplementasikan matching engine berbasis rule yang bersifat hierarchical dan deterministic (reference match -> reference+amount -> amount+name+bank+time window -> fuzzy name matching), menghasilkan skor numerik eksplisit dengan threshold yang dikalibrasi dari data historis. Machine learning tidak dipakai untuk memutuskan match finansial; ML hanya boleh dipakai kelak (Phase 3) sebatas membantu prioritisasi antrian review manusia, dengan human-in-the-loop tetap wajib untuk keputusan akhir.

## Consequences

Setiap hasil match dapat dijelaskan secara eksplisit ("cocok karena reference X sama dan amount dalam toleransi"); threshold dapat diaudit dan disetel ulang lewat testing standar; percakapan dengan auditor/regulator jadi lebih sederhana. Di sisi lain, rule engine membutuhkan effort eksplisit lebih besar untuk menangani tiap edge case (partial payment, many-to-many, reference hilang) dibanding "membiarkan model belajar sendiri"; batas atas akurasi matching mungkin lebih rendah dari model ML yang di-tuning dengan baik untuk kasus kompleks, sehingga tetap membutuhkan kapasitas review manual yang berkelanjutan.
