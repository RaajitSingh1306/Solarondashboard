"""
Unit tests for Pandera Data Contracts (Phase 2, Task 7).

Validates schema contracts, physical constraints, type coercion,
and failure case reporting.
"""

import sys
from pathlib import Path
import pandas as pd
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import contracts


def test_valid_plants_contract():
    df = pd.DataFrame([{
        "plant_id": "test_p1",
        "source": "growatt",
        "plant_name": "Test Rooftop",
        "capacity_kwp": 5.0,
        "latitude": 21.1458,
        "longitude": 79.0882,
        "city": "Nagpur",
        "operational_status": "active",
        "geocode_level": "city_centroid",
    }])
    is_valid, out, errs = contracts.validate_plants_df(df)
    assert is_valid
    assert len(errs) == 0


def test_invalid_capacity_fails_contract():
    df = pd.DataFrame([{
        "plant_id": "test_p_bad",
        "source": "growatt",
        "capacity_kwp": -5.0,  # Invalid negative capacity
    }])
    is_valid, out, errs = contracts.validate_plants_df(df)
    assert not is_valid
    assert len(errs) > 0


def test_valid_daily_generation_contract():
    df = pd.DataFrame([{
        "plant_id": "test_p1",
        "date": "2026-09-15",
        "kwh": 22.5,
        "revenue_inr": 315.0,
        "specific_yield": 4.5,
        "yield_per_day": 4.5,
        "status": "active",
        "quality_flags": None,
    }])
    is_valid, out, errs = contracts.validate_daily_df(df)
    assert is_valid
    assert len(errs) == 0


def test_unphysical_daily_yield_fails_contract():
    df = pd.DataFrame([{
        "plant_id": "test_p1",
        "date": "2026-09-15",
        "kwh": 100.0,
        "specific_yield": 15.0,  # Physically impossible (> 8.0 kWh/kWp/day)
        "status": "active",
    }])
    is_valid, out, errs = contracts.validate_daily_df(df)
    assert not is_valid
    assert len(errs) > 0


def test_valid_inverter_snapshots_contract():
    df = pd.DataFrame([{
        "plant_id": "test_p1",
        "inverter_sn": "INV-12345",
        "snapshot_ts": "2026-09-15T12:00:00",
        "ac_power_w": 3800.0,
        "dc_power_w": 3900.0,
        "temperature_c": 42.5,
        "e_today_kwh": 14.5,
        "status": "normal",
    }])
    is_valid, out, errs = contracts.validate_snapshots_df(df)
    assert is_valid
    assert len(errs) == 0


def test_extreme_inverter_temp_fails_contract():
    df = pd.DataFrame([{
        "plant_id": "test_p1",
        "inverter_sn": "INV-12345",
        "snapshot_ts": "2026-09-15T12:00:00",
        "temperature_c": 120.0,  # Impossible operating temp (> 85C)
    }])
    is_valid, out, errs = contracts.validate_snapshots_df(df)
    assert not is_valid
    assert len(errs) > 0
