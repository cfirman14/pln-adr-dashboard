"""
Halaman PLN — Reward & Penalty History.
Riwayat perhitungan reward & penalty yang SUDAH disimpan (dibaca langsung dari tab Reward_Penalty),
per periode (tanggal event asalnya).
"""

import streamlit as st

from utils.dashboard_context import load_dashboard_context, load_requests, period_filter
from utils.settlement import compute_settlements, history_rows
from utils.settlement_ui import render_history_section
from utils.sheets import get_all_requests, get_all_settlements

st.set_page_config(page_title="Reward & Penalty History — DR", layout="wide")

ctx = load_dashboard_context()
selected_gi = ctx.selected_gi

st.title(f"🗂️ Reward & Penalty History — {selected_gi}")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Refresh"):
        get_all_requests.clear()
        get_all_settlements.clear()

try:
    saved_rows = get_all_settlements(selected_gi)
except KeyError as e:
    st.info(f"Google Sheets is not configured yet (missing config: {e}). See README.md for setup.")
    st.stop()
except Exception as e:
    st.warning(f"Failed to read saved calculations from Google Sheets: {e}")
    st.stop()

if not saved_rows:
    st.info(
        "No reward or penalty calculation has been saved yet for this substation. "
        "Fill in the realised duration on the **Reward and Penalty** page and press Save — "
        "saved customers appear here."
    )
    st.stop()

requests = load_requests(selected_gi)                  # hanya untuk mencari tanggal event asal
records = history_rows(saved_rows, requests)

period_rows, _period = period_filter(records, prefix="history_period", default="all")

items = []
for r in period_rows:
    item = dict(r["_saved"])
    item["event_date"] = r["_event_date"].strftime("%d/%m/%Y") if r.get("_event_date") else ""
    items.append(item)
items.sort(key=lambda x: (x["event_date"][6:] + x["event_date"][3:5] + x["event_date"][:2], str(x.get("customer_name", ""))))

# Kewajiban yang BELUM disimpan tidak muncul di sini — arahkan ke halaman Reward and Penalty.
if requests:
    saved_keys = {str(r.get("key", "")) for r in saved_rows}
    res = compute_settlements(requests)
    waiting = [x for x in res["rewards"] + res["penalties"] if x["key"] not in saved_keys]
    if waiting:
        st.info(
            f"{len(waiting)} customer(s) are eligible for a reward or penalty but have no saved duration yet. "
            "They appear here after you fill in the duration and press Save on the **Reward and Penalty** page."
        )

render_history_section(items)
