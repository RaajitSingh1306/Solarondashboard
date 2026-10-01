"""
Solaron ML Analytics & Adaptive Physics Engine.

Provides:
1. Physics-based absolute Performance Ratio (PR) tiering.
2. Machine Learning Anomaly Detection via Isolation Forest.
3. Seasonal and Irradiance-Adaptive Loss Decomposition.
4. Explainable plant diagnostics.
"""

import math
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

# Standard benchmark PR across utility and rooftop solar (IEC 61724 standard)
STANDARD_BENCHMARK_PR = 75.0

# Seasonal Soiling Coefficients for India (monthly average dirt/dust derate factor)
# Dry winter/spring has higher airborne particulates; monsoon rains naturally wash panels.
SEASONAL_SOILING_MAP: Dict[str, float] = {
    "01": 0.05,  # Jan: Dry winter, post-harvest dust
    "02": 0.05,  # Feb: Dry, rising ambient dust
    "03": 0.06,  # Mar: Pre-summer dry heat & dust
    "04": 0.06,  # Apr: Summer dust storms / pollen
    "05": 0.06,  # May: Peak dust accumulation before monsoon
    "06": 0.03,  # Jun: Early monsoon showers begin wash cycle
    "07": 0.02,  # Jul: Heavy monsoon washing
    "08": 0.02,  # Aug: Active monsoon washing
    "09": 0.02,  # Sep: Late monsoon wash / low dust
    "10": 0.03,  # Oct: Post-monsoon drying
    "11": 0.04,  # Nov: Winter inversion, dust settling
    "12": 0.04,  # Dec: Winter smog & dry dust
}


def pr_to_tier(pr: Optional[float]) -> str:
    """
    Map absolute Performance Ratio (PR %) to industry standard health tiers.
    Eliminates relative ranking distortions where poor plants are masked as 'Good'.
    
    PR >= 75.0% -> Best (Exceeds or meets optimal benchmark)
    PR >= 60.0% -> Good (Healthy commercial operating band)
    PR >= 45.0% -> Could Be Better (Moderate underperformance)
    PR >= 30.0% -> Needs Attention (Sub-optimal, investigate losses)
    PR <  30.0% -> Critical (Severe underperformance or string failure)
    """
    if pr is None or pd.isna(pr):
        return "Critical"
    try:
        val = float(pr)
    except (ValueError, TypeError):
        return "Critical"

    if val >= 75.0:
        return "Best"
    if val >= 60.0:
        return "Good"
    if val >= 45.0:
        return "Could Be Better"
    if val >= 30.0:
        return "Needs Attention"
    return "Critical"


def rpi_to_tier(rpi_score: Optional[float], availability: Optional[float] = 1.0) -> str:
    """
    Map Relative Performance Index (RPI) and availability to operational health tiers:
    Plan 2 §3 Phase 6 (Task 19):
    - RPI >= 0.95 and availability >= 0.90 -> Best
    - RPI >= 0.85 -> Good (Watch)
    - RPI >= 0.70 -> Needs Attention (Underperforming)
    - RPI < 0.70 or availability < 0.50 -> Critical
    """
    if rpi_score is None or pd.isna(rpi_score):
        return "Critical"
    try:
        r = float(rpi_score)
        avail = float(availability if availability is not None else 1.0)
    except (ValueError, TypeError):
        return "Critical"

    if avail < 0.50 or r < 0.70:
        return "Critical"
    elif r < 0.85:
        return "Needs Attention"
    elif r < 0.95 or avail < 0.90:
        return "Good"
    else:
        return "Best"


def robust_z_score(val: float, series: Sequence[float]) -> float:
    """
    Compute robust z-score: z = (val - median) / (1.4826 * MAD).
    Plan 2 §3 Phase 5.2 (Task 16).
    """
    s = [x for x in series if x is not None and not pd.isna(x)]
    if len(s) < 3:
        return 0.0
    med = float(np.median(s))
    mad = float(np.median([abs(x - med) for x in s]))
    if mad <= 1e-6:
        return 0.0
    return round((val - med) / (1.4826 * mad), 3)


def cusum_drift_detector(
    series: Sequence[float], threshold: float = 4.0, drift: float = 0.5
) -> List[int]:
    """
    Cumulative Sum (CUSUM) detector for gradual negative performance drift (soiling / degradation).
    Plan 2 §3 Phase 5.2 (Task 16).
    Returns indices where negative drift exceeded threshold.
    """
    if not series or len(series) < 3:
        return []
    arr = [float(x) if (x is not None and not pd.isna(x)) else 0.0 for x in series]
    mean_val = float(np.mean(arr))
    std_val = float(np.std(arr)) if np.std(arr) > 1e-5 else 1.0
    s_neg = 0.0
    alarms = []
    for i, val in enumerate(arr):
        z = (val - mean_val) / std_val
        s_neg = max(0.0, s_neg - z - drift)
        if s_neg > threshold:
            alarms.append(i)
            s_neg = 0.0
    return alarms



