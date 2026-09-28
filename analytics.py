import datetime
import calendar
from typing import Any, Dict, Optional, Tuple
import pandas as pd
import requests
import db
import data_quality
import ml_analytics

INDIA_MONTHLY_GHI_DEFAULTS = {
    "01": 4.60,
    "02": 5.25,
    "03": 5.90,
    "04": 6.30,
    "05": 6.45,
    "06": 5.20,
    "07": 4.10,
    "08": 4.05,
    "09": 4.80,
    "10": 5.15,
    "11": 4.70,
    "12": 4.35,
}
STANDARD_PR_BENCHMARK = 0.75

# In-memory cache for NASA POWER GHI lookups: (lat_rounded, lon_rounded, month) -> ghi
_GHI_CACHE: Dict[Tuple[float, float, str], float] = {}

def get_ghi(lat: Optional[float], lon: Optional[float], month: str) -> float:
    """Fetch monthly average GHI (kWh/m2/day) from NASA POWER API or regional benchmark."""
    try:
        parts = month.split("-")
        m_key = f"{int(parts[1]):02d}"
    except Exception:
        m_key = "09"

    default_ghi = INDIA_MONTHLY_GHI_DEFAULTS.get(m_key, 4.80)
    if lat is None or lon is None or abs(lat) < 0.1:
        return default_ghi

    lat_r = round(lat * 2) / 2
    lon_r = round(lon * 2) / 2
    cache_key = (lat_r, lon_r, month)
    if cache_key in _GHI_CACHE:
        return _GHI_CACHE[cache_key]

    try:
        year = parts[0]
        url = "https://power.larc.nasa.gov/api/temporal/monthly/point"
        params = {
            "parameters": "ALLSKY_SFC_SW_DWN",
            "community": "RE",
            "longitude": lon_r,
            "latitude": lat_r,
            "start": year,
            "end": year,
            "format": "JSON",
        }
        res = requests.get(url, params=params, timeout=1.2)
        if res.status_code == 200:
            data = res.json()
            series = data.get("properties", {}).get("parameter", {}).get("ALLSKY_SFC_SW_DWN", {})
            val = series.get(f"{parts[0]}{parts[1]}")
            if val is not None and val > 0:
                _GHI_CACHE[cache_key] = float(val)
                return float(val)
    except Exception:
        pass

    _GHI_CACHE[cache_key] = default_ghi
    return default_ghi

def calc_pr(kwh: float, capacity_kwp: float, ghi: float, days_in_month: int) -> Optional[float]:
    """Performance Ratio = Generation (kWh) / (Installed Capacity (kWp) * GHI * Days)."""
    if not capacity_kwp or not ghi or not days_in_month:
        return None
    expected_kwh = capacity_kwp * ghi * days_in_month
    if expected_kwh <= 0:
        return None
    return round((kwh / expected_kwh) * 100.0, 2)

def specific_yield(kwh: Optional[float], kwp: Optional[float]) -> Optional[float]:
    if kwh is None or kwp is None or kwp <= 0:
        return None
    return round(kwh / kwp, 2)

def cuf(kwh: Optional[float], kwp: Optional[float], hours: Optional[int] = None) -> Optional[float]:
    """Capacity Utilisation Factor (%) = (kwh / (kwp * hours)) * 100."""
    if kwh is None or kwp is None or kwp <= 0:
        return None
    if hours is None:
        hours = 24 * 30
    return round((kwh / (kwp * hours)) * 100.0, 2)

def revenue(kwh: Optional[float], tariff_inr: float = 5.5) -> Optional[float]:
    if kwh is None:
        return None
    return round(kwh * tariff_inr, 2)

def co2_saved(kwh: Optional[float]) -> Optional[float]:
    """India CEA standard factor: 0.82 kg CO2 / kWh."""
    if kwh is None:
        return None
    return round(kwh * 0.82, 2)

def percentile_to_tier(p: float) -> str:
    if p >= 80:
        return "Best"
    if p >= 55:
        return "Good"
    if p >= 30:
        return "Could Be Better"
    if p >= 15:
        return "Needs Attention"
    return "Critical"


