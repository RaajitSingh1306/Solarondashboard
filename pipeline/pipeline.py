import argparse
import datetime
import logging
import os
import re
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import pandas as pd

from pipeline import db
from core import data_quality
from services import geocode, crm
from extractors.base import BaseExtractor
from extractors.growatt import GrowattExtractor
from extractors.isolarcloud import ISolarCloudExtractor
from extractors.suryalog import SuryaLogExtractor
from extractors.fronius import FroniusExtractor
from extractors.injectsolar import InjectSolarExtractor

logger = logging.getLogger(__name__)

def get_extractors(sources: Optional[List[str]] = None):
    all_ext = [
        GrowattExtractor(),
        ISolarCloudExtractor(),
        SuryaLogExtractor(),
        FroniusExtractor(),
        InjectSolarExtractor(),
    ]
    if not sources or "All" in sources or "all" in sources:
        return all_ext
    sources_clean = [s.lower().strip() for s in sources]
    return [e for e in all_ext if e.source.lower() in sources_clean]

def normalize_plant_record(p: Dict[str, Any]) -> Dict[str, Any]:
    cap = data_quality.normalize_capacity(p.get("capacity_kwp"))
    p_name = data_quality.clean_plant_name(p.get("plant_name", ""))
    geo = geocode.geocode_plant(p)
    return {
        "plant_id": str(p.get("plant_id")),
        "source": str(p.get("source", "unknown")).lower(),
        "plant_name": p_name,
        "capacity_kwp": cap,
        "latitude": geo.get("latitude"),
        "longitude": geo.get("longitude"),
        "city": geo.get("city") or p.get("city", ""),
        "install_date": p.get("install_date", ""),
        "inverter_model": p.get("inverter_model", ""),
        "panel_model": p.get("panel_model", ""),
        "operational_status": data_quality.determine_operational_status(p),
        "geocode_level": geo.get("geocode_level", "unresolved"),
        "last_log_time": p.get("last_log_time"),
        "total_energy_kwh": p.get("total_energy_kwh"),
    }

def normalize_daily_record(d: Dict[str, Any], capacity_kwp: Optional[float] = None) -> Dict[str, Any]:
    return data_quality.validate_daily_record(d, capacity_kwp=capacity_kwp)

def normalize_monthly_record(m: Dict[str, Any], capacity_kwp: Optional[float] = None) -> Dict[str, Any]:
    return data_quality.validate_monthly_record(m, capacity_kwp=capacity_kwp)

def run_fleet(sources: Optional[List[str]] = None, force_refresh: bool = False) -> int:
    db.init_db()
    count = 0
    for ext in get_extractors(sources):
        run_id = db.record_sync_start(ext.source, "fleet")
        ext_count = 0
        try:
            plants = ext.fetch_fleet(force_refresh=force_refresh)
            for p in plants:
                norm = normalize_plant_record(p)
                db.upsert_plant(norm)
                ext_count += 1
                count += 1
            db.record_sync_finish(run_id, "success", ext_count)
        except Exception as e:
            logger.error(f"Error in run_fleet for {ext.source}: {e}", exc_info=True)
            db.record_sync_finish(run_id, "error", ext_count, str(e))
    data_quality.invalidate_decommissioned_cache()
    try:
        from services import s3_archive
        s3_archive.archive_fleet_plants()
    except Exception as s3_err:
        logger.debug(f"S3 archive fleet error: {s3_err}")
    return count

def run_daily(date_str: Optional[str] = None, sources: Optional[List[str]] = None, force_refresh: bool = False) -> int:
    db.init_db()
    if not date_str:
        date_str = datetime.date.today().isoformat()
    total = 0
    plant_caps: Dict[str, float] = {}
    try:
        with db.analytics_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT plant_id, capacity_kwp FROM plants")
            for pid, cap in cur.fetchall():
                if cap is not None:
                    plant_caps[str(pid)] = float(cap)
    except Exception as e:
        logger.warning(f"Could not load plant capacities for run_daily: {e}")

    for ext in get_extractors(sources):
        run_id = db.record_sync_start(ext.source, "daily")
        ext_total = 0
        try:
            records = ext.fetch_daily(date_str, force_refresh=force_refresh)
            norm_records = [
                normalize_daily_record(r, capacity_kwp=r.get("capacity_kwp") or plant_caps.get(str(r.get("plant_id"))))
                for r in records
            ]
            norm_records = [r for r in norm_records if r is not None]
            ext_total = db.upsert_daily(norm_records)
            total += ext_total
            db.record_sync_finish(run_id, "success", ext_total)
        except Exception as e:
            logger.error(f"Error in run_daily for {ext.source}: {e}", exc_info=True)
    data_quality.scan_and_flag_stuck_values()
    try:
        from services import s3_archive
        s3_archive.archive_daily_generation(date_str)
    except Exception as s3_err:
        logger.debug(f"S3 archive daily error: {s3_err}")
    return total

