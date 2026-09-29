"""
Halaman respons pelanggan — dibuka lewat link unik dari email notifikasi.
URL contoh: https://nama-app-kamu.streamlit.app/Respon_Pelanggan?token=xxxxx

Pelanggan TIDAK perlu login. Token di URL berfungsi sebagai kunci akses
satu-satunya ke permintaan curtailment milik mereka.
"""

import streamlit as st

from utils.sheets import get_request_by_token, update_status

st.set_page_config(page_title="Demand Response — PLN", layout="centered")

st.title("⚡ Demand Response Request")
st.caption("Proof of Concept Simulation — OpenADR 3.1")

token = st.query_params.get("token")

if not token:
    st.error("Invalid link — token not found in URL.")
    st.stop()

try:
    request = get_request_by_token(token)
except Exception as e:
    st.error(
        "Failed to connect to the response storage system. "
        "Please try again in a moment, or contact PLN if the problem persists."
    )
    st.caption(f"Technical details: {e}")
    st.stop()

if request is None:
    st.error("Request not found. The link may no longer be valid.")
    st.stop()

st.divider()
st.subheader(f"Dear {request['customer_name']}")

col1, col2 = st.columns(2)
with col1:
    st.metric("Substation", request["gi"])
with col2:
    st.metric("Feeder", request["feeder"])

st.metric("Target Load Reduction", f"{float(request['target_curtailment_kw']):.2f} kW")

status = str(request.get("status", "PENDING")).upper()

st.divider()

if status == "PENDING":
    st.info(
        "Please confirm your availability to carry out the load reduction "
        "according to the target above."
    )
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("✅ Accept 100%", use_container_width=True, type="primary"):
            if update_status(token, "ACCEPTED 100%"):
                st.success("Thank you! Your response (**ACCEPT 100%**) has been recorded.")
                st.rerun()
            else:
                st.error("Failed to save your response. Please try again.")
    with col_b:
        if st.button("✅ Accept 80%", use_container_width=True):
            if update_status(token, "ACCEPTED 80%"):
                st.warning("Your response (**ACCEPT 80%**) has been recorded.")
                st.rerun()
            else:
                st.error("Failed to save your response. Please try again.")
    with col_c:
        if st.button("❌ Decline", use_container_width=True):
            if update_status(token, "REJECTED"):
                st.warning("Your response (**DECLINE**) has been recorded.")
                st.rerun()
            else:
                st.error("Failed to save your response. Please try again.")

elif status == "ACCEPTED 100%":
    st.success("You have **accepted 100%** this request. Thank you for your participation.")

elif status == "ACCEPTED 80%":
    st.success("You have **accepted 80%** this request. Thank you for your participation.")

elif status == "REJECTED":
    st.warning("You have **declined** this request.")

else:
    st.info(f"Request status: {status}")