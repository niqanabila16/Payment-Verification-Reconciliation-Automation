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

Login demo (password `mandiri123`): `admin@demo.test`, `finance@demo.test`, `teller.kj@demo.test`, `teller.sa@demo.test`, `cs@demo.test` (CS A: activation), `cs.b@demo.test` (CS B: activation + block).

## Coba alurnya (data demo hanya berisi user, tanpa receipt)
1. Login sebagai `teller.kj@demo.test` > **New receipt**. Input (Bank RHB, Bank transfer; sen boleh pakai koma, mis. `1200,00`; field lain sama seperti sebelumnya, hanya ditambah tanggal dan jam transaksi di struk): `150.00 / 2235277A1` (Verified), `1200.00 / 611380310m` (Verified), `320.00 / 99120054` (Review: typo), `205.00 / 55302211` (Review: amount differs), `400.00 / 90019001` (Not found).
2. Login sebagai `finance@demo.test`. Di halaman **Reconciliation** pilih bank **RHB** di sebelah kolom file, pilih `sample_data\rhb_statement_2026-09-30.csv`, lalu **Upload and match**.
3. Buka tab *Review* > klik item: field sama **hijau**, field beda **merah**, karakter berbeda digarisbawahi. Approve atau kirim koreksi ke Teller.
4. Login sebagai Teller: bell menampilkan notifikasi. Teller hanya melihat status *Pending* atau *Verified*.
5. Upload file yang sama lagi: muncul pertanyaan "Upload again?". Transaksi yang sudah tersimpan tidak dihitung dua kali.

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
python manage.py test        # 160 tes
```

## Catatan penting
- Produksi di komputer pusat: `.\scripts\serve.ps1` (Waitress) dan jadwalkan `scripts\backup.ps1`. Detail di README bagian 7.
- Notifikasi desktop dan form offline (service worker) butuh **HTTPS** atau `localhost`.
- Cabang, bank, payment method, dan relationship dikelola Admin di menu **Master data** (tidak ada yang terkunci; kode bisa diubah; ada tombol Delete bila belum dipakai).
- Empat kategori bank: RHB, ALB, PBB, MBB. Pilih bank di sebelah upload. Keempat format (RHB, ALB, PBB, MBB) sudah dicek terhadap satu file asli masing-masing. Cek cara file dibaca: `python manage.py inspect_statement <file> <rhb|alb|pbb|mbb>`.

## Forgot Password lewat e-mail (setup)
User klik **Forgot password**, isi e-mail kantor, lalu menerima link unik sekali pakai (berlaku 60 menit) untuk membuat password baru dua kali. Tanpa Admin.
1. Minta data SMTP ke IT (host, port, user, password, TLS).
2. Isi `.env`: `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_PORT=587`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS=True`, `DEFAULT_FROM_EMAIL`, `SITE_BASE_URL=http://<nama-atau-ip-pc-pusat>:8000`, `PASSWORD_RESET_MINUTES=60`.
3. Restart server, lalu tes dengan e-mail sendiri.
4. Untuk development tanpa SMTP, biarkan backend `console`: link tampil di jendela server.
5. Jika server e-mail mati, user tetap melihat pesan konfirmasi biasa dan error masuk log; Admin masih bisa memakai **Users > Reset password**.
- Tidak ada penguncian akses apa pun (sesuai permintaan), jadi simpan aplikasi di jaringan kantor/VPN.