def get_month_cyclic_features(month_str: str) -> Tuple[float, float]:
    """Encode month (1-12) as sine and cosine to preserve cyclic annual seasonality."""
    try:
        parts = str(month_str).strip().split("-")
        m = int(parts[1])
    except Exception:
        m = 9
    angle = 2.0 * math.pi * (m - 1) / 12.0
    return round(math.sin(angle), 4), round(math.cos(angle), 4)


def train_and_detect_anomalies(
    df_monthly: pd.DataFrame,
    contamination: Union[float, str] = 0.08,
) -> pd.DataFrame:
    """
    Run Isolation Forest across historical active monthly generation records to detect
    statistical performance anomalies.

    Features used:
    - yield_per_day (normalized production)
    - pr_pct (performance ratio)
    - capacity_kwp (system scale)
    - month_sin, month_cos (seasonality)

    Flags underperforming anomalies where plant performance is an outlier AND below the
    monthly median production level.
    """
    if df_monthly.empty:
        df_monthly["anomaly_score"] = 0.0
        df_monthly["anomaly_flag"] = 0
        return df_monthly

    out_df = df_monthly.copy()
    out_df["anomaly_score"] = 0.0
    out_df["anomaly_flag"] = 0

    # Filter active producing records
    kwh_num = pd.to_numeric(out_df["kwh"], errors="coerce").fillna(0.0)
    active_idx = out_df[kwh_num > 1.0].index

    if len(active_idx) < 10:
        # Not enough samples for reliable ML clustering, return default
        return out_df

    active_sub = out_df.loc[active_idx].copy()
    sin_vals, cos_vals = zip(*active_sub["month"].apply(get_month_cyclic_features))
    active_sub["sin_m"] = sin_vals
    active_sub["cos_m"] = cos_vals

    ypd = pd.to_numeric(active_sub["yield_per_day"], errors="coerce").fillna(0.0)
    pr = pd.to_numeric(active_sub["pr_pct"], errors="coerce").fillna(0.0)
    cap = pd.to_numeric(active_sub["capacity_kwp"], errors="coerce").fillna(3.3)

    X = pd.DataFrame({
        "ypd": ypd,
        "pr": pr,
        "cap": cap,
        "sin_m": active_sub["sin_m"],
        "cos_m": active_sub["cos_m"],
    }, index=active_sub.index)

    # Impute any remaining NaNs with column medians
    X = X.fillna(X.median())

    try:
        # Use adaptive contamination (defaults to 'auto' or parameter)
        iso_contamination = contamination if contamination in ('auto', None) or (isinstance(contamination, float) and 0.0 < contamination < 0.5) else 'auto'
        iso = IsolationForest(
            n_estimators=100,
            contamination=iso_contamination,
            random_state=42,
            n_jobs=-1
        )
        iso.fit(X)

        raw_pred = iso.predict(X)  # -1 = anomaly, 1 = normal
        scores = iso.decision_function(X) # lower score = more anomalous

        active_sub["raw_pred"] = raw_pred
        active_sub["score"] = scores
        active_sub["ypd_num"] = ypd

        # Group by month to find the monthly median yield
        monthly_median_ypd = active_sub.groupby("month")["ypd_num"].transform("median")

        # An underperforming anomaly is an outlier whose yield is below the peer median
        is_underperforming = (active_sub["raw_pred"] == -1) & (active_sub["ypd_num"] < monthly_median_ypd)

        out_df.loc[active_idx, "anomaly_score"] = [round(float(s), 4) for s in scores]
        out_df.loc[active_idx, "anomaly_flag"] = [1 if flag else 0 for flag in is_underperforming]
    except Exception as e:
        logger.warning(f"IsolationForest training failed, falling back to rule-based: {e}")
        # Rule-based fallback: PR < 25% on an active month
        is_fallback_anomaly = (pr < 25.0) & (ypd < 1.0)
        out_df.loc[active_idx, "anomaly_flag"] = [1 if flag else 0 for flag in is_fallback_anomaly]

    return out_df