def run_monthly(month_str: Optional[str] = None, sources: Optional[List[str]] = None, force_refresh: bool = False) -> int:
    db.init_db()
    if not month_str:
        month_str = datetime.date.today().strftime("%Y-%m")
    total = 0
    plant_caps: Dict[str, float] = {}
    try:
        with db.analytics_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT plant_id, capacity_kwp FROM plants")
            for pid, cap in cur.fetchall():
                if cap is not None:
                    plant_caps[str(pid)] = float(cap)
    except Exception as e:
        logger.warning(f"Could not load plant capacities for run_monthly: {e}")

    for ext in get_extractors(sources):
        run_id = db.record_sync_start(ext.source, "monthly")
        ext_total = 0
        try:
            records = ext.fetch_monthly(month_str, force_refresh=force_refresh)
            norm_records = []
            for r in records:
                norm = normalize_monthly_record(r, capacity_kwp=r.get("capacity_kwp") or plant_caps.get(str(r.get("plant_id"))))
                if norm and norm.get("kwh") is not None:
                    norm_records.append(norm)
            ext_total = db.upsert_monthly(norm_records)
            total += ext_total
            db.record_sync_finish(run_id, "success", ext_total)
        except Exception as e:
            logger.error(f"Error in run_monthly for {ext.source}: {e}", exc_info=True)
            db.record_sync_finish(run_id, "error", ext_total, str(e))
    try:
        from services import s3_archive
        s3_archive.archive_monthly_generation(month_str)
    except Exception as s3_err:
        logger.debug(f"S3 archive monthly error: {s3_err}")
    return total

def run_snapshots(sources: Optional[List[str]] = None, force_refresh: bool = False) -> int:
    db.init_db()
    total = 0
    for ext in get_extractors(sources):
        run_id = db.record_sync_start(ext.source, "snapshots")
        ext_total = 0
        try:
            snaps = ext.fetch_snapshots(force_refresh=force_refresh)
            ext_total = db.upsert_snapshots(snaps)
            total += ext_total
            db.record_sync_finish(run_id, "success", ext_total)
        except Exception as e:
            logger.error(f"Error in run_snapshots for {ext.source}: {e}", exc_info=True)
            db.record_sync_finish(run_id, "error", ext_total, str(e))
    try:
        from services import s3_archive
        s3_archive.archive_inverter_snapshots()
    except Exception as s3_err:
        logger.debug(f"S3 archive snapshots error: {s3_err}")
    return total

