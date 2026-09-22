"""
PART 5 — Alokasi target curtailment feeder ke tiap pelanggan.
"""

import pandas as pd


def allocate_customer_curtailment(dr_results: dict, df_customers: pd.DataFrame, customer_name_col: str):
    results = []

    for feeder_name, r in dr_results.items():
        target = r["target_curtailment_kw"]
        if target <= 0:
            continue

        customers_in_feeder = df_customers[df_customers["FEEDER"] == feeder_name].copy()
        if customers_in_feeder.empty:
            continue

        total_power = customers_in_feeder["ACTIVE_POWER_TOTAL"].sum()
        if total_power <= 0:
            continue

        customers_in_feeder["CURTAILMENT_AMOUNT_KW"] = (
            target / total_power
        ) * customers_in_feeder["ACTIVE_POWER_TOTAL"]

        results.append(customers_in_feeder)

    if results:
        return pd.concat(results, ignore_index=True)

    return pd.DataFrame(
        columns=list(df_customers.columns) + ["CURTAILMENT_AMOUNT_KW"]
    )
