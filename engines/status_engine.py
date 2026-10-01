"""
Solaron Plant-Day Status Engine (Phase 4, Task 14).

Classifies the exact operational state of every plant-day based on physical evidence:
- DECOMMISSIONED: Permanently shut down or removed
- NO_DATA: Telemetry absent from API logs (distinct from true zero)
- STUCK: Frozen / cached identical readings
- LOW_LIGHT_ZERO: Zero output due to regional storm/monsoon (peers also zero)
- FAULT_SUSPECT: Zero output while >= 70% of regional peers are producing
- PRODUCING: Normal operational generation

Enables true availability computation: Availability = PRODUCING / (PRODUCING + FAULT_SUSPECT)
"""

import datetime
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd
try:
    from pipeline import db
    from core import peer_group, data_quality
except ImportError:
    import db
    import peer_group
    import data_quality

logger = logging.getLogger(__name__)


def classify_plant_day_status(
    kwh: Optional[float],
    quality_flags: Optional[str],
    peer_yields: List[float],
    is_logged: bool = True,
    operational_status: Optional[str] = "active",
) -> str:
    """
    Classify plant-day status using multi-signal evidence.
    
    Returns one of:
    'DECOMMISSIONED' | 'NO_DATA' | 'STUCK' | 'LOW_LIGHT_ZERO' | 'FAULT_SUSPECT' | 'PRODUCING'
    """
    if str(operational_status).lower() == "decommissioned":
        return "DECOMMISSIONED"

    if not is_logged or kwh is None:
        return "NO_DATA"

    if quality_flags and "STUCK_VALUE" in quality_flags:
        return "STUCK"

    kwh_val = float(kwh)
    if kwh_val > data_quality.NOISE_FLOOR_DAILY_KWH:
        return "PRODUCING"

    # Plant produced zero/noise: evaluate regional peers
    if not peer_yields or len(peer_yields) < 3:
        return "FAULT_SUSPECT"

    peer_producing = [y for y in peer_yields if y > data_quality.NOISE_FLOOR_DAILY_KWH]
    producing_peer_ratio = len(peer_producing) / len(peer_yields)

    # If >= 70% of regional peers were producing, this plant's zero is a FAULT_SUSPECT
    if producing_peer_ratio >= 0.70:
        return "FAULT_SUSPECT"
    else:
        # Most peers also produced near zero -> regional storm, heavy overcast, or grid curtailment
        return "LOW_LIGHT_ZERO"


def classify_fleet_daily_statuses(date_str: str) -> pd.DataFrame:
    """
    Classify plant-day statuses for all plants on a given date.
    Returns DataFrame: [plant_id, date, kwh, status, status_evidence]
    """
    groups = peer_group.build_fleet_peer_groups()

    sql = """
    SELECT 
        p.plant_id,
        p.operational_status,
        p.capacity_kwp,
        d.kwh,
        d.specific_yield,
        d.quality_flags
    FROM plants p
    LEFT JOIN daily_generation d ON p.plant_id = d.plant_id AND d.date = ?;
    """
    df = db.query_df(sql, [date_str], db="analytics")
    if df.empty:
        return pd.DataFrame()

    # Pre-fetch peer yields for all peer groups on this date
    group_peer_yields: Dict[str, List[float]] = {}
    for p_info in groups.values():
        gid = p_info["group_id"]
        if gid not in group_peer_yields:
            group_peer_yields[gid] = peer_group.get_healthy_peer_yields_for_date(p_info["peers"], date_str)

    statuses = []
    for _, row in df.iterrows():
        pid = str(row["plant_id"])
        p_info = groups.get(pid, {"group_id": "fleet_national", "peers": []})
        peer_ys = group_peer_yields.get(p_info["group_id"], [])

        st = classify_plant_day_status(
            kwh=row["kwh"],
            quality_flags=row["quality_flags"],
            peer_yields=peer_ys,
            is_logged=pd.notnull(row["kwh"]),
            operational_status=row["operational_status"],
        )
        statuses.append(st)

    df["status_evidence"] = statuses
    df["date"] = date_str
    return df
