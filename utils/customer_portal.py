"""
Logika halaman pelanggan (Customer Portal): cari pelanggan lewat IDPEL, ambil riwayat
permintaan curtailment-nya, dan reward/penalti yang SUDAH disimpan PLN.

Murni logika (tanpa Streamlit/Google Sheets) supaya mudah dites.

Pencocokan baris Google Sheet -> pelanggan:
  1. Baris baru menyimpan kolom `idpel` -> dicocokkan lewat IDPEL (pasti).
  2. Baris lama (sebelum kolom idpel ada, idpel kosong) -> dicocokkan lewat
     (feeder, nama pelanggan) ke DataCustomer.csv, HANYA kalau pasangan itu unik
     di CSV (kalau ada nama kembar di feeder yang sama, baris lama tidak ditebak).
"""

from collections import Counter

from utils.idpel import ID_COL, idpel_key
from utils.period import final_per_event
from utils.settlement import classify


def _float(value) -> float:
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return 0.0


def find_customer(customers: list[dict], idpel: str) -> list[dict]:
    """Baris DataCustomer.csv yang IDPEL-nya sama (biasanya 1; bisa >1 kalau pelanggan di beberapa feeder)."""
    key = idpel_key(idpel)
    if not key:
        return []
    return [c for c in customers if idpel_key(c.get(ID_COL)) == key]


def requests_for_customer(requests: list[dict], idpel: str, customers: list[dict], name_col: str) -> list[dict]:
    """Semua baris permintaan milik IDPEL ini (lihat aturan pencocokan di docstring modul)."""
    key = idpel_key(idpel)
    if not key:
        return []

    pair_count = Counter((str(c.get("FEEDER", "")), str(c.get(name_col, ""))) for c in customers)
    legacy_pairs = {
        (str(c.get("FEEDER", "")), str(c.get(name_col, "")))
        for c in find_customer(customers, idpel)
        if pair_count[(str(c.get("FEEDER", "")), str(c.get(name_col, "")))] == 1
    }

    out = []
    for r in requests:
        row_key = idpel_key(r.get("idpel"))
        if row_key:
            if row_key == key:
                out.append(r)
        elif (str(r.get("feeder", "")), str(r.get("customer_name", ""))) in legacy_pairs:
            out.append(r)
    return out


def settlements_in_period(settlements: list[dict], period_rows: list[dict]) -> list[dict]:
    """
    Reward/penalti tersimpan yang dasarnya (basis_token) adalah baris TERAKHIR salah satu event
    dalam periode. Tiap item diberi `_event_date`. Hanya menyentuh token milik pelanggan ini.
    """
    final_by_token = {r["token"]: r for r in final_per_event(period_rows)}
    out = []
    for s in settlements:
        base = final_by_token.get(str(s.get("basis_token", "")))
        if base is not None:
            item = dict(s)
            item["_event_date"] = base.get("_event_date")
            out.append(item)
    return sorted(out, key=lambda s: (str(s.get("_event_date")), str(s.get("type"))))


def totals(settled: list[dict]) -> dict:
    """Total rupiah reward & penalti (dipisah; TIDAK ada selisih/net)."""
    return {
        "reward": sum(_float(s.get("amount_idr")) for s in settled if str(s.get("type")).upper() == "REWARD"),
        "penalty": sum(_float(s.get("amount_idr")) for s in settled if str(s.get("type")).upper() == "PENALTY"),
    }


def awaiting_settlement(period_rows: list[dict], settled_all: list[dict]) -> int:
    """Jumlah event di periode yang berhak reward/penalti tetapi PLN belum menyimpan durasi realisasinya."""
    saved_keys = {str(s.get("key", "")) for s in settled_all}
    groups = classify(final_per_event(period_rows))
    n = 0
    for kind, name in (("reward", "REWARD"), ("penalty", "PENALTY")):
        n += sum(1 for r in groups[kind] if f"{name}:{r.get('token', '')}" not in saved_keys)
    return n
