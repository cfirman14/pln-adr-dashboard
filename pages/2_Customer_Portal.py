"""
Halaman Pelanggan — Customer Portal (simulasi).
Pelanggan memasukkan IDPEL-nya, lalu melihat riwayat permintaan curtailment,
jumlah reward dan jumlah penalti pada periode yang dipilih.

CATATAN: ini PoC tanpa login — IDPEL cukup sebagai "kunci pencarian". Untuk produksi
perlu autentikasi sungguhan (IDPEL saja bukan rahasia).
"""

import pandas as pd
import streamlit as st

import config
from utils.customer_portal import (
    awaiting_settlement,
    find_customer,
    requests_for_customer,
    settlements_in_period,
    totals,
)
from utils.dashboard_context import period_filter
from utils.data_loader import load_customer_data
from utils.execution import MAX_ITERATIONS, resolve_expired_requests
from utils.idpel import ID_COL, clean_idpel
from utils.sheets import get_all_requests, get_all_settlements

st.set_page_config(page_title="Customer Portal — Demand Response", layout="wide")


def idr(value: float) -> str:
    return f"Rp {value:,.0f}"


st.title("👤 Customer Portal")
st.caption("Demand Response history, rewards and penalties — Proof of Concept simulation.")

# ---------- Search box (IDPEL) ----------
with st.form("idpel_search"):
    typed = st.text_input(
        "Customer ID (IDPEL)", max_chars=20, placeholder="e.g. 323258330020", key="portal_idpel_input",
    )
    submitted = st.form_submit_button("🔍 Search", type="primary")
if submitted:
    st.session_state["portal_idpel"] = typed.strip()

query = st.session_state.get("portal_idpel", "")
if not query:
    st.info("Enter your customer ID (IDPEL) and press **Search**.")
    st.stop()

idpel = clean_idpel(query)
if not idpel:
    st.error("IDPEL must contain digits only.")
    st.stop()

# ---------- Customer master data ----------
try:
    customers = load_customer_data().to_dict("records")
except Exception as e:
    st.error(f"Customer data is not available: {e}")
    st.stop()

if customers and ID_COL not in customers[0]:
    st.error(f"Column '{ID_COL}' was not found in the customer data file.")
    st.stop()

matches = find_customer(customers, idpel)
if not matches:
    st.error(f"IDPEL **{idpel}** was not found.")
    st.stop()

name_col = config.CUSTOMER_NAME_COL
st.subheader(str(matches[0].get(name_col, "")))
info = st.columns(3)
info[0].metric("IDPEL", idpel)
info[1].metric("Substation", ", ".join(sorted({str(m.get("TRAFO_GI", "")) for m in matches})))
info[2].metric("Feeder", ", ".join(sorted({str(m.get("FEEDER", "")) for m in matches})))

# ---------- Records from Google Sheets ----------
try:
    resolve_expired_requests()                     # lazy 30-minute auto-accept, same as the PLN pages
    all_requests = get_all_requests()
    all_settlements = get_all_settlements()
except KeyError as e:
    st.info(f"Google Sheets is not configured yet (missing config: {e}). See README.md for setup.")
    st.stop()
except Exception as e:
    st.warning(f"Failed to fetch records from Google Sheets: {e}")
    st.stop()

mine = requests_for_customer(all_requests, idpel, customers, name_col)
if not mine:
    st.info("No curtailment request has been recorded for this customer yet.")
    st.stop()

st.divider()

# ---------- Period ----------
period_rows, _period = period_filter(mine, prefix="portal_period")
if not period_rows:
    st.info("No curtailment request in the selected period.")
    st.stop()

settled = settlements_in_period(all_settlements, period_rows)
amounts = totals(settled)

# ---------- Summary ----------
m1, m2, m3 = st.columns(3)
m1.metric("🎁 Total reward", idr(amounts["reward"]))
m2.metric("⚠️ Total penalty", idr(amounts["penalty"]))
m3.metric("📨 Curtailment requests", len({r["_event_id"] for r in period_rows}))

pending_n = awaiting_settlement(period_rows, all_settlements)
if pending_n:
    st.info(
        f"{pending_n} request(s) in this period are eligible for a reward or penalty, but PLN has not "
        "recorded the realised curtailment duration yet. The amount will appear once PLN finalises it."
    )

# ---------- Request history ----------
st.subheader("Curtailment Request History")
df = pd.DataFrame(period_rows).sort_values(["_event_start", "iteration"], ascending=[False, True])
for c in ("target_curtailment_kw", "responded_kw"):      # "" (belum merespons) -> kosong, bukan teks campur angka
    df[c] = pd.to_numeric(df[c], errors="coerce").round(2)
cols = ["_event_date", "feeder", "iteration", "target_curtailment_kw", "status", "responded_kw", "sent_at", "responded_at"]
st.dataframe(
    df[[c for c in cols if c in df.columns]].rename(columns={
        "_event_date": "Event date", "feeder": "Feeder", "iteration": "Round",
        "target_curtailment_kw": "Target (kW)", "status": "Your response",
        "responded_kw": "Confirmed (kW)", "sent_at": "Sent at", "responded_at": "Responded at",
    }),
    use_container_width=True, hide_index=True,
)
st.caption(f"Round 1 is the first request; a declined request may be re-sent once (round {MAX_ITERATIONS} is the final round).")

# ---------- Reward & penalty details ----------
st.subheader("Reward and Penalty Details")
if settled:
    detail = pd.DataFrame([
        {
            "Event date": s["_event_date"],
            "Type": "Reward" if str(s.get("type")).upper() == "REWARD" else "Penalty",
            "Feeder": s.get("feeder", ""),
            "Power (kW)": s.get("power_kw", ""),
            "Duration": s.get("duration_text", ""),
            "Energy (kWh)": s.get("energy_kwh", ""),
            "Amount (IDR)": idr(float(s.get("amount_idr") or 0)),
        }
        for s in settled
    ])
    st.dataframe(detail, use_container_width=True, hide_index=True)
else:
    st.caption("No reward or penalty has been recorded for this period.")

with st.expander("How rewards and penalties work"):
    st.markdown(
        "- **Reward:** you accepted **100%** of the request in the **first round** (including automatic acceptance after 30 minutes without a response).\n"
        "- **Penalty:** you declined the request again in the **final round**.\n"
        "- **Neither:** you accepted 80% in the first round, or declined first and then accepted in the final round.\n"
        "- Amounts are calculated by PLN from the realised curtailment duration."
    )
