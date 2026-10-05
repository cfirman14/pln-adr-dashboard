"""
PART 11 — Eksekusi curtailment: auto-timeout 30 menit & iterasi ke-2.

Mengikuti flowchart "Execution of ADR":
1. Pelanggan pilih Accept 100% / Accept 80% / Decline di halaman respons.
2. Kalau tidak ada respons dalam 30 menit sejak email dikirim, request
   otomatis dianggap ACCEPTED 100% (tanpa persetujuan eksplisit pelanggan).
   PoC ini jalan di Streamlit tanpa proses background permanen, jadi
   pengecekan dilakukan "lazy": setiap kali halaman respons pelanggan ATAU
   dashboard PLN dibuka/refresh, bukan lewat scheduler terpisah.
3. Kalau pelanggan Decline, PLN operator bisa klik tombol "Run Next
   Iteration" di dashboard untuk feeder terkait: sistem membaca ulang
   kondisi grid SAAT INI (sama seperti tombol "Send Notification") dan
   mengirim ulang email HANYA ke pelanggan yang Decline, dengan target
   curtailment dari alokasi TERKINI (bukan angka lama yang tersimpan waktu
   notifikasi pertama dikirim) — supaya selalu mencerminkan kondisi grid
   paling baru. Iterasi dipicu manual oleh operator, bukan otomatis.
4. Iterasi dibatasi MAKSIMAL 2 putaran (MAX_ITERATIONS). Kalau pelanggan
   masih Decline di iterasi ke-2, TIDAK ada iterasi ke-3: statusnya final
   REJECTED. Status final inilah yang nantinya jadi dasar penalti.
"""

import datetime as dt

from utils.notify import _build_email_body, _build_response_link, send_email
from utils.sheets import append_request, get_all_requests, update_status
from utils.tokens import generate_token

RESPONSE_TIMEOUT_MINUTES = 30
MAX_ITERATIONS = 2   # putaran ke-2 adalah yang terakhir; tidak ada iterasi ke-3


