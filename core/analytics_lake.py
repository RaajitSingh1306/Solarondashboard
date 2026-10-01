"""
Solaron DuckDB Analytical Lake Engine (Phase 2, Task 9).

Provides ultra-fast columnar analytical queries and Medallion Lake export:
- Reads directly from SQLite DB and Parquet files
- Silver layer: plants_dim, daily_fact, snapshots_fact
- Gold layer: plant_day_features, plant_month_summary
- High-performance vectorized OLAP aggregates via DuckDB
"""

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import duckdb
import pandas as pd
from config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
LAKE_ROOT = BASE_DIR / "data" / "lake"
SILVER_DIR = LAKE_ROOT / "silver"
GOLD_DIR = LAKE_ROOT / "gold"


def get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    """Initialize an in-memory DuckDB connection with sqlite extension loaded."""
    conn = duckdb.connect(":memory:")
    try:
        conn.execute("INSTALL sqlite; LOAD sqlite;")
    except Exception:
        pass
    return conn


def export_sqlite_to_parquet(db_path: Optional[str] = None) -> Dict[str, int]:
    """
    Export operational SQLite analytics tables to columnar Parquet files in Silver Lake.
    """
    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    sqlite_db = db_path or settings.resolved_solar_analytics_db_path
    conn = get_duckdb_conn()
    counts = {}

    try:
        # Attach SQLite DB
        conn.execute(f"ATTACH '{sqlite_db}' AS sqlite_db (TYPE SQLITE);")

        # 1. Plants Dimension -> Silver
        plants_parquet = SILVER_DIR / "plants_dim.parquet"
        conn.execute(f"""
            COPY (
                SELECT plant_id, source, plant_name, capacity_kwp, latitude, longitude,
                       city, install_date, inverter_model, panel_model, operational_status,
                       geocode_level, updated_at
                FROM sqlite_db.plants
            ) TO '{plants_parquet}' (FORMAT PARQUET);
        """)
        counts["plants_dim"] = conn.execute(f"SELECT COUNT(*) FROM '{plants_parquet}'").fetchone()[0]

        # 2. Daily Fact -> Silver
        daily_parquet = SILVER_DIR / "daily_fact.parquet"
        conn.execute(f"""
            COPY (
                SELECT plant_id, date, kwh, revenue_inr, specific_yield, yield_per_day,
                       live_power_kw, status, quality_flags, last_log_time
                FROM sqlite_db.daily_generation
            ) TO '{daily_parquet}' (FORMAT PARQUET);
        """)
        counts["daily_fact"] = conn.execute(f"SELECT COUNT(*) FROM '{daily_parquet}'").fetchone()[0]

        # 3. Monthly Fact -> Silver
        monthly_parquet = SILVER_DIR / "monthly_fact.parquet"
        conn.execute(f"""
            COPY (
                SELECT plant_id, month, kwh, revenue_inr, specific_yield, yield_per_day,
                       pr_pct, tier, percentile, anomaly_score, anomaly_flag
                FROM sqlite_db.monthly_generation
            ) TO '{monthly_parquet}' (FORMAT PARQUET);
        """)
        counts["monthly_fact"] = conn.execute(f"SELECT COUNT(*) FROM '{monthly_parquet}'").fetchone()[0]

        # 4. Gold Layer: Plant Day Features
        gold_features_parquet = GOLD_DIR / "plant_day_features.parquet"
        conn.execute(f"""
            COPY (
                SELECT 
                    d.plant_id,
                    d.date,
                    p.source,
                    p.capacity_kwp,
                    p.city,
                    p.geocode_level,
                    d.kwh,
                    d.specific_yield,
                    d.yield_per_day,
                    d.revenue_inr,
                    d.status,
                    d.quality_flags,
                    CASE WHEN d.quality_flags LIKE '%STUCK_VALUE%' THEN 1 ELSE 0 END as is_stuck,
                    CASE WHEN d.kwh <= 0.05 THEN 1 ELSE 0 END as is_zero
                FROM '{daily_parquet}' d
                LEFT JOIN '{plants_parquet}' p ON d.plant_id = p.plant_id
            ) TO '{gold_features_parquet}' (FORMAT PARQUET);
        """)
        counts["gold_plant_day_features"] = conn.execute(f"SELECT COUNT(*) FROM '{gold_features_parquet}'").fetchone()[0]

    finally:
        conn.close()

    return counts


def query_duckdb(sql: str, params: Optional[List[Any]] = None) -> pd.DataFrame:
    """Execute arbitrary SQL query in DuckDB, returning a pandas DataFrame."""
    conn = get_duckdb_conn()
    try:
        if params:
            df = conn.execute(sql, params).df()
        else:
            df = conn.execute(sql).df()
        return df
    finally:
        conn.close()


def get_fleet_daily_summary(start_date: str, end_date: str) -> pd.DataFrame:
    """Fast analytical aggregate of daily fleet generation between two dates."""
    daily_parquet = SILVER_DIR / "daily_fact.parquet"
    if not daily_parquet.exists():
        export_sqlite_to_parquet()

    sql = f"""
    SELECT 
        date,
        COUNT(DISTINCT plant_id) as reporting_plants,
        SUM(kwh) as total_kwh,
        AVG(specific_yield) as avg_specific_yield,
        SUM(revenue_inr) as total_revenue_inr,
        SUM(CASE WHEN quality_flags LIKE '%STUCK_VALUE%' THEN 1 ELSE 0 END) as stuck_plant_count,
        SUM(CASE WHEN kwh <= 0.05 THEN 1 ELSE 0 END) as zero_plant_count
    FROM '{daily_parquet}'
    WHERE date >= ? AND date <= ?
    GROUP BY date
    ORDER BY date ASC;
    """
    return query_duckdb(sql, [start_date, end_date])


def get_plant_performance_timeseries(plant_id: str) -> pd.DataFrame:
    """Fast retrieval of a single plant's daily generation timeseries from Parquet lake."""
    daily_parquet = SILVER_DIR / "daily_fact.parquet"
    if not daily_parquet.exists():
        export_sqlite_to_parquet()

    sql = f"""
    SELECT date, kwh, specific_yield, yield_per_day, revenue_inr, status, quality_flags
    FROM '{daily_parquet}'
    WHERE plant_id = ?
    ORDER BY date ASC;
    """
    return query_duckdb(sql, [plant_id])
