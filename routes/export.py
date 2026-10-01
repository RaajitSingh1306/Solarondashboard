import io
import datetime
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
try:
    from pipeline import db
except ImportError:
    import db

router = APIRouter(prefix="/export")

def df_to_response(df: pd.DataFrame, filename_prefix: str, fmt: str = "csv") -> StreamingResponse:
    fmt = fmt.lower()
    if fmt == "xlsx":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        buffer.seek(0)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{filename_prefix}_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
        return StreamingResponse(
            buffer,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        buffer.seek(0)
        media_type = "text/csv"
        filename = f"{filename_prefix}_{datetime.date.today().strftime('%Y%m%d')}.csv"
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

@router.get("/fleet-daily")
def export_fleet_daily(
    fmt: str = Query("csv", description="csv or xlsx"),
    start: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
):
    sql = """
    SELECT d.date, p.plant_id, p.plant_name, p.source, p.capacity_kwp,
           d.kwh, d.specific_yield, d.yield_per_day, d.live_power_kw, d.status, d.revenue_inr
    FROM daily_generation d
    JOIN plants p ON d.plant_id = p.plant_id
    WHERE 1=1
    """
    params = []
    if start:
        sql += " AND d.date >= ?"
        params.append(start)
    if end:
        sql += " AND d.date <= ?"
        params.append(end)
    sql += " ORDER BY d.date DESC, p.plant_name ASC"
    df = db.query_df(sql, params, db="analytics")
    return df_to_response(df, "fleet_daily", fmt)

@router.get("/fleet-monthly")
def export_fleet_monthly(
    fmt: str = Query("csv"),
    month: Optional[str] = Query(None, description="Month YYYY-MM"),
):
    sql = """
    SELECT m.month, p.plant_id, p.plant_name, p.source, p.capacity_kwp,
           m.kwh, m.specific_yield, m.yield_per_day, m.pr_pct, m.tier, m.percentile, m.revenue_inr
    FROM monthly_generation m
    JOIN plants p ON m.plant_id = p.plant_id
    WHERE 1=1
    """
    params = []
    if month:
        sql += " AND m.month = ?"
        params.append(month)
    sql += " ORDER BY m.month DESC, p.plant_name ASC"
    df = db.query_df(sql, params, db="analytics")
    return df_to_response(df, "fleet_monthly", fmt)

@router.get("/fleet-status")
def export_fleet_status(fmt: str = Query("csv")):
    sql = """
    SELECT p.plant_id, p.plant_name, p.source, p.capacity_kwp, coalesce(p.operational_status, 'active') as operational_status,
           d.date as last_reported_date, d.status, d.live_power_kw, d.kwh as today_kwh
    FROM plants p
    LEFT JOIN (
        SELECT plant_id, date, status, live_power_kw, kwh
        FROM daily_generation
        GROUP BY plant_id HAVING date = max(date)
    ) d ON p.plant_id = d.plant_id
    ORDER BY d.status DESC, p.plant_name ASC
    """
    df = db.query_df(sql, db="analytics")
    return df_to_response(df, "fleet_status_snapshot", fmt)

@router.get("/ratings")
def export_ratings(
    fmt: str = Query("csv"),
    month: Optional[str] = Query(None, description="Month YYYY-MM"),
):
    if not month:
        month = datetime.date.today().strftime("%Y-%m")
    sql = """
    SELECT m.month, p.plant_id, p.plant_name, p.source, p.capacity_kwp,
           m.kwh, m.specific_yield, m.yield_per_day, m.pr_pct, m.tier, m.percentile
    FROM monthly_generation m
    JOIN plants p ON m.plant_id = p.plant_id
    WHERE m.month = ?
    ORDER BY m.percentile DESC
    """
    df = db.query_df(sql, [month], db="analytics")
    return df_to_response(df, f"ratings_{month}", fmt)

@router.get("/plant-daily")
def export_plant_daily(
    plant_id: str = Query(..., description="Target plant ID"),
    fmt: str = Query("csv"),
):
    sql = """
    SELECT date, plant_id, kwh, specific_yield, live_power_kw, status, revenue_inr
    FROM daily_generation
    WHERE plant_id = ?
    ORDER BY date DESC
    """
    df = db.query_df(sql, [plant_id], db="analytics")
    return df_to_response(df, f"plant_{plant_id}_daily", fmt)

@router.get("/plant-monthly")
def export_plant_monthly(
    plant_id: str = Query(..., description="Target plant ID"),
    fmt: str = Query("csv"),
):
    sql = """
    SELECT month, plant_id, kwh, specific_yield, pr_pct, tier, percentile, revenue_inr
    FROM monthly_generation
    WHERE plant_id = ?
    ORDER BY month DESC
    """
    df = db.query_df(sql, [plant_id], db="analytics")
    return df_to_response(df, f"plant_{plant_id}_monthly", fmt)

@router.get("/customers")
def export_customers(fmt: str = Query("csv")):
    sql = """
    SELECT c.id, c.plant_id, p.plant_name, c.customer_name, c.phone, c.email, c.preferred_lang, c.opt_in_status
    FROM customers c
    LEFT JOIN (SELECT plant_id, plant_name FROM plants) p ON c.plant_id = p.plant_id
    ORDER BY c.id ASC
    """
    df = db.query_df(sql, db="crm")
    return df_to_response(df, "crm_customers", fmt)

@router.get("/campaign")
def export_campaign(
    campaign_id: Optional[int] = Query(None, description="Campaign ID to export"),
    fmt: str = Query("csv"),
):
    sql = """
    SELECT q.id, q.campaign_id, c.customer_name, q.phone, q.message_text, q.language, q.status
    FROM message_queue q
    LEFT JOIN customers c ON q.customer_id = c.id
    WHERE 1=1
    """
    params = []
    if campaign_id:
        sql += " AND q.campaign_id = ?"
        params.append(campaign_id)
    sql += " ORDER BY q.id ASC"
    df = db.query_df(sql, params, db="crm")
    return df_to_response(df, f"campaign_{campaign_id or 'all'}", fmt)
