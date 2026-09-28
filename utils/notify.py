"""
PART 10 — Kirim notifikasi email ke pelanggan yang kena target curtailment.

Alur:
1. Untuk tiap pelanggan di df_alloc, generate token unik.
2. Simpan permintaan (status PENDING) ke Google Sheets lewat utils/sheets.py.
3. Kirim email berisi detail permintaan + link respons (berisi token itu).

Kredensial email disimpan di Streamlit Secrets, bukan di kode:

    [gmail]
    address = "akun-pengirim@gmail.com"
    app_password = "xxxxxxxxxxxxxxxx"   # App Password 16 karakter dari Google
"""

import datetime as dt
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import streamlit as st

from utils.sheets import append_request
from utils.tokens import generate_token


def _build_response_link(token: str) -> str:
    base_url = st.secrets["app"]["base_url"].rstrip("/")
    return f"{base_url}/Respon_Pelanggan?token={token}"


def _build_email_body(customer_name: str, gi: str, feeder: str, target_kw: float, link: str) -> str:
    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #1a1a1a;">
        <h2>⚡ Permintaan Demand Response — PLN</h2>
        <p>Yth. <b>{customer_name}</b>,</p>
        <p>
            Sehubungan dengan kondisi beban pada feeder Anda saat ini, kami
            mengajukan permintaan <b>pengurangan beban sementara (Demand Response)</b>
            dengan rincian sebagai berikut:
        </p>
        <table style="border-collapse: collapse;">
            <tr><td style="padding:4px 12px 4px 0;">Gardu Induk</td><td><b>{gi}</b></td></tr>
            <tr><td style="padding:4px 12px 4px 0;">Feeder</td><td><b>{feeder}</b></td></tr>
            <tr><td style="padding:4px 12px 4px 0;">Target Pengurangan Daya</td><td><b>{target_kw:.2f} kW</b></td></tr>
        </table>
        <p>Mohon konfirmasi kesediaan Anda dengan klik tombol di bawah ini:</p>
        <p>
            <a href="{link}"
               style="background:#0068c9; color:#ffffff; padding:10px 20px;
                      text-decoration:none; border-radius:6px; display:inline-block;">
                Buka Halaman Respons
            </a>
        </p>
        <p style="font-size:12px; color:#666;">
            Jika tombol di atas tidak berfungsi, salin tautan berikut ke browser Anda:<br>
            {link}
        </p>
        <p style="font-size:12px; color:#666;">
            Ini adalah simulasi Proof of Concept OpenADR — bukan permintaan operasional sungguhan.
        </p>
    </body>
    </html>
    """


def send_email(to_email: str, subject: str, html_body: str) -> None:
    sender = st.secrets["gmail"]["address"]
    app_password = st.secrets["gmail"]["app_password"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.sendmail(sender, to_email, msg.as_string())


def send_notifications(df_alloc, customer_name_col: str, gi_name: str, email_col: str = "EMAIL") -> list[dict]:
    """
    Kirim notifikasi untuk semua baris di df_alloc (hasil allocate_customer_curtailment).
    Return list hasil per-pelanggan: {"customer": ..., "email": ..., "success": bool, "error": str|None}
    """
    results = []
    sent_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    for _, row in df_alloc.iterrows():
        customer_name = row[customer_name_col]
        feeder = row["FEEDER"]
        target_kw = float(row["CURTAILMENT_AMOUNT_KW"])
        email = str(row.get(email_col, "")).strip()

        result = {"customer": customer_name, "email": email, "success": False, "error": None}

        if not email or email.lower() == "nan":
            result["error"] = "Kolom EMAIL kosong untuk pelanggan ini."
            results.append(result)
            continue

        token = generate_token()
        event_id = token[:8]
        link = _build_response_link(token)

        try:
            append_request({
                "token": token,
                "event_id": event_id,
                "sent_at": sent_at,
                "gi": gi_name,
                "feeder": feeder,
                "customer_name": customer_name,
                "email": email,
                "target_curtailment_kw": round(target_kw, 2),
                "status": "PENDING",
                "responded_at": "",
            })

            subject = f"[PLN ADR] Permintaan Pengurangan Beban — {feeder}"
            body = _build_email_body(customer_name, gi_name, feeder, target_kw, link)
            send_email(email, subject, body)

            result["success"] = True
        except Exception as e:
            result["error"] = str(e)

        results.append(result)

    return results
