"""
Solaron Relative Performance Index (RPI) Engine (Phase 3, Task 11).

Implements peer-relative solar generation benchmarking:
- Yf[i,d] = kWh[i,d] / kWp[i]
- ref[G,d] = median over healthy peers j in G of Yf[j,d] (producing, non-stuck)
- RPI[i,d] = Yf[i,d] / ref[G,d]
- score[i] = rolling 14-day median of RPI[i]

Cancels out solar geometry, monsoon cloud cover, and seasonal variations without pyranometers.
"""

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
try:
    from pipeline import db
    from core import peer_group
except ImportError:
    import db
    import peer_group

logger = logging.getLogger(__name__)

# Daily peer reference cache: (group_id, date) -> ref_yield
_DAILY_REF_CACHE: Dict[Tuple[str, str], float] = {}


def get_peer_reference_yield(group_id: str, peer_ids: List[str], date_str: str) -> float:
    """
    Get the median specific yield of healthy peers for a group on a given date.
    Caches results to avoid redundant database roundtrips.
    """
    cache_key = (group_id, date_str)
    if cache_key in _DAILY_REF_CACHE:
        return _DAILY_REF_CACHE[cache_key]

    yields = peer_group.get_healthy_peer_yields_for_date(peer_ids, date_str)
    if not yields or len(yields) == 0:
        _DAILY_REF_CACHE[cache_key] = 0.0
        return 0.0

    ref_val = float(np.median(yields))
    _DAILY_REF_CACHE[cache_key] = round(ref_val, 2)
    return round(ref_val, 2)


def calculate_plant_rpi_series(
    plant_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    rolling_window: int = 14,
) -> pd.DataFrame:
    """
    Compute daily RPI timeseries for a plant against its regional peer group.
    
    Returns DataFrame with:
    ['date', 'kwh', 'specific_yield', 'peer_ref_yield', 'rpi', 'rolling_rpi', 'peer_count', 'group_label']
    """
    peer_info = peer_group.get_plant_peer_group(plant_id)
    group_id = peer_info["group_id"]
    peers = peer_info["peers"]
    group_label = peer_info["label"]

    sql = """
    SELECT date, kwh, specific_yield, status, quality_flags
    FROM daily_generation
    WHERE plant_id = ?
    """
    params = [plant_id]
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    sql += " ORDER BY date ASC"

    df = db.query_df(sql, params, db="analytics")
    if df.empty:
        return pd.DataFrame()

    ref_yields = []
    rpi_values = []

    for _, row in df.iterrows():
        d_str = str(row["date"])
        sy = float(row["specific_yield"] or 0.0)
        ref = get_peer_reference_yield(group_id, peers, d_str)
        ref_yields.append(ref)

        if ref > 0.05:
            rpi = sy / ref
        elif sy <= 0.05:
            rpi = 1.0  # Whole group had zero/near-zero generation
        else:
            rpi = 1.0

        rpi_values.append(round(min(max(0.0, rpi), 3.0), 3))

    df["peer_ref_yield"] = ref_yields
    df["rpi"] = rpi_values
    df["rolling_rpi"] = df["rpi"].rolling(window=rolling_window, min_periods=3).median().round(3)
    df["rolling_rpi"] = df["rolling_rpi"].fillna(df["rpi"])
    df["peer_group"] = group_label
    df["peer_count"] = len(peers)

    return df


def classify_rpi_tier(rolling_rpi: Optional[float]) -> str:
    """Classify plant health tier based on peer-relative RPI score."""
    if rolling_rpi is None:
        return "Unknown"
    val = float(rolling_rpi)
    if val >= 0.95:
        return "Best"
    if val >= 0.80:
        return "Good"
    if val >= 0.65:
        return "Could Be Better"
    if val >= 0.35:
        return "Needs Attention"
    return "Critical"