def sync_decommissioned_plants() -> int:
    """
    Detect plants with 0 generation in BOTH the current and previous month.
    Only mark decommissioned if both recent months show zero generation.
    Plants with ANY generation in the current month are never decommissioned.
    """
    current_month = datetime.date.today().strftime("%Y-%m")
    today = datetime.date.today()
    prev_dt = datetime.date(today.year, today.month, 1) - datetime.timedelta(days=1)
    prev_month = prev_dt.strftime("%Y-%m")

    sql = """
    SELECT 
        p.plant_id,
        p.install_date,
        p.operational_status,
        COALESCE(cur.kwh, 0.0) as current_month_kwh,
        COALESCE(prev.kwh, 0.0) as prev_month_kwh
    FROM plants p
    LEFT JOIN monthly_generation cur ON p.plant_id = cur.plant_id AND cur.month = ?
    LEFT JOIN monthly_generation prev ON p.plant_id = prev.plant_id AND prev.month = ?
    """
    df = db.query_df(sql, [current_month, prev_month], db="analytics")
    if df.empty:
        return 0

    decom_ids = []
    reactivate_ids = []
    for _, row in df.iterrows():
        cur_kwh = float(row["current_month_kwh"] or 0.0)
        prev_kwh = float(row["prev_month_kwh"] or 0.0)

        if cur_kwh > 1.0:
            # Plant generated this month — ensure it's active, not decommissioned
            if row["operational_status"] == "decommissioned":
                reactivate_ids.append(row["plant_id"])
        elif cur_kwh <= 1.0 and prev_kwh <= 1.0:
            # Zero in both current and previous month
            decom_ids.append(row["plant_id"])

    if reactivate_ids:
        placeholders = ",".join(["?"] * len(reactivate_ids))
        db.execute(
            f"UPDATE plants SET operational_status = 'active' WHERE plant_id IN ({placeholders})",
            reactivate_ids,
            db="analytics"
        )

    if decom_ids:
        placeholders = ",".join(["?"] * len(decom_ids))
        db.execute(
            f"UPDATE plants SET operational_status = 'decommissioned' WHERE plant_id IN ({placeholders})",
            decom_ids,
            db="analytics"
        )
        db.execute(
            f"UPDATE loss_analysis SET expected_kwh = 0.0, shortfall_kwh = 0.0 WHERE plant_id IN ({placeholders})",
            decom_ids,
            db="analytics"
        )
        db.execute(
            f"UPDATE expected_generation SET expected_kwh = 0.0 WHERE plant_id IN ({placeholders})",
            decom_ids,
            db="analytics"
        )
    return len(decom_ids)

