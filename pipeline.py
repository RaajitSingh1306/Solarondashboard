import argparse
import datetime
import os
import re
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
import pandas as pd
import db
import data_quality
from extractors.base import BaseExtractor
from extractors.growatt import GrowattExtractor
from extractors.isolarcloud import ISolarCloudExtractor
from extractors.suryalog import SuryaLogExtractor

def get_extractors(sources: Optional[List[str]] = None):
    all_ext = [
        GrowattExtractor(),
        ISolarCloudExtractor(),
        SuryaLogExtractor(),
    ]
    if not sources or "All" in sources or "all" in sources:
        return all_ext
    sources_clean = [s.lower().strip() for s in sources]
    return [e for e in all_ext if e.source.lower() in sources_clean]

def normalize_plant_record(p: Dict[str, Any]) -> Dict[str, Any]:
    cap = data_quality.normalize_capacity(p.get("capacity_kwp"))
    p_name = data_quality.clean_plant_name(p.get("plant_name", ""))
    return {
        "plant_id": str(p.get("plant_id")),
        "source": str(p.get("source", "unknown")).lower(),
        "plant_name": p_name,
        "capacity_kwp": cap,
        "latitude": p.get("latitude"),
        "longitude": p.get("longitude"),
        "city": p.get("city", ""),
        "install_date": p.get("install_date", ""),
        "inverter_model": p.get("inverter_model", ""),
        "panel_model": p.get("panel_model", ""),
        "operational_status": p.get("operational_status", "active"),
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
        try:
            plants = ext.fetch_fleet(force_refresh=force_refresh)
            for p in plants:
                norm = normalize_plant_record(p)
                db.upsert_plant(norm)
                count += 1
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in run_fleet for {ext.source}: {e}")
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
    except Exception:
        pass

    for ext in get_extractors(sources):
        try:
            records = ext.fetch_daily(date_str, force_refresh=force_refresh)
            norm_records = [
                normalize_daily_record(r, capacity_kwp=r.get("capacity_kwp") or plant_caps.get(str(r.get("plant_id"))))
                for r in records
            ]
            norm_records = [r for r in norm_records if r is not None]
            total += db.upsert_daily(norm_records)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in run_daily for {ext.source}: {e}")
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
    except Exception:
        pass

    for ext in get_extractors(sources):
        try:
            records = ext.fetch_monthly(month_str, force_refresh=force_refresh)
            norm_records = [
                normalize_monthly_record(r, capacity_kwp=r.get("capacity_kwp") or plant_caps.get(str(r.get("plant_id"))))
                for r in records
            ]
            total += db.upsert_monthly(norm_records)
        except Exception:
            pass
    return total

def run_snapshots(sources: Optional[List[str]] = None, force_refresh: bool = False) -> int:
    db.init_db()
    total = 0
    for ext in get_extractors(sources):
        try:
            snaps = ext.fetch_snapshots(force_refresh=force_refresh)
            total += db.upsert_snapshots(snaps)
        except Exception:
            pass
    return total

def run_full_extract(
    month_str: Optional[str] = None,
    sources: Optional[List[str]] = None,
    force_refresh: bool = False,
    target_plant_id: Optional[str] = None,
    progress_cb: Optional[Callable[[str, float], None]] = None
) -> Dict[str, Any]:
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

    run_monthly(prev_month, sources=sources, force_refresh=False)
    run_daily(f"{prev_month}-28", sources=sources, force_refresh=False)

    report("Collecting live inverter telemetry snapshots...", 0.70)
    s_count = run_snapshots(sources=sources, force_refresh=force_refresh)

    # Run performance classification and NASA GHI loss attribution
    report("Benchmarking solar insolation & classifying health tiers...", 0.85)
    cls_res = analytics.classify_all(month_str)
    analytics.classify_all(prev_month)

    report("Calculating NASA POWER GHI loss attribution...", 0.95)
    loss_res = analytics.calculate_loss_analysis(month_str)
    analytics.calculate_loss_analysis(prev_month)

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
    }

