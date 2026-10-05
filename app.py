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
from utils.notify import send_notifications
from utils.sheets import get_all_requests
from utils.execution import resolve_expired_requests, latest_per_customer, run_next_iteration

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
gi_list = sorted(df_feeder_raw["GI"].dropna().astype(str).str.strip().unique())
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
                    .round(2)
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
# SECTION 4 — Kirim Notifikasi Demand Response ke Pelanggan
# ============================================================
st.subheader("Send Notification to Impacted Customers")

if df_alloc.empty:
    st.info("No Notification (all feeders are NORMAL).")
elif config.CUSTOMER_EMAIL_COL not in df_alloc.columns:
    st.warning(
        f"Column '{config.CUSTOMER_EMAIL_COL}' is not exist — "
        "Fail to send notification. Add Email Column in CSV."
    )
else:
    st.dataframe(
        df_alloc[[config.CUSTOMER_NAME_COL, config.CUSTOMER_EMAIL_COL, "FEEDER", "CURTAILMENT_AMOUNT_KW"]]
        .round(2)
        .rename(columns={
            config.CUSTOMER_NAME_COL: "Customer",
            config.CUSTOMER_EMAIL_COL: "Email",
            "CURTAILMENT_AMOUNT_KW": "Curtailment Target(kW)",
        }),
        use_container_width=True,
        hide_index=True,
    )

    if st.button("📧 Send Notification", type="primary"):
        try:
            with st.spinner("Sending Notification..."):
                results = send_notifications(df_alloc, config.CUSTOMER_NAME_COL, selected_gi)

            success_count = sum(1 for r in results if r["success"])
            st.success(f"Success {success_count} from {len(results)} notification.")

            failed = [r for r in results if not r["success"]]
            if failed:
                st.error("Some notifications unable send:")
                for r in failed:
                    st.write(f"- **{r['customer']}** ({r['email'] or 'tanpa email'}): {r['error']}")
        except KeyError as e:
            st.error(
                "Configuration in streamlit is not complete "
                f"(loss item: {e}). See README.md to setup Gmail & Google Sheets."
            )
        except Exception as e:
            st.error(f"Fail to send notification: {e}")

st.divider()

# ============================================================
# SECTION 5 — Customer Response Summary
# ============================================================
st.subheader("Customer Response Summary")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Refresh"):
        get_all_requests.clear()

try:
    # Auto-resolve any PENDING request older than 30 minutes (no response = accepted 100%)
    # before showing the summary — this is the "lazy" check since this PoC has no background job.
    resolve_expired_requests(selected_gi)
    requests = get_all_requests(selected_gi)
except KeyError as e:
    requests = None
    st.info(
        "Google Sheets is not configured yet, so responses can't be shown "
        f"(missing config: {e}). See README.md for setup."
    )
except Exception as e:
    requests = None
    st.warning(f"Failed to fetch responses from Google Sheets: {e}")

if requests is not None:
    if not requests:
        st.info("No notification has been sent yet for this substation.")
    else:
        # Status "saat ini" per pelanggan (kalau pernah dikirimi lebih dari 1 kali,
        # ambil yang iterasinya paling tinggi / paling baru).
        latest = latest_per_customer(requests)

        pending = [r for r in latest if str(r.get("status", "")).upper() == "PENDING"]
        accepted_100 = [r for r in latest if str(r.get("status", "")).upper() == "ACCEPTED 100%"]
        accepted_80 = [r for r in latest if str(r.get("status", "")).upper() == "ACCEPTED 80%"]
        auto_accepted = [r for r in latest if str(r.get("status", "")).upper() == "ACCEPTED 100% (AUTO)"]
        rejected = [r for r in latest if str(r.get("status", "")).upper() == "REJECTED"]

        confirmed_kw = sum(
            float(r.get("responded_kw") or 0)
            for r in latest
            if str(r.get("status", "")).upper().startswith("ACCEPTED")
        )
        pending_kw = sum(float(r.get("target_curtailment_kw") or 0) for r in pending)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("⏳ Pending", len(pending))
        m2.metric("✅ Accepted 100%", len(accepted_100))
        m3.metric("✅ Accepted 80%", len(accepted_80))
        m4.metric("⌛ Auto-accepted", len(auto_accepted))
        m5.metric("❌ Rejected", len(rejected))

        st.caption(
            f"Confirmed load reduction so far (latest response per customer): **{confirmed_kw:.2f} kW** "
            f"(still pending: {pending_kw:.2f} kW awaiting response)"
        )

        df_requests = pd.DataFrame(requests)
        display_cols = [
            "feeder", "customer_name", "email", "iteration",
            "target_curtailment_kw", "status", "responded_kw",
            "sent_at", "responded_at",
        ]
        display_cols = [c for c in display_cols if c in df_requests.columns]
        st.dataframe(
            df_requests[display_cols].rename(columns={
                "feeder": "Feeder",
                "customer_name": "Customer",
                "email": "Email",
                "iteration": "Iteration",
                "target_curtailment_kw": "Target (kW)",
                "status": "Status",
                "responded_kw": "Confirmed (kW)",
                "sent_at": "Sent At",
                "responded_at": "Responded At",
            }),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Table above shows full history. Metrics above use each customer's latest response only.")

        feeders_with_rejection = sorted({r["feeder"] for r in rejected})
        if feeders_with_rejection:
            if df_alloc.empty:
                st.info(
                    "Some customers declined previously, but the feeder is currently NORMAL "
                    "(no active curtailment need), so there is nothing to re-send right now."
                )
            else:
                st.markdown("**Feeders with declined customers — re-run iteration using the current allocation:**")
                for feeder_name in feeders_with_rejection:
                    if st.button(f"🔁 Run Next Iteration — {feeder_name}", key=f"iter_{feeder_name}"):
                        with st.spinner(f"Sending follow-up notification for {feeder_name}..."):
                            outcome = run_next_iteration(
                                selected_gi, feeder_name, df_alloc, config.CUSTOMER_NAME_COL
                            )

                        if outcome["sent"]:
                            success_n = sum(1 for r in outcome["sent"] if r["success"])
                            st.success(f"{outcome['message']} ({success_n}/{len(outcome['sent'])} email sent successfully)")
                            failed = [r for r in outcome["sent"] if not r["success"]]
                            for r in failed:
                                st.error(f"- **{r['customer']}** ({r['email'] or 'no email'}): {r['error']}")
                        else:
                            st.info(outcome["message"])

                        get_all_requests.clear()
                        st.rerun()

st.divider()

# ============================================================
# SECTION 6 — OpenADR Events (simulasi)
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
