import datetime
import os
import pytest
from pipeline import db, pipeline
from core import health, expected_energy, features
from services import s3_archive

def test_hourly_and_yearly_schema_and_upsert():
    """Verify hourly and yearly generation tables and upsert helpers."""
    plant_id = "test_plant_001"
    now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:00:00")
    
    # Insert hourly record
    h_rows = [{
        "plant_id": plant_id,
        "ts": now_ts,
        "power_kw": 4.5,
        "energy_kwh": 3.8,
        "source_type": "portal_history",
    }]
    count_h = db.upsert_hourly(h_rows, overwrite=True)
    assert count_h >= 1

    # Overwrite hourly record
    h_rows_updated = [{
        "plant_id": plant_id,
        "ts": now_ts,
        "power_kw": 5.0,
        "energy_kwh": 4.2,
        "source_type": "portal_history",
    }]
    db.upsert_hourly(h_rows_updated, overwrite=True)

    with db.get_conn() as conn:
        row = conn.execute("SELECT power_kw, energy_kwh FROM hourly_generation WHERE plant_id = ? AND ts = ?", (plant_id, now_ts)).fetchone()
        assert row is not None
        assert row[0] == 5.0
        assert row[1] == 4.2

    # Insert yearly record
    y_rows = [{
        "plant_id": plant_id,
        "year": "2025",
        "kwh": 6500.0,
        "specific_yield": 1420.0,
        "pr_pct": 78.5,
        "source_type": "calculated",
    }]
    count_y = db.upsert_yearly(y_rows)
    assert count_y >= 1

    with db.get_conn() as conn:
        y_res = conn.execute("SELECT kwh, specific_yield FROM yearly_generation WHERE plant_id = ? AND year = '2025'", (plant_id,)).fetchone()
        assert y_res is not None
        assert y_res[0] == 6500.0


def test_hourly_retention():
    """Verify 60-day hourly retention trims older records but keeps newer records."""
    plant_id = "test_retention_plant"
    old_ts = (datetime.date.today() - datetime.timedelta(days=75)).strftime("%Y-%m-%d 12:00:00")
    new_ts = (datetime.date.today() - datetime.timedelta(days=10)).strftime("%Y-%m-%d 12:00:00")

    db.upsert_hourly([
        {"plant_id": plant_id, "ts": old_ts, "power_kw": 2.0, "energy_kwh": 1.5, "source_type": "portal_history"},
        {"plant_id": plant_id, "ts": new_ts, "power_kw": 3.0, "energy_kwh": 2.5, "source_type": "portal_history"},
    ], overwrite=True)

    res = pipeline.run_hourly_retention(retention_days=60)
    assert res["status"] == "success"
    assert res["deleted_count"] >= 1

    with db.get_conn() as conn:
        old_check = conn.execute("SELECT count(*) FROM hourly_generation WHERE plant_id = ? AND ts = ?", (plant_id, old_ts)).fetchone()[0]
        new_check = conn.execute("SELECT count(*) FROM hourly_generation WHERE plant_id = ? AND ts = ?", (plant_id, new_ts)).fetchone()[0]
        assert old_check == 0
        assert new_check == 1


def test_backfill_progress_tracking():
    """Verify backfill checkpoint recording and retrieval."""
    src = "growatt"
    pid = "test_pid_prog"
    period = "2024-05"

    db.record_backfill_progress(src, pid, "daily", period, "success", rows=31)
    progress_list = db.get_backfill_progress(source=src, plant_id=pid, status="success")
    assert any(p["period"] == period and p["rows"] == 31 for p in progress_list)


