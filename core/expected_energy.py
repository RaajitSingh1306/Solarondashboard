"""
Unified Expected-Energy Model (Phase 2).
Provides single authoritative calculation of expected kWh:
1. physics_kwh = POA x cap x thermal_derate (from daily GHI and ambient temp)
2. plant_pr_baseline = robust P75 of (actual / physics_kwh) over clean producing days
3. expected_kwh = physics_kwh x plant_pr_baseline
4. Fallback to peer reference yield x peer RPI if irradiance/geo is missing.
"""

import datetime
import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

try:
    from pipeline import db
    from core import irradiance, peer_group
    from engines import physics, rpi
except ImportError:
    import db
    import irradiance
    import peer_group
    import physics
    import rpi

logger = logging.getLogger(__name__)

# Plant PR baseline cache: plant_id -> P75 PR baseline (float between 0.50 and 0.95)
_PLANT_PR_BASELINES: Dict[str, float] = {}


def get_plant_pr_baseline(plant_id: str, force_recompute: bool = False) -> float:
    """
    Computes robust P75 baseline PR of actual generation vs physics expectation
    over historical clean producing days for a plant.
    """
    global _PLANT_PR_BASELINES
    if not force_recompute and plant_id in _PLANT_PR_BASELINES:
        return _PLANT_PR_BASELINES[plant_id]

    sql = """
    SELECT d.date, d.kwh, d.specific_yield, p.capacity_kwp, p.capacity_effective, p.latitude, p.longitude
    FROM daily_generation d
    JOIN plants p ON d.plant_id = p.plant_id
    WHERE d.plant_id = ?
      AND d.kwh > 0.5
      AND (d.quality_flags IS NULL OR d.quality_flags NOT LIKE '%STUCK_VALUE%')
    ORDER BY d.date DESC
    LIMIT 90
    """
    df = db.query_df(sql, [plant_id], db="analytics")
    if df.empty or len(df) < 5:
        _PLANT_PR_BASELINES[plant_id] = 0.78
        return 0.78

    pr_ratios = []
    for _, row in df.iterrows():
        cap = float(row.get("capacity_effective") or row.get("capacity_kwp") or 3.3)
        if cap <= 0:
            continue
        lat = float(row.get("latitude") or 19.07)
        lon = float(row.get("longitude") or 72.87)
        d_str = str(row["date"])
        kwh = float(row["kwh"])

        irr_info = irradiance.get_daily_irradiance_and_temp(lat, lon, d_str)
        ghi = irr_info["ghi_kwh_m2"]
        temp = irr_info["temp_c"]

        phys = physics.calculate_physics_expected_energy(
            capacity_kwp=cap,
            ghi_kwh_m2_day=ghi,
            days=1,
            ambient_temp_c=temp,
            latitude=lat,
            date_str=d_str,
        )
        phys_kwh = phys["adjusted_expected_kwh"]
        if phys_kwh > 0.1:
            ratio = kwh / phys_kwh
            if 0.20 <= ratio <= 1.20:
                pr_ratios.append(ratio)

    if pr_ratios:
        p75 = float(np.percentile(pr_ratios, 75))
        baseline = round(min(max(0.60, p75), 0.92), 3)
    else:
        baseline = 0.78

    _PLANT_PR_BASELINES[plant_id] = baseline
    return baseline


