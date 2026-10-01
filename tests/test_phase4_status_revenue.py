"""
Unit tests for Plant-Day Status, Lost Revenue, and Fault Correlation (Phase 4).

Validates multi-signal status classification, lost revenue calculations,
and hardware fault code precision metrics.
"""

import sys
from pathlib import Path
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import fault_correlation
import lost_revenue
import status_engine


def test_status_classification_rules():
    # 1. Producing day
    st1 = status_engine.classify_plant_day_status(
        kwh=18.5, quality_flags=None, peer_yields=[4.2, 4.5, 4.0]
    )
    assert st1 == "PRODUCING"

    # 2. Stuck day
    st2 = status_engine.classify_plant_day_status(
        kwh=18.5, quality_flags="STUCK_VALUE", peer_yields=[4.2, 4.5, 4.0]
    )
    assert st2 == "STUCK"

    # 3. Decommissioned plant
    st3 = status_engine.classify_plant_day_status(
        kwh=0.0, quality_flags=None, peer_yields=[4.2, 4.5, 4.0], operational_status="decommissioned"
    )
    assert st3 == "DECOMMISSIONED"

    # 4. No data
    st4 = status_engine.classify_plant_day_status(
        kwh=None, quality_flags=None, peer_yields=[4.2, 4.5], is_logged=False
    )
    assert st4 == "NO_DATA"


def test_low_light_vs_fault_suspect():
    # Zero output while peers were producing (100% producing peers) -> FAULT_SUSPECT
    st_fault = status_engine.classify_plant_day_status(
        kwh=0.0, quality_flags=None, peer_yields=[3.5, 4.0, 4.2, 3.8]
    )
    assert st_fault == "FAULT_SUSPECT"

    # Zero output while peers were also dark/stormy (0% producing peers) -> LOW_LIGHT_ZERO
    st_weather = status_engine.classify_plant_day_status(
        kwh=0.0, quality_flags=None, peer_yields=[0.0, 0.02, 0.0, 0.01]
    )
    assert st_weather == "LOW_LIGHT_ZERO"


def test_lost_revenue_computation():
    # 0 expected -> 0 lost revenue
    res = lost_revenue.calculate_plant_lost_revenue(
        plant_id="test_nonexistent", capacity_kwp=5.0
    )
    assert res["revenue_at_risk_inr"] == 0.0
    assert res["availability_pct"] == 100.0


def test_fault_code_taxonomy_mapping():
    assert "Grid Undervoltage" in fault_correlation.FAULT_CODE_TAXONOMY["101"]
    assert "Inverter Over-temperature" in fault_correlation.FAULT_CODE_TAXONOMY["301"]
