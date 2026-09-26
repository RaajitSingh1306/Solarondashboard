"""
Solaron Data Quality & Physics Validation Module.

Enforces physical boundaries, solar physics rules, noise reduction,
specific yield recomputation, yield-per-day calculation, and
decommissioned plant detection across the entire Solaron fleet.
"""

import calendar
import datetime
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Solar Physics Constants for India (lat 8°N to 37°N)
# Max daily peak sun hours in India rarely exceeds 7.5 kWh/m2/day.
# With ~80% PR, max daily yield = 7.5 * 0.8 ≈ 6.0 - 7.5 kWh/kWp/day.
MAX_DAILY_YIELD_KWH_KWP = 8.0
MIN_DAILY_YIELD_KWH_KWP = 0.0

# Max monthly yield in peak months: 31 days * 6.5 ≈ 200 kWh/kWp/month.
# Absolute physical upper bound: 220 kWh/kWp/month.
MAX_MONTHLY_YIELD_KWH_KWP = 220.0
MIN_MONTHLY_YIELD_KWH_KWP = 0.0

# Noise floor: any generation <= 0.05 kWh/day or <= 0.5 kWh/month is considered zero/noise
NOISE_FLOOR_DAILY_KWH = 0.05
NOISE_FLOOR_MONTHLY_KWH = 1.0


def clean_plant_name(name: Any) -> str:
    """Normalize and trim plant names, collapsing multiple whitespace characters."""
    if not name:
        return ""
    cleaned = re.sub(r"\s+", " ", str(name)).strip()
    return cleaned


