"""
Halaman PLN — Notifikasi & Respons Pelanggan.
Kirim email permintaan curtailment, pantau respons pelanggan, dan jalankan
iterasi berikutnya untuk pelanggan yang menolak.
"""

import pandas as pd
import streamlit as st

import config
from utils.dashboard_context import load_dashboard_context, load_requests, period_filter
from utils.execution import MAX_ITERATIONS, latest_per_customer, run_next_iteration, split_rejected
from utils.notify import send_notifications
from utils.period import final_per_event
from utils.sheets import get_all_requests

st.set_page_config(page_title="Notifikasi & Respons — DR", layout="wide")

ctx = load_dashboard_context()
selected_gi = ctx.selected_gi
df_alloc = ctx.df_alloc

st.title(f"📧 Notification & Customer Response — {selected_gi}")
st.caption("Send requests to impacted customers, track their responses, and run follow-up iterations.")

if ctx.alloc_error:
    st.warning(f"Customer data not available: {ctx.alloc_error}")

# ============================================================
# SECTION A — Kirim Notifikasi Demand Response ke Pelanggan
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
# SECTION B — Customer Response Summary
# ============================================================
st.subheader("Customer Response Summary")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 Refresh"):
        get_all_requests.clear()

requests = load_requests(selected_gi)

if requests is not None:
    if not requests:
        st.info("No notification has been sent yet for this substation.")
    else:
        # Periode yang dipilih: hanya event (iterasi 1 + lanjutannya) yang mulai di rentang tanggal ini.
        period_rows, _period = period_filter(requests)
        if not period_rows:
            st.info("No notification records in the selected period.")
            st.stop()

        # Status AKHIR tiap event pelanggan di periode ini (iterasi tertinggi per event).
        latest = final_per_event(period_rows)
        # Event TERBARU tiap pelanggan (seluruh riwayat): hanya event ini yang boleh di-iterasi lagi.
        current_tokens = {r["token"] for r in latest_per_customer(requests)}

        pending = [r for r in latest if str(r.get("status", "")).upper() == "PENDING"]
        accepted_100 = [r for r in latest if str(r.get("status", "")).upper() == "ACCEPTED 100%"]
        accepted_80 = [r for r in latest if str(r.get("status", "")).upper() == "ACCEPTED 80%"]
        auto_accepted = [r for r in latest if str(r.get("status", "")).upper() == "ACCEPTED 100% (AUTO)"]
        rejected_retryable, rejected_final = split_rejected(latest)

        confirmed_kw = sum(
            float(r.get("responded_kw") or 0)
            for r in latest
            if str(r.get("status", "")).upper().startswith("ACCEPTED")
        )
        pending_kw = sum(float(r.get("target_curtailment_kw") or 0) for r in pending)

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("⏳ Pending", len(pending))
        m2.metric("✅ Accepted 100%", len(accepted_100))
        m3.metric("✅ Accepted 80%", len(accepted_80))
        m4.metric("⌛ Auto-accepted", len(auto_accepted))
        m5.metric("↩️ Declined (can re-iterate)", len(rejected_retryable))
        m6.metric("❌ Rejected (final)", len(rejected_final))

        st.caption(
            f"Confirmed load reduction so far (latest response per customer): **{confirmed_kw:.2f} kW** "
            f"(still pending: {pending_kw:.2f} kW awaiting response)"
        )

        df_requests = pd.DataFrame(period_rows)
        display_cols = [
            "_event_date", "feeder", "customer_name", "email", "iteration",
            "target_curtailment_kw", "status", "responded_kw",
            "sent_at", "responded_at",
        ]
        display_cols = [c for c in display_cols if c in df_requests.columns]
        st.dataframe(
            df_requests[display_cols].rename(columns={
                "_event_date": "Event date",
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
        st.caption("Table above shows the full history of the selected period. Metrics use the last response of each event only.")

        if rejected_final:
            final_kw = sum(float(r.get("target_curtailment_kw") or 0) for r in rejected_final)
            st.error(
                f"**{len(rejected_final)} customer(s) with FINAL rejection** "
                f"(declined after iteration {MAX_ITERATIONS}, no further iteration): "
                + ", ".join(f"{r['customer_name']} ({r['feeder']})" for r in rejected_final)
                + f" — unfulfilled target: {final_kw:.2f} kW."
            )

        # Tombol iterasi hanya untuk event TERBARU pelanggan (event lama tidak boleh dikirim ulang).
        rejected_current = [r for r in rejected_retryable if r["token"] in current_tokens]
        n_old = len(rejected_retryable) - len(rejected_current)
        if n_old:
            st.caption(
                f"{n_old} declined customer(s) in this period belong to an older event and can no longer be re-iterated."
            )
        feeders_with_rejection = sorted({r["feeder"] for r in rejected_current})
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
