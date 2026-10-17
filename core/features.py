"""
Solaron Feature Store Engine (Phase 1, Task: Data Foundation).
Builds and populates plant_day_features table:
- kwh, specific_yield (on effective capacity), day_status, quality_ok
- peer_ref_yield, rpi, rolling 7/14/30-day RPI medians
- ghi_daily, poa, expected_kwh
- telemetry gap flags
"""

import datetime
import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

try:
    from pipeline import db
    from core import expected_energy, peer_group
    from engines import rpi, status_engine
except ImportError:
    import db
    import expected_energy
    import peer_group
    import rpi
    import status_engine

logger = logging.getLogger(__name__)


def build_features_for_period(
    date_or_month: str,
    plant_ids: Optional[List[str]] = None,
) -> int:
    """
    Builds and upserts plant_day_features records for a date ('YYYY-MM-DD') or month ('YYYY-MM').
    Vectorised with single SQL pulls and pandas operations.
    """
    db.init_db()

    # Determine date condition
    if len(date_or_month) == 10:
        date_cond = "d.date = ?"
        params = [date_or_month]
    else:
        date_cond = "substr(d.date, 1, 7) = ?"
        params = [date_or_month[:7]]

    plant_filter = ""
    if plant_ids:
        placeholders = ",".join(["?"] * len(plant_ids))
        plant_filter = f" AND d.plant_id IN ({placeholders})"
        params.extend(plant_ids)

    sql = f"""
    SELECT 
        d.plant_id,
        d.date,
        d.kwh,
        d.specific_yield,
        d.status as daily_status,
        d.quality_flags,
        p.capacity_kwp,
        p.capacity_effective,
        p.capacity_suspect,
        p.latitude,
        p.longitude,
        p.operational_status
    FROM daily_generation d
    JOIN plants p ON d.plant_id = p.plant_id
    WHERE {date_cond} {plant_filter}
    ORDER BY d.date ASC, d.plant_id ASC
    """
    df = db.query_df(sql, params, db="analytics")
    if df.empty:
        return 0

    fleet_groups = peer_group.build_fleet_peer_groups()
    unique_dates = df["date"].dropna().unique()

    # Precompute daily peer references per group for affected dates
    daily_group_refs: Dict[Tuple[str, str], float] = {}
    group_map = {info["group_id"]: info["peers"] for info in fleet_groups.values()}
    for gid, peers in group_map.items():
        for d in unique_dates:
            daily_group_refs[(gid, d)] = rpi.get_peer_reference_yield(gid, peers, d)

    records = []
    # Process rows
    for _, row in df.iterrows():
        pid = str(row["plant_id"])
        d_str = str(row["date"])
        kwh = float(row["kwh"] or 0.0)
        nom_cap = float(row["capacity_kwp"] or 3.3)
        eff_cap = float(row.get("capacity_effective") or nom_cap)
        is_suspect = bool(row.get("capacity_suspect"))
        cap = eff_cap if (is_suspect or eff_cap != nom_cap) and eff_cap > 0 else nom_cap
        if cap <= 0:
            cap = 3.3

        sy = round(kwh / cap, 3)

        q_flags = str(row.get("quality_flags") or "")
        quality_ok = 0 if ("STUCK_VALUE" in q_flags or "SY_IMPOSSIBLE" in q_flags) else 1

        p_info = fleet_groups.get(pid, {"group_id": "fleet_national", "peers": []})
        gid = p_info["group_id"]
        peer_ref = daily_group_refs.get((gid, d_str), 0.0)

        # RPI
        if peer_ref > 0.05:
            rpi_val = round(min(max(0.0, sy / peer_ref), 3.0), 3)
        else:
            rpi_val = 1.0

        # Day status
        peer_yields = [peer_ref] if peer_ref > 0 else []
        day_st = status_engine.classify_plant_day_status(
            kwh=kwh,
            quality_flags=q_flags,
            peer_yields=peer_yields,
            is_logged=True,
            operational_status=row.get("operational_status", "active"),
        )

        # Expected energy & irradiance
        plant_dict = {
            "plant_id": pid,
            "capacity_kwp": nom_cap,
            "capacity_effective": cap,
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
        }
        exp_info = expected_energy.expected_daily_kwh(plant_dict, d_str)

        records.append({
            "plant_id": pid,
            "date": d_str,
            "kwh": round(kwh, 2),
            "specific_yield": sy,
            "day_status": day_st,
            "quality_ok": quality_ok,
            "peer_ref_yield": peer_ref,
            "rpi": rpi_val,
            "rpi_7d_median": rpi_val,   # Updated in rolling step below
            "rpi_14d_median": rpi_val,
            "rpi_30d_median": rpi_val,
            "ghi_daily": exp_info.get("ghi_daily"),
            "poa": exp_info.get("poa"),
            "expected_kwh": exp_info.get("expected_kwh"),
            "is_telemetry_gap": 1 if day_st in ("NO_DATA", "INSUFFICIENT_PEERS") else 0,
        })

    feat_df = pd.DataFrame(records)
    # Rolling medians per plant
    feat_df["rpi_7d_median"] = feat_df.groupby("plant_id")["rpi"].transform(lambda s: s.rolling(7, min_periods=1).median().round(3))
    feat_df["rpi_14d_median"] = feat_df.groupby("plant_id")["rpi"].transform(lambda s: s.rolling(14, min_periods=1).median().round(3))
    feat_df["rpi_30d_median"] = feat_df.groupby("plant_id")["rpi"].transform(lambda s: s.rolling(30, min_periods=1).median().round(3))

    upsert_rows = feat_df.to_dict(orient="records")
    return db.upsert_plant_day_features(upsert_rows)


def get_plant_features(plant_id: str, date_str: str) -> Optional[Dict[str, Any]]:
    """Retrieves stored feature vector for a plant on a given date."""
    sql = "SELECT * FROM plant_day_features WHERE plant_id = ? AND date = ?"
    df = db.query_df(sql, [plant_id, date_str], db="analytics")
    if df.empty:
        return None
    return df.iloc[0].to_dict()