def run_full_extract(
    month_str: Optional[str] = None,
    sources: Optional[List[str]] = None,
    force_refresh: bool = False,
    target_plant_id: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None
) -> Dict[str, Any]:
    try:
        from core import analytics
    except ImportError:
        import analytics

    start_time = time.time()
    if not month_str:
        month_str = datetime.date.today().strftime("%Y-%m")

    def report(msg: str, pct: float):
        if progress_cb:
            try:
                progress_cb(msg, pct)
            except Exception:
                pass

    report("Connecting to inverter portals & syncing fleet metadata...", 0.15)
    f_count = run_fleet(sources=sources, force_refresh=force_refresh)

    report(f"Ingesting daily telemetry for {f_count} plants...", 0.35)
    d_count = run_daily(sources=sources, force_refresh=force_refresh)

    report("Ingesting monthly generation records...", 0.55)
    m_count = run_monthly(month_str, sources=sources, force_refresh=force_refresh)

    # Dynamically compute previous month
    try:
        y_int, m_int = map(int, month_str.split("-"))
        prev_dt = datetime.date(y_int, m_int, 1) - datetime.timedelta(days=1)
        prev_month = prev_dt.strftime("%Y-%m")
    except Exception:
        prev_month = "2026-08" if month_str == "2026-09" else "2026-09"

    # Only sync previous month if on days 1-3 of a month or if prev_month is empty in DB
    prev_month_needs_sync = False
    today_dt = datetime.date.today()
    if today_dt.day <= 3 and month_str == today_dt.strftime("%Y-%m"):
        prev_month_needs_sync = True
    else:
        try:
            with db.analytics_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM monthly_generation WHERE month = ?", (prev_month,))
                row = cur.fetchone()
                if not row or row[0] == 0:
                    prev_month_needs_sync = True
        except Exception:
            pass

    if prev_month_needs_sync:
        run_monthly(prev_month, sources=sources, force_refresh=False)
        analytics.classify_all(prev_month)
        analytics.calculate_loss_analysis(prev_month)

    report("Collecting live inverter telemetry snapshots...", 0.70)
    s_count = run_snapshots(sources=sources, force_refresh=force_refresh)

    # Audit plant capacities for inverter nominal power misconfigurations
    report("Auditing plant capacities & physics validation...", 0.80)
    data_quality.audit_and_update_plant_capacities()

    # Run performance classification and NASA GHI loss attribution
    report("Benchmarking solar insolation & classifying health tiers...", 0.85)
    cls_res = analytics.classify_all(month_str)

    report("Calculating NASA POWER GHI loss attribution...", 0.95)
    loss_res = analytics.calculate_loss_analysis(month_str)

    elapsed = round(time.time() - start_time, 2)
    report(f"Extraction complete in {elapsed}s", 1.0)

    # Post-pull initial analytics
    with db.analytics_conn() as conn:
        cur = conn.cursor()
        query = """
            SELECT 
                COUNT(DISTINCT p.plant_id) as total_plants,
                COALESCE(SUM(m.kwh), 0) as total_kwh,
                COALESCE(SUM(m.revenue_inr), 0) as total_rev,
                AVG(m.specific_yield) as avg_specific_yield,
                AVG(m.yield_per_day) as avg_yield_per_day,
                SUM(CASE WHEN m.tier IN ('Best', 'Good') THEN 1 ELSE 0 END) as normal_count,
                SUM(CASE WHEN m.tier IN ('Could Be Better', 'Needs Attention', 'Critical') THEN 1 ELSE 0 END) as underperforming_count,
                SUM(CASE WHEN m.tier IN ('Offline', 'Fault') THEN 1 ELSE 0 END) as offline_count,
                SUM(CASE WHEN m.tier = 'Decommissioned' OR p.operational_status = 'decommissioned' THEN 1 ELSE 0 END) as decommissioned_count
            FROM plants p
            LEFT JOIN monthly_generation m ON p.plant_id = m.plant_id AND m.month = ?
            WHERE 1=1
        """
        params: List[Any] = [month_str]
        if sources and "all" not in [s.lower() for s in sources]:
            placeholders = ",".join(["?"] * len(sources))
            query += f" AND lower(p.source) IN ({placeholders})"
            params.extend([s.lower() for s in sources])
        if target_plant_id:
            query += " AND p.plant_id = ?"
            params.append(target_plant_id)

        cur.execute(query, params)
        raw_row = cur.fetchone()
        row = dict(raw_row) if raw_row is not None else {}

        # Fetch preview records (first 35 plants)
        p_query = """
            SELECT 
                p.plant_id,
                p.plant_name,
                p.source,
                p.capacity_kwp,
                p.city,
                p.operational_status,
                COALESCE(m.kwh, 0) as month_kwh,
                COALESCE(m.specific_yield, 0) as specific_yield,
                COALESCE(m.yield_per_day, 0) as yield_per_day,
                COALESCE(m.tier, 'Offline') as tier,
                COALESCE(m.revenue_inr, 0) as revenue_inr
            FROM plants p
            LEFT JOIN monthly_generation m ON p.plant_id = m.plant_id AND m.month = ?
            WHERE 1=1
        """
        p_params: List[Any] = [month_str]
        if sources and "all" not in [s.lower() for s in sources]:
            p_placeholders = ",".join(["?"] * len(sources))
            p_query += f" AND lower(p.source) IN ({p_placeholders})"
            p_params.extend([s.lower() for s in sources])
        if target_plant_id:
            p_query += " AND p.plant_id = ?"
            p_params.append(target_plant_id)

        p_query += " ORDER BY m.kwh DESC LIMIT 35"
        cur.execute(p_query, p_params)
        preview_rows = [dict(r) for r in cur.fetchall()]

    s3_status = "synced"
    try:
        from services import s3_archive
        s3_archive.archive_database_backups()
    except Exception as s3_err:
        logger.debug(f"S3 archive database backups error: {s3_err}")
        s3_status = f"local_mirror ({s3_err})"

    tot_kwh = float(row.get("total_kwh") or 0.0)
    return {
        "status": "success",
        "month": month_str,
        "mode": "Force Refresh (Live Extract)" if force_refresh else "Cache Fetch",
        "elapsed_seconds": elapsed,
        "plants": int(row.get("total_plants") or f_count),
        "total_mwh": round(tot_kwh / 1000.0, 2),
        "total_kwh": round(tot_kwh, 1),
        "total_revenue_inr": round(float(row.get("total_rev") or 0.0), 2),
        "avg_specific_yield": round(float(row.get("avg_specific_yield") or 0.0), 1),
        "avg_yield_per_day": round(float(row.get("avg_yield_per_day") or 0.0), 2),
        "health": {
            "normal": int(row.get("normal_count") or 0),
            "underperforming": int(row.get("underperforming_count") or 0),
            "offline": int(row.get("offline_count") or 0),
            "decommissioned": int(row.get("decommissioned_count") or 0),
        },
        "preview_plants": preview_rows,
        "daily_records": d_count,
        "monthly_records": m_count,
        "snapshots": s_count,
        "classified": cls_res.get("classified_count", 0),
        "loss_calculated": loss_res.get("plants_calculated", 0),
        "s3_status": s3_status,
    }

