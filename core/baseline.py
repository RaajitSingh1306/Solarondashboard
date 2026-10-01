"""
Solaron RPI Baseline & Soiling Sawtooth Detector (Phase 3, Task 12).

Calculates plant-specific intrinsic baseline and isolates soiling degradation:
- base[i] = plant's own median RPI over good producing days (absorbs tilt, orientation, age)
- expected[i,d] = ref[G,d] * kWp[i] * base[i]
- Sawtooth detector: Finds gradual RPI decay followed by abrupt reset (cleaning/rain)
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
try:
    from engines import rpi
    from pipeline import db
except ImportError:
    import rpi
    import db

logger = logging.getLogger(__name__)


def compute_plant_baseline_rpi(rpi_df: pd.DataFrame) -> float:
    """
    Compute intrinsic baseline RPI (base[i]) for a plant.
    Uses the 75th percentile of producing days to represent clean array potential.
    """
    if rpi_df.empty or "rpi" not in rpi_df.columns:
        return 1.0

    producing = rpi_df[rpi_df["kwh"] > 0.05]["rpi"].dropna()
    if producing.empty or len(producing) < 5:
        return 1.0

    # 75th percentile represents clean, unshaded performance
    base_val = float(np.percentile(producing, 75))
    return round(min(max(0.5, base_val), 1.5), 3)


def detect_soiling_sawtooth(
    rpi_df: pd.DataFrame,
    min_decay_days: int = 10,
    min_reset_jump: float = 0.15,
) -> List[Dict[str, Any]]:
    """
    Detect soiling sawtooth events in a plant's RPI timeseries:
    1. Gradual decay over >= min_decay_days
    2. Abrupt reset jump >= min_reset_jump within 1-2 days (cleaning event or rain)
    """
    if rpi_df.empty or len(rpi_df) < min_decay_days + 2:
        return []

    df = rpi_df.sort_values("date").reset_index(drop=True)
    rolling_rpi = df["rolling_rpi"].values
    dates = df["date"].values
    n = len(rolling_rpi)

    events = []
    i = min_decay_days
    while i < n - 1:
        # Check for sudden upward reset jump between day i and day i+1 or i+2
        current_val = rolling_rpi[i]
        next_val = rolling_rpi[min(i + 2, n - 1)]
        jump = next_val - current_val

        if jump >= min_reset_jump:
            # Check if previous min_decay_days showed net downward trend
            past_val = rolling_rpi[max(0, i - min_decay_days)]
            decay = past_val - current_val

            if decay > 0.08:  # Decayed at least 8% before jumping back
                start_date = str(dates[max(0, i - min_decay_days)])
                reset_date = str(dates[i])
                events.append({
                    "start_date": start_date,
                    "reset_date": reset_date,
                    "pre_reset_rpi": round(float(current_val), 3),
                    "post_reset_rpi": round(float(next_val), 3),
                    "recovered_rpi_pct": round(float(jump * 100), 1),
                    "decay_duration_days": min_decay_days,
                })
                i += min_decay_days  # Skip forward past event window
                continue
        i += 1

    return events


def calculate_peer_expected_energy(
    plant_id: str,
    capacity_kwp: float,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Compute daily expected generation based on peer reference insolation and plant baseline:
    expected[i,d] = ref[G,d] * kWp[i] * base[i]
    """
    rpi_df = rpi.calculate_plant_rpi_series(plant_id, start_date=start_date, end_date=end_date)
    if rpi_df.empty:
        return pd.DataFrame()

    base_rpi = compute_plant_baseline_rpi(rpi_df)
    cap = float(capacity_kwp) if capacity_kwp and capacity_kwp > 0 else 3.3

    rpi_df["baseline_rpi"] = base_rpi
    rpi_df["expected_kwh"] = (rpi_df["peer_ref_yield"] * cap * base_rpi).round(2)
    rpi_df["lost_kwh"] = (rpi_df["expected_kwh"] - rpi_df["kwh"]).clip(lower=0.0).round(2)

    return rpi_df
