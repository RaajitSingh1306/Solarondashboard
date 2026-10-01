"""
Solaron Inverter Fault Code Correlation Engine (Phase 4, Task 16).

Correlates algorithmic FAULT_SUSPECT plant-days with hardware inverter fault codes:
- Maps vendor error codes to physical categories
- Evaluates statistical precision of anomaly/fault detection rules
- Produces ground-truth labels for machine learning model tuning
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
try:
    from pipeline import db
    from engines import status_engine
except ImportError:
    import db
    import status_engine

logger = logging.getLogger(__name__)

# Standard Hardware Fault Category Mapping
FAULT_CODE_TAXONOMY = {
    "101": "Grid Undervoltage / Outage",
    "102": "Grid Overvoltage",
    "103": "Grid Frequency Out of Range",
    "104": "Grid Disconnected (Islanding)",
    "201": "PV String Overvoltage",
    "202": "PV Insulation Resistance Fault",
    "203": "PV Ground Fault",
    "301": "Inverter Over-temperature",
    "302": "Internal Hardware Fault",
    "401": "Communication Logger Timeout",
    "402": "Meter Disconnected",
}


def correlate_fault_codes_for_date(date_str: str) -> Dict[str, Any]:
    """
    Correlate algorithmic plant-day statuses with hardware inverter snapshot error codes.
    Returns precision statistics and matched incident records.
    """
    # 1. Fetch statuses for the date
    status_df = status_engine.classify_fleet_daily_statuses(date_str)
    if status_df.empty:
        return {"date": date_str, "fault_suspects": 0, "matched_with_code": 0, "precision_pct": 0.0, "matches": []}

    suspect_pids = status_df[status_df["status_evidence"] == "FAULT_SUSPECT"]["plant_id"].tolist()
    if not suspect_pids:
        return {"date": date_str, "fault_suspects": 0, "matched_with_code": 0, "precision_pct": 100.0, "matches": []}

    # 2. Query inverter snapshots for these plants on that date
    placeholders = ",".join(["?"] * len(suspect_pids))
    sql = f"""
    SELECT plant_id, inverter_sn, fault_code, status, temperature_c, ac_power_w
    FROM inverter_snapshots
    WHERE plant_id IN ({placeholders})
      AND strftime('%Y-%m-%d', snapshot_ts) = ?
      AND fault_code IS NOT NULL AND fault_code != '' AND fault_code != '0';
    """
    params = suspect_pids + [date_str]
    snaps_df = db.query_df(sql, params, db="analytics")

    matched_pids = set(snaps_df["plant_id"].tolist()) if not snaps_df.empty else set()
    matched_count = len(matched_pids)
    total_suspects = len(suspect_pids)
    precision_pct = round((matched_count / max(total_suspects, 1)) * 100.0, 1)

    matches = []
    if not snaps_df.empty:
        for _, row in snaps_df.iterrows():
            f_code = str(row["fault_code"])
            f_desc = FAULT_CODE_TAXONOMY.get(f_code, f"Vendor Error {f_code}")
            matches.append({
                "plant_id": row["plant_id"],
                "inverter_sn": row["inverter_sn"],
                "fault_code": f_code,
                "fault_category": f_desc,
                "temperature_c": row["temperature_c"],
            })

    return {
        "date": date_str,
        "total_fault_suspects": total_suspects,
        "matched_with_hardware_fault": matched_count,
        "precision_pct": precision_pct,
        "matched_incidents": matches,
    }
