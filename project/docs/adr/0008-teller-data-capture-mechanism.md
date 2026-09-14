# ADR-0008: Microsoft Forms + SharePoint (Interim) Bermigrasi ke Custom Web Form (Target), Bukan Google Forms atau Form Builder Pihak Ketiga

## Status

Accepted

## Context

Dengan OCR ditunda (ADR-0007), sistem tetap membutuhkan cara yang andal untuk menangkap data transaksi terstruktur di sisi customer/teller sebagai bahan matching. Bot WhatsApp yang sudah berjalan saat ini hanya bisa membalas customer dan tidak dapat diandalkan sebagai sumber ekspor data terstruktur. Beberapa tool pembuat form dievaluasi (Google Forms, Microsoft Forms, SharePoint List, Power Apps, form custom buatan sendiri, dan form builder pihak ketiga seperti Typeform/JotForm). Perusahaan beroperasi di lingkungan Microsoft 365 dengan persyaratan keamanan yang ketat, yang menyingkirkan tool apa pun yang memindahkan data transaksi finansial ke luar tenant yang diatur.

## Decision

Dalam jangka pendek, input data teller menggunakan Microsoft Forms dengan respons dialirkan ke SharePoint List/Excel table (lewat konektor Power Automate standar, non-premium), yang di-polling backend kami via Microsoft Graph API -- meniru pola ingestion yang sudah direncanakan untuk file XLSX bank. Begitu backend inti sudah live (sekitar Milestone 3-4), ini akan digantikan oleh custom web form yang dilayani langsung oleh backend kami sendiri, memberikan penangkapan data real-time dan kontrol penuh atas validasi/RBAC/audit logging. Google Forms dan form builder pihak ketiga (Typeform, JotForm, Airtable Forms, dst.) ditolak secara eksplisit karena memindahkan data finansial ke luar tenant Microsoft yang diaudit. Power Apps tidak dipakai untuk kebutuhan ini karena biaya lisensi per user (USD 10-20/user/bulan per perubahan harga Januari 2026) tidak sebanding dengan kesederhanaan form yang dibutuhkan.

## Consequences

Mekanisme penangkapan jangka pendek dapat dirilis cepat tanpa biaya lisensi tambahan dan tetap berada dalam postur keamanan Microsoft yang sudah disetujui; menggunakan ulang pola integrasi Graph API yang memang sudah direncanakan di tempat lain, sehingga tidak menambah jenis integrasi baru; kondisi target jangka panjang memberi kontrol real-time penuh tanpa biaya per-user berkelanjutan. Di sisi lain, solusi interim punya latensi polling (bukan real-time) dan tetap bergantung pada persetujuan app registration Graph API yang sama seperti yang dicatat di desain teknis utama; sistem untuk sementara bergantung pada dua mekanisme penangkapan data berbeda selama masa migrasi, sehingga keduanya harus diuji dan mekanisme pertama perlu di-deprecate secara bersih setelah migrasi selesai.
