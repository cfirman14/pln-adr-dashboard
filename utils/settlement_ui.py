"""
Bagian dashboard PLN: realisasi durasi curtailment PER PELANGGAN -> reward (insentif)
dan penalty. Dipakai oleh pages/0_Reward_dan_Penalty.py.

Alur per pelanggan (baris di tabel reward / penalty):
  - Belum disimpan : kotak jam + menit dan tombol 💾 Save.
  - Sudah disimpan : nilai tersimpan tampil read-only (kotak durasi hilang) + tombol ✏️ Edit.
  - Setelah Edit   : kotak durasi muncul lagi HANYA di baris itu (💾 Save / ✖ Cancel).

Tarif (C_avoidable, C_energy) tidak bisa diubah dari halaman ini: nilainya
ditetapkan di config.py / utils/settlement.py.
"""

import html

import streamlit as st

from utils.execution import MAX_ITERATIONS
from utils.settlement import (
    C_AVOIDABLE_IDR_PER_KWH,
    C_ENERGY_IDR_PER_KWH,
    INCENTIVE_SHARE,
    PENALTY_RATIO,
    apply_duration,
    compute_settlements,
)
from utils.sheets import get_all_settlements, upsert_settlements

FLASH_KEY = "settle_flash"

# Lebar kolom: header dan baris HARUS memakai daftar yang sama supaya sejajar.
REWARD_WIDTHS = [2.3, 1.2, 2.4, 1.2, 1.5, 1.8, 1.4]
PENALTY_WIDTHS = [2.1, 1.2, 2.4, 1.1, 1.4, 0.8, 1.7, 1.4]


def _idr(value: float) -> str:
    return f"Rp {value:,.0f}"


ROW_LINE = (
    "<hr style='margin:0.2rem 0; border:none; border-top:1px solid rgba(128,128,128,0.28);'/>"
)


def _cell(col, text: str, align: str = "left", bold: bool = False, muted: bool = False, small: bool = False) -> None:
    """Satu sel tabel (HTML kecil) supaya teks rata & angka rata kanan."""
    style = f"text-align:{align}; margin:0;"
    if bold:
        style += " font-weight:700;"
    if muted:
        style += " opacity:0.7;"
    if small:
        style += " font-size:0.85rem;"
    col.markdown(f"<div style='{style}'>{text}</div>", unsafe_allow_html=True)


