"""
Solaron Standard Metrics & KPI Specification Engine (Phase 1, Task 5).

Single source of truth for all solar engineering formulas, physical bounds,
units, confidence indicators, and edge case handling across the Solaron fleet.

Adheres to IEC 61724 Standard for Photovoltaic System Performance Monitoring.
"""

import math
from typing import Any, Dict, Optional, Tuple, Union
from config import settings
try:
    from core import data_quality
except ImportError:
    import data_quality

# Metric Catalog with complete audit metadata
METRIC_CATALOG: Dict[str, Dict[str, Any]] = {
    "specific_yield": {
        "name": "Specific Yield",
        "symbol": "Y_f",
        "standard": "IEC 61724",
        "unit": "kWh/kWp",
        "formula": "E_actual / P_peak",
        "description": "Total generated electrical energy normalized by installed DC peak capacity.",
        "bounds_daily": (0.0, data_quality.MAX_DAILY_YIELD_KWH_KWP),
        "bounds_monthly": (0.0, data_quality.MAX_MONTHLY_YIELD_KWH_KWP),
        "edge_cases": "If capacity <= 0 or kwh is negative, returns None/0.0.",
    },
    "yield_per_day": {
        "name": "Yield Per Day",
        "symbol": "Y_d",
        "standard": "Solaron Standard",
        "unit": "kWh/kWp/day",
        "formula": "E_actual / (P_peak * days_elapsed)",
        "description": "Average daily specific generation rate across active elapsed days in the period.",
        "bounds_daily": (0.0, data_quality.MAX_DAILY_YIELD_KWH_KWP),
        "bounds_monthly": (0.0, data_quality.MAX_DAILY_YIELD_KWH_KWP),
        "edge_cases": "Clamped to physical maximum solar insolation limit (8.0 kWh/kWp/day in India).",
    },
    "pr_pct": {
        "name": "Performance Ratio",
        "symbol": "PR",
        "standard": "IEC 61724",
        "unit": "%",
        "formula": "(E_actual / (P_peak * GHI * days)) * 100",
        "description": "Overall solar system efficiency relative to theoretical energy available from insolation.",
        "bounds": (0.0, 150.0),
        "edge_cases": "Values > 100% indicate underestimated GHI, oversized DC array, or faulty capacity.",
    },
    "cuf_pct": {
        "name": "Capacity Utilisation Factor",
        "symbol": "CUF",
        "standard": "MNRE / CEA Standard",
        "unit": "%",
        "formula": "(E_actual / (P_peak * hours_in_period)) * 100",
        "description": "Ratio of actual energy produced to the theoretical energy if running at 100% capacity 24/7.",
        "bounds": (0.0, 35.0),
        "edge_cases": "In India solar conditions, annual CUF is typically 15% to 22%; peak month <= 30%.",
    },
    "rpi": {
        "name": "Relative Performance Index",
        "symbol": "RPI",
        "standard": "Solaron Peer-Relative (Plan 2)",
        "unit": "ratio",
        "formula": "Y_f(plant, day) / median(Y_f(healthy_peers, day))",
        "description": "Ratio of plant specific yield to median specific yield of healthy regional peers.",
        "bounds": (0.0, 2.0),
        "edge_cases": "Requires >= 5 healthy peers. Cancels cloud/monsoon weather noise without pyranometers.",
    },
    "revenue_inr": {
        "name": "Financial Revenue",
        "symbol": "Rev",
        "standard": "Net Metering Tariff",
        "unit": "INR",
        "formula": "E_actual * Tariff_per_kWh",
        "description": "Financial savings / revenue generated based on customer net-metering tariff.",
        "bounds": (0.0, 10_000_000.0),
        "edge_cases": "Defaults to settings.price_per_unit (14.0 INR/kWh). Cannot be negative.",
    },
    "co2_saved_kg": {
        "name": "Avoided Carbon Emissions",
        "symbol": "CO2",
        "standard": "CEA Baseline Database v20",
        "unit": "kg CO2",
        "formula": "E_actual * 0.82",
        "description": "Greenhouse gas emissions avoided using Indian grid average carbon emission intensity factor.",
        "bounds": (0.0, 10_000_000.0),
        "edge_cases": "Clamped to zero for negative generation.",
    },
    "plant_availability_pct": {
        "name": "Plant Availability",
        "symbol": "A_plant",
        "standard": "IEEE 762",
        "unit": "%",
        "formula": "(producing_days / (producing_days + fault_suspect_days)) * 100",
        "description": "Operational uptime percentage excluding grid outages and scheduled maintenance.",
        "bounds": (0.0, 100.0),
        "edge_cases": "Zero-divided handled gracefully (returns 100% if no downtime logged).",
    },
}


def compute_specific_yield(kwh: Optional[float], capacity_kwp: Optional[float], is_daily: bool = False) -> Optional[float]:
    """Calculate specific yield: E_actual / P_peak (kWh/kWp)."""
    return data_quality.recompute_specific_yield(kwh, capacity_kwp, is_daily=is_daily)