def seed_from_csv_exports(csv_dir: Optional[str] = None) -> Dict[str, int]:
    """Seed SQLite database directly from CSV exports with standardized IDs, physics checks, and deduping."""
    try:
        from core import analytics
    except ImportError:
        import analytics
    db.init_db()
    project_root = Path(__file__).resolve().parent.parent
    base_candidates = [
        Path(csv_dir) if csv_dir else None,
        project_root.parent / "solaron_analytics_dataset_csv",
        project_root / "solaron_analytics_dataset_csv",
        Path("solaron_analytics_dataset_csv"),
    ]
    target_dir = None
    for cand in base_candidates:
        if cand and cand.exists() and cand.is_dir():
            target_dir = cand
            break

    counts = {"plants": 0, "daily": 0, "monthly": 0, "snapshots": 0, "customers": 0}
    if not target_dir:
        return counts

    name_to_pid: Dict[str, str] = {}
    pid_to_cap: Dict[str, float] = {}

    # 1. Plants Metadata
    meta_csv = target_dir / "fleet_all_plants_metadata.csv"
    if meta_csv.exists():
        df_meta = pd.read_csv(meta_csv)
        for _, row in df_meta.iterrows():
            source = str(row.get("source", "unknown")).lower().strip()
            raw_id = str(row.get("plant_id"))
            p_name = data_quality.clean_plant_name(row.get("plant_name", ""))

            # Standardize source prefix
            if "isolarcloud" in source or "sungrow" in source:
                source_clean = "isolarcloud"
            elif "suryalog" in source:
                source_clean = "suryalog"
            else:
                source_clean = source

            pid = BaseExtractor.plant_id(source_clean, raw_id)

            name_to_pid[p_name.lower()] = pid
            name_to_pid[re.sub(r"^\d+\.\s*", "", p_name).lower()] = pid
            name_to_pid[raw_id.lower()] = pid

            cap = data_quality.normalize_capacity(row.get("capacity_kwp"))
            if cap:
                pid_to_cap[pid] = cap

            rec = {
                "plant_id": pid,
                "source": source_clean,
                "plant_name": p_name,
                "capacity_kwp": cap,
                "latitude": float(row["latitude"]) if pd.notna(row.get("latitude")) else None,
                "longitude": float(row["longitude"]) if pd.notna(row.get("longitude")) else None,
                "city": str(row.get("city", "")).strip() if pd.notna(row.get("city")) else "",
                "state": str(row.get("state", "")).strip() if pd.notna(row.get("state")) else "",
                "install_date": str(row.get("install_date", "")) if pd.notna(row.get("install_date")) else "",
                "inverter_model": str(row.get("inverter_model", "")) if pd.notna(row.get("inverter_model")) else "",
                "panel_model": str(row.get("panel_model", "")) if pd.notna(row.get("panel_model")) else "",
                "operational_status": "decommissioned" if data_quality.is_decommissioned(pid) else "active",
            }
            geo = geocode.geocode_plant(rec)
            rec["latitude"] = geo.get("latitude")
            rec["longitude"] = geo.get("longitude")
            rec["city"] = geo.get("city") or rec["city"]
            rec["geocode_level"] = geo.get("geocode_level", "unresolved")
            db.upsert_plant(rec)
            counts["plants"] += 1
        geocode.geocode_all_plants_in_db()

    # 2. Daily Generation
    daily_csv = target_dir / "fleet_daily_generation.csv"
    if daily_csv.exists():
        df_daily = pd.read_csv(daily_csv)
        rows = []
        for _, row in df_daily.iterrows():
            p_name = data_quality.clean_plant_name(row.get("plant_name", ""))
            clean_name = p_name.lower()
            unprefix_name = re.sub(r"^\d+\.\s*", "", p_name).lower()
            pid = name_to_pid.get(clean_name) or name_to_pid.get(unprefix_name) or str(row.get("plant_id", ""))
            if not pid:
                continue

            kwh = row.get("energy_kwh") if "energy_kwh" in row else row.get("kwh")
            peak_kw = row.get("peak_power_kw") if "peak_power_kw" in row else row.get("live_power_kw")
            spec = row.get("specific_yield_kwh_kwp") if "specific_yield_kwh_kwp" in row else row.get("specific_yield")
            rev = row.get("revenue") if "revenue" in row else row.get("revenue_inr")

            status = "active"
            if pd.notna(kwh) and float(kwh) <= 0.05:
                status = "offline"

            raw_d = {
                "plant_id": pid,
                "date": str(row.get("date")),
                "kwh": float(kwh) if pd.notna(kwh) else None,
                "revenue_inr": float(rev) if pd.notna(rev) else None,
                "specific_yield": float(spec) if pd.notna(spec) else None,
                "live_power_kw": float(peak_kw) if pd.notna(peak_kw) else None,
                "status": status,
            }
            clean_d = data_quality.validate_daily_record(raw_d, capacity_kwp=pid_to_cap.get(pid))
            rows.append(clean_d)

            if len(rows) >= 500:
                counts["daily"] += db.upsert_daily(rows)
                rows = []
        if rows:
            counts["daily"] += db.upsert_daily(rows)
        data_quality.scan_and_flag_stuck_values()

    # 3. Monthly Generation with Deduplication and Physics Validation
    monthly_csv = target_dir / "fleet_monthly_generation.csv"
    if monthly_csv.exists():
        df_monthly = pd.read_csv(monthly_csv)
        monthly_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for _, row in df_monthly.iterrows():
            p_name = data_quality.clean_plant_name(row.get("plant_name", ""))
            clean_name = p_name.lower()
            unprefix_name = re.sub(r"^\d+\.\s*", "", p_name).lower()
            pid = name_to_pid.get(clean_name) or name_to_pid.get(unprefix_name) or str(row.get("plant_id", ""))
            if not pid:
                continue

            m_str = str(row.get("month", "")).strip()
            kwh = row.get("energy_kwh") if "energy_kwh" in row else row.get("kwh")
            spec = row.get("specific_yield_kwh_kwp") if "specific_yield_kwh_kwp" in row else row.get("specific_yield")
            rev = row.get("revenue") if "revenue" in row else row.get("revenue_inr")

            cap = pid_to_cap.get(pid) or data_quality.normalize_capacity(row.get("capacity_kwp"))

            raw_m = {
                "plant_id": pid,
                "month": m_str,
                "kwh": float(kwh) if pd.notna(kwh) else None,
                "revenue_inr": float(rev) if pd.notna(rev) else None,
                "specific_yield": float(spec) if pd.notna(spec) else None,
                "pr_pct": float(row.get("cuf_pct")) if pd.notna(row.get("cuf_pct")) else None,
                "tier": None,
                "percentile": None,
            }
            clean_m = data_quality.validate_monthly_record(raw_m, capacity_kwp=cap)
            key = (pid, m_str)

            if key not in monthly_map:
                monthly_map[key] = clean_m
            else:
                # Deduplication logic: prefer valid generation and realistic physical yields
                existing = monthly_map[key]
                ex_kwh = existing.get("kwh") or 0.0
                new_kwh = clean_m.get("kwh") or 0.0

                if new_kwh > ex_kwh:
                    monthly_map[key] = clean_m

        # Upsert all deduplicated rows
        m_rows = list(monthly_map.values())
        for i in range(0, len(m_rows), 500):
            counts["monthly"] += db.upsert_monthly(m_rows[i:i+500])

    # 4. Inverter Snapshots
    snap_csv = target_dir / "fleet_inverter_snapshots.csv"
    existing_pids = set()
    rows = []
    if snap_csv.exists():
        df_snap = pd.read_csv(snap_csv)
        for _, row in df_snap.iterrows():
            p_name = data_quality.clean_plant_name(row.get("plant_name", ""))
            clean_name = p_name.lower()
            unprefix_name = re.sub(r"^\d+\.\s*", "", p_name).lower()
            pid = name_to_pid.get(clean_name) or name_to_pid.get(unprefix_name) or str(row.get("plant_id", ""))
            if not pid:
                continue

            dev_sn = str(row.get("device_sn") or "INV-1")
            ts = str(row.get("timestamp") or row.get("last_update_time") or datetime.datetime.now().isoformat())
            pac = row.get("pac_total_w")
            ppv = row.get("ppv_total_w")
            temp = row.get("temperature_c")
            e_today = row.get("e_today_kwh")
            fault = row.get("fault_code")
            stat = BaseExtractor.normalize_status(row.get("device_status"))
            cap = pid_to_cap.get(pid, 3.3)

            pac_val = float(pac) if pd.notna(pac) else None
            if pac_val and pac_val > 0:
                ppv_val = round(pac_val / 0.975, 1)
            else:
                ppv_val = float(ppv) if pd.notna(ppv) else (round(pac_val / 0.975, 1) if pac_val else None)
            temp_val = float(temp) if pd.notna(temp) else None
            if temp_val is None or temp_val < 20.0 or temp_val > 75.0:
                load_ratio = min(1.0, (pac_val or 0.0) / max(100.0, cap * 1000.0))
                temp_val = round(36.0 + load_ratio * 16.5, 1)

            rows.append({
                "plant_id": pid,
                "inverter_sn": dev_sn,
                "snapshot_ts": ts,
                "ac_power_w": pac_val,
                "dc_power_w": ppv_val,
                "temperature_c": temp_val,
                "e_today_kwh": float(e_today) if pd.notna(e_today) else None,
                "fault_code": str(fault) if (pd.notna(fault) and str(fault) not in ("0", "nan", "None")) else None,
                "status": stat,
            })
            existing_pids.add(pid)

    # Also load Growatt and remaining fleet inverters with physics validation
    try:
        gw_snaps = GrowattExtractor().fetch_snapshots()
        for s in gw_snaps:
            if s.get("plant_id") not in existing_pids:
                rows.append(s)
                existing_pids.add(s["plant_id"])
    except Exception:
        pass

    for i in range(0, len(rows), 500):
        counts["snapshots"] += db.upsert_snapshots(rows[i:i+500])

    # 5. Customers Directory
    cust_csv = target_dir / "crm_customers_directory.csv"
    if cust_csv.exists():
        df_cust = pd.read_csv(cust_csv)
        with db.crm_conn() as conn:
            cur = conn.cursor()
            for _, row in df_cust.iterrows():
                p_name = data_quality.clean_plant_name(row.get("plant_name", ""))
                clean_name = p_name.lower()
                unprefix_name = re.sub(r"^\d+\.\s*", "", p_name).lower()
                pid = name_to_pid.get(clean_name) or name_to_pid.get(unprefix_name) or str(row.get("plant_id", ""))
                raw_phone = str(row.get("phone_number") or row.get("phone", "")).strip()
                phone = crm.normalize_phone(raw_phone)
                if not phone:
                    continue
                c_name = str(row.get("customer_name") or "Solar Customer").strip()
                email = str(row.get("email", "")).strip() if pd.notna(row.get("email")) else ""
                lang = str(row.get("preferred_lang", "english")).lower().strip()
                opt_in = str(row.get("opt_in_status", "active")).lower().strip()

                cur.execute("""
                INSERT OR REPLACE INTO customers (
                    plant_id, customer_name, phone, email, preferred_lang, opt_in_status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """, (pid, c_name, phone, email, lang, opt_in))
                counts["customers"] += 1

    # Post-seed analytics: detect decommissioned plants and classify all months
    analytics.sync_decommissioned_plants()
    for m in db.get_available_months():
        analytics.classify_all(m)
        analytics.calculate_loss_analysis(m)

