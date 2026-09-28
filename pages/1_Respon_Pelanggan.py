"""
Halaman respons pelanggan — dibuka lewat link unik dari email notifikasi.
URL contoh: https://nama-app-kamu.streamlit.app/Respon_Pelanggan?token=xxxxx

Pelanggan TIDAK perlu login. Token di URL berfungsi sebagai kunci akses
satu-satunya ke permintaan curtailment milik mereka.
"""

import streamlit as st

from utils.sheets import get_request_by_token, update_status

st.set_page_config(page_title="Respons Demand Response — PLN", layout="centered")

st.title("⚡ Permintaan Demand Response")
st.caption("Simulasi Proof of Concept — OpenADR 3.1")

token = st.query_params.get("token")

if not token:
    st.error("Link tidak valid — token tidak ditemukan di URL.")
    st.stop()

try:
    request = get_request_by_token(token)
except Exception as e:
    st.error(
        "Gagal terhubung ke sistem penyimpanan respons. "
        "Coba lagi beberapa saat, atau hubungi PLN jika masalah berlanjut."
    )
    st.caption(f"Detail teknis: {e}")
    st.stop()

if request is None:
    st.error("Permintaan tidak ditemukan. Link mungkin sudah tidak berlaku.")
    st.stop()

st.divider()
st.subheader(f"Yth. {request['customer_name']}")

col1, col2 = st.columns(2)
with col1:
    st.metric("Gardu Induk", request["gi"])
with col2:
    st.metric("Feeder", request["feeder"])

st.metric("Target Pengurangan Daya", f"{float(request['target_curtailment_kw']):.2f} kW")

status = str(request.get("status", "PENDING")).upper()

st.divider()

if status == "PENDING":
    st.info(
        "Mohon konfirmasi kesediaan Anda untuk melakukan pengurangan beban "
        "sesuai target di atas."
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("✅ Terima", use_container_width=True, type="primary"):
            if update_status(token, "ACCEPTED"):
                st.success("Terima kasih! Respons Anda (**TERIMA**) sudah tercatat.")
                st.rerun()
            else:
                st.error("Gagal menyimpan respons. Coba lagi.")
    with col_b:
        if st.button("❌ Tolak", use_container_width=True):
            if update_status(token, "REJECTED"):
                st.warning("Respons Anda (**TOLAK**) sudah tercatat.")
                st.rerun()
            else:
                st.error("Gagal menyimpan respons. Coba lagi.")

elif status == "ACCEPTED":
    st.success("Anda sudah **menerima** permintaan ini. Terima kasih atas partisipasinya.")

elif status == "REJECTED":
    st.warning("Anda sudah **menolak** permintaan ini.")

else:
    st.info(f"Status permintaan: {status}")
