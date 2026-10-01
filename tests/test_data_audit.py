"""
Unit tests for Solaron Data Audit Engine (Phase 2, Task 8).

Validates field completeness calculation, reconciliation routines,
and telemetry quality metric generation.
"""

import sys
from pathlib import Path
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import data_audit


def test_field_completeness_structure():
    df = data_audit.audit_field_completeness()
    assert not df.empty
    expected_cols = ["source", "total_plants", "lat_pct", "city_pct", "cap_pct", "geocode_pct"]
    for col in expected_cols:
        assert col in df.columns
    # Ensure percentages are within [0, 100]
    for _, row in df.iterrows():
        assert 0.0 <= row["cap_pct"] <= 100.0
        assert 0.0 <= row["geocode_pct"] <= 100.0


def test_monthly_daily_reconciliation_structure():
    res = data_audit.audit_monthly_daily_reconciliation()
    assert "total_checked" in res
    assert "discrepancies" in res
    assert "reconciliation_rate_pct" in res
    assert 0.0 <= res["reconciliation_rate_pct"] <= 100.0


def test_stuck_and_zero_runs_structure():
    res = data_audit.audit_stuck_and_zero_runs()
    assert "total_records" in res
    assert "stuck_records" in res
    assert "zero_records" in res
    assert res["total_records"] >= res["stuck_records"]


def test_full_audit_report_generation():
    report = data_audit.generate_full_audit_report()
    assert "completeness" in report
    assert "reconciliation" in report
    assert "stuck_telemetry" in report
    assert len(report["completeness"]) > 0
