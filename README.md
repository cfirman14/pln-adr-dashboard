# Demand Response Dashboard — OpenADR PoC

Dashboard simulasi Demand Response (threshold check → target curtailment →
alokasi pelanggan → event OpenADR 3.1) untuk Project 1 — Smart Building
Energy Digital Twin.

Ini adalah hasil konversi dari notebook Google Colab ke aplikasi web
Streamlit, supaya bisa diakses lewat browser tanpa perlu membuka Colab.

## Struktur project

```
pln-adr-dashboard/
├── app.py                        # halaman utama Streamlit (dashboard PLN)
├── config.py                      # PART 0 — konfigurasi (edit di sini kalau pindah GI)
├── pages/
│   └── 1_Respon_Pelanggan.py      # halaman respons pelanggan (dibuka lewat link email)
├── utils/
│   ├── data_loader.py             # PART 1 — baca CSV feeder & pelanggan
│   ├── threshold.py               # PART 3-4 — threshold check & target curtailment
│   ├── curtailment.py             # PART 5 — alokasi ke pelanggan
│   ├── openadr_events.py          # PART 7 — bungkus jadi event OpenADR 3.1
│   ├── tokens.py                  # PART 8 — token unik link respons
│   ├── sheets.py                  # PART 9 — simpan/baca respons di Google Sheets
│   └── notify.py                  # PART 10 — kirim email notifikasi
├── data/                          # data contoh (demo), format sama seperti CSV asli
├── .streamlit/
│   └── secrets.toml.example       # TEMPLATE kredensial (copy jadi secrets.toml, isi sendiri)
├── requirements.txt
└── README.md
```

## Jalankan di komputer sendiri

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Browser akan otomatis terbuka ke `http://localhost:8501`.

## Push ke GitHub

```bash
git init
git add .
git commit -m "Initial commit: DR dashboard OpenADR PoC"
git branch -M main
git remote add origin https://github.com/<username>/<nama-repo>.git
git push -u origin main
```

## Deploy ke Streamlit Community Cloud (gratis)

1. Buka https://share.streamlit.io dan login pakai akun GitHub.
2. Klik **New app**, pilih repo ini, branch `main`, dan file utama `app.py`.
3. Klik **Deploy**. Setelah build selesai, dashboard bisa diakses lewat URL publik.

## Soal sumber data (penting)

Di Colab, data dibaca langsung dari Google Drive (`drive.mount`). Streamlit
Cloud **tidak bisa** mount Google Drive seperti itu, jadi ada dua opsi:

- **Demo/testing** — pakai data contoh di folder `data/` (aktif secara
  default lewat toggle "Pakai data contoh" di sidebar).
- **Data real** — pengguna upload CSV feeder & pelanggan langsung lewat
  file uploader di sidebar setiap kali membuka dashboard, ATAU (untuk
  otomatis) hubungkan ke Google Sheets/Drive API pakai service account,
  simpan kredensialnya di **Streamlit Secrets** (Settings → Secrets di
  dashboard Streamlit Cloud), lalu baca lewat `st.secrets`. Jangan pernah
  commit file kredensial ke GitHub.

## Fitur Notifikasi Email + Respons Pelanggan

Dashboard bisa mengirim email ke pelanggan yang kena target curtailment,
berisi link ke halaman respons (Terima/Tolak). Fitur ini butuh 3 hal yang
**harus kamu siapkan sendiri** (kredensial pribadi/institusi, tidak bisa
dibuatkan otomatis):

### 1. Gmail App Password (untuk kirim email)

1. Aktifkan **2-Step Verification** di akun Gmail yang mau dipakai kirim
   (Google Account → Security → 2-Step Verification).
2. Buka https://myaccount.google.com/apppasswords
3. Generate App Password baru (pilih nama app bebas, misal "PLN ADR Dashboard").
4. Simpan 16 karakter yang muncul — ini `app_password` di secrets, **beda**
   dengan password login Gmail biasa.

### 2. Google Sheet + Service Account (untuk simpan respons)

1. Buat 1 Google Sheet baru (kosong saja, header akan dibuat otomatis oleh
   app pertama kali dipakai).
2. Copy **ID sheet**-nya dari URL:
   `https://docs.google.com/spreadsheets/d/`**`ID_SHEET_DI_SINI`**`/edit`
3. Buka https://console.cloud.google.com/ → buat project baru (atau pakai
   yang sudah ada) → aktifkan **Google Sheets API** dan **Google Drive API**
   (menu "APIs & Services" → "Enable APIs and Services").
4. Buat **Service Account**: "APIs & Services" → "Credentials" → "Create
   Credentials" → "Service Account". Beri nama bebas, lanjut sampai selesai.
5. Buka service account yang baru dibuat → tab **Keys** → "Add Key" →
   "Create new key" → pilih **JSON** → file JSON otomatis ke-download.
6. Buka Google Sheet dari langkah 1 → klik **Share** → paste email service
   account (format `...@....iam.gserviceaccount.com`, ada di file JSON
   kolom `client_email`) → beri akses **Editor**.

### 3. Isi Streamlit Secrets

1. Copy `.streamlit/secrets.toml.example` jadi `.streamlit/secrets.toml`
   (file ini sudah otomatis diabaikan Git, aman tidak ke-upload).
2. Isi bagian `[gmail]` dan `[app]` sesuai langkah 1 & 2 di atas.
3. Isi bagian `[gcp_service_account]` dengan isi file JSON dari langkah 2
   (format TOML, lihat contoh di file `.example`-nya).
4. Untuk deploy di Streamlit Community Cloud: buka app kamu di
   share.streamlit.io → **Settings** → **Secrets** → paste seluruh isi
   `secrets.toml` yang sudah lengkap ke sana.

### 4. Data pelanggan butuh kolom EMAIL

`data/DataCustomer.csv` sekarang punya kolom `EMAIL` tambahan. Data contoh
saat ini masih pakai email **placeholder** (`...@example.com`) — ganti
minimal 1 baris dengan email asli kamu sendiri untuk testing supaya bisa
lihat hasilnya masuk ke inbox.

## Catatan status project

Event OpenADR yang dihasilkan (Section 5 dashboard) adalah **simulasi
struktural** — formatnya valid sesuai OpenADR 3.1 Definitions, tapi belum
benar-benar di-POST ke VTN server sungguhan.

Fitur notifikasi (Section 4) juga simulasi PoC: token akses berbasis link
(tanpa login pelanggan), cocok untuk demo/skripsi tapi belum ada mekanisme
kedaluwarsa link atau proteksi anti-spam untuk penggunaan produksi sungguhan.