def expected_daily_kwh(plant: Dict[str, Any], date_str: str) -> Dict[str, Any]:
    """
    Computes daily expected generation (kWh) for a plant on a given date:
    1. Physics POA x capacity x thermal derate
    2. Plant fitted PR baseline
    3. Peer RPI fallback if needed
    """
    pid = str(plant.get("plant_id", ""))
    cap = float(plant.get("capacity_effective") or plant.get("capacity_kwp") or 3.3)
    if cap <= 0:
        cap = 3.3
    lat = plant.get("latitude")
    lon = plant.get("longitude")

    if lat is not None and lon is not None and abs(float(lat)) > 0.1:
        irr_info = irradiance.get_daily_irradiance_and_temp(float(lat), float(lon), date_str)
        ghi = irr_info["ghi_kwh_m2"]
        temp = irr_info["temp_c"]

        phys = physics.calculate_physics_expected_energy(
            capacity_kwp=cap,
            ghi_kwh_m2_day=ghi,
            days=1,
            ambient_temp_c=temp,
            latitude=float(lat),
            date_str=date_str,
        )
        phys_kwh = phys["adjusted_expected_kwh"]
        poa = phys["poa_irradiance"]
        thermal_loss = phys["thermal_loss_kwh"]
        baseline_pr = get_plant_pr_baseline(pid)
        exp_kwh = round(phys_kwh * baseline_pr, 2)
        model_type = "physics_fitted_pr"
    else:
        # Fallback to peer group reference yield
        p_group = peer_group.get_plant_peer_group(pid)
        ref_yield = rpi.get_peer_reference_yield(p_group["group_id"], p_group["peers"], date_str)
        if ref_yield > 0.05:
            exp_kwh = round(ref_yield * cap, 2)
            model_type = "peer_reference"
            ghi = ref_yield / 0.75
            poa = ghi
            thermal_loss = 0.0
            baseline_pr = 0.75
        else:
            ghi = 4.8
            poa = 4.8
            baseline_pr = 0.75
            exp_kwh = round(cap * ghi * baseline_pr, 2)
            model_type = "regional_default"
            thermal_loss = 0.0

    return {
        "plant_id": pid,
        "date": date_str,
        "expected_kwh": exp_kwh,
        "ghi_daily": ghi,
        "poa": poa,
        "thermal_loss_kwh": thermal_loss,
        "plant_pr_baseline": baseline_pr,
        "model_type": model_type,
    }


def expected_monthly_kwh(plant: Dict[str, Any], month_str: str, observed_days: Optional[int] = None) -> Dict[str, Any]:
    """
    Computes monthly expected generation by summing daily expected values or monthly physics.
    """
    pid = str(plant.get("plant_id", ""))
    cap = float(plant.get("capacity_effective") or plant.get("capacity_kwp") or 3.3)
    if cap <= 0:
        cap = 3.3
    lat = plant.get("latitude")
    lon = plant.get("longitude")

    try:
        y, m = [int(x) for x in month_str.split("-")]
        import calendar
        _, total_days = calendar.monthrange(y, m)
    except Exception:
        total_days = 30

    eval_days = observed_days if (observed_days and observed_days > 0) else total_days

    if lat is not None and lon is not None and abs(float(lat)) > 0.1:
        # Mid-month representative calculation or day sum
        mid_date = f"{month_str}-15"
        irr = irradiance.get_daily_irradiance_and_temp(float(lat), float(lon), mid_date)
        ghi = irr["ghi_kwh_m2"]
        temp = irr["temp_c"]

        phys = physics.calculate_physics_expected_energy(
            capacity_kwp=cap,
            ghi_kwh_m2_day=ghi,
            days=eval_days,
            ambient_temp_c=temp,
            latitude=float(lat),
            month=int(month_str[5:7]),
            date_str=mid_date,
        )
        phys_kwh = phys["adjusted_expected_kwh"]
        baseline_pr = get_plant_pr_baseline(pid)
        exp_kwh = round(phys_kwh * baseline_pr, 2)
        model = "physics_monthly"
    else:
        ghi = 4.8
        baseline_pr = 0.75
        exp_kwh = round(cap * ghi * eval_days * baseline_pr, 2)
        model = "fallback_monthly"

    return {
        "plant_id": pid,
        "month": month_str,
        "expected_kwh": exp_kwh,
        "ghi_kwh_m2_day": ghi,
        "eval_days": eval_days,
        "model_type": model,
    }
