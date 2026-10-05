"""
Dashboard Demand Response — OpenADR PoC (halaman utama: kondisi feeder & alokasi).
Jalankan lokal:  streamlit run app.py

Halaman lain (sidebar):
  - Notification and Response : kirim email ke pelanggan + rekap respons + iterasi
  - Reward and Penalty     : input durasi realisasi, hitung & simpan reward/penalty
  - Respon Pelanggan       : halaman untuk pelanggan (dibuka lewat link di email)
"""

import json

import pandas as pd
import streamlit as st

import config
from utils.dashboard_context import load_dashboard_context
from utils.openadr_events import build_all_events

st.set_page_config(page_title="DR Dashboard — OpenADR PoC", layout="wide")

ctx = load_dashboard_context()
selected_gi = ctx.selected_gi
feeder_data = ctx.feeder_data
summary = ctx.summary
dr_results = ctx.dr_results
target_curtailment_total = ctx.target_curtailment_total
df_alloc = ctx.df_alloc

# ============================================================
# HEADER
# ============================================================
st.title(f"⚡ Demand Response Dashboard — {selected_gi}")
st.caption("Simulation — OpenADR 3.0")

# ============================================================
# SECTION 1 — Kondisi terkini per feeder
# ============================================================
st.subheader("Current Condition")

cols = st.columns(len(feeder_data) + 1)

for col, (feeder_name, data) in zip(cols, feeder_data.items()):
    with col:
        badge = "🔴 TRIGGER" if data["status"] == "TRIGGER" else "🟢 NORMAL"
        st.metric(
            label=f"{feeder_name}  ·  {badge}",
            value=f"{data['power_active']:.2f} kW",
            delta=f"Loading {data['loading_pct']:.1f}%",
            delta_color="inverse" if data["status"] == "TRIGGER" else "normal",
        )
        st.caption(f"{data['date']} • {data['time']}")

with cols[-1]:
    total_badge = "🔴 TRIGGER" if summary["total_status"] == "TRIGGER" else "🟢 NORMAL"
    st.metric(
        label=f"TOTAL {selected_gi}  ·  {total_badge}",
        value=f"{summary['total_power_active']:.2f} kW",
        delta=f"Loading {summary['total_loading_pct']:.1f}%",
    )
    st.caption(f"Trafo Capacity: {summary['gi_capacity']:.0f} MVA")

st.divider()

# ============================================================
# SECTION 2 — Target curtailment per feeder
# ============================================================
st.subheader("Target Curtailment per Feeder")

df_dr = pd.DataFrame(
    [
        {
            "Feeder": name,
            "Power Active (kW)": round(r["power_active"], 2),
            "Loading (%)": round(r["loading_pct"], 1),
            "Status": r["dr_status"],
            "Target Curtailment (kW)": round(r["target_curtailment_kw"], 2),
        }
        for name, r in dr_results.items()
    ]
)
st.dataframe(df_dr, use_container_width=True, hide_index=True)
st.caption(f"Total target curtailment (accumulation): **{target_curtailment_total:.2f} kW**")

st.divider()

# ============================================================
# SECTION 3 — Alokasi per pelanggan
# ============================================================
st.subheader("Curtailment Allocation per Customer")

if ctx.alloc_error:
    st.warning(f"Customer data not available: {ctx.alloc_error}")
elif df_alloc.empty:
    st.info("No TRIGGER Feeder — No curtailment allocation.")
else:
    for feeder_name in df_alloc["FEEDER"].unique():
        subset = df_alloc[df_alloc["FEEDER"] == feeder_name]
        with st.expander(f"{feeder_name} — {subset['CURTAILMENT_AMOUNT_KW'].sum():.2f} kW", expanded=True):
            st.dataframe(
                subset[[config.CUSTOMER_NAME_COL, "ACTIVE_POWER_TOTAL", "CURTAILMENT_AMOUNT_KW"]]
                .round(2)
                .rename(columns={
                    config.CUSTOMER_NAME_COL: "Pelanggan",
                    "ACTIVE_POWER_TOTAL": "Power Aktif (kW)",
                    "CURTAILMENT_AMOUNT_KW": "Curtailment (kW)",
                }),
                use_container_width=True,
                hide_index=True,
            )

st.caption("Send notifications and track customer responses on the **Notification and Response** page (sidebar).")

st.divider()

# ============================================================
# SECTION 4 — OpenADR Events (simulasi)
# ============================================================
st.subheader("OpenADR 3.0 Events (Simulation)")

if not df_alloc.empty:
    feeder_names = list(feeder_data.keys())
    program_registry = config.build_program_registry(feeder_names)
    events = build_all_events(df_alloc, config.CUSTOMER_NAME_COL, program_registry)

    st.caption(f"Total event generate: {len(events)}")

    if events:
        st.json(events[0], expanded=False)
        st.download_button(
            "Download all event (JSON)",
            data=json.dumps(events, indent=2),
            file_name="openadr_events.json",
            mime="application/json",
        )
else:
    st.info("No event — all feeders are NORMAL.")
