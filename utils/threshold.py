"""
Threshold check dan DR trigger + target curtailment.
"""


def check_status(power_value: float, max_value: float, trigger_ratio: float = 0.80):
    loading_pct = (power_value / max_value) * 100
    status = "TRIGGER" if loading_pct >= trigger_ratio * 100 else "NORMAL"
    return status, loading_pct


def run_threshold_check(feeder_data: dict, max_per_feeder: float, trigger_ratio: float):
    for data in feeder_data.values():
        status, loading_pct = check_status(data["power_active"], max_per_feeder, trigger_ratio)
        data["status"] = status
        data["loading_pct"] = loading_pct

    total_power_active = sum(d["power_active"] for d in feeder_data.values())
    n_feeder = len(feeder_data)
    max_total = max_per_feeder * n_feeder
    total_status, total_loading_pct = check_status(total_power_active, max_total, trigger_ratio)

    return {
        "total_power_active": total_power_active,
        "max_total": max_total,
        "total_status": total_status,
        "total_loading_pct": total_loading_pct,
    }


def run_dr_trigger_check(feeder_data: dict, max_per_feeder: float, trigger_ratio: float, safe_target_ratio: float):
    safe_target_level = max_per_feeder * safe_target_ratio
    dr_results = {}

    for feeder_name, data in feeder_data.items():
        power_value = data["power_active"]
        status, loading_pct = check_status(power_value, max_per_feeder, trigger_ratio)

        if status == "TRIGGER":
            target_curtailment = max(power_value - safe_target_level, 0)
        else:
            target_curtailment = 0.0

        dr_results[feeder_name] = {
            "power_active": power_value,
            "dr_status": status,
            "loading_pct": loading_pct,
            "target_curtailment_kw": target_curtailment,
        }

    target_curtailment_total = sum(r["target_curtailment_kw"] for r in dr_results.values())
    return dr_results, target_curtailment_total