def classify_all(month: Optional[str] = None) -> Dict[str, Any]:
    """
    Classify all plants for a month and write tier, percentile, pr_pct, anomaly_score, and anomaly_flag.
    Layer 1: Offline / Decommissioned / Fault filter for non-generating plants.
    Layer 2: Absolute Physics Performance Ratio (PR) tiering.
    Layer 3: Machine Learning Anomaly Detection via Isolation Forest.
    """
    if not month:
        month = datetime.date.today().strftime("%Y-%m")

    # Sync decommissioned status first
    sync_decommissioned_plants()

    try:
        parts = month.split("-")
        year = int(parts[0])
        m_int = int(parts[1])
        days_in_month = calendar.monthrange(year, m_int)[1]
    except Exception:
        days_in_month = 30

    sql = """
    SELECT 
        m.plant_id, m.month, m.kwh, m.specific_yield, m.yield_per_day,
        p.source, p.capacity_kwp, coalesce(p.latitude, 19.07) as latitude, coalesce(p.longitude, 72.87) as longitude,
        coalesce(p.operational_status, 'active') as operational_status,
        coalesce(d.status, 'active') as latest_status
    FROM monthly_generation m
    JOIN plants p ON m.plant_id = p.plant_id
    LEFT JOIN (
        SELECT plant_id, status FROM daily_generation 
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY plant_id HAVING date = max(date)
    ) d ON m.plant_id = d.plant_id
    WHERE m.month = ?;
    """
    df = db.query_df(sql, [month, month], db="analytics")
    if df.empty:
        return {"classified_count": 0, "month": month, "tiers": {}, "anomalies": 0}

    updates = []
    tier_counts = {
        "Best": 0, "Good": 0, "Could Be Better": 0, "Needs Attention": 0,
        "Critical": 0, "Offline": 0, "Fault": 0, "Decommissioned": 0
    }

    # Split active vs non-active
    kwh_vals = pd.to_numeric(df["kwh"], errors="coerce").fillna(0.0)
    active_mask = (kwh_vals > 1.0)
    non_active_df = df[~active_mask]
    active_df = df[active_mask].copy()

    for _, row in non_active_df.iterrows():
        if row["operational_status"] == "decommissioned":
            tier = "Decommissioned"
        elif row["latest_status"] == "fault":
            tier = "Fault"
        else:
            tier = "Offline"
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        updates.append({
            "plant_id": row["plant_id"],
            "month": month,
            "tier": tier,
            "percentile": 0.0,
            "pr_pct": 0.0,
            "anomaly_score": None,
            "anomaly_flag": 0
        })

    anomalies_detected = 0
    if not active_df.empty:
        # Compute GHI, theoretical energy, and absolute PR for each active plant
        pr_list = []
        for _, row in active_df.iterrows():
            cap = float(row["capacity_kwp"] or 3.3)
            if cap <= 0:
                cap = 3.3
            lat = float(row["latitude"] or 19.07)
            lon = float(row["longitude"] or 72.87)
            ghi = get_ghi(lat, lon, month)
            kwh = float(row["kwh"] or 0.0)
            theoretical = ghi * days_in_month * cap
            pr = round((kwh / theoretical) * 100.0, 1) if theoretical > 0 else 0.0
            pr_list.append(pr)

        active_df["pr_pct"] = pr_list
        # Absolute PR-based Tiering
        active_df["tier"] = active_df["pr_pct"].apply(ml_analytics.pr_to_tier)

        # Peer percentile rank by specific yield (for leaderboard & reference)
        sy = pd.to_numeric(active_df["specific_yield"], errors="coerce").fillna(0.0)
        if len(active_df) == 1:
            active_df["percentile"] = 75.0
        else:
            active_df["percentile"] = (sy.rank(pct=True) * 100.0).round(1)

        # Machine Learning Anomaly Detection via Isolation Forest
        active_scored = ml_analytics.train_and_detect_anomalies(active_df)

        for _, row in active_scored.iterrows():
            tier = row["tier"]
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
            if int(row.get("anomaly_flag", 0)) == 1:
                anomalies_detected += 1
            updates.append({
                "plant_id": row["plant_id"],
                "month": month,
                "tier": tier,
                "percentile": float(row.get("percentile", 0.0)),
                "pr_pct": float(row.get("pr_pct", 0.0)),
                "anomaly_score": float(row["anomaly_score"]) if pd.notnull(row.get("anomaly_score")) else None,
                "anomaly_flag": int(row.get("anomaly_flag", 0))
            })

    # Persist back to monthly_generation
    update_sql = """
    UPDATE monthly_generation
    SET tier = :tier,
        percentile = :percentile,
        pr_pct = :pr_pct,
        anomaly_score = :anomaly_score,
        anomaly_flag = :anomaly_flag
    WHERE plant_id = :plant_id AND month = :month;
    """
    db.executemany(update_sql, updates, db="analytics")
    return {
        "classified_count": len(updates),
        "month": month,
        "tiers": tier_counts,
        "anomalies": anomalies_detected
    }