def _is_expired(sent_at: str, timeout_minutes: int = RESPONSE_TIMEOUT_MINUTES) -> bool:
    """Cek apakah sent_at (format '%Y-%m-%d %H:%M:%S UTC') sudah lewat timeout_minutes."""
    try:
        sent_dt = dt.datetime.strptime(sent_at, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return False
    return (dt.datetime.now(dt.timezone.utc) - sent_dt) > dt.timedelta(minutes=timeout_minutes)


def resolve_if_expired(token: str, request: dict) -> dict:
    """
    Dipanggil dari halaman respons pelanggan (pages/1_Respon_Pelanggan.py).
    Kalau request ini masih PENDING dan sudah lewat 30 menit sejak dikirim,
    otomatis tandai ACCEPTED 100% (AUTO) sebelum ditampilkan ke pelanggan.
    Return dict request yang sudah diperbarui (atau sama persis kalau tidak expired).
    """
    status = str(request.get("status", "")).upper()
    if status == "PENDING" and _is_expired(str(request.get("sent_at", ""))):
        target = float(request.get("target_curtailment_kw") or 0)
        if update_status(token, "ACCEPTED 100% (AUTO)", responded_kw=target):
            updated = dict(request)
            updated["status"] = "ACCEPTED 100% (AUTO)"
            updated["responded_kw"] = round(target, 2)
            return updated
    return request


def resolve_expired_requests(gi_name: str | None = None) -> list[str]:
    """
    Dipanggil dari dashboard PLN tiap kali dibuka/refresh. Scan semua request
    PENDING untuk gi_name (atau semua GI kalau None), auto-resolve yang sudah
    lewat 30 menit jadi ACCEPTED 100% (AUTO). Return list token yang baru diresolve.
    """
    requests = get_all_requests(gi_name)
    resolved = []
    for r in requests:
        status = str(r.get("status", "")).upper()
        if status == "PENDING" and _is_expired(str(r.get("sent_at", ""))):
            target = float(r.get("target_curtailment_kw") or 0)
            if update_status(r["token"], "ACCEPTED 100% (AUTO)", responded_kw=target):
                resolved.append(r["token"])
    if resolved:
        get_all_requests.clear()
    return resolved


def latest_per_customer(requests: list[dict]) -> list[dict]:
    """
    Kalau 1 pelanggan punya beberapa baris (iterasi 1, 2, dst, atau beberapa
    kali "Send Notification" di sesi berbeda), ambil baris dengan nomor
    iterasi tertinggi sebagai status "saat ini". Kalau iterasinya sama
    (misal beberapa kali Send Notification tanpa pernah di-iterasi), baris
    dengan sent_at paling baru yang dipakai.
    """
    latest: dict[tuple, dict] = {}
    for r in requests:
        key = (r.get("feeder", ""), r.get("customer_name", ""))
        iteration = int(r.get("iteration") or 1)
        existing = latest.get(key)
        if existing is None:
            latest[key] = r
            continue
        existing_iteration = int(existing.get("iteration") or 1)
        if iteration > existing_iteration:
            latest[key] = r
        elif iteration == existing_iteration and str(r.get("sent_at", "")) >= str(existing.get("sent_at", "")):
            latest[key] = r
    return list(latest.values())


def _iteration_of(r: dict) -> int:
    try:
        return int(r.get("iteration") or 1)
    except (ValueError, TypeError):
        return 1


def split_rejected(latest: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Pisahkan pelanggan REJECTED (status terkini) jadi dua kelompok:
    - retryable : REJECTED di iterasi < MAX_ITERATIONS -> masih boleh di-iterasi lagi
    - final     : REJECTED di iterasi >= MAX_ITERATIONS -> penolakan final (dasar penalti)
    """
    rejected = [r for r in latest if str(r.get("status", "")).upper() == "REJECTED"]
    retryable = [r for r in rejected if _iteration_of(r) < MAX_ITERATIONS]
    final = [r for r in rejected if _iteration_of(r) >= MAX_ITERATIONS]
    return retryable, final


def run_next_iteration(gi_name: str, feeder: str, df_alloc, customer_name_col: str, email_col: str = "EMAIL") -> dict:
    """
    Kirim ulang notifikasi untuk 1 feeder, HANYA ke pelanggan yang status
    terbarunya REJECTED, memakai target curtailment dari alokasi TERKINI
    (df_alloc — hasil allocate_customer_curtailment dengan data grid saat
    dashboard terakhir dimuat), persis seperti logika tombol "Send
    Notification". Ini supaya iterasi 2 selalu mencerminkan kondisi grid
    paling baru, bukan angka lama yang tersimpan di Google Sheet.

    Return {"sent": [{"customer","email","success","error"}, ...], "message": str}
    """
    resolve_expired_requests(gi_name)
    all_requests = get_all_requests(gi_name)
    feeder_requests = [r for r in all_requests if r.get("feeder") == feeder]
    latest = latest_per_customer(feeder_requests)

    retryable, final = split_rejected(latest)
    rejected_names = {r["customer_name"] for r in retryable}
    if not rejected_names:
        if final:
            return {
                "sent": [],
                "message": f"Maximum of {MAX_ITERATIONS} iterations reached. "
                           f"{len(final)} customer(s) remain REJECTED (final) — no further iteration.",
            }
        return {"sent": [], "message": "No customer to re-notify (no one has declined in the latest round)."}

    subset = df_alloc[(df_alloc["FEEDER"] == feeder) & (df_alloc[customer_name_col].isin(rejected_names))]
    if subset.empty:
        return {
            "sent": [],
            "message": "Declined customer(s) are no longer in the current curtailment allocation "
                       "(the feeder may now be back to NORMAL).",
        }

    iteration_by_customer = {r["customer_name"]: _iteration_of(r) for r in latest}

    sent_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    results = []

    for _, row in subset.iterrows():
        customer_name = row[customer_name_col]
        target_kw = float(row["CURTAILMENT_AMOUNT_KW"])
        email = str(row.get(email_col, "")).strip()
        next_iteration = iteration_by_customer.get(customer_name, 1) + 1

        token = generate_token()
        event_id = token[:8]
        link = _build_response_link(token)

        result = {"customer": customer_name, "email": email, "success": False, "error": None}

        if not email or email.lower() == "nan":
            result["error"] = "EMAIL column is empty for this customer."
            results.append(result)
            continue

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
                "responded_kw": "",
                "iteration": next_iteration,
                "campaign_id": sent_at,
            })

            subject = f"[PLN ADR] Load Reduction Request (Follow-up {next_iteration}) — {feeder}"
            body = _build_email_body(customer_name, gi_name, feeder, target_kw, link, iteration=next_iteration)
            send_email(email, subject, body)
            result["success"] = True
        except Exception as e:
            result["error"] = str(e)

        results.append(result)

    get_all_requests.clear()
    return {
        "sent": results,
        "message": f"Re-sent follow-up to {len(results)} customer(s) who declined, using the current curtailment allocation.",
    }
