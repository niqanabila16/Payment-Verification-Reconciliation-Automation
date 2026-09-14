# tests

- `unit/` -- test logic kritikal (formatter, scoring, normalisasi) tanpa dependency eksternal.
- `integration/` -- test end-to-end dengan database & file lokal (pakai file di `samples/`).
- `fixtures/` -- taruh salinan file dari `samples/` di sini kalau butuh versi yang dimodifikasi khusus untuk test (jangan modifikasi file asli di `samples/`).

Lihat Technical Design Document Bagian 27 (Testing Strategy) dan Solo Delivery Plan Bagian 8 (Definition of Done) untuk standar minimal coverage.