def classify_plant(plant_id: str, month: Optional[str] = None) -> Tuple[str, float, str]:
    if not month:
        month = datetime.date.today().strftime("%Y-%m")
    row = db.query_df(
        """
        SELECT tier, percentile, pr_pct, specific_yield, yield_per_day, anomaly_score, anomaly_flag 
        FROM monthly_generation 
        WHERE plant_id = ? AND month = ?
        """,
        [plant_id, month],
        db="analytics"
    )
    if row.empty or pd.isna(row.iloc[0]["tier"]):
        # Try running classify_all
        classify_all(month)
        row = db.query_df(
            """
            SELECT tier, percentile, pr_pct, specific_yield, yield_per_day, anomaly_score, anomaly_flag 
            FROM monthly_generation 
            WHERE plant_id = ? AND month = ?
            """,
            [plant_id, month],
            db="analytics"
        )

    if row.empty:
        return "Unknown", 0.0, "No monthly data available."
    r = row.iloc[0]
    tier = str(r["tier"] or "Unknown")
    pct = float(r["percentile"] or 0.0)
    pr = float(r["pr_pct"]) if pd.notnull(r.get("pr_pct")) else None
    sy = float(r["specific_yield"]) if pd.notnull(r.get("specific_yield")) else None
    ypd = float(r["yield_per_day"]) if pd.notnull(r.get("yield_per_day")) else None
    flag = int(r.get("anomaly_flag") or 0)
    score = float(r["anomaly_score"]) if pd.notnull(r.get("anomaly_score")) else None

    explanation = ml_analytics.explain_plant_performance(
        plant_id=plant_id,
        month=month,
        tier=tier,
        pr_pct=pr,
        percentile=pct,
        specific_yield=sy,
        yield_per_day=ypd,
        anomaly_flag=flag,
        anomaly_score=score
    )
    return tier, pct, explanation

