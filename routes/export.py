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

MONTHLY_COLUMNS = {
    # Plant Profile
    "plant_id": {
        "label": "Plant ID",
        "group": "Plant Profile",
        "expr": "p.plant_id",
        "default": True,
    },
    "plant_name": {
        "label": "Plant Name",
        "group": "Plant Profile",
        "expr": "p.plant_name",
        "default": True,
    },
    "source": {
        "label": "Platform",
        "group": "Plant Profile",
        "expr": "p.source",
        "default": True,
    },
    "capacity_kwp": {
        "label": "Capacity (kWp)",
        "group": "Plant Profile",
        "expr": "p.capacity_kwp",
        "default": True,
    },
    "operational_status": {
        "label": "Operational Status",
        "group": "Plant Profile",
        "expr": "coalesce(p.operational_status, 'active')",
        "default": True,
    },
    "city": {
        "label": "City",
        "group": "Plant Profile",
        "expr": "p.city",
        "default": False,
    },
    "install_date": {
        "label": "Install Date",
        "group": "Plant Profile",
        "expr": "p.install_date",
        "default": False,
    },
    "inverter_model": {
        "label": "Inverter Model",
        "group": "Plant Profile",
        "expr": "p.inverter_model",
        "default": False,
    },
    "panel_model": {
        "label": "Panel Model",
        "group": "Plant Profile",
        "expr": "p.panel_model",
        "default": False,
    },

    # Generation & Yield
    "month": {
        "label": "Month (YYYY-MM)",
        "group": "Generation & Yield",
        "expr": "m.month",
        "default": True,
    },
    "kwh": {
        "label": "Total Generation (kWh)",
        "group": "Generation & Yield",
        "expr": "m.kwh",
        "default": True,
    },
    "specific_yield": {
        "label": "Specific Yield (kWh/kWp)",
        "group": "Generation & Yield",
        "expr": "m.specific_yield",
        "default": True,
    },
    "yield_per_day": {
        "label": "Yield per Day (Units/kWp/day)",
        "group": "Generation & Yield",
        "expr": "m.yield_per_day",
        "default": True,
    },
    "revenue_inr": {
        "label": "Est. Savings (INR)",
        "group": "Generation & Yield",
        "expr": "m.revenue_inr",
        "default": True,
    },

    # Performance & Health
    "pr_pct": {
        "label": "Performance Ratio (%)",
        "group": "Performance & Health",
        "expr": "m.pr_pct",
        "default": True,
    },
    "tier": {
        "label": "Performance Tier",
        "group": "Performance & Health",
        "expr": "m.tier",
        "default": True,
    },
    "percentile": {
        "label": "Fleet Percentile",
        "group": "Performance & Health",
        "expr": "m.percentile",
        "default": True,
    },
    "anomaly_score": {
        "label": "Anomaly Score",
        "group": "Performance & Health",
        "expr": "m.anomaly_score",
        "default": False,
    },
    "anomaly_flag": {
        "label": "Anomaly Flag",
        "group": "Performance & Health",
        "expr": "m.anomaly_flag",
        "default": False,
    },

    # Loss Attribution & NASA Benchmark
    "expected_kwh": {
        "label": "Expected Baseline (kWh)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "eg.expected_kwh",
        "default": False,
    },
    "ghi_kwh_m2_day": {
        "label": "NASA GHI (kWh/m2/day)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "eg.ghi_kwh_m2_day",
        "default": False,
    },
    "shortfall_kwh": {
        "label": "Net Shortfall (kWh)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "la.shortfall_kwh",
        "default": False,
    },
    "comm_loss_kwh": {
        "label": "Communication Loss (kWh)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "la.comm_loss_kwh",
        "default": False,
    },
    "shutdown_loss_kwh": {
        "label": "Shutdown Loss (kWh)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "la.shutdown_loss_kwh",
        "default": False,
    },
    "weather_loss_kwh": {
        "label": "Weather Irradiance Loss (kWh)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "la.weather_loss_kwh",
        "default": False,
    },
    "soiling_loss_kwh": {
        "label": "Soiling Loss (kWh)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "la.soiling_loss_kwh",
        "default": False,
    },
    "shading_loss_kwh": {
        "label": "Shading Loss (kWh)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "la.shading_loss_kwh",
        "default": False,
    },
    "unknown_loss_kwh": {
        "label": "Unattributed Loss (kWh)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "la.unknown_loss_kwh",
        "default": False,
    },
    "realization_rate_pct": {
        "label": "Realization Rate (%)",
        "group": "Loss Attribution (NASA Benchmark)",
        "expr": "la.realization_rate_pct",
        "default": False,
    },
}