def test_monthly_and_yearly_rollups():
    """Verify rollup_monthly_from_daily and rollup_yearly_from_daily."""
    plant_id = "test_rollup_plant"
    # Seed plant
    with db.get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO plants (plant_id, plant_name, source, capacity_kwp) VALUES (?, ?, ?, ?)",
                     (plant_id, "Test Rollup Plant", "growatt", 10.0))

    # Seed 3 days of generation in 2025-04
    dates = ["2025-04-10", "2025-04-11", "2025-04-12"]
    d_rows = [
        {"plant_id": plant_id, "date": d, "kwh": 40.0, "specific_yield": 4.0, "status": "active", "source_type": "portal_history"}
        for d in dates
    ]
    db.upsert_daily(d_rows, overwrite=True)

    # Rollup month (returns count of plants rolled up)
    res_m = pipeline.rollup_monthly_from_daily("2025-04")
    assert res_m >= 1

    with db.get_conn() as conn:
        m_row = conn.execute("SELECT kwh, specific_yield FROM monthly_generation WHERE plant_id = ? AND month = '2025-04'", (plant_id,)).fetchone()
        assert m_row is not None
        assert abs(m_row[0] - 120.0) < 0.1
        assert abs(m_row[1] - 12.0) < 0.1

    # Rollup year
    res_y = pipeline.rollup_yearly_from_daily("2025")
    assert res_y >= 1

    with db.get_conn() as conn:
        y_row = conn.execute("SELECT kwh FROM yearly_generation WHERE plant_id = ? AND year = '2025'", (plant_id,)).fetchone()
        assert y_row is not None
        assert abs(y_row[0] - 120.0) < 0.1


def test_parquet_export_curated():
    """Verify PyArrow Parquet export creates valid snappy-compressed parquet files."""
    res = s3_archive.export_curated_parquet("daily")
    assert res["status"] == "success"
    assert res["rows"] >= 0
    local_path = res.get("local_path")
    assert local_path is not None
    assert os.path.exists(local_path)
    assert local_path.endswith(".parquet")


def test_expected_energy_physics_model():
    """Verify unified expected energy model produces physically realistic estimates."""
    plant_meta = {
        "plant_id": "test_ee_plant",
        "capacity_kwp": 10.0,
        "latitude": 19.07,
        "longitude": 72.87,
    }
    ee_res = expected_energy.expected_daily_kwh(plant_meta, "2026-04-15")
    assert ee_res["expected_kwh"] > 0
    assert 20.0 <= ee_res["expected_kwh"] <= 60.0
    assert ee_res["model_type"] in ("physics_fitted_pr", "regional_default", "peer_reference")


def test_health_tier_and_state_engine():
    """Verify health index evaluation, tier mapping, and distinct operational states."""
    plant = {
        "plant_id": "test_health_p1",
        "capacity_kwp": 10.0,
        "latitude": 19.07,
        "longitude": 72.87,
        "operational_status": "active",
    }
    # Test healthy operating plant
    health_normal = health.evaluate_daily_plant_health(
        plant=plant,
        date_str="2026-04-15",
        kwh=45.0,
    )
    assert health_normal["performance_tier"] in ("Best", "Good", "Could Be Better")
    assert health_normal["operational_state"] == "PRODUCING"
    assert health_normal["health_index"] is not None
    assert health_normal["health_index"] >= 0.70

    # Test plant with zero gen (comms loss or fault)
    health_zero = health.evaluate_daily_plant_health(
        plant=plant,
        date_str="2026-04-15",
        kwh=0.0,
    )
    assert health_zero["performance_tier"] == "Critical"
    assert health_zero["operational_state"] in ("FAULT", "COMMS_LOSS", "INACTIVE")


def test_features_store():
    """Verify plant_day_features creation and retrieval."""
    feat = {
        "plant_id": "test_feat_plant",
        "date": "2026-05-01",
        "actual_kwh": 35.0,
        "expected_kwh": 38.0,
        "ghi_daily": 5.2,
        "poa": 5.4,
        "specific_yield": 3.5,
        "day_status": "NORMAL",
        "quality_ok": 1,
        "peer_ref_yield": 3.6,
        "rpi": 0.92,
        "is_telemetry_gap": 0,
    }
    db.upsert_plant_day_features([feat])
    fetched = features.get_plant_features("test_feat_plant", "2026-05-01")
    assert fetched is not None
    assert fetched["kwh"] == 35.0
    assert fetched["expected_kwh"] == 38.0
    assert fetched["rpi"] == 0.92