def compute_yield_per_day(kwh: Optional[float], capacity_kwp: Optional[float], days: int = 1) -> Optional[float]:
    """Calculate yield per day: E_actual / (P_peak * days) (kWh/kWp/day)."""
    return data_quality.compute_yield_per_day(kwh, capacity_kwp, days=days)


def compute_cuf(kwh: Optional[float], capacity_kwp: Optional[float], hours: Optional[int] = None) -> Optional[float]:
    """Calculate Capacity Utilisation Factor: (kwh / (kwp * hours)) * 100 (%)."""
    if kwh is None or capacity_kwp is None or capacity_kwp <= 0:
        return None
    if hours is None or hours <= 0:
        hours = 24 * 30
    kwh_clean = max(0.0, float(kwh))
    cuf_val = (kwh_clean / (float(capacity_kwp) * float(hours))) * 100.0
    return round(min(cuf_val, 35.0), 2)


def compute_pr(kwh: Optional[float], capacity_kwp: Optional[float], ghi: Optional[float], days: Optional[int]) -> Optional[float]:
    """Calculate Performance Ratio: (E / (P_peak * GHI * days)) * 100 (%)."""
    if kwh is None or capacity_kwp is None or ghi is None or days is None:
        return None
    try:
        kwh_f = max(0.0, float(kwh))
        cap_f = float(capacity_kwp)
        ghi_f = float(ghi)
        days_i = int(days)
    except (ValueError, TypeError):
        return None

    if cap_f <= 0 or ghi_f <= 0 or days_i <= 0:
        return None

    expected = cap_f * ghi_f * days_i
    if expected <= 0:
        return None
    return round((kwh_f / expected) * 100.0, 2)


def compute_rpi(plant_specific_yield: Optional[float], peer_median_specific_yield: Optional[float]) -> Optional[float]:
    """Calculate Relative Performance Index: Yf(plant) / Yf(peer_median)."""
    if plant_specific_yield is None or peer_median_specific_yield is None:
        return None
    if peer_median_specific_yield <= 0.05:
        return 1.0 if plant_specific_yield <= 0.05 else 2.0
    rpi = float(plant_specific_yield) / float(peer_median_specific_yield)
    return round(min(max(0.0, rpi), 3.0), 3)


def compute_revenue(kwh: Optional[float], tariff_inr: Optional[float] = None) -> Optional[float]:
    """Calculate revenue in INR. Defaults to settings.price_per_unit."""
    if kwh is None:
        return None
    if tariff_inr is None:
        tariff_inr = getattr(settings, "price_per_unit", 14.0)
    try:
        t_f = float(tariff_inr)
        k_f = max(0.0, float(kwh))
    except (ValueError, TypeError):
        return None
    return round(k_f * t_f, 2)


def compute_co2_saved(kwh: Optional[float]) -> Optional[float]:
    """Calculate avoided CO2 in kg: kwh * 0.82."""
    if kwh is None:
        return None
    try:
        k_f = max(0.0, float(kwh))
    except (ValueError, TypeError):
        return None
    return round(k_f * 0.82, 2)


def compute_availability(producing_days: int, fault_days: int) -> float:
    """Calculate availability percentage: (producing / (producing + fault)) * 100."""
    total = producing_days + fault_days
    if total <= 0:
        return 100.0
    return round((producing_days / total) * 100.0, 1)


def get_confidence_indicator(geocode_level: Optional[str], peer_count: int = 0) -> Dict[str, Any]:
    """
    Produce transparency and confidence metadata for displayed metrics.
    Rule 1: 'Never plot a number you can't explain.'
    """
    score = 0
    reasons = []

    # Geocode confidence
    if geocode_level == "exact":
        score += 40
        reasons.append("Exact GPS telemetry coordinates from inverter portal.")
    elif geocode_level == "pincode_centroid":
        score += 35
        reasons.append("High-accuracy 6-digit postal code centroid.")
    elif geocode_level == "city_centroid":
        score += 25
        reasons.append("Regional city centroid coordinates.")
    else:
        score += 10
        reasons.append("Fallback coordinates; local irradiance benchmark.")

    # Peer group confidence
    if peer_count >= 15:
        score += 60
        reasons.append(f"Strong peer group statistical baseline ({peer_count} peers).")
    elif peer_count >= 5:
        score += 45
        reasons.append(f"Standard regional peer baseline ({peer_count} peers).")
    elif peer_count > 0:
        score += 25
        reasons.append(f"Small peer group ({peer_count} peers); fallback to state average.")
    else:
        score += 10
        reasons.append("Independent plant telemetry; no regional peers available.")

    confidence_tier = "High" if score >= 80 else ("Medium" if score >= 50 else "Low")
    return {
        "confidence_score": score,
        "confidence_tier": confidence_tier,
        "details": " | ".join(reasons),
        "peer_count": peer_count,
        "geocode_level": geocode_level or "unresolved",
    }
