"""
PART 0 — KONFIGURASI LOKASI
Titik ganti tunggal kalau project ini dipakai untuk GI/feeder lain.
"""

# Nama file CSV default (dipakai kalau user tidak upload file sendiri).
# Sekarang cukup 1 file untuk semua GI & feeder — GI dipilih dinamis di
# sidebar dashboard berdasarkan isi kolom "GI" pada file ini.
FEEDER_DATA_FILE = "Feeder.csv"

# Kapasitas & threshold
MAX_PER_FEEDER_KW = 8500       # kW, kapasitas maksimal per feeder (10kVA dikali 0.85 PF)
TRIGGER_RATIO = 0.80          # ambang trigger (80%)
SAFE_TARGET_RATIO = 0.80      # target aman setelah curtailment

#Reward and Penalty
C_AVOIDABLE_IDR_PER_KWH = 59723   # IDR/kWh, avoided marginal generation cost (dasar insentif)
C_ENERGY_IDR_PER_KWH = 59723      # IDR/kWh, PLN energy production/purchase cost (dasar penalty)
INCENTIVE_SHARE = 1 / 3
PENALTY_RATIO = 0.80

# Data pelanggan
CUSTOMER_FILE = "DataCustomer.csv"
CUSTOMER_NAME_COL = "NAMA_PELANGGAN"
CUSTOMER_EMAIL_COL = "EMAIL"

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