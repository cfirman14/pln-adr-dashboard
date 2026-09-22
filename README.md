# Demand Response Dashboard — OpenADR PoC

Dashboard simulasi Demand Response (threshold check → target curtailment →
alokasi pelanggan → event OpenADR 3.1) untuk Project 1 — Smart Building
Energy Digital Twin.

Ini adalah hasil konversi dari notebook Google Colab ke aplikasi web
Streamlit, supaya bisa diakses lewat browser tanpa perlu membuka Colab.

## Struktur project

```
pln-adr-dashboard/
├── app.py                  # halaman utama Streamlit
├── config.py                # PART 0 — konfigurasi lokasi (edit di sini kalau pindah GI)
├── utils/
│   ├── data_loader.py       # PART 1 — baca CSV feeder & pelanggan
│   ├── threshold.py         # PART 3-4 — threshold check & target curtailment
│   ├── curtailment.py       # PART 5 — alokasi ke pelanggan
│   └── openadr_events.py    # PART 7 — bungkus jadi event OpenADR 3.1
├── data/                    # data contoh (demo), format sama seperti CSV asli
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

## Catatan status project

Event OpenADR yang dihasilkan (Section 4 dashboard) adalah **simulasi
struktural** — formatnya valid sesuai OpenADR 3.1 Definitions, tapi belum
benar-benar di-POST ke VTN server sungguhan.
