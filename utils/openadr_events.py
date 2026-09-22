"""
PART 7 — Bungkus target curtailment per pelanggan jadi event OpenADR 3.1.
Simulasi struktural: JSON valid sesuai OpenADR 3.1 Definitions,
belum benar-benar POST ke server VTN sungguhan.
"""

import uuid
from datetime import datetime, timezone


def build_openadr_event_customer(customer_name, feeder_label, curtailment_kw, program_registry, current_datetime=None):
    if current_datetime is None:
        current_datetime = datetime.now(timezone.utc)

    program_info = program_registry[feeder_label]
    event_id = str(uuid.uuid4())[:8]
    setpoint_value = round(curtailment_kw, 2)

    return {
        "objectType": "EVENT",
        "id": event_id,
        "createdDateTime": current_datetime.isoformat(),
        "eventName": f"ADR_event_{customer_name}_{current_datetime.strftime('%Y%m%d%H%M')}".replace(" ", "_"),
        "programID": program_info["programID"],
        "priority": 1,
        "targets": [customer_name],
        "payloadDescriptors": [{"payloadType": "DISPATCH_SETPOINT", "units": "KW"}],
        "intervalPeriod": {"start": current_datetime.isoformat(), "duration": "PT30M"},
        "intervals": [
            {"id": 0, "payloads": [{"type": "DISPATCH_SETPOINT", "values": [setpoint_value]}]}
        ],
    }


def build_all_events(df_customer_curtailment, customer_name_col, program_registry):
    current_datetime = datetime.now(timezone.utc)
    events = []

    for _, row in df_customer_curtailment.iterrows():
        curtailment_kw = row["CURTAILMENT_AMOUNT_KW"]
        if curtailment_kw <= 0:
            continue
        events.append(
            build_openadr_event_customer(
                customer_name=row[customer_name_col],
                feeder_label=row["FEEDER"],
                curtailment_kw=curtailment_kw,
                program_registry=program_registry,
                current_datetime=current_datetime,
            )
        )

    return events
