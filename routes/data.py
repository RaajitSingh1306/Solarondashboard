import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
import db
import analytics
import pipeline
import scheduler

router = APIRouter()

@router.get("/fleet")
def get_fleet(
    month: Optional[str] = Query(None, description="Month filter: YYYY-MM"),
    source: Optional[str] = Query(None, description="Platform filter: growatt, isolarcloud, suryalog"),
    status: Optional[str] = Query(None, description="Status filter: active, offline, fault"),
):
    if hasattr(month, "default"):
        month = month.default
    if hasattr(source, "default"):
        source = source.default
    if hasattr(status, "default"):
        status = status.default
    target_month = month or datetime.date.today().strftime("%Y-%m")
    sql = """
    SELECT 
        p.plant_id, p.source, p.plant_name, p.capacity_kwp, p.city,
        coalesce(p.operational_status, 'active') as operational_status,
        coalesce(d.status, 'active') as status,
        d.live_power_kw,
        d.kwh,
        d.specific_yield,
        d.yield_per_day as daily_yield_per_day,
        m.kwh as monthly_kwh,
        m.specific_yield as monthly_specific_yield,
        m.yield_per_day as monthly_yield_per_day,
        m.tier,
        m.percentile
    FROM plants p
    LEFT JOIN (
        SELECT plant_id, status, live_power_kw, kwh, specific_yield, yield_per_day, date
        FROM daily_generation
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY plant_id HAVING date = max(date)
    ) d ON p.plant_id = d.plant_id
    LEFT JOIN (
        SELECT plant_id, kwh, specific_yield, yield_per_day, tier, percentile, month
        FROM monthly_generation
        WHERE month = ?
    ) m ON p.plant_id = m.plant_id
    WHERE 1=1
    """
    params = [target_month, target_month]
    if source and source.lower() != "all":
        sql += " AND lower(p.source) = ?"
        params.append(source.lower())
    if status and status.lower() != "all":
        sql += " AND lower(d.status) = ?"
        params.append(status.lower())
    sql += " ORDER BY p.plant_name ASC;"

    df = db.query_df(sql, params, db="analytics")
    plants = df.to_dict(orient="records") if not df.empty else []
    return {
        "month": target_month,
        "count": len(plants),
        "plants": plants,
    }

@router.get("/months")
def get_months():
    return {"months": db.get_available_months()}

@router.get("/loss-waterfall/{month}")
def get_loss_waterfall(month: str):
    return analytics.get_loss_waterfall(month)

@router.get("/plant/{plant_id}")
def get_plant_cockpit(plant_id: str, month: Optional[str] = Query(None)):
    target_month = month or datetime.date.today().strftime("%Y-%m")
    plant_df = db.query_df("SELECT * FROM plants WHERE plant_id = ?", [plant_id], db="analytics")
    if plant_df.empty:
        raise HTTPException(status_code=404, detail="Plant not found")
    plant_info = plant_df.iloc[0].to_dict()

    # 30-day daily history
    daily_df = db.query_df(
        "SELECT date, kwh, specific_yield, live_power_kw, status FROM daily_generation WHERE plant_id = ? ORDER BY date DESC LIMIT 30",
        [plant_id],
        db="analytics"
    )
    daily = daily_df.iloc[::-1].to_dict(orient="records") if not daily_df.empty else []

    # 12-month monthly history
    monthly_df = db.query_df(
        "SELECT month, kwh, specific_yield, pr_pct, tier, percentile FROM monthly_generation WHERE plant_id = ? ORDER BY month DESC LIMIT 12",
        [plant_id],
        db="analytics"
    )
    monthly = monthly_df.iloc[::-1].to_dict(orient="records") if not monthly_df.empty else []

    # Inverters
    inv_df = db.query_df(
        """
        SELECT inverter_sn, max(snapshot_ts) as snapshot_ts, ac_power_w, temperature_c, e_today_kwh, fault_code, status
        FROM inverter_snapshots WHERE plant_id = ?
        GROUP BY inverter_sn
        """,
        [plant_id],
        db="analytics"
    )
    inverters = inv_df.to_dict(orient="records") if not inv_df.empty else []

    # Latest tier
    tier, percentile, explanation = analytics.classify_plant(plant_id)

    return {
        "plant": plant_info,
        "daily": daily,
        "monthly": monthly,
        "inverters": inverters,
        "tier": tier,
        "percentile": percentile,
        "explanation": explanation,
    }

