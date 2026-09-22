"""
PART 1 — Baca data feeder & pelanggan.
Versi single-CSV: 1 file Feeder.csv berisi semua GI & feeder (kolom GI, Feeder),
dengan banyak baris timestamp per feeder. Sumber file bisa dari folder data/
(demo) atau upload user (tidak lagi dari Google Drive, karena Streamlit Cloud
tidak bisa mount Drive seperti Colab).
"""

import pandas as pd


def load_feeder_data(uploaded_file=None, default_path: str = "data/Feeder.csv") -> pd.DataFrame:
    """
    Baca seluruh data feeder (semua GI, semua timestamp) jadi 1 DataFrame mentah.
    Filter ke 1 GI dan ambil snapshot terakhir dilakukan di get_latest_snapshot().
    """
    source = uploaded_file if uploaded_file is not None else default_path

    df = pd.read_csv(source)
    df.columns = [col.strip() for col in df.columns]

    df["Timestamp"] = pd.to_datetime(df["Timestamp"].astype(str).str.strip())
    df["GI"] = df["GI"].astype(str).str.strip()
    df["Feeder"] = df["Feeder"].astype(str).str.strip()

    return df


def get_latest_snapshot(df: pd.DataFrame, gi_name: str) -> dict:
    """
    Ambil baris terakhir (per feeder) untuk 1 GI tertentu, dan bentuk dict
    dengan struktur SAMA seperti versi lama — supaya threshold.py,
    curtailment.py, dan openadr_events.py tidak perlu diubah sama sekali.
    """
    df_gi = df[df["GI"] == gi_name]
    if df_gi.empty:
        return {}

    idx_latest = df_gi.groupby("Feeder")["Timestamp"].idxmax()
    latest = df_gi.loc[idx_latest].sort_values("Feeder")

    feeder_data = {}
    for _, row in latest.iterrows():
        feeder_data[row["Feeder"]] = {
            "date": row["Timestamp"].strftime("%d-%m-%Y"),
            "time": row["Timestamp"].strftime("%H:%M:%S"),
            "power_active": float(row["Power Active"]),
        }
    return feeder_data


def load_customer_data(uploaded_file=None, default_path: str = "data/DataCustomer.csv"):
    source = uploaded_file if uploaded_file is not None else default_path
    df = pd.read_csv(source)
    df.columns = [col.strip() for col in df.columns]
    return df