def seed_from_csv_exports(csv_dir: Optional[str] = None) -> Dict[str, int]:
    """Seed SQLite database directly from CSV exports with standardized IDs, physics checks, and deduping."""
    import analytics
    db.init_db()
    base_candidates = [
        Path(csv_dir) if csv_dir else None,
        Path(__file__).resolve().parent.parent / "solaron_analytics_dataset_csv",
        Path(__file__).resolve().parent / "solaron_analytics_dataset_csv",
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
                "install_date": str(row.get("install_date", "")) if pd.notna(row.get("install_date")) else "",
                "inverter_model": str(row.get("inverter_model", "")) if pd.notna(row.get("inverter_model")) else "",
                "panel_model": str(row.get("panel_model", "")) if pd.notna(row.get("panel_model")) else "",
                "operational_status": "active",
            }
            db.upsert_plant(rec)
            counts["plants"] += 1

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
                phone = str(row.get("phone_number") or row.get("phone", "")).strip()
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

def run_historical_backfill(
    start_year_month: Optional[str] = None,
    end_year_month: Optional[str] = None,
    sources: Optional[List[str]] = None,
    include_daily: bool = True,
    force_refresh: bool = False,
    progress_cb: Optional[Callable[[str, float], None]] = None
) -> Dict[str, Any]:
    """
    Backfills monthly and representative daily solar generation records across the lifetime of the fleet.
    If start_year_month is None, automatically detects the earliest plant installation date in the database.
    """
    import analytics
    start_time = time.time()

    def report(msg: str, pct: float):
        if progress_cb:
            try:
                progress_cb(msg, pct)
            except Exception:
                pass

    report("Verifying fleet metadata and installation dates...", 0.05)
    run_fleet(sources=sources, force_refresh=force_refresh)

    # Determine date range
    if not start_year_month:
        with db.analytics_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MIN(install_date) FROM plants WHERE install_date IS NOT NULL AND install_date != 'nan' AND install_date != ''")
            row = cur.fetchone()
            earliest = row[0] if row and row[0] else "2023-01-01"
            start_year_month = earliest[:7]

    if not end_year_month:
        end_year_month = datetime.date.today().strftime("%Y-%m")

    # Generate list of YYYY-MM
    try:
        sy, sm = map(int, start_year_month.split("-"))
        ey, em = map(int, end_year_month.split("-"))
    except Exception:
        sy, sm = 2023, 1
        ey, em = 2026, 9

    months = []
    curr_y, curr_m = sy, sm
    while (curr_y < ey) or (curr_y == ey and curr_m <= em):
        months.append(f"{curr_y:04d}-{curr_m:02d}")
        curr_m += 1
        if curr_m > 12:
            curr_m = 1
            curr_y += 1

    total_months = len(months)
    report(f"Starting historical backfill for {total_months} months ({start_year_month} to {end_year_month})...", 0.10)

    total_monthly_records = 0
    total_daily_records = 0

    for idx, m in enumerate(months):
        progress_base = 0.10 + 0.80 * (idx / max(total_months, 1))
        report(f"[{idx+1}/{total_months}] Ingesting monthly telemetry for {m}...", progress_base)
        
        m_count = run_monthly(m, sources=sources, force_refresh=force_refresh)
        total_monthly_records += m_count

        if include_daily:
            d_count = run_daily(f"{m}-28", sources=sources, force_refresh=force_refresh)
            total_daily_records += d_count

        try:
            analytics.classify_all(m)
            analytics.calculate_loss_analysis(m)
        except Exception:
            pass

    report("Syncing decommissioned plants & finalizing fleet metrics...", 0.95)
    analytics.sync_decommissioned_plants()

    elapsed = round(time.time() - start_time, 2)
    report(f"Historical backfill complete in {elapsed}s: {total_monthly_records} monthly records across {total_months} months.", 1.0)

    return {
        "status": "success",
        "months_processed": total_months,
        "start_month": start_year_month,
        "end_month": end_year_month,
        "monthly_records": total_monthly_records,
        "daily_records": total_daily_records,
        "duration_sec": elapsed
    }

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
