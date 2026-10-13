"""
Halaman PLN — Reward & Penalty (yang BELUM diisi durasinya).
PLN mengisi realisasi durasi curtailment (jam + menit) per pelanggan; setelah disimpan ke tab
"Reward_Penalty" di Google Sheet, pelanggan itu pindah ke halaman "Reward and Penalty History".
Semua tanggal ditampilkan: kewajiban yang belum diisi tidak boleh tersembunyi oleh filter periode.
"""

import streamlit as st

from utils.dashboard_context import load_dashboard_context, load_requests
from utils.settlement_ui import render_settlement_section
from utils.sheets import get_all_requests, get_all_settlements

st.set_page_config(page_title="Reward & Penalty — DR", layout="wide")

ctx = load_dashboard_context()
selected_gi = ctx.selected_gi

st.title(f"💰 Reward & Penalty — {selected_gi}")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Refresh"):
        get_all_requests.clear()
        get_all_settlements.clear()

render_settlement_section(selected_gi, load_requests(selected_gi))