def calculate_adaptive_losses(
    shortfall: float,
    expected_kwh: float,
    actual_kwh: float,
    ghi: float,
    default_ghi: float,
    zero_ratio: float,
    fault_ratio: float,
    month_str: str,
) -> Dict[str, float]:
    """
    Decompose generation shortfall using adaptive physics and telemetry factors:
    1. Comm loss: measured by observed zero-generation ratio.
    2. Shutdown loss: measured by recorded fault state ratio.
    3. Weather deficit: calculated from actual location GHI vs regional benchmark.
    4. Soiling loss: scaled by seasonal dust/monsoon wash calendar.
    5. Shading loss: physical horizon obstruction.
    6. Unknown loss: residual balance of system loss.
    """
    if shortfall <= 0.0:
        return {
            "comm_loss": 0.0,
            "shutdown_loss": 0.0,
            "weather_loss": 0.0,
            "soiling_loss": 0.0,
            "shading_loss": 0.0,
            "unknown_loss": 0.0,
        }

    try:
        parts = month_str.split("-")
        m_key = f"{int(parts[1]):02d}"
    except Exception:
        m_key = "09"

    # 1. Communication / Telemetry Loss
    # Lost generation during logged offline/zero days
    comm_loss = round(shortfall * min(0.60, zero_ratio * 0.85), 2)

    # 2. Inverter Fault / Shutdown Loss
    shutdown_loss = round(shortfall * min(0.40, fault_ratio * 0.90), 2)

    # 3. Weather / Irradiance Loss (deficit vs clear sky baseline ~5.8 kWh/m2/day)
    # If GHI is lower than clear-sky standard, weather was cloud-restricted
    clear_sky_ref = max(5.5, default_ghi)
    weather_deficit_factor = max(0.0, (clear_sky_ref - ghi) / clear_sky_ref) if clear_sky_ref > 0 else 0.15
    weather_ratio = min(0.45, max(0.08, weather_deficit_factor * 0.75))
    weather_loss = round(shortfall * weather_ratio, 2)

    # 4. Seasonal Soiling Loss
    soiling_rate = SEASONAL_SOILING_MAP.get(m_key, 0.03)
    soiling_loss = round(min(shortfall * 0.20, expected_kwh * soiling_rate), 2)

    # 5. Shading / Obstruction Loss
    shading_loss = round(min(shortfall * 0.10, expected_kwh * 0.02), 2)

    # Reconcile total classified losses with actual shortfall
    classified = comm_loss + shutdown_loss + weather_loss + soiling_loss + shading_loss
    if classified > shortfall:
        scale = shortfall / classified
        comm_loss = round(comm_loss * scale, 2)
        shutdown_loss = round(shutdown_loss * scale, 2)
        weather_loss = round(weather_loss * scale, 2)
        soiling_loss = round(soiling_loss * scale, 2)
        shading_loss = round(shading_loss * scale, 2)
        unknown_loss = 0.0
    else:
        unknown_loss = round(shortfall - classified, 2)

    return {
        "comm_loss": comm_loss,
        "shutdown_loss": shutdown_loss,
        "weather_loss": weather_loss,
        "soiling_loss": soiling_loss,
        "shading_loss": shading_loss,
        "unknown_loss": unknown_loss,
    }


def explain_plant_performance(
    plant_id: str,
    month: str,
    tier: str,
    pr_pct: Optional[float],
    percentile: Optional[float],
    specific_yield: Optional[float],
    yield_per_day: Optional[float],
    anomaly_flag: int = 0,
    anomaly_score: Optional[float] = None,
) -> str:
    """Generate clear, professional operational diagnostics for operators."""
    if tier in ("Decommissioned", "Offline", "Fault"):
        return f"Plant status is {tier.upper()} with negligible or zero generation recorded in {month}."

    pr_str = f"{pr_pct:.1f}%" if pr_pct is not None else "—"
    sy_str = f"{specific_yield:.1f} kWh/kWp" if specific_yield is not None else "—"
    ypd_str = f"{float(yield_per_day):.2f} units/kWp/day" if (yield_per_day is not None and float(yield_per_day) > 0) else "—"

    if anomaly_flag == 1:
        return (
            f"⚡ ML ANOMALY DETECTED: Operating at {pr_str} PR ({tier} Tier) with {sy_str} ({ypd_str}). "
            f"Output is statistically divergent from seasonal peers (score: {anomaly_score or -0.05:.3f}). "
            f"Dispatch inspection for string clipping, inverter derating, or severe localized shading."
        )

    if tier == "Best":
        return f"Optimal performance: {pr_str} PR (Best Tier) with {sy_str} ({ypd_str}). System meets or exceeds industry standard benchmark."
    elif tier == "Good":
        return f"Healthy performance: {pr_str} PR (Good Tier) with {sy_str} ({ypd_str}). Operating in standard commercial range."
    elif tier == "Could Be Better":
        return f"Moderate performance: {pr_str} PR (Could Be Better Tier) with {sy_str} ({ypd_str}). Consider panel cleaning and string check."
    elif tier == "Needs Attention":
        return f"Sub-optimal performance: {pr_str} PR (Needs Attention Tier) with {sy_str} ({ypd_str}). Generation is significantly below potential; review loss breakdown."
    else:
        return f"Critical underperformance: {pr_str} PR (Critical Tier) with {sy_str} ({ypd_str}). Urgent inverter, fuse, and string inspection recommended."
