"""
Solaron Plant Escalation Categorizer Engine.

Classifies every active plant daily into one of 6 operational categories:
1. ALL_FINE: actual_kwh >= 0.90 * baseline_kwh
2. AVERAGE: 0.70 <= ratio < 0.90
3. CRITICAL_PERF: ratio < 0.70 (and plant is online)
4. OFFLINE: Missing telemetry or offline status on classification date
5. INACTIVE: Consecutive zero-generation or offline days >= 7
6. PLANT_CRITICAL: Inverter snapshot fault code detected or safety hazard

Baseline Strategy:
Uses each plant's own 30-day rolling median of historical generation (absorbs orientation,
shading, capacity differences). Falls back to capacity_kwp * 4.0 if < 14 days of history.
"""

import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

try:
    from pipeline import db
except ImportError:
    import db

logger = logging.getLogger(__name__)

INACTIVE_DAYS_THRESHOLD = 7
OFFLINE_HOURS_THRESHOLD = 4
MIN_BASELINE_HISTORY_DAYS = 14
ASSUMED_SUN_HOURS = 4.0


def get_plant_baseline(plant_id: str, before_date: Optional[str] = None) -> Tuple[float, str]:
    """
    Computes baseline kWh for a plant.
    Primary: 30-day rolling median of the plant's own historical kWh.
    Fallback: capacity_kwp * 4.0 sun-hours if < 14 days of historical data.
    """
    if not before_date:
        before_date = datetime.date.today().isoformat()

    sql = """
    SELECT kwh FROM daily_generation
    WHERE plant_id = ? AND date < ? AND kwh IS NOT NULL AND kwh > 0.1
    ORDER BY date DESC
    LIMIT 30;
    """
    df = db.query_df(sql, [plant_id, before_date], db="analytics")

    if not df.empty and len(df) >= MIN_BASELINE_HISTORY_DAYS:
        kwh_values = df["kwh"].astype(float).tolist()
        median_kwh = float(np.median(kwh_values))
        if median_kwh > 0.1:
            return round(median_kwh, 2), "30_day_median"

    # Fallback to capacity * assumed sun hours
    plant_df = db.query_df(
        "SELECT capacity_kwp, capacity_effective FROM plants WHERE plant_id = ?",
        [plant_id],
        db="analytics"
    )
    cap = 3.0  # default residential fallback
    if not plant_df.empty:
        c_eff = plant_df.iloc[0].get("capacity_effective")
        c_kwp = plant_df.iloc[0].get("capacity_kwp")
        if pd.notnull(c_eff) and float(c_eff) > 0:
            cap = float(c_eff)
        elif pd.notnull(c_kwp) and float(c_kwp) > 0:
            cap = float(c_kwp)

    return round(cap * ASSUMED_SUN_HOURS, 2), "capacity_fallback"


def count_consecutive_zero_days(plant_id: str, up_to_date: str) -> int:
    """
    Counts consecutive zero or missing/offline generation days up to `up_to_date`.
    """
    sql = """
    SELECT date, kwh, status FROM daily_generation
    WHERE plant_id = ? AND date <= ?
    ORDER BY date DESC
    LIMIT 30;
    """
    df = db.query_df(sql, [plant_id, up_to_date], db="analytics")
    if df.empty:
        return 0

    zero_count = 0
    for _, row in df.iterrows():
        kwh = row.get("kwh")
        status = str(row.get("status") or "").lower()
        if pd.isnull(kwh) or float(kwh or 0.0) <= 0.1 or status == "offline":
            zero_count += 1
        else:
            break
    return zero_count


def get_plant_fault_indicator(plant_id: str, date_str: str) -> Optional[str]:
    """
    Checks if any active hardware fault code was logged for the plant on date_str.
    """
    sql = """
    SELECT fault_code, status FROM inverter_snapshots
    WHERE plant_id = ? AND strftime('%Y-%m-%d', snapshot_ts) = ?
      AND fault_code IS NOT NULL AND fault_code != '' AND fault_code != '0'
    ORDER BY snapshot_ts DESC
    LIMIT 1;
    """
    df = db.query_df(sql, [plant_id, date_str], db="analytics")
    if not df.empty:
        return str(df.iloc[0]["fault_code"])
    return None


