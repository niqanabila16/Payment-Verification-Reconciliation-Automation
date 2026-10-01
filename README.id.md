# Ringkasan Setup (Bahasa Indonesia)

Dokumen lengkap ada di [README.md](README.md) (bahasa Inggris, sesuai BR-9). Ini versi singkat sampai aplikasi berjalan.

## Syarat
- Windows 10/11, **Python 3.12** (centang *Add python.exe to PATH* saat install).
- Cek di PowerShell: `py -3.12 --version`

## Setup cepat (PowerShell, dari folder project)
```powershell
cd C:\path\ke\payment-reconciliation
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup.ps1      # buat venv, install paket, buat .env + secret key, migrate, isi data demo
.\scripts\run.ps1        # jalankan di http://127.0.0.1:8000
```

Login demo (password `Demo-Pass-2026!`): `admin@demo.test`, `finance@demo.test`, `teller.kj@demo.test`, `teller.pj@demo.test`.

## Coba alurnya
1. Login sebagai Finance > **Bank statements** > pilih *Bank Mandiri* > upload `sample_data\mandiri_statement_2026-09-30.csv`.
2. Hasil: 5 Match (GFP), 1 Typo, 1 Manual review, 1 Not found.
3. Buka **Reconciliation** > klik item typo: field sama berwarna **hijau**, field beda berwarna **merah**, karakter yang berbeda digarisbawahi.
4. Approve, atau kirim feedback ke Teller. Login sebagai Teller untuk melihat notifikasi dan memperbaiki receipt.

## Langkah manual (jika script diblokir)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"   # tempel hasilnya ke DJANGO_SECRET_KEY di .env
python manage.py migrate
python manage.py seed_demo            # atau: python manage.py createsuperuser
python manage.py runserver
```

## Tes otomatis
```powershell
python manage.py test        # 81 tes
```

## Catatan penting
- Produksi di komputer pusat: `.\scripts\serve.ps1` (Waitress) dan jadwalkan `scripts\backup.ps1`. Detail di README bagian 7.
- Notifikasi desktop dan form offline (service worker) butuh **HTTPS** atau `localhost`.
- Master data cabang dan bank belum punya layar admin; tambahkan lewat perintah di README bagian 8.
