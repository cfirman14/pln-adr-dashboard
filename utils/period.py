"""
PART 13 — Periode (tanggal) & pengelompokan "event" untuk data respons pelanggan.

Google Sheet merekam SEMUA permintaan dari waktu ke waktu. Supaya dashboard bisa
menampilkan periode tertentu saja, modul ini:

1. Mengubah `sent_at` (UTC) menjadi tanggal lokal (default WIB = UTC+7).
   Atur lewat config.py:  DISPLAY_UTC_OFFSET_HOURS = 7
   (offset tetap, bukan nama zona waktu, supaya jalan di Windows tanpa paket tzdata.)

2. Mengelompokkan baris jadi "event" per pelanggan. Satu event = iterasi 1 + iterasi
   berikutnya untuk pelanggan & feeder yang sama. Tanggal event = tanggal ITERASI 1,
   jadi iterasi 2 yang dikirim lewat tengah malam tetap ikut event tanggal awalnya.

3. Menyediakan:
   - filter_by_period    : ambil event yang tanggal awalnya ada di rentang tertentu
   - final_per_event     : baris TERAKHIR (iterasi tertinggi) tiap event
   - current_per_customer: status event TERBARU tiap pelanggan (dipakai untuk iterasi)

Modul ini murni logika (tanpa Streamlit/Google Sheets) supaya mudah dites.
"""

import datetime as dt

import config

SENT_AT_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
UTC_OFFSET_HOURS = getattr(config, "DISPLAY_UTC_OFFSET_HOURS", 7)
LOCAL_TZ = dt.timezone(dt.timedelta(hours=UTC_OFFSET_HOURS))

_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def parse_sent_at(value) -> dt.datetime | None:
    """'2026-10-05 16:50:00 UTC' -> datetime UTC. None kalau formatnya tidak dikenal."""
    try:
        return dt.datetime.strptime(str(value), SENT_AT_FORMAT).replace(tzinfo=dt.timezone.utc)
    except (ValueError, TypeError):
        return None


def to_local_date(moment: dt.datetime | None) -> dt.date | None:
    return moment.astimezone(LOCAL_TZ).date() if moment else None


def today_local() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).astimezone(LOCAL_TZ).date()


def _iteration_of(r: dict) -> int:
    try:
        return int(r.get("iteration") or 1)
    except (ValueError, TypeError):
        return 1


def annotate_events(requests: list[dict]) -> list[dict]:
    """
    Salinan tiap baris + 3 kolom bantu (urutan baris asli dipertahankan):
      _event_start : waktu (UTC) iterasi 1 dari event-nya, format sent_at ("" kalau tidak diketahui)
      _event_date  : tanggal lokal event (date) atau None
      _event_id    : "feeder|pelanggan|_event_start" — identitas event
    Baris iterasi >1 mewarisi event dari baris sebelumnya milik pelanggan+feeder yang sama.
    """
    order = sorted(
        range(len(requests)),
        key=lambda i: (parse_sent_at(requests[i].get("sent_at")) or _EPOCH, _iteration_of(requests[i]), i),
    )
    chain_start: dict[tuple, dt.datetime | None] = {}
    out: list[dict | None] = [None] * len(requests)

    for i in order:
        r = requests[i]
        key = (str(r.get("feeder", "")), str(r.get("customer_name", "")))
        sent = parse_sent_at(r.get("sent_at"))
        if _iteration_of(r) == 1 or key not in chain_start:
            chain_start[key] = sent
        start = chain_start[key]

        row = dict(r)
        row["_event_start"] = start.strftime(SENT_AT_FORMAT) if start else ""
        row["_event_date"] = to_local_date(start)
        row["_event_id"] = f"{key[0]}|{key[1]}|{row['_event_start']}"
        out[i] = row
    return out


def date_bounds(rows: list[dict]) -> tuple[dt.date, dt.date] | None:
    """(tanggal event paling awal, paling akhir) dari baris hasil annotate_events; None kalau tak ada tanggal."""
    dates = [r["_event_date"] for r in rows if r.get("_event_date")]
    return (min(dates), max(dates)) if dates else None


def filter_by_period(rows: list[dict], start: dt.date, end: dt.date) -> list[dict]:
    """Baris (hasil annotate_events) yang EVENT-nya mulai antara start dan end (inklusif)."""
    return [r for r in rows if r.get("_event_date") and start <= r["_event_date"] <= end]


def _pick_final(rows: list[dict]) -> dict:
    return max(rows, key=lambda r: (_iteration_of(r), str(r.get("sent_at", ""))))


def final_per_event(requests: list[dict]) -> list[dict]:
    """Baris TERAKHIR (iterasi tertinggi) untuk setiap event. Satu pelanggan bisa muncul >1 kali (event berbeda)."""
    groups: dict[str, list[dict]] = {}
    for r in annotate_events(requests):
        groups.setdefault(r["_event_id"], []).append(r)
    return [_pick_final(g) for g in groups.values()]


def current_per_customer(requests: list[dict]) -> list[dict]:
    """Status EVENT TERBARU tiap pelanggan+feeder (baris terakhir dari event itu)."""
    latest: dict[tuple, dict] = {}
    for r in final_per_event(requests):
        key = (str(r.get("feeder", "")), str(r.get("customer_name", "")))
        if key not in latest or r["_event_start"] > latest[key]["_event_start"]:
            latest[key] = r
    return list(latest.values())
