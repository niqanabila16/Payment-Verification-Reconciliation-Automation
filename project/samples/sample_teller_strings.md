# Contoh Teller String

Format: `<branch_code>/<sender_name>/<entity_name>/<entity_type>/<bank_code>/RM<amount>/<reference_number>/<status_code>`

Lihat Technical Design Document Bagian 11 untuk definisi lengkap tiap field dan cara sanitasi karakter "/" di dalam nama.

## Contoh Valid

KJG/MOHD IKHWAN BIN MOBIN/IKMO NIAGA/COMPANY/RHB/RM708.50/1055889/CHK

KJG/JUNAEDI NURJANNAH/-/INDIVIDUAL/RHB/RM300.00/-/CHK

PJY/SITI AMINAH BINTI HASSAN/-/INDIVIDUAL/MAYBANK/RM1200.00/IBG20260902551/CHK

PJY/RAJESH A-L KUMAR/-/INDIVIDUAL/MAYBANK/RM450.75/DNT20260905332/CHK

## Contoh yang Butuh Sanitasi (nama mengandung "/")

Input OCR mentah   : RAJESH A/L KUMAR
Setelah sanitasi    : RAJESH A-L KUMAR   (lihat Technical Design Document Bagian 11.3)

## Contoh Field Kosong (reference tidak tersedia dari channel QR)

KJG/DINI/-/INDIVIDUAL/RHB/RM2050.00/-/CHK

> Field yang kosong diisi placeholder "-", bukan dikosongkan begitu saja -- lihat Bagian 11.4 Technical Design Document. Transaksi tanpa reference otomatis turun ke Level 3/4 matching (lihat Bagian 15.3).
