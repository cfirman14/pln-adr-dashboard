"""
Konteks bersama untuk semua halaman PLN (dashboard utama, Notifikasi & Respons,
Reward & Penalty). Tiap halaman Streamlit adalah skrip terpisah, jadi sidebar
(sumber data + pilihan GI), pembacaan data feeder, threshold, dan alokasi
curtailment dikumpulkan di sini supaya hasilnya IDENTIK di semua halaman.

Widget sidebar memakai key tetap, jadi pilihan (mis. GI) terbawa saat pindah halaman.
"""

import datetime as dt
from dataclasses import dataclass

import pandas as pd
import streamlit as st

import config
from utils.curtailment import allocate_customer_curtailment
from utils.data_loader import get_latest_snapshot, load_customer_data, load_feeder_data
from utils.execution import resolve_expired_requests
from utils.period import annotate_events, date_bounds, filter_by_period, today_local
from utils.sheets import get_all_requests
from utils.threshold import run_dr_trigger_check, run_threshold_check


@dataclass
class DashboardContext:
    selected_gi: str
    feeder_data: dict
    summary: dict
    dr_results: dict
    target_curtailment_total: float
    df_alloc: pd.DataFrame
    alloc_error: str | None


def load_dashboard_context() -> DashboardContext:
    """Gambar sidebar, baca data, hitung threshold & alokasi. Berhenti (st.stop) kalau data bermasalah."""
    # ---------- Sidebar: sumber data ----------
    st.sidebar.header("Data Source")
    use_demo_data = st.sidebar.toggle("Use Demo Data", value=True, key="use_demo_data")

    uploaded_feeder_file = None
    uploaded_customer_file = None

    if not use_demo_data:
        st.sidebar.caption("Upload CSV feeder (1 file")
        uploaded_feeder_file = st.sidebar.file_uploader("CSV — Feeder Data", type="csv", key="upload_feeder")
        uploaded_customer_file = st.sidebar.file_uploader("CSV — Customer Data", type="csv", key="upload_customer")

    # ---------- Load data feeder (mentah, semua GI) ----------
    try:
        df_feeder_raw = load_feeder_data(uploaded_feeder_file)
    except Exception as e:
        st.error(f"Fail to read data feeder: {e}")
        st.stop()

    # ---------- Choose Substation ----------
    gi_list = sorted(df_feeder_raw["GI"].dropna().astype(str).str.strip().unique())
    if st.session_state.get("selected_gi") not in gi_list:
        st.session_state.pop("selected_gi", None)      # pilihan lama tidak ada di data ini
    selected_gi = st.sidebar.selectbox("Choose Substation", gi_list, key="selected_gi")

    st.sidebar.divider()
    st.sidebar.caption(f"Capacity/feeder: {config.MAX_PER_FEEDER_KW} kW")
    st.sidebar.caption(f"Trigger tier: {config.TRIGGER_RATIO * 100:.0f}%")

    # ---------- Snapshot terakhir GI terpilih ----------
    feeder_data = get_latest_snapshot(df_feeder_raw, selected_gi)
    if not feeder_data:
        st.error(f"No feeder data for this substation '{selected_gi}'.")
        st.stop()

    # ---------- Threshold + DR trigger + target curtailment ----------
    summary = run_threshold_check(feeder_data, config.MAX_PER_FEEDER_KW, config.TRIGGER_RATIO)
    dr_results, target_curtailment_total = run_dr_trigger_check(
        feeder_data, config.MAX_PER_FEEDER_KW, config.TRIGGER_RATIO, config.SAFE_TARGET_RATIO
    )

    # ---------- Alokasi per pelanggan ----------
    try:
        df_customers = load_customer_data(uploaded_customer_file)
        df_alloc = allocate_customer_curtailment(dr_results, df_customers, config.CUSTOMER_NAME_COL)
        alloc_error = None
    except Exception as e:
        df_alloc = pd.DataFrame()
        alloc_error = str(e)

    return DashboardContext(
        selected_gi=selected_gi,
        feeder_data=feeder_data,
        summary=summary,
        dr_results=dr_results,
        target_curtailment_total=target_curtailment_total,
        df_alloc=df_alloc,
        alloc_error=alloc_error,
    )


def load_requests(selected_gi: str):
    """
    Ambil riwayat respons pelanggan dari Google Sheets (setelah auto-resolve request
    PENDING yang lewat 30 menit). Return list, atau None kalau gagal (pesan sudah ditampilkan).
    """
    try:
        # "Lazy" check: PoC ini tidak punya proses background, jadi timeout 30 menit
        # dicek setiap halaman PLN dibuka/refresh.
        resolve_expired_requests(selected_gi)
        return get_all_requests(selected_gi)
    except KeyError as e:
        st.info(
            "Google Sheets is not configured yet, so responses can't be shown "
            f"(missing config: {e}). See README.md for setup."
        )
    except Exception as e:
        st.warning(f"Failed to fetch responses from Google Sheets: {e}")
    return None


PERIOD_KEY = "period_range"


def period_filter(requests: list[dict]):
    """
    Pemilih periode (rentang tanggal EVENT, WIB) untuk halaman Notifikasi & Reward/Penalty.
    Tanggal event = tanggal iterasi 1 (iterasi 2 yang lewat tengah malam tetap ikut event awalnya).
    Default: hari terakhir yang punya data. Pilihan ikut terbawa antar halaman (key yang sama).

    Return (baris_dalam_periode, (tanggal_mulai, tanggal_akhir) atau None kalau data tak punya tanggal).
    """
    annotated = annotate_events(requests)
    bounds = date_bounds(annotated)
    if bounds is None:
        st.caption("Records have no valid date, so the period filter is not available.")
        return annotated, None
    lo, hi = bounds
    max_day = max(hi, today_local())

    current = st.session_state.get(PERIOD_KEY)
    valid = (
        isinstance(current, (tuple, list)) and 1 <= len(current) <= 2
        and all(isinstance(d, dt.date) and lo <= d <= max_day for d in current)
    )
    if not valid:
        st.session_state[PERIOD_KEY] = (hi, hi)

    col_date, col_quick = st.columns([2, 3], vertical_alignment="bottom")
    # Tombol cepat diproses SEBELUM date_input dibuat (boleh mengubah nilainya di run yang sama).
    with col_quick:
        q1, q2, q3 = st.columns(3)
        if q1.button("Latest day", use_container_width=True, key="period_latest"):
            st.session_state[PERIOD_KEY] = (hi, hi)
        if q2.button("Last 7 days", use_container_width=True, key="period_week"):
            st.session_state[PERIOD_KEY] = (max(lo, hi - dt.timedelta(days=6)), hi)
        if q3.button("All dates", use_container_width=True, key="period_all"):
            st.session_state[PERIOD_KEY] = (lo, hi)
    with col_date:
        picked = st.date_input(
            "Period (event date, WIB)", min_value=lo, max_value=max_day,
            key=PERIOD_KEY, format="DD/MM/YYYY",
        )

    picked = picked if isinstance(picked, (tuple, list)) else (picked,)
    start, end = picked[0], picked[-1]
    rows = filter_by_period(annotated, start, end)
    n_events = len({r["_event_id"] for r in rows})
    st.caption(
        f"Showing **{n_events} event(s)** ({len(rows)} record(s)) from {start:%d/%m/%Y} to {end:%d/%m/%Y} "
        f"— of {len({r['_event_id'] for r in annotated})} event(s) in the sheet. Dates are in WIB (UTC+7)."
    )
    return rows, (start, end)
