# app/formatter

Teller string generator -- fungsi deterministic yang mengubah structured data jadi string format `KJG/NAMA/.../CHK` dan sebaliknya (parser). Lihat Technical Design Document Bagian 11 dan `samples/sample_teller_strings.md` untuk contoh input/output.

Logic di sini **wajib** ada unit test (lihat `tests/unit/`) karena tidak ada peer review kalau dikerjakan solo (lihat Solo Delivery Plan, Bagian 8 -- Definition of Done).
