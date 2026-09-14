# Payment Verification & Reconciliation Automation
## Panduan Setup Lengkap (Windows + Git Bash)

Package ini berisi seluruh dokumen perencanaan, skema database, sample data, konfigurasi, dan skeleton folder project untuk sistem otomasi verifikasi & reconciliation pembayaran. Panduan ini menuntun Anda dari **kondisi laptop kosong sama sekali** sampai environment development lokal siap dipakai.

**Target pembaca:** developer (termasuk solo developer, lihat `docs/03-Solo-Delivery-Plan.docx`) yang baru pertama kali memegang project ini.

**Asumsi:** Windows 10/11, memakai **Git Bash** sebagai terminal utama (bukan Command Prompt/PowerShell), koneksi internet aktif, dan akun email kerja (untuk Microsoft 365) sudah ada.

---

## Daftar Isi

1. [Struktur Package](#1-struktur-package)
2. [Tahap 0 -- Install Tools Dasar](#tahap-0)
3. [Tahap 1 -- Extract Package & Buka di Git Bash](#tahap-1)
4. [Tahap 2 -- Setup Akun GitHub](#tahap-2)
5. [Tahap 3 -- Setup Environment Variable (.env)](#tahap-3)
6. [Tahap 4 -- Jalankan Database Lokal (Docker)](#tahap-4)
7. [Tahap 5 -- Import Skema Database & Sample Data](#tahap-5)
8. [Tahap 6 -- Verifikasi Database](#tahap-6)
9. [Tahap 7 -- Setup Microsoft Forms + SharePoint List + Power Automate](#tahap-7)
10. [Tahap 8 -- Setup Azure AD App Registration (Graph API)](#tahap-8)
11. [Tahap 9 -- Setup Microsoft Teams Webhook (Notifikasi)](#tahap-9)
12. [Tahap 10 -- Uji Coba Sample Data](#tahap-10)
13. [Urutan Membaca Dokumen](#11-urutan-membaca-dokumen)
14. [Troubleshooting Umum](#12-troubleshooting-umum)
15. [Referensi Silang Dokumen & Keputusan](#13-referensi-silang)

---

## 1. Struktur Package

```
payment-reconciliation-project/
├── README.md                          <- Anda sedang membaca file ini
├── docs/
│   ├── 01-Technical-Design-Document.docx
│   ├── 02-Agile-Delivery-Plan-Tim.docx
│   ├── 03-Solo-Delivery-Plan.docx
│   ├── 04-Solo-Delivery-Plan-Finance-First.docx
│   └── adr/                           <- Architecture Decision Records (format Nygard)
│       ├── README.md
│       └── 0001 s.d. 0008 ....md
├── database/
│   ├── schema.sql                     <- DDL lengkap (jalankan pertama kali)
│   ├── seed_sample_data.sql           <- Data contoh untuk testing
│   └── ERD.md                         <- Penjelasan entity & relasi
├── samples/
│   ├── sample_bank_statement_RHB.xlsx
│   ├── sample_bank_statement_MAYBANK.xlsx
│   ├── sample_teller_strings.md
│   ├── sample_bank_format_config_RHB.json
│   └── sample_ocr_result.json
├── config/
│   ├── docker-compose.yml
│   └── .env.example
└── app-skeleton/                      <- Struktur folder kode (lihat Technical Design Document Bagian 24)
    ├── app/{api,ocr,formatter,bank_ingest,matching,notifications,models,config}/
    ├── workers/
    └── tests/{unit,integration,fixtures}/
```

---

<a name="tahap-0"></a>
## Tahap 0 -- Install Tools Dasar

> Langkah ini dilakukan **sebelum** Git Bash ada di komputer Anda. Buka **PowerShell** (klik kanan Start Menu > "Windows PowerShell" atau "Terminal") untuk langkah instalasi awal ini saja.

### 0.1 Install Git for Windows (termasuk Git Bash)

```powershell
winget install --id Git.Git -e --source winget
```

Setelah selesai, **tutup PowerShell**, lalu buka **Git Bash** dari Start Menu (ketik "Git Bash"). **Mulai dari sini, semua perintah di panduan ini dijalankan dari Git Bash**, kecuali disebutkan lain.

Verifikasi di Git Bash:

```bash
git --version
# contoh output: git version 2.46.0.windows.1
```

### 0.2 Install Python

```bash
winget install --id Python.Python.3.12 -e --source winget
```

Tutup dan buka ulang Git Bash, lalu verifikasi:

```bash
python --version
# atau kalau tidak ketemu:
python3 --version
```

### 0.3 Install Docker Desktop

```bash
winget install --id Docker.DockerDesktop -e --source winget
```

Setelah instalasi selesai:
1. **Buka aplikasi "Docker Desktop"** dari Start Menu (harus dibuka manual sekali, tunggu sampai statusnya "Running" di system tray).
2. Docker Desktop di Windows butuh **WSL2** -- kalau muncul prompt untuk install/enable WSL2, ikuti instruksinya dan restart komputer kalau diminta.

Verifikasi dari Git Bash (Docker Desktop harus sudah running):

```bash
docker --version
docker compose version
```

### 0.4 Install VS Code (opsional, direkomendasikan)

```bash
winget install --id Microsoft.VisualStudioCode -e --source winget
```

> **Kalau `winget` tidak dikenali:** komputer Anda mungkin versi Windows lama. Download installer manual dari: Git -- https://git-scm.com/download/win , Python -- https://www.python.org/downloads/ , Docker Desktop -- https://www.docker.com/products/docker-desktop/ , VS Code -- https://code.visualstudio.com/download

---

<a name="tahap-1"></a>
## Tahap 1 -- Extract Package & Buka di Git Bash

1. Extract file zip package ini via Windows Explorer (klik kanan > "Extract All...") ke lokasi kerja Anda, misalnya `D:\Projects\`.
2. Buka Git Bash, masuk ke folder hasil extract:

```bash
cd /d/Projects/payment-reconciliation-project
# catatan: Git Bash memetakan D:\ menjadi /d/, C:\ menjadi /c/, dst.
pwd
ls -la
```

Anda harus melihat folder `docs/`, `database/`, `samples/`, `config/`, `app-skeleton/` dan file `README.md` ini.

---

<a name="tahap-2"></a>
## Tahap 2 -- Setup Akun GitHub

1. Kalau belum punya akun, daftar di https://github.com
2. Generate SSH key dari Git Bash (untuk push tanpa input password terus-menerus):

```bash
ssh-keygen -t ed25519 -C "email_anda@company.com.my"
# tekan Enter 3x untuk pakai lokasi & pengaturan default (tanpa passphrase kalau mau lebih cepat, tapi passphrase lebih aman)
```

3. Copy public key yang dihasilkan:

```bash
cat ~/.ssh/id_ed25519.pub
```

4. Buka https://github.com/settings/keys > "New SSH key" > paste hasil copy tadi > "Add SSH key".
5. Buat repository baru di GitHub (private, karena ini menyangkut sistem finansial) -- klik "New repository" di https://github.com/new
6. Kembali ke Git Bash, inisialisasi repo lokal dan push pertama kali:

```bash
git init
git add .
git commit -m "Initial commit: project scaffold, docs, schema, samples"
git branch -M main
git remote add origin git@github.com:USERNAME_ANDA/NAMA_REPO.git
git push -u origin main
```

> Ganti `USERNAME_ANDA` dan `NAMA_REPO` sesuai punya Anda. Kalau perintah `git push` minta konfirmasi fingerprint SSH pertama kali, ketik `yes`.

---

<a name="tahap-3"></a>
## Tahap 3 -- Setup Environment Variable (.env)

```bash
cp config/.env.example config/.env
```

Buka `config/.env` di VS Code (`code config/.env`) atau text editor lain, lalu sesuaikan minimal:
- `POSTGRES_PASSWORD` -- ganti dari `changeme_local_only` ke password lain untuk lokal (tidak kritis untuk dev lokal, tapi biasakan tidak pakai default).
- Biarkan variabel `AZURE_*`, `MS_GRAPH_*`, `WHATSAPP_*` tetap ter-comment (`#`) dulu -- itu baru diisi di Tahap 7-9 dan Phase 2.

> **PENTING:** file `.env` (bukan `.env.example`) berisi credential asli nantinya -- **jangan pernah** di-commit ke git. Tambahkan baris `.env` ke file `.gitignore`:

```bash
echo ".env" >> .gitignore
echo "config/.env" >> .gitignore
git add .gitignore
git commit -m "Ignore .env file"
```

---

<a name="tahap-4"></a>
## Tahap 4 -- Jalankan Database Lokal (Docker)

Pastikan **Docker Desktop sedang berjalan** (cek ikon di system tray), lalu dari root folder project:

```bash
cd config
docker compose up -d
```

Output yang diharapkan: 3 container jalan (`reconciliation_postgres`, `reconciliation_redis`, `reconciliation_pgadmin`). Cek statusnya:

```bash
docker compose ps
```

Semua container harus berstatus `running`/`healthy`. Kalau ada yang gagal, lihat log:

```bash
docker compose logs postgres
```

---

<a name="tahap-5"></a>
## Tahap 5 -- Import Skema Database & Sample Data

Kembali ke root folder project:

```bash
cd ..
```

Import skema (membuat semua tabel):

```bash
docker exec -i reconciliation_postgres psql -U reconciliation_user -d reconciliation_db < database/schema.sql
```

Import data contoh:

```bash
docker exec -i reconciliation_postgres psql -U reconciliation_user -d reconciliation_db < database/seed_sample_data.sql
```

Kalau kedua perintah di atas berjalan tanpa pesan `ERROR`, database Anda sudah siap dengan struktur tabel + beberapa baris data contoh.

---

<a name="tahap-6"></a>
## Tahap 6 -- Verifikasi Database

**Opsi A -- lewat command line (psql):**

```bash
docker exec -it reconciliation_postgres psql -U reconciliation_user -d reconciliation_db -c "SELECT transaction_code, status FROM bot_transactions;"
docker exec -it reconciliation_postgres psql -U reconciliation_user -d reconciliation_db -c "SELECT match_level, match_score, match_status FROM reconciliations;"
```

Anda harus melihat 2 baris di `bot_transactions` (MIR-20260908-00123 dan -00124) dan 1 baris hasil match di `reconciliations` dengan `match_score = 99.00`.

**Opsi B -- lewat browser (pgAdmin, lebih mudah dilihat visual):**

1. Buka browser ke http://localhost:8081
2. Login: email `admin@local.test`, password `admin` (sesuai `config/docker-compose.yml`)
3. Klik "Add New Server" -- Tab "General": Name = `Local`. Tab "Connection": Host = `postgres` (nama service di docker-compose, BUKAN `localhost`), Port = `5432`, Username = `reconciliation_user`, Password = sesuai `config/.env`.
4. Setelah connect, navigasi ke Databases > reconciliation_db > Schemas > public > Tables -- klik kanan tabel mana pun > "View/Edit Data" > "All Rows".

---

<a name="tahap-7"></a>
## Tahap 7 -- Setup Microsoft Forms + SharePoint List + Power Automate

> Ini mekanisme capture data teller **interim** sesuai `docs/adr/0008-teller-data-capture-mechanism.md`. Butuh akun Microsoft 365 kerja (bukan akun pribadi) dan izin membuat Form/List/Flow -- kalau ditolak, hubungi admin M365 perusahaan.

### 7.1 Buat Microsoft Form

1. Buka https://forms.office.com, login pakai akun M365 kerja.
2. Klik "New Form", beri judul "Input Transaksi Teller".
3. Tambahkan field, samakan dengan kolom `bot_transactions` di `database/schema.sql`:
   - "Nama Pengirim" -- Text
   - "Bank Tujuan" -- Choice (isi pilihan sesuai `bank_code` di `bank_format_configs`, contoh: RHB, MAYBANK)
   - "Nominal (RM)" -- Text dengan restriction "Number"
   - "Nomor Referensi" -- Text (boleh kosong)
   - "Nama Entitas/Bisnis" -- Text (boleh kosong)
4. Klik ikon titik tiga (`...`) di kanan atas > **Settings**:
   - "Who can fill out this form" -> pilih **"Only people in my organization"** (supaya submitter otomatis terekam identitas AD-nya -- ini pengganti audit trail manual).
   - Aktifkan **"Record name"**.
5. Bagikan link form ke teller (via Teams chat/email internal).

### 7.2 Buat SharePoint List

1. Buka site tim/departemen finance Anda di `https://[namatenant].sharepoint.com/...`
2. Klik "New" > "List" > "Blank list" -- beri nama `TellerTransactions`.
3. Tambah kolom (klik "+ Add column"), samakan tipe data dengan field form di atas:
   - `SenderName` -- Single line of text
   - `BankCode` -- Choice
   - `AmountRM` -- Currency atau Number
   - `ReferenceNumber` -- Single line of text
   - `EntityName` -- Single line of text

### 7.3 Hubungkan Form ke List via Power Automate

1. Buka https://make.powerautomate.com, login dengan akun sama.
2. Klik "Create" > "Automated cloud flow".
3. Beri nama flow, di kolom trigger cari **"Microsoft Forms"** > pilih **"When a new response is submitted"** > pilih Form "Input Transaksi Teller" yang dibuat tadi > "Create".
4. Klik "+ New step" > cari **"Microsoft Forms"** lagi > pilih **"Get response details"** > Form Id pilih form yang sama, Response Id pilih dynamic content dari trigger sebelumnya.
5. Klik "+ New step" > cari **"SharePoint"** > pilih **"Create item"** > isi Site Address (site finance Anda) dan List Name (`TellerTransactions`) > map tiap kolom List ke dynamic content jawaban form yang sesuai (mis. `SenderName` <- jawaban "Nama Pengirim").
6. Klik "Save", lalu submit 1 jawaban contoh di form untuk test -- cek apakah item baru otomatis muncul di SharePoint List.

> Konektor "Microsoft Forms" dan "SharePoint - Create item" adalah **konektor standar (bukan premium)** -- tidak butuh lisensi Power Automate Premium tambahan, sesuai `docs/adr/0008-teller-data-capture-mechanism.md`.

---

<a name="tahap-8"></a>
## Tahap 8 -- Setup Azure AD App Registration (untuk Backend Polling via Graph API)

> Ini yang memungkinkan backend kita membaca isi SharePoint List secara terprogram. Butuh peran admin di Azure AD/Entra ID -- kalau bukan admin, minta tim IT yang mengerjakan langkah ini dan berikan Anda hasil di poin 5.

1. Buka https://portal.azure.com, cari **"App registrations"** > **"New registration"**.
2. Beri nama (contoh: `reconciliation-backend-graph`), pilih **"Accounts in this organizational directory only"** > "Register".
3. Di halaman Overview app yang baru dibuat, catat:
   - **Application (client) ID**
   - **Directory (tenant) ID**
4. Ke menu **"Certificates & secrets"** > "New client secret" > beri deskripsi & masa berlaku > "Add". **Copy nilai Value-nya SEKARANG JUGA** (tidak akan ditampilkan lagi setelah Anda pindah halaman).
5. Ke menu **"API permissions"** > "Add a permission" > "Microsoft Graph" > "Application permissions" > cari dan centang **`Sites.Read.Write.All`** (atau scope yang lebih sempit kalau tersedia untuk site spesifik) > "Add permissions".
6. Klik **"Grant admin consent for [nama organisasi]"** -- **ini butuh role admin**, dan merupakan titik approval yang disebut di `docs/01-Technical-Design-Document.docx` Bagian 20.
7. Masukkan hasil poin 3-4 ke `config/.env`:

```bash
# di config/.env
MS_GRAPH_TENANT_ID=<Directory tenant ID dari langkah 3>
MS_GRAPH_CLIENT_ID=<Application client ID dari langkah 3>
MS_GRAPH_CLIENT_SECRET=<Client secret value dari langkah 4>
```

Untuk `MS_SHAREPOINT_SITE_ID` dan `MS_SHAREPOINT_LIST_ID`, cara tercepat adalah memanggil Graph Explorer (https://developer.microsoft.com/en-us/graph/graph-explorer) login dengan akun yang sama, lalu jalankan query `GET https://graph.microsoft.com/v1.0/sites/{hostname}:/sites/{site-path}` untuk dapat Site ID, dilanjutkan `GET /sites/{site-id}/lists` untuk dapat List ID dari `TellerTransactions`.

---

<a name="tahap-9"></a>
## Tahap 9 -- Setup Microsoft Teams Webhook (Notifikasi)

> **Catatan penting:** cara lama "Connectors > Incoming Webhook" di Teams **sudah resmi dipensiunkan Microsoft per Mei 2026** dan tidak berfungsi lagi. Panduan di bawah pakai cara pengganti resminya, yaitu **Workflows app**. Kalau Anda menemukan tutorial lain di internet yang menyebut "Connectors", abaikan -- sudah tidak berlaku.

1. Buka Microsoft Teams, masuk ke channel finance yang dituju untuk notifikasi.
2. Klik ikon **"..."** di sebelah nama channel > pilih **"Workflows"**.
3. Cari template resmi **"Post to a channel when a webhook request is received"** (berbasis trigger "When a Teams webhook request is received").
4. Ikuti wizard: beri nama workflow, pastikan channel tujuan sudah benar sesuai yang Anda buka di langkah 1 > selesaikan pembuatan.
5. Setelah selesai, akan ditampilkan sebuah **Webhook URL** -- copy URL tersebut.
6. Masukkan ke `config/.env`:

```bash
TEAMS_WEBHOOK_URL=<paste URL di sini>
```

7. Uji coba kirim notifikasi manual dari Git Bash (format Adaptive Card sederhana):

```bash
curl -H "Content-Type: application/json" -d '{
  "type": "message",
  "attachments": [{
    "contentType": "application/vnd.microsoft.card.adaptive",
    "content": {
      "type": "AdaptiveCard",
      "version": "1.4",
      "body": [{"type": "TextBlock", "text": "Test notifikasi dari setup lokal berhasil.", "wrap": true}]
    }
  }]
}' "$TEAMS_WEBHOOK_URL"
```

Kalau berhasil, pesan "Test notifikasi dari setup lokal berhasil." akan muncul di channel Teams yang dipilih.

---

<a name="tahap-10"></a>
## Tahap 10 -- Uji Coba Sample Data

Cek isi file sample yang tersedia untuk development:

```bash
ls -la samples/
```

- `sample_bank_statement_RHB.xlsx` dan `sample_bank_statement_MAYBANK.xlsx` -- 2 format kolom berbeda, untuk menguji parser bank yang data-driven (lihat `database/schema.sql` tabel `bank_format_configs`).
- `sample_teller_strings.md` -- contoh string format teller, termasuk contoh yang butuh sanitasi karakter "/".
- `sample_ocr_result.json` -- contoh struktur data hasil OCR (dipakai mulai Phase 2).

Hitung SHA256 hash sebuah file (dipakai untuk mekanisme idempotency di `bank_file_batches.file_hash`, lihat `docs/adr/0005-bank-ingestion-via-xlsx-folder.md`):

```bash
sha256sum samples/sample_bank_statement_RHB.xlsx
```

Bandingkan dua kali menjalankan perintah yang sama pada file yang sama -- hash-nya harus identik. Ini prinsip yang dipakai file watcher untuk mendeteksi file yang sudah pernah diproses.

---

## 11. Urutan Membaca Dokumen

Kalau Anda baru bergabung ke proyek ini, baca dengan urutan berikut supaya konteksnya nyambung:

| Urutan | Dokumen | Kenapa |
|---|---|---|
| 1 | `docs/01-Technical-Design-Document.docx` | Arsitektur & desain teknis lengkap -- fondasi semua keputusan lain |
| 2 | `docs/adr/README.md` lalu ADR 0001-0008 | Keputusan-keputusan kunci beserta alasannya, versi ringkas dari dokumen desain |
| 3 | `docs/04-Solo-Delivery-Plan-Finance-First.docx` | Rencana delivery YANG DIPAKAI SAAT INI (revisi finance-first, OCR ditunda) |
| 4 | `docs/03-Solo-Delivery-Plan.docx` | Rencana solo versi awal (OCR-dulu) -- untuk konteks, sudah di-supersede sebagian oleh ADR-0007 |
| 5 | `docs/02-Agile-Delivery-Plan-Tim.docx` | Rencana kalau nanti proyek discale ke tim, bukan solo lagi |
| 6 | `database/ERD.md` + `database/schema.sql` | Detail struktur data setelah paham desain besarnya |

---

## 12. Troubleshooting Umum

| Masalah | Solusi |
|---|---|
| `winget` tidak dikenali di Git Bash | Pastikan dijalankan dari PowerShell untuk instalasi awal (Tahap 0), atau update Windows/App Installer dari Microsoft Store |
| `docker: command not found` | Docker Desktop belum dibuka -- buka aplikasinya dari Start Menu, tunggu status "Running" di tray, baru coba lagi |
| `port is already allocated` saat `docker compose up` | Ada aplikasi lain pakai port 5432/6379/8081 -- matikan aplikasi itu, atau ubah port mapping di `config/docker-compose.yml` (contoh: `"5433:5432"`) |
| `psql: FATAL: password authentication failed` | Password di command tidak cocok dengan `config/.env` -- cek ulang `POSTGRES_PASSWORD` |
| Git Bash tidak bisa `cd` ke drive lain (D:, E:) | Gunakan format `/d/nama_folder`, bukan `D:\nama_folder` |
| `git push` gagal, `Permission denied (publickey)` | SSH key belum ditambahkan ke GitHub (ulangi Tahap 2 poin 3-4), atau salah paste public key (pastikan copy seluruh baris termasuk `ssh-ed25519` di awal) |
| File `.xlsx` sample tidak bisa dibuka Excel dengan rapi | Buka dengan Excel/LibreOffice Calc biasa (klik 2x), bukan text editor -- ini file binary format Excel asli |
| Line ending berantakan (`^M` di akhir baris) saat edit file di Git Bash | Set `git config --global core.autocrlf true` sebelum clone/commit berikutnya |

---

## 13. Referensi Silang

Kalau Anda menemukan sesuatu di kode/database dan ingin tahu **kenapa** desainnya begitu, ini peta cepatnya:

| Yang Anda Lihat | Cari Alasannya Di |
|---|---|
| Kolom `entry_source` di tabel `bot_transactions` | `docs/adr/0008-teller-data-capture-mechanism.md` |
| Tidak ada tabel terkait Virtual Account | `docs/adr/0004-no-virtual-account.md` |
| Semua nominal disimpan sebagai INTEGER (minor units), bukan FLOAT | `docs/01-Technical-Design-Document.docx` Bagian 15.1 |
| `match_score` dan `match_level` di `reconciliations` | `docs/01-Technical-Design-Document.docx` Bagian 15-16, `docs/adr/0003-deterministic-matching-not-ml.md` |
| Folder `app/ocr/` masih kosong | `docs/adr/0007-finance-first-sequencing.md` -- OCR baru Phase 2 |
| Kenapa notifikasi ke Teams, bukan WhatsApp group | `docs/adr/0006-teams-not-whatsapp-group-for-internal-notification.md` |
| Kenapa ada 2 bank sample dengan format kolom beda | Menguji `bank_format_configs` benar-benar data-driven, lihat `docs/01-Technical-Design-Document.docx` Bagian 13 |
| Kenapa cuma 2 role di `finance_users` (bukan 4) | `docs/03-Solo-Delivery-Plan.docx` Bagian 4 -- MVP-Solo scope dipangkas |

---

Selamat membangun. Kalau ada langkah di panduan ini yang sudah tidak sesuai (menu Microsoft berubah lagi, versi tool baru, dst.), update file ini dan catat perubahannya sebagai ADR baru kalau itu mengubah keputusan arsitektur, bukan cuma langkah teknis (lihat `docs/adr/README.md` bagian "Cara Menambah ADR Baru").
