# ADR-0005: Ingestion Data Bank via Download XLSX Manual + Folder Automation, Bukan Direct Bank API

## Status

Accepted

## Context

Integrasi API langsung (host-to-host) dengan tiap bank tidak tersedia untuk MVP -- belum ada kerja sama teknis dengan bank, dan mengadakannya adalah proyek besar tersendiri per bank. Saat ini finance sudah terbiasa men-download data transaksi secara manual dari internet banking dalam format XLSX.

## Decision

Untuk MVP, sistem tidak akan mencoba integrasi API langsung ke bank. Sebagai gantinya, finance tetap men-download XLSX secara manual dan menaruhnya di folder aman yang dipantau; sebuah pipeline otomatis (file watcher dengan readiness check, idempotency berbasis hash, column mapping per bank, normalisasi) mengambil alih sejak file itu masuk folder.

## Consequences

MVP dapat dikirim tanpa perlu negosiasi kerja sama/akses API bank yang berada di luar kendali dan timeline tim delivery; satu langkah manual yang tersisa (download + taruh file) jauh lebih kecil dibanding pekerjaan reconciliation manual yang dihilangkan. Di sisi lain, tetap ada langkah manual residual beserta latensinya (finance harus ingat men-download secara berkala); sistem harus menangani secara defensif kondisi file dunia nyata yang berantakan (download belum selesai, upload duplikat, format berubah) karena tidak mengontrol sumber data secara langsung. Integrasi API langsung dapat dipertimbangkan ulang di Phase 3 bila volume/ekonomi membenarkannya.
