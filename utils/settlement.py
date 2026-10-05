"""
PART 12 — Perhitungan reward (insentif) & penalty setelah curtailment dieksekusi.

Aturan (sesuai flowchart "Proposed PLN Automatic Demand Response Workflow"):

REWARD (insentif)
  Diberikan HANYA ke pelanggan yang menyetujui 100% di ITERASI 1:
  status ACCEPTED 100% atau ACCEPTED 100% (AUTO — tidak merespons 30 menit).
    I = 1/3 x C_avoidable x E_curtailed
    E_curtailed = P_curtailed (kW) x T (jam)

PENALTY
  Dikenakan HANYA ke pelanggan yang masih REJECTED di iterasi terakhir
  (iterasi ke-MAX_ITERATIONS). Dasar dayanya adalah target yang diminta di
  iterasi tersebut (P_offered,2nd).
    Penalty = 80% x C_energy x P_offered,2nd (kW) x T (jam)

TIDAK dapat reward dan TIDAK kena penalti:
  - Accept 80% di iterasi 1.
  - Menolak di iterasi 1 lalu menerima (berapapun, termasuk AUTO) di iterasi 2.
  - Masih PENDING, atau REJECTED di iterasi 1 yang belum di-iterasi lagi.

T = realisasi durasi curtailment yang diisi manual oleh PLN (jam + menit),
SETIAP PELANGGAN punya durasi sendiri (key = token baris dasar pelanggan itu).
Tarif (C_avoidable, C_energy), 1/3, dan 80% ditetapkan di script / config.py,
bukan diisi di halaman dashboard.

Modul ini murni perhitungan (tanpa Streamlit/Google Sheets) supaya mudah dites.
Nilai tarif bisa ditimpa dari config.py dengan menambah konstanta bernama sama.
"""

import datetime as dt

import config
from utils.execution import MAX_ITERATIONS, latest_per_customer

INCENTIVE_SHARE = getattr(config, "INCENTIVE_SHARE", 1 / 3)
PENALTY_RATIO = getattr(config, "PENALTY_RATIO", 0.80)
# Default: PLTG (avg) dari slide Week 7 (Rp 59.723/kWh). Sesuaikan dengan tarif PLN sebenarnya.
C_AVOIDABLE_IDR_PER_KWH = getattr(config, "C_AVOIDABLE_IDR_PER_KWH", 59723)
C_ENERGY_IDR_PER_KWH = getattr(config, "C_ENERGY_IDR_PER_KWH", 59723)

REWARD_STATUSES = {"ACCEPTED 100%", "ACCEPTED 100% (AUTO)"}


def duration_in_hours(hours: int, minutes: int) -> float:
    return int(hours) + int(minutes) / 60


def duration_text(hours: int, minutes: int) -> str:
    return f"{int(hours)} h {int(minutes):02d} min"


def _iteration_of(r: dict) -> int:
    try:
        return int(r.get("iteration") or 1)
    except (ValueError, TypeError):
        return 1


def _float(value) -> float:
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return 0.0


def classify(latest: list[dict]) -> dict:
    """
    Kelompokkan status TERKINI tiap pelanggan (hasil latest_per_customer):
      reward  : iterasi 1 & ACCEPTED 100% / ACCEPTED 100% (AUTO)
      penalty : REJECTED di iterasi >= MAX_ITERATIONS
      pending : masih PENDING
      awaiting: REJECTED di iterasi < MAX_ITERATIONS (belum di-iterasi lagi)
      neutral : sisanya (Accept 80%, atau menerima di iterasi 2) -> tanpa reward/penalti
    """
    groups = {"reward": [], "penalty": [], "pending": [], "awaiting": [], "neutral": []}
    for r in latest:
        status = str(r.get("status", "")).upper()
        it = _iteration_of(r)
        if status == "PENDING":
            groups["pending"].append(r)
        elif it == 1 and status in REWARD_STATUSES:
            groups["reward"].append(r)
        elif status == "REJECTED" and it >= MAX_ITERATIONS:
            groups["penalty"].append(r)
        elif status == "REJECTED":
            groups["awaiting"].append(r)
        else:
            groups["neutral"].append(r)
    return groups


def apply_duration(item: dict, hours: int, minutes: int) -> dict:
    """
    Salinan `item` (hasil compute_settlements) dengan durasi (jam, menit) tertentu:
    menghitung ulang T, energi (kWh), dan jumlah (IDR). Dipakai untuk pratinjau &
    penyimpanan per pelanggan di halaman Reward & Penalty.
    """
    T = duration_in_hours(hours, minutes)
    energy = item["power_kw"] * T
    out = dict(item)
    out.update({
        "duration_hours": round(T, 4),
        "duration_text": duration_text(hours, minutes),
        "energy_kwh": round(energy, 2),
        "amount_idr": round(item["factor"] * item["rate_idr_per_kwh"] * energy, 2),
        "calculated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    })
    return out


def compute_settlements(
    requests: list[dict],
    durations: dict | None = None,
    c_avoidable: float = C_AVOIDABLE_IDR_PER_KWH,
    c_energy: float = C_ENERGY_IDR_PER_KWH,
) -> dict:
    """
    Hitung reward & penalty dari seluruh riwayat request (1 GI).

    durations: {token_baris_dasar: (jam, menit)} — durasi realisasi PER PELANGGAN.
               Pelanggan yang tidak ada di dict dianggap 0 jam 0 menit (jumlah = 0).
    Return {"rewards": [...], "penalties": [...], "groups": {...}}.
    Tiap item berisi semua angka yang dipakai (untuk ditampilkan & disimpan).
    """
    durations = durations or {}
    groups = classify(latest_per_customer(requests))
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def base(r: dict, kind: str, power_kw: float, rate: float, factor: float, formula: str) -> dict:
        hours, minutes = durations.get(r.get("token", ""), (0, 0))
        item = {
            "key": f"{kind}:{r.get('token', '')}",
            "calculated_at": now,
            "type": kind,
            "gi": r.get("gi", ""),
            "feeder": r.get("feeder", ""),
            "customer_name": r.get("customer_name", ""),
            "email": r.get("email", ""),
            "basis_token": r.get("token", ""),
            "iteration": _iteration_of(r),
            "power_kw": round(power_kw, 2),
            "rate_idr_per_kwh": rate,
            "factor": factor,                      # tidak dibulatkan: 1/3 harus tetap tepat
            "formula": formula,
        }
        return apply_duration(item, hours, minutes)

    rewards = []
    for r in groups["reward"]:
        power = _float(r.get("responded_kw")) or _float(r.get("target_curtailment_kw"))
        rewards.append(base(r, "REWARD", power, c_avoidable, INCENTIVE_SHARE,
                            "1/3 x C_avoidable x P_curtailed x T"))

    penalties = []
    for r in groups["penalty"]:
        power = _float(r.get("target_curtailment_kw"))   # P_offered,2nd = target di iterasi terakhir
        penalties.append(base(r, "PENALTY", power, c_energy, PENALTY_RATIO,
                              "80% x C_energy x P_offered,2nd x T"))

    return {"rewards": rewards, "penalties": penalties, "groups": groups}
