"""
Unit tests for Model Calibration & Evaluation Framework (Phase 5).

Validates anomaly feedback logging, adaptive Isolation Forest contamination,
and precision/recall/F1 evaluation routines.
"""

import sys
from pathlib import Path
import pandas as pd
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import db
import evaluation
import ml_analytics


def test_anomaly_feedback_persistence():
    db.init_db()
    test_pid = "test_feedback_plant"
    fb_id = db.log_anomaly_feedback(
        plant_id=test_pid,
        date_or_month="2026-09",
        flag_type="ISOLATION_FOREST",
        technician_label="real_fault",
        notes="Blown string fuse identified and replaced",
        logged_by="lead_engineer",
    )
    assert fb_id > 0

    records = db.get_anomaly_feedback(plant_id=test_pid)
    assert len(records) >= 1
    rec = records[0]
    assert rec["technician_label"] == "real_fault"
    assert rec["notes"] == "Blown string fuse identified and replaced"
    assert rec["logged_by"] == "lead_engineer"

    # Clean up test feedback
    db.execute("DELETE FROM anomaly_feedback WHERE plant_id = ?", [test_pid])


def test_adaptive_isolation_forest_contamination():
    # Build active dataset of 30 plants
    rows = []
    for i in range(30):
        rows.append({
            "plant_id": f"p_{i}",
            "month": "2026-09",
            "kwh": 400.0 + (i * 5),
            "yield_per_day": 3.8 + (i * 0.05),
            "pr_pct": 72.0 + (i * 0.2),
            "capacity_kwp": 5.0,
            "specific_yield": 80.0,
        })
    df = pd.DataFrame(rows)

    # Test auto contamination
    scored = ml_analytics.train_and_detect_anomalies(df, contamination="auto")
    assert "anomaly_score" in scored.columns
    assert "anomaly_flag" in scored.columns


def test_model_evaluation_metrics_structure():
    metrics = evaluation.evaluate_anomaly_model("2026-09")
    assert "precision" in metrics
    assert "recall" in metrics
    assert "f1_score" in metrics
    assert 0.0 <= metrics["precision"] <= 1.0
    assert 0.0 <= metrics["recall"] <= 1.0
