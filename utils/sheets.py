"""
PART 9 — Simpan & baca status respons pelanggan lewat Google Sheets.

Kenapa Google Sheets (bukan file CSV lokal)? Streamlit Community Cloud tidak
punya penyimpanan permanen — tiap kali app di-restart/redeploy, semua file
yang ditulis lokal akan hilang. Google Sheets jadi "database" sederhana yang
tetap ada dan bisa dilihat langsung tanpa tools tambahan.

Setup yang dibutuhkan (lihat README.md untuk langkah lengkap):
1. Buat Google Sheet baru dengan baris header persis seperti SHEET_HEADERS
   di bawah ini.
2. Buat Service Account di Google Cloud Console, aktifkan Google Sheets API,
   download JSON credential-nya.
3. Share Google Sheet itu ke email service account (akses Editor).
4. Simpan credential JSON + ID sheet ke Streamlit Secrets:

    [gcp_service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "..."
    client_email = "..."
    client_id = "..."
    ... (isi lengkap dari file JSON)

    [app]
    sheet_id = "ID_GOOGLE_SHEET_KAMU"
    base_url = "https://nama-app-kamu.streamlit.app"
"""

import datetime as dt

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

SHEET_HEADERS = [
    "token",
    "event_id",
    "sent_at",
    "gi",
    "feeder",
    "customer_name",
    "email",
    "target_curtailment_kw",
    "status",
    "responded_at",
    "responded_kw",
    "iteration",
    "campaign_id",
]


def _get_client():
    creds_info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_worksheet():
    client = _get_client()
    sheet_id = st.secrets["app"]["sheet_id"]
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.sheet1

    # Pastikan header sudah benar (cuma diisi sekali kalau sheet masih kosong)
    first_row = worksheet.row_values(1)
    if first_row != SHEET_HEADERS:
        worksheet.update("A1", [SHEET_HEADERS])

    return worksheet


def append_request(row: dict) -> None:
    """Tambah 1 baris permintaan baru (status awal selalu PENDING)."""
    worksheet = _get_worksheet()
    values = [row.get(col, "") for col in SHEET_HEADERS]
    worksheet.append_row(values, value_input_option="USER_ENTERED")


def get_request_by_token(token: str) -> dict | None:
    """Cari 1 baris permintaan berdasarkan token. None kalau tidak ketemu."""
    worksheet = _get_worksheet()
    records = worksheet.get_all_records()
    for record in records:
        if str(record.get("token", "")) == token:
            return record
    return None


def update_status(token: str, new_status: str, responded_kw: float | None = None) -> bool:
    """
    Update status (mis. ACCEPTED 100%/ACCEPTED 80%/REJECTED) untuk 1 token.
    responded_kw (opsional): besaran kW aktual yang disetujui pelanggan
    (mis. 80% dari target_curtailment_kw kalau pelanggan pilih "Accept 80%").
    True kalau berhasil ketemu.
    """
    worksheet = _get_worksheet()
    cell = worksheet.find(token, in_column=1)
    if cell is None:
        return False

    responded_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status_col = SHEET_HEADERS.index("status") + 1
    responded_col = SHEET_HEADERS.index("responded_at") + 1

    worksheet.update_cell(cell.row, status_col, new_status)
    worksheet.update_cell(cell.row, responded_col, responded_at)

    if responded_kw is not None and "responded_kw" in SHEET_HEADERS:
        responded_kw_col = SHEET_HEADERS.index("responded_kw") + 1
        worksheet.update_cell(cell.row, responded_kw_col, round(responded_kw, 2))

    return True


@st.cache_data(ttl=15, show_spinner=False)
def get_all_requests(gi_name: str | None = None) -> list[dict]:
    """
    Ambil semua baris permintaan (dipakai untuk rekap respons pelanggan di dashboard).
    Kalau gi_name diisi, hanya baris untuk gardu induk tersebut yang dikembalikan.
    Di-cache 15 detik supaya tidak terlalu sering panggil Google Sheets API.
    """
    worksheet = _get_worksheet()
    records = worksheet.get_all_records()
    if gi_name:
        records = [r for r in records if str(r.get("gi", "")) == gi_name]
    return records


# ============================================================
# Sheet ke-2: Reward_Penalty (spreadsheet yang sama, tab berbeda)
# ============================================================
SETTLEMENT_SHEET_NAME = "Reward_Penalty"

SETTLEMENT_HEADERS = [
    "key",
    "calculated_at",
    "type",
    "gi",
    "feeder",
    "customer_name",
    "email",
    "basis_token",
    "iteration",
    "power_kw",
    "duration_hours",
    "duration_text",
    "energy_kwh",
    "rate_idr_per_kwh",
    "factor",
    "amount_idr",
    "formula",
]


def _get_settlement_worksheet():
    """Ambil tab Reward_Penalty; dibuat otomatis (+ header) kalau belum ada."""
    client = _get_client()
    spreadsheet = client.open_by_key(st.secrets["app"]["sheet_id"])
    try:
        worksheet = spreadsheet.worksheet(SETTLEMENT_SHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=SETTLEMENT_SHEET_NAME, rows=1000, cols=len(SETTLEMENT_HEADERS)
        )

    if worksheet.row_values(1) != SETTLEMENT_HEADERS:
        worksheet.update(range_name="A1", values=[SETTLEMENT_HEADERS])
    return worksheet


def upsert_settlements(rows: list[dict]) -> dict:
    """
    Simpan hasil perhitungan reward/penalty. Kunci baris = kolom "key"
    (jenis + token baris dasar), jadi menyimpan ulang dengan durasi/tarif baru
    MENIMPA baris yang sama, bukan menambah duplikat.
    Return {"added": n, "updated": n}.
    """
    worksheet = _get_settlement_worksheet()
    existing_keys = worksheet.col_values(1)          # termasuk header di indeks 0
    row_by_key = {k: i + 1 for i, k in enumerate(existing_keys) if i > 0 and k}

    to_append, updated = [], 0
    for row in rows:
        values = [row.get(col, "") for col in SETTLEMENT_HEADERS]
        sheet_row = row_by_key.get(row["key"])
        if sheet_row:
            worksheet.update(range_name=f"A{sheet_row}", values=[values], raw=True)
            updated += 1
        else:
            to_append.append(values)

    if to_append:
        worksheet.append_rows(to_append, value_input_option="RAW")

    get_all_settlements.clear()
    return {"added": len(to_append), "updated": updated}


@st.cache_data(ttl=15, show_spinner=False)
def get_all_settlements(gi_name: str | None = None) -> list[dict]:
    """Baca semua baris tab Reward_Penalty (opsional difilter per GI)."""
    records = _get_settlement_worksheet().get_all_records()
    if gi_name:
        records = [r for r in records if str(r.get("gi", "")) == gi_name]
    return records
