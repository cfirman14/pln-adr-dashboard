"""
PART 1 — Baca data feeder & pelanggan.
Versi Streamlit: sumber file bisa dari folder data/ (demo) atau upload user
(tidak lagi dari Google Drive, karena Streamlit Cloud tidak bisa mount Drive
seperti Colab).
"""

import pandas as pd


def load_feeder_data(feeder_files: dict, uploaded_files: dict | None = None, data_dir: str = "data"):
    """
    feeder_files: {nama_feeder: nama_file_default}
    uploaded_files: {nama_feeder: file_object_dari_streamlit} (opsional)
    """
    feeder_data = {}

    for feeder_name, filename in feeder_files.items():
        if uploaded_files and uploaded_files.get(feeder_name) is not None:
            source = uploaded_files[feeder_name]
        else:
            source = f"{data_dir}/{filename}"

        df = pd.read_csv(source, sep=";")
        df.columns = [col.strip() for col in df.columns]
        df["Timestamp"] = pd.to_datetime(df["Timestamp"].str.strip())

        latest = df.iloc[-1]
        feeder_data[feeder_name] = {
            "date": latest["Timestamp"].strftime("%d-%m-%Y"),
            "time": latest["Timestamp"].strftime("%H:%M:%S"),
            "power_active": float(latest["Power Active"]),
        }

    return feeder_data


def load_customer_data(uploaded_file=None, default_path: str = "data/DataCustomer.csv"):
    source = uploaded_file if uploaded_file is not None else default_path
    df = pd.read_csv(source)
    df.columns = [col.strip() for col in df.columns]
    return df