@router.get("/live")
def get_live():
    counts_df = db.query_df("""
    SELECT 
        coalesce(status, 'unknown') as status, 
        count(*) as count 
    FROM (
        SELECT plant_id, status FROM daily_generation 
        GROUP BY plant_id HAVING date = max(date)
    ) GROUP BY status;
    """, db="analytics")
    status_summary = {row["status"]: row["count"] for _, row in counts_df.iterrows()}

    snaps_df = db.query_df("""
    SELECT plant_id, inverter_sn, snapshot_ts, ac_power_w, temperature_c, e_today_kwh, fault_code, status
    FROM inverter_snapshots
    ORDER BY snapshot_ts DESC LIMIT 50;
    """, db="analytics")
    snapshots = snaps_df.to_dict(orient="records") if not snaps_df.empty else []

    return {
        "status_counts": status_summary,
        "latest_snapshots": snapshots,
    }

@router.get("/ratings/current")
def get_current_ratings():
    cur_month = datetime.date.today().strftime("%Y-%m")
    return get_monthly_ratings(cur_month)

@router.get("/ratings/monthly/{month}")
def get_monthly_ratings(month: str):
    df = db.query_df("""
    SELECT 
        m.plant_id, p.plant_name, p.source, p.capacity_kwp,
        m.month, m.kwh, m.specific_yield, m.pr_pct, m.tier, m.percentile
    FROM monthly_generation m
    JOIN plants p ON m.plant_id = p.plant_id
    WHERE m.month = ?
    ORDER BY m.percentile DESC;
    """, [month], db="analytics")

    if df.empty or df["tier"].isna().all():
        analytics.classify_all(month)
        df = db.query_df("""
        SELECT 
            m.plant_id, p.plant_name, p.source, p.capacity_kwp,
            m.month, m.kwh, m.specific_yield, m.pr_pct, m.tier, m.percentile
        FROM monthly_generation m
        JOIN plants p ON m.plant_id = p.plant_id
        WHERE m.month = ?
        ORDER BY m.percentile DESC;
        """, [month], db="analytics")

    records = df.to_dict(orient="records") if not df.empty else []
    dist = {}
    for r in records:
        t = r.get("tier") or "Unknown"
        dist[t] = dist.get(t, 0) + 1

    return {
        "month": month,
        "total_rated": len(records),
        "distribution": dist,
        "plants": records,
    }

@router.get("/fleet/status")
def get_fleet_status(alerts_only: bool = Query(False, description="Return only offline and fault plants")):
    sql = """
    SELECT 
        p.plant_id, p.plant_name, p.source, p.capacity_kwp,
        d.date, d.status, d.live_power_kw, d.kwh
    FROM plants p
    JOIN (
        SELECT plant_id, date, status, live_power_kw, kwh
        FROM daily_generation
        GROUP BY plant_id HAVING date = max(date)
    ) d ON p.plant_id = d.plant_id
    """
    if alerts_only:
        sql += " WHERE d.status IN ('offline', 'fault')"
    sql += " ORDER BY d.status DESC, p.plant_name ASC;"

    df = db.query_df(sql, db="analytics")
    plants = df.to_dict(orient="records") if not df.empty else []
    return {
        "count": len(plants),
        "alerts_only": alerts_only,
        "plants": plants,
    }

@router.get("/scheduler/status")
def scheduler_status():
    return scheduler.get_job_status()

@router.post("/scheduler/trigger")
def trigger_full_extract():
    res = pipeline.run_full_extract()
    return {"status": "success", "result": res}