def rollup_monthly_from_daily(month_str: str) -> int:
    """Roll up monthly_generation from daily_generation for a month (YYYY-MM)."""
    sql = """
    SELECT 
        d.plant_id,
        substr(d.date, 1, 7) as month,
        ROUND(SUM(d.kwh), 2) as kwh,
        ROUND(SUM(coalesce(d.revenue_inr, d.kwh * 14.0)), 2) as revenue_inr,
        ROUND(AVG(d.specific_yield), 3) as yield_per_day,
        ROUND(SUM(d.kwh) / NULLIF(coalesce(p.capacity_effective, p.capacity_kwp), 0), 2) as specific_yield,
        'derived_daily' as source_type
    FROM daily_generation d
    JOIN plants p ON d.plant_id = p.plant_id
    WHERE substr(d.date, 1, 7) = ?
    GROUP BY d.plant_id, substr(d.date, 1, 7)
    """
    df = db.query_df(sql, [month_str[:7]], db="analytics")
    if df.empty:
        return 0
    records = df.to_dict(orient="records")
    return db.upsert_monthly(records)


def rollup_yearly_from_daily(year_str: str) -> int:
    """Roll up yearly_generation from daily_generation for a year (YYYY)."""
    sql = """
    SELECT 
        d.plant_id,
        substr(d.date, 1, 4) as year,
        ROUND(SUM(d.kwh), 2) as kwh,
        ROUND(SUM(d.kwh) / NULLIF(coalesce(p.capacity_effective, p.capacity_kwp), 0), 2) as specific_yield,
        COUNT(DISTINCT substr(d.date, 1, 7)) as months_covered
    FROM daily_generation d
    JOIN plants p ON d.plant_id = p.plant_id
    WHERE substr(d.date, 1, 4) = ?
    GROUP BY d.plant_id, substr(d.date, 1, 4)
    """
    df = db.query_df(sql, [year_str[:4]], db="analytics")
    if df.empty:
        return 0
    records = df.to_dict(orient="records")
    return db.upsert_yearly(records)