def _split_duration(total_hours) -> tuple[int, int]:
    try:
        total = float(total_hours or 0)
    except (ValueError, TypeError):
        return 0, 0
    hours = int(total)
    minutes = int(round((total - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    return min(hours, 24), minutes


def _render_row(item: dict, saved_row: dict | None, requests, kind: str) -> None:
    """Satu baris pelanggan. kind: 'REWARD' atau 'PENALTY'."""
    token = item["basis_token"]
    editing = bool(st.session_state.get(f"editing_{token}"))
    input_mode = saved_row is None or editing
    is_penalty = kind == "PENALTY"

    widths = PENALTY_WIDTHS if is_penalty else REWARD_WIDTHS
    cols = st.columns(widths, vertical_alignment="center")
    i = iter(range(len(widths)))

    _cell(cols[next(i)], f"<b>{html.escape(str(item['customer_name']))}</b><br>"
                         f"<span style='opacity:0.7'>{html.escape(str(item['feeder']))}</span>")
    _cell(cols[next(i)], f"{item['power_kw']:.2f}", "right")

    # ---- kolom durasi ----
    c_t = cols[next(i)]
    if input_mode:
        dh, dm = _split_duration(saved_row["duration_hours"]) if saved_row else (0, 0)
        with c_t:
            ch, cm = st.columns(2)
            hours = ch.number_input("Hours", min_value=0, max_value=24, value=dh, step=1, key=f"dur_h_{token}",
                                    label_visibility="collapsed")
            minutes = cm.number_input("Minutes", min_value=0, max_value=59, value=dm, step=1, key=f"dur_m_{token}",
                                    label_visibility="collapsed")
        shown = apply_duration(item, hours, minutes)          # pratinjau langsung
    else:
        _cell(c_t, html.escape(str(saved_row["duration_text"])), "right")
        hours = minutes = None
        shown = saved_row

    _cell(cols[next(i)], f"{float(shown['energy_kwh']):,.2f}", "right")
    _cell(cols[next(i)], f"{float(shown['rate_idr_per_kwh']):,.0f}", "right")
    if is_penalty:
        _cell(cols[next(i)], f"{float(shown['factor']):.0%}", "right")
    amount = float(shown["amount_idr"])
    _cell(cols[next(i)], f"{_idr(amount)}" + (" <span style='opacity:0.6;font-weight:400'>(preview)</span>" if input_mode else ""),
          "right", bold=True)

    # ---- kolom aksi ----
    c_a = cols[next(i)]
    if not input_mode:
        if c_a.button("✏️ Edit", key=f"edit_{token}", use_container_width=True):
            st.session_state[f"editing_{token}"] = True
            st.rerun()
        return

    if c_a.button("💾 Save", key=f"save_{token}", type="primary", use_container_width=True):
        if hours * 60 + minutes <= 0:
            st.session_state[FLASH_KEY] = ("error", f"{item['customer_name']}: duration must be greater than 0.")
        else:
            try:
                outcome = upsert_settlements([apply_duration(item, hours, minutes)])
                verb = "updated" if outcome["updated"] else "saved"
                st.session_state[FLASH_KEY] = ("success", f"{item['customer_name']}: {verb} ({_idr(amount)}).")
                st.session_state.pop(f"editing_{token}", None)
            except KeyError as e:
                st.session_state[FLASH_KEY] = ("error", f"Google Sheets is not configured (missing config: {e}).")
            except Exception as e:
                st.session_state[FLASH_KEY] = ("error", f"Failed to save: {e}")
        st.rerun()

    if editing and c_a.button("✖ Cancel", key=f"cancel_{token}", use_container_width=True):
        st.session_state.pop(f"editing_{token}", None)
        st.rerun()


def _render_group(title: str, caption: str, items: list[dict], saved_by_key: dict, requests, kind: str) -> None:
    st.markdown(title)
    st.caption(caption)
    if not items:
        st.info("No customer is eligible yet." if kind == "REWARD" else "No customer is subject to a penalty.")
        return

    if kind == "PENALTY":
        widths = PENALTY_WIDTHS
        labels = ["Customer", "P offered, 2nd (kW)", "T (hours · minutes)", "Energy (kWh)", "C_energy (IDR/kWh)",
                  "Ratio", "Penalty (IDR)", ""]
        aligns = ["left", "right", "right", "right", "right", "right", "right", "left"]
    else:
        widths = REWARD_WIDTHS
        labels = ["Customer", "P curtailed (kW)", "T (hours · minutes)", "Energy (kWh)", "C_avoidable (IDR/kWh)",
                  "Incentive (IDR)", ""]
        aligns = ["left", "right", "right", "right", "right", "right", "left"]

    with st.container(border=True):
        for col, label, align in zip(st.columns(widths), labels, aligns):
            _cell(col, label, align, bold=True, muted=True, small=True)
        for item in items:
            st.markdown(ROW_LINE, unsafe_allow_html=True)
            _render_row(item, saved_by_key.get(item["key"]), requests, kind)


def render_settlement_section(gi_name: str, requests) -> None:
    st.subheader("Reward & Penalty Settlement")

    if requests is None:
        st.info("Customer responses are not available, so reward/penalty can't be calculated yet.")
        return
    if not requests:
        st.info("No notification has been sent yet for this substation.")
        return

    # pesan hasil aksi sebelumnya (disimpan sebelum st.rerun)
    flash = st.session_state.pop(FLASH_KEY, None)
    if flash:
        (st.success if flash[0] == "success" else st.error)(flash[1])

    st.caption(
        "Fill in the **realized curtailment duration for each customer** and press Save on that row. "
        "Saved rows are locked; use ✏️ Edit to correct a single customer. "
        "Reward only goes to customers who accepted 100% in iteration 1 (incl. auto-accept). "
        f"Penalty only applies to customers still REJECTED after iteration {MAX_ITERATIONS}."
    )
    st.caption(
        f"Rates are fixed in the script (config.py): C_avoidable = **{_idr(C_AVOIDABLE_IDR_PER_KWH)}/kWh**, "
        f"C_energy = **{_idr(C_ENERGY_IDR_PER_KWH)}/kWh**."
    )

    result = compute_settlements(requests)          # pelanggan yang berhak; durasi 0 = belum diisi
    rewards, penalties, groups = result["rewards"], result["penalties"], result["groups"]

    try:
        saved_rows = get_all_settlements(gi_name)
    except Exception as e:
        saved_rows = []
        st.warning(f"Could not read saved calculations ({e}). Saved rows can't be shown right now.")
    saved_by_key = {str(r.get("key", "")): r for r in saved_rows}

    # ---------------- Ringkasan: hanya yang SUDAH disimpan ----------------
    saved_rewards = [saved_by_key[x["key"]] for x in rewards if x["key"] in saved_by_key]
    saved_penalties = [saved_by_key[x["key"]] for x in penalties if x["key"] in saved_by_key]
    total_eligible = len(rewards) + len(penalties)
    n_saved = len(saved_rewards) + len(saved_penalties)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("🎁 Total incentive (saved)", _idr(sum(float(r["amount_idr"]) for r in saved_rewards)))
    m2.metric("⚠️ Total penalty (saved)", _idr(sum(float(r["amount_idr"]) for r in saved_penalties)))
    m3.metric("Customers saved", f"{n_saved} / {total_eligible}")
    m4.metric("Awaiting duration", total_eligible - n_saved)

    _render_group(
        "**Reward (incentive)** — accepted 100% in iteration 1",
        f"I = {INCENTIVE_SHARE:.2f} (1/3) × C_avoidable × P_curtailed × T",
        rewards, saved_by_key, requests, "REWARD",
    )
    st.write("")
    _render_group(
        f"**Penalty** — still REJECTED after iteration {MAX_ITERATIONS}",
        f"Penalty = {PENALTY_RATIO:.0%} × C_energy × P_offered,2nd × T",
        penalties, saved_by_key, requests, "PENALTY",
    )

    n_pending, n_await, n_neutral = len(groups["pending"]), len(groups["awaiting"]), len(groups["neutral"])
    st.caption(
        f"Not included — no reward & no penalty: {n_neutral} customer(s) (Accept 80%, or accepted in "
        f"iteration {MAX_ITERATIONS}); {n_await} declined in iteration 1 and not re-iterated yet; "
        f"{n_pending} still pending."
    )