def categorize_plant(plant_id: str, date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Classifies a plant on a given date into one of the 6 categories.
    
    Returns metadata dictionary including:
    - category: ALL_FINE | AVERAGE | CRITICAL_PERF | OFFLINE | INACTIVE | PLANT_CRITICAL
    - actual_kwh, baseline_kwh, ratio, fault_code, consecutive_zero_days, reason
    """
    if not date_str:
        date_str = datetime.date.today().isoformat()

    # 1. Check hardware fault code
    fault_code = get_plant_fault_indicator(plant_id, date_str)
    if fault_code:
        baseline, b_src = get_plant_baseline(plant_id, date_str)
        return {
            "plant_id": plant_id,
            "date": date_str,
            "category": "PLANT_CRITICAL",
            "actual_kwh": 0.0,
            "baseline_kwh": baseline,
            "ratio": 0.0,
            "fault_code": fault_code,
            "consecutive_zero_days": 0,
            "baseline_source": b_src,
            "reason": f"Hardware inverter fault code {fault_code} detected",
        }

    # 2. Check consecutive zero / inactive days
    consecutive_zeros = count_consecutive_zero_days(plant_id, date_str)
    if consecutive_zeros >= INACTIVE_DAYS_THRESHOLD:
        baseline, b_src = get_plant_baseline(plant_id, date_str)
        return {
            "plant_id": plant_id,
            "date": date_str,
            "category": "INACTIVE",
            "actual_kwh": 0.0,
            "baseline_kwh": baseline,
            "ratio": 0.0,
            "fault_code": None,
            "consecutive_zero_days": consecutive_zeros,
            "baseline_source": b_src,
            "reason": f"Zero generation / offline for {consecutive_zeros} consecutive days",
        }

    # 3. Retrieve today's daily record
    daily_df = db.query_df(
        "SELECT kwh, status FROM daily_generation WHERE plant_id = ? AND date = ?",
        [plant_id, date_str],
        db="analytics"
    )

    is_offline = False
    today_kwh: Optional[float] = None
    if daily_df.empty:
        is_offline = True
    else:
        row = daily_df.iloc[0]
        st = str(row.get("status") or "").lower()
        kwh_val = row.get("kwh")
        if st == "offline" or pd.isnull(kwh_val):
            is_offline = True
        else:
            today_kwh = float(kwh_val)

    baseline, b_src = get_plant_baseline(plant_id, date_str)

    if is_offline or today_kwh is None:
        return {
            "plant_id": plant_id,
            "date": date_str,
            "category": "OFFLINE",
            "actual_kwh": 0.0,
            "baseline_kwh": baseline,
            "ratio": 0.0,
            "fault_code": None,
            "consecutive_zero_days": consecutive_zeros,
            "baseline_source": b_src,
            "reason": "Plant telemetry missing or logged as offline",
        }

    # 4. Performance Ratio Assessment with Peer RPI Weather-Awareness
    ratio = (today_kwh / baseline) if baseline > 0 else 0.0
    ratio_round = round(ratio, 3)

    # Cross-check peer RPI for that day to avoid false alarms on cloudy days
    try:
        from core import peer_group
        from engines import rpi

        p_info = peer_group.get_plant_peer_group(plant_id)
        peer_ref = rpi.get_peer_reference_yield(p_info["group_id"], p_info["peers"], date_str)
        plant_df = db.query_df(
            "SELECT capacity_kwp, capacity_effective FROM plants WHERE plant_id = ?",
            [plant_id],
            db="analytics"
        )
        cap = 3.3
        if not plant_df.empty:
            cap = float(plant_df.iloc[0].get("capacity_effective") or plant_df.iloc[0].get("capacity_kwp") or 3.3)
        plant_sy = (today_kwh / cap) if cap > 0 else 0.0
        daily_rpi = round(plant_sy / peer_ref, 2) if peer_ref > 0.05 else None
    except Exception:
        daily_rpi = None

    # Weather-aware categorization:
    # If ratio >= 0.90 -> ALL_FINE.
    # If ratio is lower due to cloudy weather (peer_ref also dropped and daily_rpi >= 0.85) -> ALL_FINE
    if ratio >= 0.90 or (daily_rpi is not None and daily_rpi >= 0.85 and ratio >= 0.50):
        cat = "ALL_FINE"
        reason = f"Generation at {int(ratio*100)}% of baseline" + (f" (Peer RPI: {daily_rpi})" if daily_rpi else "")
    elif ratio >= 0.70 or (daily_rpi is not None and daily_rpi >= 0.70 and ratio >= 0.40):
        cat = "AVERAGE"
        reason = f"Generation at {int(ratio*100)}% of baseline (mild underperformance)"
    else:
        cat = "CRITICAL_PERF"
        reason = f"Severe underperformance: {int(ratio*100)}% of baseline"

    return {
        "plant_id": plant_id,
        "date": date_str,
        "category": cat,
        "actual_kwh": round(today_kwh, 2),
        "baseline_kwh": baseline,
        "ratio": ratio_round,
        "fault_code": None,
        "consecutive_zero_days": consecutive_zeros,
        "baseline_source": b_src,
        "reason": reason,
    }


def categorize_all_plants(date_str: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Runs categorization for all active plants in the fleet on date_str.
    """
    if not date_str:
        date_str = datetime.date.today().isoformat()

    plants = db.get_plants(include_decommissioned=False)
    results = []
    for p in plants:
        pid = str(p.get("plant_id"))
        try:
            res = categorize_plant(pid, date_str)
            results.append(res)
        except Exception as e:
            logger.warning("Failed to categorize plant %s: %s", pid, e)
    return results
