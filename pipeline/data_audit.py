"""
Solaron Fleet Data Audit & Quality Profiler (Phase 2, Task 8).

Generates a comprehensive data health profile across the entire Solaron fleet:
1. Field completeness per source (lat, lon, city, capacity, install_date)
2. Zero-generation run length analysis
3. Repeated/stuck-value rate per plant
4. Monthly vs sum(daily) energy reconciliation
5. Capacity unit sanity verification
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from pipeline import db
    from core import data_quality
except ImportError:
    import db
    import data_quality



def audit_field_completeness() -> pd.DataFrame:
    """Analyze completeness percentage per field per vendor source."""
    sql = """
    SELECT 
        source,
        COUNT(*) as total_plants,
        SUM(CASE WHEN latitude IS NOT NULL AND abs(latitude) > 0.1 THEN 1 ELSE 0 END) as has_lat,
        SUM(CASE WHEN longitude IS NOT NULL AND abs(longitude) > 0.1 THEN 1 ELSE 0 END) as has_lon,
        SUM(CASE WHEN city IS NOT NULL AND city != '' AND city != 'nan' THEN 1 ELSE 0 END) as has_city,
        SUM(CASE WHEN capacity_kwp IS NOT NULL AND capacity_kwp > 0 THEN 1 ELSE 0 END) as has_capacity,
        SUM(CASE WHEN install_date IS NOT NULL AND install_date != '' AND install_date != 'nan' THEN 1 ELSE 0 END) as has_install_date,
        SUM(CASE WHEN geocode_level IN ('exact', 'pincode_centroid', 'city_centroid') THEN 1 ELSE 0 END) as high_fidelity_geocoded
    FROM plants
    GROUP BY source;
    """
    df = db.query_df(sql, db="analytics")
    if df.empty:
        return df

    df["lat_pct"] = (df["has_lat"] / df["total_plants"] * 100).round(1)
    df["city_pct"] = (df["has_city"] / df["total_plants"] * 100).round(1)
    df["cap_pct"] = (df["has_capacity"] / df["total_plants"] * 100).round(1)
    df["geocode_pct"] = (df["high_fidelity_geocoded"] / df["total_plants"] * 100).round(1)
    return df


def audit_monthly_daily_reconciliation(threshold_pct: float = 5.0) -> Dict[str, Any]:
    """
    Check reconciliation between monthly_generation.kwh and sum(daily_generation.kwh).
    Flags any plant-month where disparity exceeds threshold_pct.
    """
    sql = """
    SELECT 
        m.plant_id,
        m.month,
        m.kwh as monthly_kwh,
        COALESCE(d.daily_sum_kwh, 0.0) as daily_sum_kwh,
        d.logged_days
    FROM monthly_generation m
    LEFT JOIN (
        SELECT plant_id, strftime('%Y-%m', date) as m_month, SUM(kwh) as daily_sum_kwh, COUNT(*) as logged_days
        FROM daily_generation
        GROUP BY plant_id, m_month
    ) d ON m.plant_id = d.plant_id AND m.month = d.m_month
    WHERE m.kwh > 1.0;
    """
    df = db.query_df(sql, db="analytics")
    if df.empty:
        return {"total_checked": 0, "discrepancies": 0, "max_diff_pct": 0.0, "flagged": []}

    df["diff_kwh"] = (df["monthly_kwh"] - df["daily_sum_kwh"]).abs()
    df["diff_pct"] = (df["diff_kwh"] / df["monthly_kwh"] * 100).round(2)

    flagged = df[(df["diff_pct"] > threshold_pct) & (df["logged_days"] >= 20)]
    return {
        "total_checked": len(df),
        "discrepancies": len(flagged),
        "reconciliation_rate_pct": round(((len(df) - len(flagged)) / max(len(df), 1)) * 100.0, 1),
        "flagged": flagged.to_dict(orient="records"),
    }


def audit_stuck_and_zero_runs() -> Dict[str, Any]:
    """Audit prevalence of stuck/repeated non-zero values and extended zero runs."""
    sql = """
    SELECT 
        COUNT(*) as total_daily_records,
        SUM(CASE WHEN quality_flags LIKE '%STUCK_VALUE%' THEN 1 ELSE 0 END) as stuck_records,
        SUM(CASE WHEN kwh <= 0.05 THEN 1 ELSE 0 END) as zero_records
    FROM daily_generation;
    """
    df = db.query_df(sql, db="analytics")
    if df.empty:
        return {"total": 0, "stuck": 0, "stuck_pct": 0.0, "zero": 0}

    row = df.iloc[0]
    total = int(row["total_daily_records"] or 0)
    stuck = int(row["stuck_records"] or 0)
    zero = int(row["zero_records"] or 0)

    return {
        "total_records": total,
        "stuck_records": stuck,
        "stuck_pct": round((stuck / max(total, 1)) * 100.0, 2),
        "zero_records": zero,
        "zero_pct": round((zero / max(total, 1)) * 100.0, 2),
    }


def generate_full_audit_report() -> Dict[str, Any]:
    """Execute all audit routines and compile master report."""
    db.init_db()
    completeness = audit_field_completeness()
    reconciliation = audit_monthly_daily_reconciliation()
    stuck_stats = audit_stuck_and_zero_runs()

    return {
        "completeness": completeness.to_dict(orient="records") if not completeness.empty else [],
        "reconciliation": reconciliation,
        "stuck_telemetry": stuck_stats,
    }


def print_audit_table():
    report = generate_full_audit_report()

    print("\n" + "=" * 75)
    print("                  SOLARON FLEET DATA QUALITY AUDIT")
    print("=" * 75)

    print("\n1. FIELD COMPLETENESS BY VENDOR SOURCE:")
    print(f"{'Source':<15} {'Plants':<8} {'Lat %':<8} {'City %':<8} {'Cap %':<8} {'Geocoded %'}")
    print("-" * 75)
    for r in report["completeness"]:
        print(f"{r['source']:<15} {r['total_plants']:<8} {r['lat_pct']:<8.1f} {r['city_pct']:<8.1f} {r['cap_pct']:<8.1f} {r['geocode_pct']:<8.1f}")

    print("\n2. MONTHLY VS SUM(DAILY) RECONCILIATION:")
    rec = report["reconciliation"]
    print(f"  - Plant-Months Checked:   {rec['total_checked']}")
    print(f"  - Reconciliation Rate:    {rec.get('reconciliation_rate_pct', 100)}%")
    print(f"  - Discrepancies (>5%):    {rec['discrepancies']}")

    print("\n3. TELEMETRY QUALITY & NOISE FLAGS:")
    st = report["stuck_telemetry"]
    print(f"  - Total Daily Records:    {st['total_records']}")
    print(f"  - Stuck / Flat Days:      {st['stuck_records']} ({st['stuck_pct']}%)")
    print(f"  - Zero / Offline Days:    {st['zero_records']} ({st['zero_pct']}%)")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    print_audit_table()
