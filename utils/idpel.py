"""
IDPEL — ID unik pelanggan PLN (kolom IDPEL di DataCustomer.csv).

Nama pelanggan bisa mirip/kembar, jadi IDPEL dipakai sebagai identitas.
Modul kecil ini sengaja tidak mengimpor modul lain di utils/ supaya aman dipakai
dari notify.py maupun execution.py (menghindari impor melingkar).

Nama kolom bisa diubah dengan menambah  CUSTOMER_ID_COL = "IDPEL"  di config.py.
"""

import re

import config

ID_COL = getattr(config, "CUSTOMER_ID_COL", "IDPEL")


def clean_idpel(value) -> str:
    """Hanya digit, tanpa spasi / '.0' / 'nan'. '' kalau kosong. Contoh: 323258330020.0 -> '323258330020'."""
    s = str(value if value is not None else "").strip()
    if s.lower() in ("", "nan", "none"):
        return ""
    s = re.sub(r"\.0+$", "", s)
    return re.sub(r"\D", "", s)


def idpel_key(value) -> str:
    """Kunci pembanding: digit saja, tanpa nol di depan (Google Sheets bisa membuang nol di depan)."""
    return clean_idpel(value).lstrip("0")
