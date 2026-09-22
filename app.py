"""
Dashboard Demand Response — OpenADR PoC
Run Local:  streamlit run app.py
"""

import json

import pandas as pd
import streamlit as st

import config
from utils.data_loader import load_feeder_data, load_customer_data
from utils.threshold import run_threshold_check, run_dr_trigger_check
from utils.curtailment import allocate_customer_curtailment
from utils.openadr_events import build_all_events

st.set_page_config(page_title=f"DR Dashboard — {config.LOCATION_NAME}", layout="wide")

# ---------- Sidebar: sumber data ----------
st.sidebar.header("Data Source")
use_demo_data = st.sidebar.toggle("Use Demo Data", value=True)

uploaded_feeder_files = {}
uploaded_customer_file = None

if not use_demo_data:
    st.sidebar.caption("Upload CSV feeder")
    for feeder_name in config.FEEDER_FILES:
        uploaded_feeder_files[feeder_name] = st.sidebar.file_uploader(
            f"CSV — {feeder_name}", type="csv", key=f"upload_{feeder_name}"
        )
    uploaded_customer_file = st.sidebar.file_uploader("CSV — Customer Data", type="csv")

st.sidebar.divider()
st.sidebar.caption(f"Capacity/feeder: {config.MAX_PER_FEEDER_KW} kW")
st.sidebar.caption(f"Trigger tier: {config.TRIGGER_RATIO * 100:.0f}%")

# ---------- Load data ----------
try:
    feeder_data = load_feeder_data(config.FEEDER_FILES, uploaded_feeder_files)
except Exception as e:
    st.error(f"Fail to read feeder data: {e}")
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
st.title(f"⚡ Demand Response Dashboard — {config.LOCATION_NAME}")
st.caption("Simulation — OpenADR 3.1")

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
        label=f"TOTAL {config.LOCATION_NAME}  ·  {total_badge}",
        value=f"{summary['total_power_active']:.2f} kW",
        delta=f"Loading {summary['total_loading_pct']:.1f}%",
    )
    st.caption(f"Maks total: {summary['max_total']:.0f} kW")

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
# SECTION 3 — Target per Customer
# ============================================================
st.subheader("Curtailment Target per Customer")

try:
    df_customers = load_customer_data(uploaded_customer_file)
    df_alloc = allocate_customer_curtailment(dr_results, df_customers, config.CUSTOMER_NAME_COL)

    if df_alloc.empty:
        st.info("No TRIGGER — No need curtailment.")
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
    st.warning(f"No Cust. Data Available: {e}")
    df_alloc = pd.DataFrame()

st.divider()

# ============================================================
# SECTION 4 — OpenADR Events (Simulation)
# ============================================================
st.subheader("OpenADR 3.1 Events (Simulation)")

if not df_alloc.empty:
    feeder_names = list(config.FEEDER_FILES.keys())
    program_registry = config.build_program_registry(feeder_names)
    events = build_all_events(df_alloc, config.CUSTOMER_NAME_COL, program_registry)

    st.caption(f"Total event: {len(events)}")

    if events:
        st.json(events[0], expanded=False)
        st.download_button(
            "Download semua event (JSON)",
            data=json.dumps(events, indent=2),
            file_name="openadr_events.json",
            mime="application/json",
        )
else:
    st.info("No event — all feeders are NORMAL.")
