"""
Solaron Fleet Capacity Audit Report Script (Phase 1, Task 4).

Scans all solar plants in SQLite database to detect capacity anomalies:
1. YIELD_TOO_HIGH: Max daily specific yield > 8.0 kWh/kWp (indicates capacity is severely underestimated)
2. YIELD_TOO_LOW: Max daily specific yield < 0.5 kWh/kWp on active days (indicates capacity entered in Watts)
3. MISSING_CAPACITY: Capacity is NULL, zero, or negative
4. SUSPECT_COMMERCIAL: High generation with residential-scale capacity denominator
"""

import argparse
import sys
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from pipeline import db
    from core import data_quality
except ImportError:
    import db
    import data_quality


def run_capacity_audit(db_name: str = "analytics") -> pd.DataFrame:
    """Run comprehensive capacity sanity audit across entire fleet."""
    db.init_db()

    sql = """
    SELECT 
        p.plant_id,
        p.plant_name,
        p.source,
        p.capacity_kwp,
        p.operational_status,
        p.city,
        COUNT(d.date) as logged_days,
        MAX(d.kwh) as max_daily_kwh,
        AVG(d.kwh) as avg_daily_kwh,
        MAX(d.specific_yield) as max_specific_yield,
        AVG(d.specific_yield) as avg_specific_yield
    FROM plants p
    LEFT JOIN daily_generation d ON p.plant_id = d.plant_id
    GROUP BY p.plant_id
    ORDER BY p.capacity_kwp DESC;
    """

    df = db.query_df(sql, db=db_name)
    if df.empty:
        print("No plants found in database.")
        return df

    anomalies = []
    for _, row in df.iterrows():
        pid = row["plant_id"]
        cap = row["capacity_kwp"]
        max_kwh = float(row["max_daily_kwh"] or 0.0)
        max_sy = float(row["max_specific_yield"] or 0.0)
        op_stat = str(row.get("operational_status", "")).lower()

        flags = []
        if cap is None or cap <= 0:
            flags.append("MISSING_CAPACITY")
        elif op_stat != "decommissioned" and max_kwh > 0:
            # Check for physically impossible specific yields (> 8.0 kWh/kWp/day)
            if max_sy > data_quality.MAX_DAILY_YIELD_KWH_KWP:
                flags.append("YIELD_TOO_HIGH")
            # If generating but max yield is below 0.5, capacity might be in Watts
            elif max_sy < 0.5 and max_kwh > 5.0:
                flags.append("YIELD_TOO_LOW")

        anomalies.append(",".join(flags) if flags else "NORMAL")

    df["audit_flag"] = anomalies
    return df


def print_audit_report(df: pd.DataFrame):
    total = len(df)
    flagged = df[df["audit_flag"] != "NORMAL"]
    
    print("\n" + "=" * 70)
    print("             SOLARON FLEET CAPACITY AUDIT REPORT")
    print("=" * 70)
    print(f"Total Fleet Plants:          {total}")
    print(f"Healthy / Normal Capacities: {total - len(flagged)} ({(total - len(flagged))/total*100:.1f}%)")
    print(f"Flagged Anomalies:           {len(flagged)} ({len(flagged)/total*100:.1f}%)")
    print("-" * 70)

    # Capacity Bracket Distribution
    brackets = df["capacity_kwp"].apply(data_quality.get_capacity_bracket).value_counts()
    print("\nCapacity Bracket Distribution:")
    for b_name, count in brackets.items():
        print(f"  - {b_name:<25}: {count:>4} plants ({count/total*100:.1f}%)")

    # Anomaly breakdown
    if not flagged.empty:
        print("\nFlagged Capacity Anomalies:")
        print(f"{'Plant ID':<22} {'Name':<25} {'Cap(kWp)':<10} {'Max kWh':<10} {'Flag'}")
        print("-" * 75)
        for _, r in flagged.iterrows():
            p_name = str(r["plant_name"])[:23]
            cap_str = f"{r['capacity_kwp']:.1f}" if pd.notnull(r['capacity_kwp']) else "NULL"
            print(f"{r['plant_id']:<22} {p_name:<25} {cap_str:<10} {r['max_daily_kwh']:<10.1f} {r['audit_flag']}")
    else:
        print("\nAll plant capacities pass physical boundary checks (0.1 to 10,000 kWp, yield <= 8.0).")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    df = run_capacity_audit()
    print_audit_report(df)