DAILY_COLUMNS = {
    "plant_id": {
        "label": "Plant ID",
        "group": "Plant Profile",
        "expr": "p.plant_id",
        "default": True,
    },
    "plant_name": {
        "label": "Plant Name",
        "group": "Plant Profile",
        "expr": "p.plant_name",
        "default": True,
    },
    "source": {
        "label": "Platform",
        "group": "Plant Profile",
        "expr": "p.source",
        "default": True,
    },
    "capacity_kwp": {
        "label": "Capacity (kWp)",
        "group": "Plant Profile",
        "expr": "p.capacity_kwp",
        "default": True,
    },
    "city": {
        "label": "City",
        "group": "Plant Profile",
        "expr": "p.city",
        "default": False,
    },
    "date": {
        "label": "Date (YYYY-MM-DD)",
        "group": "Daily Telemetry",
        "expr": "d.date",
        "default": True,
    },
    "kwh": {
        "label": "Daily Generation (kWh)",
        "group": "Daily Telemetry",
        "expr": "d.kwh",
        "default": True,
    },
    "specific_yield": {
        "label": "Specific Yield (kWh/kWp)",
        "group": "Daily Telemetry",
        "expr": "d.specific_yield",
        "default": True,
    },
    "yield_per_day": {
        "label": "Yield per Day (Units/kWp/day)",
        "group": "Daily Telemetry",
        "expr": "d.yield_per_day",
        "default": True,
    },
    "live_power_kw": {
        "label": "Live Power (kW)",
        "group": "Daily Telemetry",
        "expr": "d.live_power_kw",
        "default": True,
    },
    "status": {
        "label": "Status",
        "group": "Daily Telemetry",
        "expr": "d.status",
        "default": True,
    },
    "revenue_inr": {
        "label": "Est. Savings (INR)",
        "group": "Daily Telemetry",
        "expr": "d.revenue_inr",
        "default": True,
    },
    "quality_flags": {
        "label": "Quality Flags",
        "group": "Daily Telemetry",
        "expr": "d.quality_flags",
        "default": False,
    },
    "last_log_time": {
        "label": "Last Log Time",
        "group": "Daily Telemetry",
        "expr": "d.last_log_time",
        "default": False,
    },
}

@router.get("/columns")
def get_export_columns(dataset: str = Query("monthly", description="monthly or daily")):
    """Return available export column definitions with grouping and default selections."""
    registry = MONTHLY_COLUMNS if dataset == "monthly" else DAILY_COLUMNS
    return [
        {
            "key": k,
            "label": meta["label"],
            "group": meta["group"],
            "default": meta["default"],
        }
        for k, meta in registry.items()
    ]

def _get_val(param, default=None):
    if param is None or hasattr(param, "default"):
        return default
    return param

