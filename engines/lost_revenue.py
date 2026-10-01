"""
Solaron Lost Energy & Revenue at Risk Engine (Phase 4, Task 15).

Translates operational downtime and performance shortfalls into actionable financial metrics:
- Lost kWh on FAULT_SUSPECT days
- Revenue at Risk (lost kWh * tariff)
- Evidence-based loss decomposition (Outage, Soiling, Weather, Residual)
- Plant operational availability percentage
"""

import logging
from typing import Any, Dict, List, Optional
import pandas as pd
from config import settings
try:
    from core import baseline
    from engines import status_engine
except ImportError:
    import baseline
    import status_engine

logger = logging.getLogger(__name__)


def calculate_plant_lost_revenue(
    plant_id: str,
    capacity_kwp: float,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    tariff_inr: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Calculate energy shortfall, loss breakdown, and financial revenue at risk.
    """
    if tariff_inr is None:
        tariff_inr = getattr(settings, "price_per_unit", 14.0)

    # 1. Fetch expected vs actual energy from peer-relative baseline engine
    exp_df = baseline.calculate_peer_expected_energy(
        plant_id, capacity_kwp=capacity_kwp, start_date=start_date, end_date=end_date
    )
    if exp_df.empty:
        return {
            "plant_id": plant_id,
            "total_expected_kwh": 0.0,
            "total_actual_kwh": 0.0,
            "total_shortfall_kwh": 0.0,
            "revenue_at_risk_inr": 0.0,
            "availability_pct": 100.0,
            "producing_days": 0,
            "fault_days": 0,
            "loss_breakdown": {
                "outage_kwh": 0.0,
                "soiling_kwh": 0.0,
                "residual_kwh": 0.0,
            },
        }

    # 2. Identify soiling events
    soiling_events = baseline.detect_soiling_sawtooth(exp_df)
    soiling_dates = set()
    for ev in soiling_events:
        s_date = ev["start_date"]
        r_date = ev["reset_date"]
        mask = (exp_df["date"] >= s_date) & (exp_df["date"] <= r_date)
        soiling_dates.update(exp_df[mask]["date"].tolist())

    total_expected = round(float(exp_df["expected_kwh"].sum()), 2)
    total_actual = round(float(exp_df["kwh"].sum()), 2)
    total_shortfall = round(max(0.0, total_expected - total_actual), 2)

    # Decompose losses by plant-day state
    outage_kwh = 0.0
    soiling_kwh = 0.0
    producing_days = 0
    fault_days = 0

    for _, row in exp_df.iterrows():
        d_str = row["date"]
        kwh = float(row["kwh"] or 0.0)
        lost = float(row["lost_kwh"] or 0.0)

        if kwh <= 0.05:
            # Full outage day
            outage_kwh += lost
            fault_days += 1
        else:
            producing_days += 1
            if d_str in soiling_dates:
                soiling_kwh += lost

    residual_kwh = round(max(0.0, total_shortfall - outage_kwh - soiling_kwh), 2)
    outage_kwh = round(min(outage_kwh, total_shortfall), 2)
    soiling_kwh = round(min(soiling_kwh, total_shortfall - outage_kwh), 2)

    # Availability
    total_active_days = producing_days + fault_days
    avail_pct = round((producing_days / max(total_active_days, 1)) * 100.0, 1)

    revenue_at_risk = round(total_shortfall * tariff_inr, 2)
    outage_revenue = round(outage_kwh * tariff_inr, 2)
    soiling_revenue = round(soiling_kwh * tariff_inr, 2)

    return {
        "plant_id": plant_id,
        "tariff_inr": tariff_inr,
        "total_expected_kwh": total_expected,
        "total_actual_kwh": total_actual,
        "total_shortfall_kwh": total_shortfall,
        "revenue_at_risk_inr": revenue_at_risk,
        "availability_pct": avail_pct,
        "producing_days": producing_days,
        "fault_days": fault_days,
        "loss_breakdown": {
            "outage_kwh": outage_kwh,
            "outage_revenue_inr": outage_revenue,
            "soiling_kwh": soiling_kwh,
            "soiling_revenue_inr": soiling_revenue,
            "residual_kwh": residual_kwh,
            "residual_revenue_inr": round(residual_kwh * tariff_inr, 2),
        },
    }