def calculate_loss_analysis(month: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate expected generation and 6-part loss attribution for all plants for the given month.
    Decomposes generation shortfalls into:
    1. Communication loss (telemetry dropouts / 0 kWh active days)
    2. Inverter shutdown / fault loss
    3. Weather / cloud irradiance deficit
    4. Soiling / panel dust accumulation
    5. Shading / obstacle obstruction
    6. Unknown / unclassified shortfall
    """
    if not month:
        month = datetime.date.today().strftime("%Y-%m")

    try:
        parts = month.split("-")
        year = int(parts[0])
        m_int = int(parts[1])
        m_key = f"{m_int:02d}"
        days_in_month = calendar.monthrange(year, m_int)[1]
    except Exception:
        year = datetime.date.today().year
        m_int = datetime.date.today().month
        m_key = f"{m_int:02d}"
        days_in_month = 30

    sql = """
    SELECT 
        p.plant_id, p.source, p.plant_name, p.capacity_kwp,
        coalesce(p.latitude, 19.07) as latitude,
        coalesce(p.longitude, 72.87) as longitude,
        coalesce(p.operational_status, 'active') as operational_status,
        coalesce(m.kwh, 0.0) as actual_kwh
    FROM plants p
    LEFT JOIN monthly_generation m ON p.plant_id = m.plant_id AND m.month = ?
    """
    df = db.query_df(sql, [month], db="analytics")
    if df.empty:
        return {"status": "no_plants", "month": month, "count": 0}

    # Query daily zero generation / offline counts for that month
    daily_stats = db.query_df("""
        SELECT plant_id, 
               count(*) as total_logged_days,
               sum(CASE WHEN kwh <= 0.05 OR status = 'offline' THEN 1 ELSE 0 END) as zero_days,
               sum(CASE WHEN status = 'fault' THEN 1 ELSE 0 END) as fault_days
        FROM daily_generation
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY plant_id
    """, [month], db="analytics")

    daily_map = {}
    if not daily_stats.empty:
        for _, r in daily_stats.iterrows():
            daily_map[str(r["plant_id"])] = {
                "zero_days": int(r["zero_days"] or 0),
                "fault_days": int(r["fault_days"] or 0),
                "total_days": int(r["total_logged_days"] or 0),
            }

    expected_rows = []
    loss_rows = []
    pr_updates = []

    for _, row in df.iterrows():
        pid = str(row["plant_id"])
        cap = float(row["capacity_kwp"] or 3.3)
        if cap <= 0:
            cap = 3.3
        actual_kwh = float(row["actual_kwh"] or 0.0)
        lat = float(row["latitude"] or 19.07)
        lon = float(row["longitude"] or 72.87)

        # 1. GHI Irradiance
        ghi = get_ghi(lat, lon, month)
        if not ghi or ghi <= 0:
            ghi = INDIA_MONTHLY_GHI_DEFAULTS.get(m_key, 4.5)

        # Decommissioned plants are extracted and listed, but excluded from loss analysis
        if row.get("operational_status") == "decommissioned":
            expected_rows.append({
                "plant_id": pid,
                "month": month,
                "expected_kwh": 0.0,
                "ghi_kwh_m2_day": round(ghi, 2),
                "latitude": lat,
                "longitude": lon,
            })
            loss_rows.append({
                "plant_id": pid,
                "month": month,
                "expected_kwh": 0.0,
                "actual_kwh": 0.0,
                "shortfall_kwh": 0.0,
                "comm_loss_kwh": 0.0,
                "shutdown_loss_kwh": 0.0,
                "weather_loss_kwh": 0.0,
                "soiling_loss_kwh": 0.0,
                "shading_loss_kwh": 0.0,
                "unknown_loss_kwh": 0.0,
                "performance_ratio": 0.0,
                "realization_rate_pct": 0.0,
            })
            pr_updates.append({
                "plant_id": pid,
                "month": month,
                "pr_pct": 0.0,
            })
            continue

        # Baseline expected kWh = GHI * Days * Capacity * Benchmark PR (0.75)
        expected_kwh = round(ghi * days_in_month * cap * STANDARD_PR_BENCHMARK, 2)
        expected_rows.append({
            "plant_id": pid,
            "month": month,
            "expected_kwh": expected_kwh,
            "ghi_kwh_m2_day": round(ghi, 2),
            "latitude": lat,
            "longitude": lon,
        })

        # Performance Ratio & Realization Rate
        theoretical_energy = ghi * days_in_month * cap
        pr = round((actual_kwh / theoretical_energy) * 100.0, 1) if theoretical_energy > 0 else 0.0
        realization = round((actual_kwh / expected_kwh) * 100.0, 1) if expected_kwh > 0 else 0.0

        pr_updates.append({
            "plant_id": pid,
            "month": month,
            "pr_pct": pr,
        })

        shortfall = max(0.0, round(expected_kwh - actual_kwh, 2))
        d_info = daily_map.get(pid, {"zero_days": 0, "fault_days": 0, "total_days": days_in_month})
        zero_ratio = (d_info["zero_days"] / max(1, days_in_month))
        fault_ratio = (d_info["fault_days"] / max(1, days_in_month))

        if shortfall <= 0.0:
            loss_rows.append({
                "plant_id": pid,
                "month": month,
                "expected_kwh": expected_kwh,
                "actual_kwh": actual_kwh,
                "shortfall_kwh": 0.0,
                "comm_loss_kwh": 0.0,
                "shutdown_loss_kwh": 0.0,
                "weather_loss_kwh": 0.0,
                "soiling_loss_kwh": 0.0,
                "shading_loss_kwh": 0.0,
                "unknown_loss_kwh": 0.0,
                "performance_ratio": pr,
                "realization_rate_pct": realization,
            })
        else:
            default_ghi = INDIA_MONTHLY_GHI_DEFAULTS.get(m_key, 4.5)
            losses = ml_analytics.calculate_adaptive_losses(
                shortfall=shortfall,
                expected_kwh=expected_kwh,
                actual_kwh=actual_kwh,
                ghi=ghi,
                default_ghi=default_ghi,
                zero_ratio=zero_ratio,
                fault_ratio=fault_ratio,
                month_str=month,
            )
            comm_loss = losses["comm_loss"]
            shutdown_loss = losses["shutdown_loss"]
            weather_loss = losses["weather_loss"]
            soiling_loss = losses["soiling_loss"]
            shading_loss = losses["shading_loss"]
            unknown_loss = losses["unknown_loss"]

            loss_rows.append({
                "plant_id": pid,
                "month": month,
                "expected_kwh": expected_kwh,
                "actual_kwh": actual_kwh,
                "shortfall_kwh": shortfall,
                "comm_loss_kwh": comm_loss,
                "shutdown_loss_kwh": shutdown_loss,
                "weather_loss_kwh": weather_loss,
                "soiling_loss_kwh": soiling_loss,
                "shading_loss_kwh": shading_loss,
                "unknown_loss_kwh": unknown_loss,
                "performance_ratio": pr,
                "realization_rate_pct": realization,
            })

    if expected_rows:
        db.upsert_expected_generation(expected_rows)
    if loss_rows:
        db.upsert_loss_analysis(loss_rows)
    if pr_updates:
        db.executemany("UPDATE monthly_generation SET pr_pct = :pr_pct WHERE plant_id = :plant_id AND month = :month", pr_updates, db="analytics")

    return {
        "status": "success",
        "month": month,
        "plants_calculated": len(loss_rows),
    }

def get_loss_waterfall(month: Optional[str] = None, source: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve aggregated fleet loss analysis and waterfall metrics for the given month and optional platform."""
    if not month:
        month = datetime.date.today().strftime("%Y-%m")

    sql = """
    SELECT 
        count(l.plant_id) as total_plants,
        sum(l.expected_kwh) as total_expected_kwh,
        sum(l.actual_kwh) as total_actual_kwh,
        sum(l.shortfall_kwh) as total_shortfall_kwh,
        sum(l.comm_loss_kwh) as total_comm_loss,
        sum(l.shutdown_loss_kwh) as total_shutdown_loss,
        sum(l.weather_loss_kwh) as total_weather_loss,
        sum(l.soiling_loss_kwh) as total_soiling_loss,
        sum(l.shading_loss_kwh) as total_shading_loss,
        sum(l.unknown_loss_kwh) as total_unknown_loss,
        avg(CASE WHEN l.expected_kwh > 0 THEN l.performance_ratio END) as avg_pr,
        avg(CASE WHEN l.expected_kwh > 0 THEN l.realization_rate_pct END) as avg_realization
    FROM loss_analysis l
    JOIN plants p ON l.plant_id = p.plant_id
    WHERE l.month = ? AND (p.operational_status IS NULL OR p.operational_status != 'decommissioned')
    """
    params = [month]
    if source and source.lower() != "all":
        sql += " AND lower(p.source) = ?"
        params.append(source.lower())

    df = db.query_df(sql, params, db="analytics")
    if df.empty or not df.iloc[0]["total_plants"] or df.iloc[0]["total_plants"] == 0:
        # Calculate on the fly if not present
        calculate_loss_analysis(month)
        df = db.query_df(sql, params, db="analytics")

    if df.empty or not df.iloc[0]["total_plants"] or int(df.iloc[0]["total_plants"]) == 0:
        return {
            "month": month,
            "source": source or "All",
            "total_plants": 0,
            "expected_kwh": 0.0,
            "actual_kwh": 0.0,
            "shortfall_kwh": 0.0,
            "comm_loss_kwh": 0.0,
            "shutdown_loss_kwh": 0.0,
            "weather_loss_kwh": 0.0,
            "soiling_loss_kwh": 0.0,
            "shading_loss_kwh": 0.0,
            "unknown_loss_kwh": 0.0,
            "avg_pr": 0.0,
            "avg_realization": 0.0,
        }

    r = df.iloc[0]
    return {
        "month": month,
        "source": source or "All",
        "total_plants": int(r["total_plants"] or 0),
        "expected_kwh": round(float(r["total_expected_kwh"] or 0.0), 1),
        "actual_kwh": round(float(r["total_actual_kwh"] or 0.0), 1),
        "shortfall_kwh": round(float(r["total_shortfall_kwh"] or 0.0), 1),
        "comm_loss_kwh": round(float(r["total_comm_loss"] or 0.0), 1),
        "shutdown_loss_kwh": round(float(r["total_shutdown_loss"] or 0.0), 1),
        "weather_loss_kwh": round(float(r["total_weather_loss"] or 0.0), 1),
        "soiling_loss_kwh": round(float(r["total_soiling_loss"] or 0.0), 1),
        "shading_loss_kwh": round(float(r["total_shading_loss"] or 0.0), 1),
        "unknown_loss_kwh": round(float(r["total_unknown_loss"] or 0.0), 1),
        "avg_pr": round(float(r["avg_pr"] or 0.0), 1),
        "avg_realization": round(float(r["avg_realization"] or 0.0), 1),
    }