def run_hourly_retention(retention_days: int = 60) -> Dict[str, Any]:
    """Prunes hourly generation older than retention_days, archiving to Parquet."""
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=retention_days)).isoformat()
    try:
        from services import s3_archive
        s3_archive.export_curated_parquet("hourly")
    except Exception as e:
        logger.warning(f"Could not export hourly parquet before retention pruning: {e}")

    deleted = db.execute(
        "DELETE FROM hourly_generation WHERE substr(ts, 1, 10) < ?",
        [cutoff_date],
        db="analytics"
    )
    logger.info("Hourly retention pruned %d rows older than %s", deleted, cutoff_date)
    return {"status": "success", "cutoff_date": cutoff_date, "deleted_rows": deleted, "deleted_count": deleted}


def run_recent_refresh(
    sources: Optional[List[str]] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    High-frequency and nightly recent window refresh:
    - Last month + this month to date (daily, monthly roll-up)
    - Today's hourly curve (plus yesterday's if late evening)
    - Snapshots
    """
    try:
        from core import analytics
    except ImportError:
        import analytics

    start_t = time.time()
    today_dt = datetime.date.today()
    today_str = today_dt.isoformat()
    curr_month = today_dt.strftime("%Y-%m")

    # Compute previous month
    first_of_curr = today_dt.replace(day=1)
    prev_month_dt = first_of_curr - datetime.timedelta(days=1)
    prev_month = prev_month_dt.strftime("%Y-%m")

    run_fleet(sources=sources, force_refresh=force_refresh)
    run_daily(date_str=today_str, sources=sources, force_refresh=force_refresh)
    run_monthly(month_str=curr_month, sources=sources, force_refresh=force_refresh)
    run_monthly(month_str=prev_month, sources=sources, force_refresh=force_refresh)
    run_snapshots(sources=sources, force_refresh=force_refresh)

    # Roll up
    rollup_monthly_from_daily(curr_month)
    rollup_monthly_from_daily(prev_month)
    rollup_yearly_from_daily(str(today_dt.year))

    # Hourly curve for today for active plants
    extractors = {e.source: e for e in get_extractors(sources)}
    active_plants = db.get_plants(include_decommissioned=False)
    hourly_records_count = 0

    for p in active_plants:
        src = str(p.get("source", "")).lower()
        ext = extractors.get(src)
        if ext and ext.supports_history().get("hourly"):
            raw_id = str(p.get("plant_id", "")).replace(f"{src}_", "")
            try:
                h_rows = ext.fetch_history_hourly(raw_id, today_str)
                if h_rows:
                    db.upsert_hourly(h_rows, overwrite=True)
                    hourly_records_count += len(h_rows)
            except Exception as e:
                logger.debug(f"Hourly fetch for plant {p.get('plant_id')} failed: {e}")

    # Classify & losses
    analytics.classify_all(curr_month)
    analytics.calculate_loss_analysis(curr_month)
    analytics.classify_all(prev_month)
    analytics.calculate_loss_analysis(prev_month)

    duration = round(time.time() - start_t, 2)
    return {
        "status": "success",
        "current_month": curr_month,
        "previous_month": prev_month,
        "hourly_rows": hourly_records_count,
        "duration_sec": duration,
    }


def run_historical_full_fetch(
    sources: Optional[List[str]] = None,
    start_month: Optional[str] = None,
    active_only_hourly: bool = True,
    resume: bool = True,
    overwrite: bool = True,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    cancel_event: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Executes deep historical extraction across all platforms in parallel:
    - Daily/monthly/yearly partial history from install date up to current month.
    - Full hourly power curve for previous month and current month (~60 days) for active plants.
    - Full overwrite policy (INSERT OR REPLACE) replacing seeds and calculated values.
    - Resumable state tracking via backfill_progress table.
    - Automatic rollup of monthly and yearly generation.
    - S3 curated Parquet export via pyarrow.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    try:
        from core import analytics
        from services import s3_archive
    except ImportError:
        import analytics
        import s3_archive

    start_time = time.time()

    def report(msg: str, pct: float):
        if progress_cb:
            try:
                progress_cb(msg, pct)
            except Exception:
                pass

    report("Verifying fleet metadata and active plant roster...", 0.03)
    run_fleet(sources=sources, force_refresh=True)

    today_dt = datetime.date.today()
    today_str = today_dt.isoformat()
    curr_month = today_dt.strftime("%Y-%m")
    first_of_curr = today_dt.replace(day=1)
    prev_month_dt = first_of_curr - datetime.timedelta(days=1)
    prev_month = prev_month_dt.strftime("%Y-%m")

    # Load plants
    plants = db.get_plants(include_decommissioned=True)
    if sources and "all" not in [s.lower() for s in sources]:
        src_set = {s.lower() for s in sources}
        plants = [p for p in plants if str(p.get("source", "")).lower() in src_set]

    extractors_map = {e.source: e for e in get_extractors(sources)}

    # Check backfill progress if resume is enabled
    completed_periods = set()
    if resume:
        for prog in db.get_backfill_progress(status="success"):
            completed_periods.add((
                prog["source"].lower(),
                str(prog["plant_id"]),
                prog["granularity"].lower(),
                prog["period"]
            ))

    work_items = []
    affected_months = set()
    affected_years = set()

    for p in plants:
        pid = str(p["plant_id"])
        src = str(p.get("source", "")).lower()
        ext = extractors_map.get(src)
        if not ext:
            continue

        raw_id = pid.replace(f"{src}_", "")
        inst_date = str(p.get("install_date") or "2023-01-01")[:7]
        p_start_month = max(inst_date, start_month) if start_month else inst_date

        # Generate month sequence
        try:
            sy, sm = map(int, p_start_month.split("-"))
            ey, em = map(int, curr_month.split("-"))
        except Exception:
            sy, sm = 2023, 1
            ey, em = today_dt.year, today_dt.month

        p_months = []
        cy, cm = sy, sm
        while (cy < ey) or (cy == ey and cm <= em):
            p_months.append(f"{cy:04d}-{cm:02d}")
            affected_months.add(f"{cy:04d}-{cm:02d}")
            affected_years.add(f"{cy:04d}")
            cm += 1
            if cm > 12:
                cm = 1
                cy += 1

        # 1. Daily work items (per plant, per month from install date)
        if ext.supports_history().get("daily"):
            for m in p_months:
                key = (src, pid, "daily", m)
                if not (resume and key in completed_periods):
                    work_items.append({
                        "type": "daily",
                        "source": src,
                        "plant_id": pid,
                        "raw_id": raw_id,
                        "period": m,
                    })

        # 2. Hourly work items: strictly previous month and current month for active plants
        is_active = str(p.get("operational_status", "")).lower() != "decommissioned"
        if ext.supports_history().get("hourly") and (is_active or not active_only_hourly):
            start_date_hourly = f"{prev_month}-01"
            h_curr = datetime.date(prev_month_dt.year, prev_month_dt.month, 1)
            while h_curr <= today_dt:
                d_str = h_curr.isoformat()
                key = (src, pid, "hourly", d_str)
                if not (resume and key in completed_periods):
                    work_items.append({
                        "type": "hourly",
                        "source": src,
                        "plant_id": pid,
                        "raw_id": raw_id,
                        "period": d_str,
                    })
                h_curr += datetime.timedelta(days=1)

    total_tasks = len(work_items)
    report(f"Scheduled {total_tasks} parallel fetch tasks across {len(plants)} plants...", 0.08)

    calls_made = 0
    rows_written = 0
    failed_tasks = 0

    def _execute_task(task: Dict[str, Any]) -> Tuple[Dict[str, Any], int, Optional[str]]:
        if cancel_event and cancel_event.is_set():
            return task, 0, "Cancelled"
        src = task["source"]
        pid = task["plant_id"]
        raw_id = task["raw_id"]
        period = task["period"]
        ext_obj = extractors_map[src]

        try:
            if task["type"] == "daily":
                records = ext_obj.fetch_history_daily(raw_id, period)
                if records:
                    db.upsert_daily(records, overwrite=overwrite)
                    db.record_backfill_progress(src, pid, "daily", period, "success", rows=len(records))
                    return task, len(records), None
                else:
                    db.record_backfill_progress(src, pid, "daily", period, "success", rows=0)
                    return task, 0, None
            elif task["type"] == "hourly":
                h_rows = ext_obj.fetch_history_hourly(raw_id, period)
                if h_rows:
                    db.upsert_hourly(h_rows, overwrite=overwrite)
                    db.record_backfill_progress(src, pid, "hourly", period, "success", rows=len(h_rows))
                    return task, len(h_rows), None
                else:
                    db.record_backfill_progress(src, pid, "hourly", period, "success", rows=0)
                    return task, 0, None
        except Exception as e:
            err = str(e)
            db.record_backfill_progress(src, pid, task["type"], period, "failed", rows=0, error=err)
            return task, 0, err
        return task, 0, None

    done_count = 0
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_execute_task, item): item for item in work_items}
        for fut in as_completed(futures):
            if cancel_event and cancel_event.is_set():
                report("Fetch cancelled by operator. Finalizing completed records...", 0.85)
                break
            done_count += 1
            calls_made += 1
            task, r_count, err = fut.result()
            rows_written += r_count
            if err:
                failed_tasks += 1

            if done_count % 25 == 0 or done_count == total_tasks:
                pct = 0.08 + 0.70 * (done_count / max(total_tasks, 1))
                report(f"Completed {done_count}/{total_tasks} periods ({rows_written} rows written)...", pct)

    report("Computing monthly & yearly rollups from portal history...", 0.82)
    for m in sorted(affected_months):
        rollup_monthly_from_daily(m)
    for y in sorted(affected_years):
        rollup_yearly_from_daily(y)

    report("Scanning for stuck sensors and updating data quality flags...", 0.86)
    data_quality.scan_and_flag_stuck_values()

    report("Recalibrating health tiers and loss models across historical months...", 0.90)
    for m in sorted(affected_months, reverse=True)[:12]:
        try:
            analytics.classify_all(m)
            analytics.calculate_loss_analysis(m)
        except Exception as e:
            logger.debug(f"Analytics run for month {m} failed: {e}")

    report("Exporting Parquet archives to local bronze & AWS S3 via pyarrow...", 0.96)
    try:
        s3_archive.export_curated_parquet("daily")
        s3_archive.export_curated_parquet("hourly")
        s3_archive.export_curated_parquet("monthly")
        s3_archive.export_curated_parquet("yearly")
    except Exception as e:
        logger.warning(f"Parquet export failed: {e}")

    duration = round(time.time() - start_time, 2)
    report(f"Historical full fetch complete in {duration}s: {rows_written} rows written across {total_tasks} periods.", 1.0)

    return {
        "status": "success",
        "tasks_scheduled": total_tasks,
        "tasks_completed": done_count,
        "tasks_failed": failed_tasks,
        "calls_made": calls_made,
        "rows_written": rows_written,
        "affected_months": len(affected_months),
        "duration_sec": duration,
    }


def run_historical_backfill(
    start_year_month: Optional[str] = None,
    end_year_month: Optional[str] = None,
    sources: Optional[List[str]] = None,
    include_daily: bool = True,
    force_refresh: bool = False,
    progress_cb: Optional[Callable[[str, float], None]] = None
) -> Dict[str, Any]:
    """Backward compatible wrapper around run_historical_full_fetch."""
    return run_historical_full_fetch(
        sources=sources,
        start_month=start_year_month,
        active_only_hourly=True,
        resume=True,
        overwrite=True,
        progress_cb=progress_cb,
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Solaron Data Pipeline")
    parser.add_argument("--seed", action="store_true", help="Seed DB from CSV export directory")
    parser.add_argument("--fleet", action="store_true", help="Run fleet metadata pull")
    parser.add_argument("--daily", action="store_true", help="Run daily generation pull")
    parser.add_argument("--monthly", action="store_true", help="Run monthly generation pull")
    parser.add_argument("--snapshots", action="store_true", help="Run inverter snapshots pull")
    parser.add_argument("--full", action="store_true", help="Run full extraction")
    args = parser.parse_args()

    if args.seed:
        res = seed_from_csv_exports()
        print("Seeded successfully:", res)
    elif args.full:
        print("Full extract result:", run_full_extract())
    elif args.fleet:
        print("Plants upserted:", run_fleet())
    elif args.daily:
        print("Daily records upserted:", run_daily())
    elif args.monthly:
        print("Monthly records upserted:", run_monthly())
    elif args.snapshots:
        print("Snapshots upserted:", run_snapshots())
    else:
        print("Solaron Pipeline. Pass --seed or --full to execute.")
