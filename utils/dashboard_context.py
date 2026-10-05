"""
Konteks bersama untuk semua halaman PLN (dashboard utama, Notifikasi & Respons,
Reward & Penalty). Tiap halaman Streamlit adalah skrip terpisah, jadi sidebar
(sumber data + pilihan GI), pembacaan data feeder, threshold, dan alokasi
curtailment dikumpulkan di sini supaya hasilnya IDENTIK di semua halaman.

Widget sidebar memakai key tetap, jadi pilihan (mis. GI) terbawa saat pindah halaman.
"""

from dataclasses import dataclass

import pandas as pd
import streamlit as st

import config
from utils.curtailment import allocate_customer_curtailment
from utils.data_loader import get_latest_snapshot, load_customer_data, load_feeder_data
from utils.execution import resolve_expired_requests
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
