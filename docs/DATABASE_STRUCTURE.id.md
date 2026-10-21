# Struktur database (Bahasa Indonesia)

Sumber kebenaran struktur ada di kode: `apps/*/models.py` (tabel, tipe data, relasi) dan `apps/*/migrations/` (riwayat perubahan skema).
Diagram siap pakai: `docs/database.dbml` (paste ke https://dbdiagram.io > Import > DBML). Database SQLite berada di `db.sqlite3` (atau PostgreSQL bila `DB_ENGINE=postgres`).
Untuk melihat tipe data langsung dari database: `python manage.py inspectdb` atau `sqlite3 db.sqlite3 ".schema"`.

## Relasi utama

```
accounts_branch 1 ──< accounts_user (teller)
accounts_user   1 ──< receipts_tellersubmission        (submitted_by: SATU teller per receipt)
accounts_branch 1 ──< receipts_tellersubmission
core_bank       1 ──< receipts_tellersubmission / reconciliation_statementimport / reconciliation_statemententry
receipts_tellersubmission 1 ── 1 reconciliation_reconciliationmatch 1 ── 0..1 reconciliation_statemententry (GFP)
reconciliation_statementimport 1 ──< reconciliation_statemententry
cards_cardupload 1 ──< cards_card >── 0..1 accounts_branch
accounts_branch 1 ──< cards_activationrequest
```
`1 ──<` = one-to-many (satu di kiri, banyak di kanan).

## Tabel, fungsi, dan isi satu baris (instance)

| Tabel | Fungsi | Contoh satu baris |
|---|---|---|
| `accounts_branch` | Master cabang | `KJ / Kajang` |
| `accounts_user` | Semua pengguna dan role (teller, finance, admin, cs) | `teller.kj@demo.test`, role teller, branch KJ |
| `core_bank` | Master bank + pembaca statement | `RHB / RHB Bank / format rhb` |
| `core_paymentmethod`, `core_relationship` | Isi dropdown (receipt menyimpan kode-nya) | `TRANSFER / Bank transfer`, `SELF / Self` |
| `core_transactiondescription` | Opsi filter "Transaction description" (dikelola Admin) | `DuitNow CR Trf CA` untuk ALB |
| `receipts_tellersubmission` | **Satu bukti bayar yang diinput Teller** | holder `KARYATI LESTARI`, RM 1.000,00, ref `05831232`, bank RHB, cabang PJ |
| `reconciliation_statementimport` | Satu file mutasi bank yang diupload Finance (riwayat upload) | `CA Transaction.csv`, bank RHB, 12 baris |
| `reconciliation_statemententry` | Satu baris transaksi di file bank (hanya kolom yang diekstrak) | nama `LESTARI KARYATI`, RM 1.000,00, ref `0000002895`, desc `RPP INWARD INST TRF` |
| `reconciliation_reconciliationmatch` | **Status + penghubung** satu receipt dengan (paling banyak) satu baris bank | status `gfp`, entry #8; atau `pending` tanpa entry |
| `cards_cardupload` | Satu file kartu yang diupload CS | `cards.xlsx`, 30 kartu |
| `cards_card` | Satu nomor kartu fisik | `5123450000000001`, status `delivered`, cabang KJ |
| `cards_activationrequest` | Satu PDF nasabah yang dikirim Teller untuk aktivasi kartu | `AHMAD BIN ALI.pdf`, status `sent` |
| `core_auditlog` | Jejak audit (hanya tambah, tidak bisa diubah/dihapus) | `match.rejected` oleh Finance + payload |
| `core_notification` | Notifikasi (lonceng) | "Receipt #4 was rejected by Finance: ..." |

## Mengapa Teller : Receipt = one-to-many

* **Satu teller dapat menginput banyak receipt** dalam sehari: setiap kali ada nasabah membayar, satu baris baru muncul di `receipts_tellersubmission`. Jadi dari sisi `accounts_user` hubungannya "satu ke banyak".
* **Satu receipt hanya dimiliki satu teller**: sebuah receipt adalah catatan satu kejadian pembayaran yang dimasukkan satu orang pada satu waktu (`submitted_by_id`, satu kolom, bukan daftar). Karena kolom FK ada di sisi "banyak" (receipt), sebuah receipt tidak mungkin menunjuk dua teller. Kalau relasinya many-to-many, kita butuh tabel perantara dan pertanyaan "siapa yang bertanggung jawab atas receipt ini" menjadi kabur. Satu pemilik membuat audit, notifikasi Reject, dan koreksi jelas: Reject dikirim ke teller yang menginput.
* Cabang juga one-to-many dengan alasan sama (`branch_id` mengikuti cabang login teller, bukan dari form). Receipt tetap menyimpan cabangnya walau teller pindah. Bila akun teller dihapus, `submitted_by_id` menjadi kosong (SET NULL) tetapi receipt tetap ada, karena data keuangan tidak boleh ikut hilang.

## Relasi lain dan alasannya

* **Receipt 1 : 1 Match** (`teller_submission_id` unik). Setiap receipt punya tepat satu baris status. Status (pending/gfp/review/not_found/rejected) dipisah dari receipt agar data input teller bersih dan riwayat status bisa berubah tanpa mengubah data asli.
* **Match 0..1 : 1 Baris bank** (`bank_statement_entry_id` unik). Satu baris bank hanya boleh melunasi satu receipt: mencegah satu transaksi bank dipakai dua kali. Nilainya kosong sampai ada GFP.
* **Saran (Review) dan baris yang ditolak** disimpan di kolom terpisah (`suggested_...`, `rejected_...`), sehingga hubungan final (GFP) tidak pernah tercampur dengan tebakan.
* **Import 1 : banyak Entry**. Menghapus file bank (retensi 31 hari) ikut menghapus barisnya (CASCADE). Match tidak ikut terhapus: FK-nya SET NULL dan receipt GFP menyimpan salinan baris bank di `bank_snapshot`.
* **Bank 1 : banyak** receipt, import, dan entry: statement hanya dicocokkan dengan receipt bank yang sama.
* **CardUpload 1 : banyak Card** (urutan file disimpan di `position`). `card_no` unik agar nomor yang sama tidak masuk dua kali. Kartu terhubung ke cabang tujuan ketika Delivered.
* **Branch 1 : banyak ActivationRequest**: Teller hanya melihat permintaan cabangnya sendiri.

## Menghapus data uji

`python manage.py reset_test_data --yes` (hanya saat `DJANGO_DEBUG=True`) menghapus receipt, match, file/baris bank, notifikasi, dan audit trail, tetapi mempertahankan user, cabang, bank, dan dropdown. Tambah `--cards` untuk data kartu/PDF, atau `--receipts-only` untuk menghapus receipt saja (baris bank kembali menjadi Open Item). Setelah itu file bank yang sama bisa diupload lagi tanpa peringatan "pernah diupload".
