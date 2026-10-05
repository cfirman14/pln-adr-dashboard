"""
Halaman PLN — Reward & Penalty.
PLN mengisi realisasi durasi curtailment (jam + menit); sistem menghitung insentif
(reward) dan penalty, lalu hasilnya bisa disimpan ke tab "Reward_Penalty" di Google Sheet.
"""

import streamlit as st

from utils.dashboard_context import load_dashboard_context, load_requests, period_filter
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

requests = load_requests(selected_gi)

if requests:
    period_rows, _period = period_filter(requests)
    render_settlement_section(selected_gi, period_rows)
else:
    render_settlement_section(selected_gi, requests)
