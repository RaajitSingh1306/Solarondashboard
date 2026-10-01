"""
Unit tests for DuckDB Analytical Lake Engine (Phase 2, Task 9).

Validates Parquet lake exports, DuckDB vectorized queries, and
fast analytics retrievals.
"""

import sys
from pathlib import Path
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import analytics_lake


def test_parquet_export_integrity():
    res = analytics_lake.export_sqlite_to_parquet()
    assert "plants_dim" in res
    assert "daily_fact" in res
    assert "gold_plant_day_features" in res
    assert res["plants_dim"] > 0
    assert res["daily_fact"] > 0


def test_duckdb_query_execution():
    df = analytics_lake.query_duckdb("SELECT 42 as answer, 'solar' as domain")
    assert not df.empty
    assert df.iloc[0]["answer"] == 42
    assert df.iloc[0]["domain"] == "solar"


def test_fleet_daily_summary():
    df = analytics_lake.get_fleet_daily_summary("2026-09-01", "2026-09-10")
    assert not df.empty
    assert "total_kwh" in df.columns
    assert "reporting_plants" in df.columns
    assert "avg_specific_yield" in df.columns


def test_plant_timeseries_retrieval():
    # Pick first plant
    plants_df = analytics_lake.query_duckdb(
        f"SELECT plant_id FROM '{analytics_lake.SILVER_DIR / 'plants_dim.parquet'}' LIMIT 1"
    )
    assert not plants_df.empty
    pid = plants_df.iloc[0]["plant_id"]

    ts_df = analytics_lake.get_plant_performance_timeseries(pid)
    assert not ts_df.empty
    assert "kwh" in ts_df.columns
    assert "date" in ts_df.columns