def normalize_capacity(cap: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Validate and normalize plant capacity in kWp.
    Solar plants in this fleet range from ~1 kWp to ~500 kWp.
    Values > 5,000 are in Watts and must be divided by 1000.
    Commercial plants (e.g. 194.4 kWp) MUST NOT be divided.
    """
    if cap is None:
        return default
    try:
        val = float(cap)
        if val <= 0:
            return default
        # Only divide if clearly entered in Watts (> 5000 W)
        if val > 5000:
            val = val / 1000.0
        # Bounds check: 0.1 kWp to 10,000 kWp
        if 0.1 <= val <= 10000.0:
            return round(val, 2)
        return default
    except (ValueError, TypeError):
        return default


def get_days_in_month(month_str: str) -> int:
    """Return number of days in YYYY-MM string."""
    try:
        parts = month_str.strip().split("-")
        year = int(parts[0])
        month = int(parts[1])
        return calendar.monthrange(year, month)[1]
    except Exception:
        return 30


def get_elapsed_days_in_month(month_str: str) -> int:
    """
    Return elapsed days for the given month.
    For the current ongoing month, returns the current day of the month (e.g. 25 on Sep 25).
    For past months, returns total days in that month (e.g. 31 for August).
    For future months, returns total days in that month.
    """
    total_days = get_days_in_month(month_str)
    try:
        today = datetime.date.today()
        current_ym = today.strftime("%Y-%m")
        clean_m = (month_str or "").strip()
        if clean_m == current_ym:
            return max(1, min(today.day, total_days))
        return max(1, total_days)
    except Exception:
        return total_days


def recompute_specific_yield(
    kwh: Optional[float], capacity_kwp: Optional[float], is_daily: bool = False, month_str: Optional[str] = None
) -> Optional[float]:
    """
    Recompute specific yield directly from actual energy and capacity.
    Eliminates discrepancies where platforms report generic or erroneous specific yields.
    """
    if kwh is None or capacity_kwp is None or capacity_kwp <= 0:
        return None

    # Clamp negative energy
    kwh_clean = max(0.0, float(kwh))
    if is_daily and kwh_clean < NOISE_FLOOR_DAILY_KWH:
        return 0.0
    if not is_daily and kwh_clean < NOISE_FLOOR_MONTHLY_KWH:
        return 0.0

    raw_sy = kwh_clean / float(capacity_kwp)
    if is_daily:
        raw_sy = min(raw_sy, MAX_DAILY_YIELD_KWH_KWP)
    else:
        raw_sy = min(raw_sy, MAX_MONTHLY_YIELD_KWH_KWP)
    return round(raw_sy, 2)


def compute_yield_per_day(
    kwh: Optional[float], capacity_kwp: Optional[float], days: int = 1
) -> Optional[float]:
    """
    Compute normalized generation yield per day: units / kWp / day.
    Explicitly requested metric for standardized plant comparison.
    Clamped to physical upper bound of 8.0 units/kWp/day.
    """
    if kwh is None or capacity_kwp is None or capacity_kwp <= 0 or days <= 0:
        return None

    kwh_clean = max(0.0, float(kwh))
    ypd = kwh_clean / (float(capacity_kwp) * float(days))
    ypd = min(ypd, MAX_DAILY_YIELD_KWH_KWP)
    return round(ypd, 2)


def get_capacity_bracket(capacity_kwp: Optional[float]) -> str:
    """
    Group plants into capacity brackets for fair peer-group comparisons:
    - 0-3 kWp: Small Residential
    - 3-5 kWp: Standard Residential
    - 5-10 kWp: Large Residential
    - 10-50 kWp: Commercial Rooftop
    - 50+ kWp: Industrial / Utility
    """
    if capacity_kwp is None or capacity_kwp <= 0:
        return "Unknown"
    if capacity_kwp <= 3.2:
        return "0-3 kWp"
    if capacity_kwp <= 5.2:
        return "3-5 kWp"
    if capacity_kwp <= 10.5:
        return "5-10 kWp"
    if capacity_kwp <= 50.0:
        return "10-50 kWp"
    return "50+ kWp"


def validate_daily_record(
    record: Dict[str, Any], capacity_kwp: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Validate and sanitize daily record: reject negative values, remove noise floor,
    reject future dates beyond today, and compute specific yield and yield_per_day.
    """
    out = dict(record)
    d_date = str(out.get("date", "")).strip()
    today_str = datetime.date.today().isoformat()
    if d_date and d_date > today_str:
        return None
    kwh = out.get("kwh")
    if kwh is not None:
        try:
            kwh_val = float(kwh)
            if kwh_val < NOISE_FLOOR_DAILY_KWH:
                kwh_val = 0.0
            out["kwh"] = round(kwh_val, 2)
        except (ValueError, TypeError):
            out["kwh"] = 0.0
    else:
        out["kwh"] = 0.0

    cap = normalize_capacity(capacity_kwp or out.get("capacity_kwp"))
    if cap and cap > 0 and out["kwh"] is not None:
        sy = recompute_specific_yield(out["kwh"], cap, is_daily=True)
        out["specific_yield"] = sy
        out["yield_per_day"] = sy
    else:
        out["specific_yield"] = out.get("specific_yield") or 0.0
        out["yield_per_day"] = out.get("specific_yield") or 0.0

    # Sanitize revenue: no negative revenue
    rev = out.get("revenue_inr")
    if rev is not None:
        try:
            out["revenue_inr"] = max(0.0, round(float(rev), 2))
        except (ValueError, TypeError):
            out["revenue_inr"] = 0.0

    # Normalize status based on generation
    if out["kwh"] is not None and out["kwh"] > NOISE_FLOOR_DAILY_KWH:
        out["status"] = "active"
    elif out.get("status") != "fault":
        out["status"] = "offline"

    return out


def validate_monthly_record(
    record: Dict[str, Any], capacity_kwp: Optional[float] = None
) -> Dict[str, Any]:
    """
    Validate and sanitize monthly record: reject negative values, remove noise floor,
    and compute specific yield and yield_per_day directly from actual telemetry.
    """
    out = dict(record)
    month_str = str(out.get("month", ""))
    elapsed_days = get_elapsed_days_in_month(month_str)

    kwh = out.get("kwh")
    if kwh is not None:
        try:
            kwh_val = float(kwh)
            if kwh_val < NOISE_FLOOR_MONTHLY_KWH:
                kwh_val = 0.0
            out["kwh"] = round(kwh_val, 2)
        except (ValueError, TypeError):
            out["kwh"] = 0.0
    else:
        out["kwh"] = 0.0

    cap = normalize_capacity(capacity_kwp or out.get("capacity_kwp"))
    if cap and cap > 0 and out["kwh"] is not None:
        sy = recompute_specific_yield(out["kwh"], cap, is_daily=False, month_str=month_str)
        out["specific_yield"] = sy
        out["yield_per_day"] = compute_yield_per_day(out["kwh"], cap, days=elapsed_days)
    else:
        out["specific_yield"] = out.get("specific_yield") or 0.0
        out["yield_per_day"] = 0.0

    rev = out.get("revenue_inr")
    if rev is not None:
        try:
            out["revenue_inr"] = max(0.0, round(float(rev), 2))
        except (ValueError, TypeError):
            out["revenue_inr"] = 0.0

    return out


def is_plant_decommissioned(
    total_lifetime_kwh: float,
    months_with_zero: int,
    months_tracked: int,
    install_date_str: Optional[str] = None,
) -> bool:
    """
    Determine if a plant is permanently decommissioned or shut down.
    A plant is decommissioned if:
    1. It has 0 generation across all tracked months (>= 2 months tracked), OR
    2. Its lifetime recorded energy is <= 1.0 kWh despite being installed over 1 year ago.
    """
    if months_tracked >= 2 and months_with_zero == months_tracked:
        return True

    if install_date_str:
        try:
            inst_date = datetime.date.fromisoformat(install_date_str[:10])
            today = datetime.date.today()
            days_old = (today - inst_date).days
            if days_old > 365 and total_lifetime_kwh <= NOISE_FLOOR_MONTHLY_KWH:
                return True
        except Exception:
            pass

    return False
