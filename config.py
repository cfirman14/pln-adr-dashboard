"""
PART 0 — KONFIGURASI LOKASI
Titik ganti tunggal kalau project ini dipakai untuk GI/feeder lain.
"""

LOCATION_NAME = "GI Garut"

# Nama feeder & nama file CSV default (dipakai kalau user tidak upload file sendiri)
FEEDER_FILES = {
    "F. Cikelet": "normalFeeder.csv",
    "F. Cipanas": "normalFeeder2.csv",
    "F. Cikopo": "normalFeeder3.csv",
}

# Kapasitas & threshold
MAX_PER_FEEDER_KW = 500       # kW, kapasitas maksimal per feeder
TRIGGER_RATIO = 0.80          # ambang trigger (80%)
SAFE_TARGET_RATIO = 0.80      # target aman setelah curtailment

# Data pelanggan
CUSTOMER_FILE = "DataCustomer.csv"
CUSTOMER_NAME_COL = "NAMA_PELANGGAN"

# --- Auto-generate: TIDAK PERLU diubah manual ---
def slugify(feeder_name: str) -> str:
    return feeder_name.lower().replace("f. ", "").replace(" ", "_")


def build_feeder_mapping(feeder_names):
    return {
        f"target_curtailment_feeder_{i}": name
        for i, name in enumerate(feeder_names, start=1)
    }


def build_program_registry(feeder_names):
    return {
        name: {
            "programID": f"prog-{slugify(name)}",
            "programName": f"PLN_ADR_{slugify(name).capitalize()}",
        }
        for name in feeder_names
    }