@router.get("/fleet-daily")
def export_fleet_daily(
    fmt: str = Query("csv", description="csv or xlsx"),
    cols: Optional[str] = Query(None, description="Comma-separated column keys"),
    month: Optional[str] = Query(None, description="Filter single month YYYY-MM"),
    start: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    source: Optional[str] = Query(None, description="Platform filter"),
    include_decom: bool = Query(True, description="Whether to include decommissioned plants"),
):
    fmt_str = str(_get_val(fmt, "csv")).lower()
    cols_val = _get_val(cols)
    month_val = _get_val(month)
    start_val = _get_val(start)
    end_val = _get_val(end)
    source_val = _get_val(source)
    include_decom_val = bool(_get_val(include_decom, True))

    if cols_val:
        requested_keys = [c.strip() for c in cols_val.split(",") if c.strip() in DAILY_COLUMNS]
    else:
        requested_keys = []
    if not requested_keys:
        requested_keys = [k for k, meta in DAILY_COLUMNS.items() if meta["default"]]

    select_clauses = [f"{DAILY_COLUMNS[k]['expr']} AS \"{DAILY_COLUMNS[k]['label']}\"" for k in requested_keys]
    select_str = ", ".join(select_clauses)

    sql = f"""
    SELECT {select_str}
    FROM daily_generation d
    JOIN plants p ON d.plant_id = p.plant_id
    WHERE 1=1
    """
    params = []
    if month_val and month_val != "All":
        sql += " AND d.date >= ? AND d.date <= ?"
        params.append(f"{month_val}-01")
        params.append(f"{month_val}-31")
    else:
        if start_val:
            sql += " AND d.date >= ?"
            params.append(start_val)
        if end_val:
            sql += " AND d.date <= ?"
            params.append(end_val)

    if source_val and source_val != "All":
        sql += " AND p.source = ?"
        params.append(source_val.lower())

    if not include_decom_val:
        sql += " AND coalesce(p.operational_status, 'active') != 'decommissioned'"

    sql += " ORDER BY d.date DESC, p.plant_name ASC"
    df = db.query_df(sql, params, db="analytics")
    prefix = f"fleet_daily_{month_val}" if (month_val and month_val != "All") else "fleet_daily"
    return df_to_response(df, prefix, fmt_str)

@router.get("/fleet-monthly")
def export_fleet_monthly(
    fmt: str = Query("csv", description="csv or xlsx"),
    cols: Optional[str] = Query(None, description="Comma-separated column keys"),
    month: Optional[str] = Query(None, description="Target month YYYY-MM"),
    start_month: Optional[str] = Query(None, description="Start month YYYY-MM"),
    end_month: Optional[str] = Query(None, description="End month YYYY-MM"),
    source: Optional[str] = Query(None, description="Platform filter: growatt, isolarcloud, suryalog"),
    include_decom: bool = Query(True, description="Whether to include decommissioned plants"),
):
    fmt_str = str(_get_val(fmt, "csv")).lower()
    cols_val = _get_val(cols)
    month_val = _get_val(month)
    start_month_val = _get_val(start_month)
    end_month_val = _get_val(end_month)
    source_val = _get_val(source)
    include_decom_val = bool(_get_val(include_decom, True))

    if cols_val:
        requested_keys = [c.strip() for c in cols_val.split(",") if c.strip() in MONTHLY_COLUMNS]
    else:
        requested_keys = []
    if not requested_keys:
        requested_keys = [k for k, meta in MONTHLY_COLUMNS.items() if meta["default"]]

    select_clauses = [f"{MONTHLY_COLUMNS[k]['expr']} AS \"{MONTHLY_COLUMNS[k]['label']}\"" for k in requested_keys]
    select_str = ", ".join(select_clauses)

    sql = f"""
    SELECT {select_str}
    FROM monthly_generation m
    JOIN plants p ON m.plant_id = p.plant_id
    LEFT JOIN expected_generation eg ON m.plant_id = eg.plant_id AND m.month = eg.month
    LEFT JOIN loss_analysis la ON m.plant_id = la.plant_id AND m.month = la.month
    WHERE 1=1
    """
    params = []
    if month_val and month_val != "All":
        sql += " AND m.month = ?"
        params.append(month_val)
    else:
        if start_month_val:
            sql += " AND m.month >= ?"
            params.append(start_month_val)
        if end_month_val:
            sql += " AND m.month <= ?"
            params.append(end_month_val)

    if source_val and source_val != "All":
        sql += " AND p.source = ?"
        params.append(source_val.lower())

    if not include_decom_val:
        sql += " AND coalesce(p.operational_status, 'active') != 'decommissioned'"

    sql += " ORDER BY m.month DESC, p.plant_name ASC"
    df = db.query_df(sql, params, db="analytics")
    prefix = f"fleet_monthly_{month_val}" if (month_val and month_val != "All") else "fleet_monthly"
    return df_to_response(df, prefix, fmt_str)

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
