"""
Unified Plant Health Classification System (Phase 3).
Single source of truth for operational states and performance tiers across the fleet.

Separates:
1. Operational State: PRODUCING | COMMS_LOSS | FAULT | INACTIVE | DECOMMISSIONED | NO_DATA
2. Performance Tier: Best | Good | Could Be Better | Needs Attention | Critical | Unknown
3. Confidence: 0.0 - 1.0 (based on geocode precision, peer count, capacity confidence, days observed)
"""

import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Tuple
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

# Single authoritative tier threshold configuration
HEALTH_TIER_THRESHOLDS = {
    "Best": 0.95,             # >= 95% of expected / peer benchmark
    "Good": 0.80,             # 80% - 95%
    "Could Be Better": 0.65,  # 65% - 80%
    "Needs Attention": 0.40,  # 40% - 65%
    "Critical": 0.0,          # < 40%
}


def score_to_performance_tier(score: Optional[float]) -> str:
    """Classify unified health index / weather-adjusted score into performance tier."""
    if score is None or pd.isna(score):
        return "Unknown"
    try:
        val = float(score)
    except (ValueError, TypeError):
        return "Unknown"

    if val >= HEALTH_TIER_THRESHOLDS["Best"]:
        return "Best"
    if val >= HEALTH_TIER_THRESHOLDS["Good"]:
        return "Good"
    if val >= HEALTH_TIER_THRESHOLDS["Could Be Better"]:
        return "Could Be Better"
    if val >= HEALTH_TIER_THRESHOLDS["Needs Attention"]:
        return "Needs Attention"
    return "Critical"


def determine_operational_state(
    kwh: Optional[float],
    day_status: Optional[str] = None,
    plant_status: Optional[str] = None,
    peer_ref_yield: float = 0.0,
    has_recent_log: bool = True,
) -> str:
    """
    Classify plant operational state distinctly from performance tier:
    - DECOMMISSIONED: formally retired or removed from portal
    - NO_DATA: missing readings or telemetry offline
    - COMMS_LOSS: logger silent/zero while regional peers are healthy
    - FAULT: hardware alarm or confirmed string failure
    - INACTIVE: zero generation during non-monsoon zero-yield spell
    - PRODUCING: active power feed into grid
    """
    if str(plant_status).lower() == "decommissioned":
        return "DECOMMISSIONED"

    if kwh is None:
        return "NO_DATA"

    kwh_val = float(kwh)
    if kwh_val > 0.05:
        return "PRODUCING"

    # kwh <= 0.05
    if not has_recent_log:
        return "COMMS_LOSS"

    if day_status == "FAULT_SUSPECT":
        return "FAULT"
    if day_status == "LOW_LIGHT_ZERO":
        return "INACTIVE"
    if day_status == "INSUFFICIENT_PEERS":
        return "COMMS_LOSS"

    if peer_ref_yield > 0.5:
        return "COMMS_LOSS"
    return "INACTIVE"


def compute_health_confidence(
    geocode_level: Optional[str] = None,
    peer_count: int = 0,
    capacity_suspect: bool = False,
    observed_ratio: float = 1.0,
) -> float:
    """
    Calculates 0.0 - 1.0 confidence score for health assessments:
    - Exact geocode vs city centroid vs unresolved
    - Robust peer count (>= 5 peers)
    - Capacity confidence (flagged suspect -> -0.25)
    - Observed completeness ratio
    """
    conf = 1.0
    geo = str(geocode_level or "").lower()
    if geo == "exact":
        conf *= 1.0
    elif geo == "city_centroid":
        conf *= 0.90
    else:
        conf *= 0.75

    if peer_count < 3:
        conf *= 0.70
    elif peer_count < 5:
        conf *= 0.85

    if capacity_suspect:
        conf *= 0.75

    conf *= max(0.4, min(1.0, float(observed_ratio)))
    return round(conf, 2)


def evaluate_daily_plant_health(
    plant: Dict[str, Any],
    date_str: str,
    kwh: Optional[float],
    quality_flags: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes unified daily health record for a plant.
    """
    pid = str(plant["plant_id"])
    exp_info = expected_energy.expected_daily_kwh(plant, date_str)
    expected_kwh = float(exp_info["expected_kwh"] or 1.0)

    p_group = peer_group.get_plant_peer_group(pid)
    peer_ref = rpi.get_peer_reference_yield(p_group["group_id"], p_group["peers"], date_str)

    day_st = status_engine.classify_plant_day_status(
        kwh=kwh,
        quality_flags=quality_flags,
        peer_yields=[peer_ref] if peer_ref > 0 else [],
        is_logged=kwh is not None,
        operational_status=plant.get("operational_status", "active"),
    )

    op_state = determine_operational_state(
        kwh=kwh,
        day_status=day_st,
        plant_status=plant.get("operational_status", "active"),
        peer_ref_yield=peer_ref,
    )

    if op_state == "PRODUCING" and expected_kwh > 0.05 and kwh is not None:
        health_idx = round(min(max(0.0, float(kwh) / expected_kwh), 2.5), 3)
        tier = score_to_performance_tier(health_idx)
    elif op_state in ("DECOMMISSIONED", "NO_DATA"):
        health_idx = None
        tier = "Unknown"
    else:
        health_idx = 0.0
        tier = "Critical"

    conf = compute_health_confidence(
        geocode_level=plant.get("geocode_level"),
        peer_count=p_group.get("peer_count", 0),
        capacity_suspect=bool(plant.get("capacity_suspect")),
        observed_ratio=1.0,
    )

    return {
        "plant_id": pid,
        "date": date_str,
        "operational_state": op_state,
        "health_index": health_idx,
        "performance_tier": tier,
        "confidence": conf,
        "expected_kwh": expected_kwh,
        "actual_kwh": kwh,
        "peer_group": p_group.get("label", "National Fleet"),
    }
