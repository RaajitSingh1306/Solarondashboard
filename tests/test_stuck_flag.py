"""
Unit tests for Stuck-Value Flagging (Phase 1, Task 1).

Validates detection of repeated identical non-zero kWh generation readings across
consecutive days, ensuring noise floor/offline days are excluded and real variability
is preserved.
"""

import sys
from pathlib import Path
import sqlite3
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import data_quality
import db


def test_stuck_value_3_consecutive_days():
    records = [
        {"plant_id": "test_p1", "date": "2026-09-01", "kwh": 18.5},
        {"plant_id": "test_p1", "date": "2026-09-02", "kwh": 18.5},
        {"plant_id": "test_p1", "date": "2026-09-03", "kwh": 18.5},
        {"plant_id": "test_p1", "date": "2026-09-04", "kwh": 22.0},
    ]
    flagged = data_quality.detect_stuck_values(records, consecutive_threshold=3)
    
    assert data_quality.is_stuck_value(flagged[0].get("quality_flags"))
    assert data_quality.is_stuck_value(flagged[1].get("quality_flags"))
    assert data_quality.is_stuck_value(flagged[2].get("quality_flags"))
    assert not data_quality.is_stuck_value(flagged[3].get("quality_flags"))


def test_stuck_value_below_threshold_not_flagged():
    records = [
        {"plant_id": "test_p1", "date": "2026-09-01", "kwh": 18.5},
        {"plant_id": "test_p1", "date": "2026-09-02", "kwh": 18.5},
        {"plant_id": "test_p1", "date": "2026-09-03", "kwh": 22.0},
    ]
    flagged = data_quality.detect_stuck_values(records, consecutive_threshold=3)
    for r in flagged:
        assert not data_quality.is_stuck_value(r.get("quality_flags"))


def test_normal_variable_series_not_flagged():
    records = [
        {"plant_id": "test_p1", "date": "2026-09-01", "kwh": 14.2},
        {"plant_id": "test_p1", "date": "2026-09-02", "kwh": 18.5},
        {"plant_id": "test_p1", "date": "2026-09-03", "kwh": 12.1},
        {"plant_id": "test_p1", "date": "2026-09-04", "kwh": 16.8},
        {"plant_id": "test_p1", "date": "2026-09-05", "kwh": 15.0},
    ]
    flagged = data_quality.detect_stuck_values(records, consecutive_threshold=3)
    for r in flagged:
        assert not data_quality.is_stuck_value(r.get("quality_flags"))


def test_zero_and_noise_days_not_flagged_as_stuck():
    records = [
        {"plant_id": "test_p1", "date": "2026-09-01", "kwh": 0.0},
        {"plant_id": "test_p1", "date": "2026-09-02", "kwh": 0.0},
        {"plant_id": "test_p1", "date": "2026-09-03", "kwh": 0.0},
        {"plant_id": "test_p1", "date": "2026-09-04", "kwh": 0.03},  # noise floor <= 0.05
        {"plant_id": "test_p1", "date": "2026-09-05", "kwh": 0.03},
        {"plant_id": "test_p1", "date": "2026-09-06", "kwh": 0.03},
    ]
    flagged = data_quality.detect_stuck_values(records, consecutive_threshold=3)
    for r in flagged:
        assert not data_quality.is_stuck_value(r.get("quality_flags"))


def test_multi_plant_independent_flagging():
    records = [
        # Plant A has stuck values
        {"plant_id": "plant_A", "date": "2026-09-01", "kwh": 10.0},
        {"plant_id": "plant_A", "date": "2026-09-02", "kwh": 10.0},
        {"plant_id": "plant_A", "date": "2026-09-03", "kwh": 10.0},
        # Plant B has variable values
        {"plant_id": "plant_B", "date": "2026-09-01", "kwh": 10.0},
        {"plant_id": "plant_B", "date": "2026-09-02", "kwh": 12.0},
        {"plant_id": "plant_B", "date": "2026-09-03", "kwh": 14.0},
    ]
    flagged = data_quality.detect_stuck_values(records, consecutive_threshold=3)
    plant_a_flags = [data_quality.is_stuck_value(r.get("quality_flags")) for r in flagged if r["plant_id"] == "plant_A"]
    plant_b_flags = [data_quality.is_stuck_value(r.get("quality_flags")) for r in flagged if r["plant_id"] == "plant_B"]
    
    assert all(plant_a_flags)
    assert not any(plant_b_flags)


def test_db_upsert_and_scan_stuck_values():
    db.init_db()
    test_plant_id = "test_stuck_synthetic_plant"
    
    # Insert test plant
    db.upsert_plant({
        "plant_id": test_plant_id,
        "source": "test",
        "plant_name": "Synthetic Stuck Test Plant",
        "capacity_kwp": 5.0,
    })
    
    test_days = [
        {"plant_id": test_plant_id, "date": "2026-01-01", "kwh": 9.1, "status": "active"},
        {"plant_id": test_plant_id, "date": "2026-01-02", "kwh": 9.1, "status": "active"},
        {"plant_id": test_plant_id, "date": "2026-01-03", "kwh": 9.1, "status": "active"},
        {"plant_id": test_plant_id, "date": "2026-01-04", "kwh": 15.0, "status": "active"},
    ]
    db.upsert_daily(test_days)
    
    flagged_count = data_quality.scan_and_flag_stuck_values()
    assert flagged_count >= 3
    
    # Query database to verify persistence
    df = db.query_df(
        "SELECT date, quality_flags FROM daily_generation WHERE plant_id = ? ORDER BY date ASC",
        [test_plant_id]
    )
    assert len(df) == 4
    assert df.iloc[0]["quality_flags"] == "STUCK_VALUE"
    assert df.iloc[1]["quality_flags"] == "STUCK_VALUE"
    assert df.iloc[2]["quality_flags"] == "STUCK_VALUE"
    assert df.iloc[3]["quality_flags"] is None
    
    # Clean up test rows
    db.execute("DELETE FROM daily_generation WHERE plant_id = ?", [test_plant_id])
    db.execute("DELETE FROM plants WHERE plant_id = ?", [test_plant_id])
