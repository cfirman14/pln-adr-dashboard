"""
Dashboard Demand Response — OpenADR PoC
Jalankan lokal:  streamlit run app.py
"""

import json

import pandas as pd
import streamlit as st

import config
from utils.data_loader import load_feeder_data, get_latest_snapshot, load_customer_data
from utils.threshold import run_threshold_check, run_dr_trigger_check
from utils.curtailment import allocate_customer_curtailment
from utils.openadr_events import build_all_events

st.set_page_config(page_title="DR Dashboard — OpenADR PoC", layout="wide")

# ---------- Sidebar: sumber data ----------
st.sidebar.header("Data Source")
use_demo_data = st.sidebar.toggle("Use Demo Data", value=True)

uploaded_feeder_file = None
uploaded_customer_file = None

if not use_demo_data:
    st.sidebar.caption("Upload CSV feeder (1 file")
    uploaded_feeder_file = st.sidebar.file_uploader("CSV — Feeder Data", type="csv")
    uploaded_customer_file = st.sidebar.file_uploader("CSV — Customer Data", type="csv")

# ---------- Load data feeder (mentah, semua GI) ----------
try:
    df_feeder_raw = load_feeder_data(uploaded_feeder_file)
except Exception as e:
    st.error(f"Fail to read data feeder: {e}")
    st.stop()

# ---------- Choose Substation ----------
gi_list = sorted(df_feeder_raw["GI"].unique())
selected_gi = st.sidebar.selectbox("Choose Substation", gi_list)

st.sidebar.divider()
st.sidebar.caption(f"Capacity/feeder: {config.MAX_PER_FEEDER_KW} kW")
st.sidebar.caption(f"Trigger tier: {config.TRIGGER_RATIO * 100:.0f}%")

# ---------- Choosen Substation ----------
feeder_data = get_latest_snapshot(df_feeder_raw, selected_gi)
if not feeder_data:
    st.error(f"No feeder data for this substation '{selected_gi}'.")
    st.stop()

# ---------- Part 3: Threshold check ----------
summary = run_threshold_check(feeder_data, config.MAX_PER_FEEDER_KW, config.TRIGGER_RATIO)

# ---------- Part 4: DR trigger + target curtailment ----------
dr_results, target_curtailment_total = run_dr_trigger_check(
    feeder_data, config.MAX_PER_FEEDER_KW, config.TRIGGER_RATIO, config.SAFE_TARGET_RATIO
)

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
    st.caption(f"Max total: {summary['max_total']:.0f} kW")

st.divider()

# ============================================================
# SECTION 2 — Target curtailment per feeder
# ============================================================
st.subheader("Target Curtailment per Feeder")

df_dr = pd.DataFrame(
    [
        {
            "Feeder": name,
            "Power Active (kW)": r["power_active"],
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

try:
    df_customers = load_customer_data(uploaded_customer_file)
    df_alloc = allocate_customer_curtailment(dr_results, df_customers, config.CUSTOMER_NAME_COL)

    if df_alloc.empty:
        st.info("No TRIGGER Feeder — No curtailment allocation.")
    else:
        for feeder_name in df_alloc["FEEDER"].unique():
            subset = df_alloc[df_alloc["FEEDER"] == feeder_name]
            with st.expander(f"{feeder_name} — {subset['CURTAILMENT_AMOUNT_KW'].sum():.2f} kW", expanded=True):
                st.dataframe(
                    subset[[config.CUSTOMER_NAME_COL, "ACTIVE_POWER_TOTAL", "CURTAILMENT_AMOUNT_KW"]]
                    .rename(columns={
                        config.CUSTOMER_NAME_COL: "Pelanggan",
                        "ACTIVE_POWER_TOTAL": "Power Aktif (kW)",
                        "CURTAILMENT_AMOUNT_KW": "Curtailment (kW)",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
except Exception as e:
    st.warning(f"Customer data not available: {e}")
    df_alloc = pd.DataFrame()

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
