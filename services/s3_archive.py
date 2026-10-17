"""
Solaron AWS S3 Bronze Archival Service.

Implements automated backup and bronze archiving to AWS S3:
1. Escalation state daily snapshots (JSON) -> s3://{bucket}/solaron/escalation/state/{date}.json
2. Escalation log audit stream (JSONL) -> s3://{bucket}/solaron/escalation/log/{year}-{month}.jsonl
3. Gupshup inbound log stream (JSONL) -> s3://{bucket}/solaron/gupshup/inbound/{year}-{month}.jsonl
4. Daily generation backup (JSON) -> s3://{bucket}/solaron/bronze/daily_gen/{date}.json
5. Monthly generation backup (JSON) -> s3://{bucket}/solaron/bronze/monthly_gen/{month}.json
6. Nightly full online SQLite DB backups -> s3://{bucket}/backups/db/{date}/solar_analytics_{ts}.db and crm_data_{ts}.db

Guards:
- Default is never to overwrite existing historical data unless empty or zero bytes.
- All archives attach date/timestamp metadata.
- Includes local bronze mirror and graceful fallback.
"""

import datetime
import json
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from config import settings

try:
    from pipeline import db
except ImportError:
    import db

logger = logging.getLogger(__name__)

LOCAL_BRONZE_DIR = Path(__file__).resolve().parent.parent / "data" / "bronze"
LOCAL_BACKUPS_DIR = Path(__file__).resolve().parent.parent / "data" / "backups"


def get_s3_client():
    """Returns a configured boto3 S3 client, or None if credentials are not configured."""
    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        return None
    try:
        return boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region or "ap-south-1"
        )
    except Exception as e:
        logger.warning("Could not initialize S3 client: %s", e)
        return None


def check_s3_connection() -> Dict[str, Any]:
    """Validates S3 connectivity and bucket access via head_bucket."""
    client = get_s3_client()
    bucket = settings.s3_bucket_name or "solaron-dashboard-data"
    if not client:
        return {"connected": False, "error": "AWS credentials missing in .env"}
    try:
        client.head_bucket(Bucket=bucket)
        return {"connected": True, "bucket": bucket}
    except Exception as e:
        return {"connected": False, "bucket": bucket, "error": str(e)}


def upload_content_to_s3(
    s3_key: str,
    content: str,
    content_type: str = "application/json",
    overwrite_if_empty_only: bool = True,
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Uploads string content to S3, or writes to local bronze directory.
    Guarded by 'overwrite_if_empty_only': preserves existing non-empty archives.
    """
    client = get_s3_client()
    bucket = settings.s3_bucket_name or "solaron-dashboard-data"

    # Always ensure local mirror
    local_path = LOCAL_BRONZE_DIR / s3_key
    local_path.parent.mkdir(parents=True, exist_ok=True)
    if not (overwrite_if_empty_only and local_path.exists() and local_path.stat().st_size > 0):
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)

    meta = metadata or {}
    meta["created_at"] = datetime.datetime.now().isoformat()

    if client:
        try:
            # Check if object already exists and is non-empty
            if overwrite_if_empty_only:
                try:
                    head = client.head_object(Bucket=bucket, Key=s3_key)
                    existing_size = head.get("ContentLength", 0)
                    if existing_size > 0:
                        logger.info(f"Preserving existing S3 object s3://{bucket}/{s3_key} ({existing_size} bytes). Never overwrite rule active.")
                        return {
                            "status": "preserved_existing",
                            "target": f"s3://{bucket}/{s3_key}",
                            "size_bytes": existing_size,
                        }
                except ClientError as e:
                    # 404 Not Found is expected when new
                    if e.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey"):
                        logger.debug(f"Head object check returned error: {e}")

            client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
                Metadata={k.lower(): str(v) for k, v in meta.items()},
            )
            logger.info("Successfully uploaded %s to S3 bucket %s (%d bytes)", s3_key, bucket, len(content))
            return {"status": "uploaded", "target": f"s3://{bucket}/{s3_key}", "size_bytes": len(content)}
        except (ClientError, NoCredentialsError) as e:
            logger.warning("S3 upload failed for %s, cached locally: %s", s3_key, e)
            return {"status": "local_fallback", "target": str(local_path), "error": str(e)}

    return {"status": "local_mirror", "target": str(local_path), "size_bytes": len(content)}


def upload_file_to_s3(
    local_file: Path,
    s3_key: str,
    overwrite_if_empty_only: bool = True,
    metadata: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Uploads a binary file (such as a SQLite backup) to S3."""
    client = get_s3_client()
    bucket = settings.s3_bucket_name or "solaron-dashboard-data"

    if not local_file.exists():
        return {"status": "error", "error": f"File {local_file} not found"}

    file_size = local_file.stat().st_size
    meta = metadata or {}
    meta["created_at"] = datetime.datetime.now().isoformat()
    meta["file_size_bytes"] = str(file_size)

    if client:
        try:
            if overwrite_if_empty_only:
                try:
                    head = client.head_object(Bucket=bucket, Key=s3_key)
                    if head.get("ContentLength", 0) > 0:
                        logger.info(f"Preserving existing S3 backup s3://{bucket}/{s3_key}. Never overwrite rule active.")
                        return {"status": "preserved_existing", "target": f"s3://{bucket}/{s3_key}", "size_bytes": head.get("ContentLength", 0)}
                except ClientError:
                    pass

            extra_args = {"Metadata": {k.lower(): str(v) for k, v in meta.items()}}
            client.upload_file(str(local_file), bucket, s3_key, ExtraArgs=extra_args)
            logger.info(f"Uploaded binary file {local_file.name} to s3://{bucket}/{s3_key} ({file_size} bytes)")
            return {"status": "uploaded", "target": f"s3://{bucket}/{s3_key}", "size_bytes": file_size}
        except Exception as e:
            logger.warning(f"S3 file upload failed for {s3_key}: {e}")
            return {"status": "local_only", "target": str(local_file), "error": str(e)}

    return {"status": "local_only", "target": str(local_file), "size_bytes": file_size}


def archive_escalation_state(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Snapshots all current escalation states to JSON."""
    if not date_str:
        date_str = datetime.date.today().isoformat()

    sql = "SELECT * FROM escalation_state ORDER BY id ASC;"
    df = db.query_df(sql, db="crm")
    records = df.to_dict(orient="records") if not df.empty else []

    payload = {
        "snapshot_date": date_str,
        "total_active_states": len(records),
        "created_at": datetime.datetime.now().isoformat(),
        "states": records
    }
    content = json.dumps(payload, indent=2, default=str)
    s3_key = f"solaron/escalation/state/{date_str}.json"
    res = upload_content_to_s3(s3_key, content, metadata={"date": date_str, "type": "escalation_state"})
    res["count"] = len(records)
    return res


def archive_escalation_log(month: Optional[str] = None) -> Dict[str, Any]:
    """Appends monthly escalation log transitions to JSONL."""
    if not month:
        month = datetime.date.today().strftime("%Y-%m")

    sql = "SELECT * FROM escalation_log WHERE substr(created_at, 1, 7) = ? ORDER BY id ASC;"
    df = db.query_df(sql, [month], db="crm")
    records = df.to_dict(orient="records") if not df.empty else []

    lines = [json.dumps(r, default=str) for r in records]
    content = "\n".join(lines)
    s3_key = f"solaron/escalation/log/{month}.jsonl"
    res = upload_content_to_s3(s3_key, content, content_type="application/x-ndjson", metadata={"month": month, "type": "escalation_log"})
    res["count"] = len(records)
    return res


def archive_inbound_log(month: Optional[str] = None) -> Dict[str, Any]:
    """Archives Gupshup webhook inbound messages to monthly JSONL."""
    if not month:
        month = datetime.date.today().strftime("%Y-%m")

    sql = "SELECT * FROM gupshup_inbound_log WHERE substr(created_at, 1, 7) = ? ORDER BY id ASC;"
    df = db.query_df(sql, [month], db="crm")
    records = df.to_dict(orient="records") if not df.empty else []

    lines = [json.dumps(r, default=str) for r in records]
    content = "\n".join(lines)
    s3_key = f"solaron/gupshup/inbound/{month}.jsonl"
    res = upload_content_to_s3(s3_key, content, content_type="application/x-ndjson", metadata={"month": month, "type": "gupshup_inbound"})
    res["count"] = len(records)
    return res


def archive_daily_generation(date_str: Optional[str] = None) -> Dict[str, Any]:
    """Backs up daily generation telemetry for date_str to bronze layer."""
    if not date_str:
        date_str = datetime.date.today().isoformat()

    sql = "SELECT * FROM daily_generation WHERE date = ?;"
    df = db.query_df(sql, [date_str], db="analytics")
    records = df.to_dict(orient="records") if not df.empty else []

    payload = {
        "date": date_str,
        "total_records": len(records),
        "archived_at": datetime.datetime.now().isoformat(),
        "generation": records
    }
    content = json.dumps(payload, indent=2, default=str)
    s3_key = f"solaron/bronze/daily_gen/{date_str}.json"
    res = upload_content_to_s3(s3_key, content, metadata={"date": date_str, "type": "daily_generation"})
    res["count"] = len(records)
    return res


def archive_monthly_generation(month_str: Optional[str] = None) -> Dict[str, Any]:
    """Backs up monthly generation records for month_str to bronze layer."""
    if not month_str:
        month_str = datetime.date.today().strftime("%Y-%m")

    sql = "SELECT * FROM monthly_generation WHERE month = ?;"
    df = db.query_df(sql, [month_str], db="analytics")
    records = df.to_dict(orient="records") if not df.empty else []

    payload = {
        "month": month_str,
        "total_records": len(records),
        "archived_at": datetime.datetime.now().isoformat(),
        "generation": records
    }
    content = json.dumps(payload, indent=2, default=str)
    s3_key = f"solaron/bronze/monthly_gen/{month_str}.json"
    res = upload_content_to_s3(s3_key, content, metadata={"month": month_str, "type": "monthly_generation"})
    res["count"] = len(records)
    return res


def archive_database_backups(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Performs online SQLite backups for solar_analytics.db and crm_data.db,
    saves them to data/backups/, and uploads to s3://{bucket}/backups/db/{date_str}/.
    """
    if not date_str:
        date_str = datetime.date.today().isoformat()

    LOCAL_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {}

    db_map = {
        "solar_analytics": Path(__file__).resolve().parent.parent / "data" / "solar_analytics.db",
        "crm_data": Path(__file__).resolve().parent.parent / "data" / "crm_data.db"
    }

    for name, db_path in db_map.items():
        if not db_path.exists():
            continue
        backup_file = LOCAL_BACKUPS_DIR / f"{name}_{ts}.db"
        try:
            # Perform atomic online SQLite backup
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(backup_file))
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            s3_key = f"backups/db/{date_str}/{backup_file.name}"
            upload_res = upload_file_to_s3(
                backup_file,
                s3_key,
                metadata={"database": name, "date": date_str, "timestamp": ts}
            )
            results[name] = upload_res
            logger.info(f"Database backup for {name} complete: {upload_res}")
        except Exception as e:
            logger.error(f"Error backing up {name}: {e}", exc_info=True)
            results[name] = {"status": "error", "error": str(e)}

    return results


def archive_fleet_plants(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Backs up all fleet plant metadata from the local database to S3 bronze layer:
    s3://{bucket}/solaron/bronze/fleet/plants_{date_str}.json and updates latest.json.
    """
    if not date_str:
        date_str = datetime.date.today().isoformat()

    sql = "SELECT * FROM plants ORDER BY plant_id ASC;"
    df = db.query_df(sql, db="analytics")
    records = df.to_dict(orient="records") if not df.empty else []

    try:
        from core import platforms
        plat_keys = platforms.platform_keys()
    except Exception:
        plat_keys = ["growatt", "isolarcloud", "suryalog", "fronius", "injectsolar"]

    sources_map = {k: sum(1 for r in records if str(r.get("source", "")).lower() == k) for k in plat_keys}
    sources_map["other"] = sum(1 for r in records if str(r.get("source", "")).lower() not in plat_keys)

    payload = {
        "date": date_str,
        "total_plants": len(records),
        "sources": sources_map,
        "archived_at": datetime.datetime.now().isoformat(),
        "plants": records
    }
    content = json.dumps(payload, indent=2, default=str)
    s3_key = f"solaron/bronze/fleet/plants_{date_str}.json"
    res = upload_content_to_s3(s3_key, content, metadata={"date": date_str, "type": "fleet_plants", "total_plants": str(len(records))})

    # Also update latest pointer
    try:
        upload_content_to_s3("solaron/bronze/fleet/latest.json", content, overwrite_if_empty_only=False, metadata={"date": date_str, "type": "fleet_latest"})
    except Exception as e:
        logger.debug("Could not update latest fleet S3 pointer: %s", e)

    res["count"] = len(records)
    return res


def archive_inverter_snapshots(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Backs up inverter telemetry snapshots to S3 bronze layer:
    s3://{bucket}/solaron/bronze/snapshots/{date_str}.json
    """
    if not date_str:
        date_str = datetime.date.today().isoformat()

    sql = "SELECT * FROM inverter_snapshots ORDER BY id DESC LIMIT 2000;"
    df = db.query_df(sql, db="analytics")
    records = df.to_dict(orient="records") if not df.empty else []

    payload = {
        "date": date_str,
        "total_records": len(records),
        "archived_at": datetime.datetime.now().isoformat(),
        "snapshots": records
    }
    content = json.dumps(payload, indent=2, default=str)
    s3_key = f"solaron/bronze/snapshots/{date_str}.json"
    res = upload_content_to_s3(s3_key, content, metadata={"date": date_str, "type": "inverter_snapshots", "total_records": str(len(records))})
    res["count"] = len(records)
    return res


def archive_excel_upload(local_file_path: Path, month_str: str, parsed_records: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Uploads raw uploaded Excel report and parsed records to S3:
    Raw: s3://{bucket}/solaron/raw/excel/{month_str}/{filename}
    Parsed: s3://{bucket}/solaron/bronze/excel/{month_str}.json
    """
    results = {}
    if local_file_path.exists():
        s3_raw_key = f"solaron/raw/excel/{month_str}/{local_file_path.name}"
        res_file = upload_file_to_s3(local_file_path, s3_raw_key, overwrite_if_empty_only=False, metadata={"month": month_str, "type": "raw_excel_report"})
        results["raw_file"] = res_file

    if parsed_records:
        payload = {
            "month": month_str,
            "filename": local_file_path.name,
            "total_records": len(parsed_records),
            "archived_at": datetime.datetime.now().isoformat(),
            "records": parsed_records
        }
        content = json.dumps(payload, indent=2, default=str)
        s3_json_key = f"solaron/bronze/excel/{month_str}_{local_file_path.stem}.json"
        res_json = upload_content_to_s3(s3_json_key, content, overwrite_if_empty_only=False, metadata={"month": month_str, "type": "parsed_excel_records"})
        results["parsed_records"] = res_json

    return results


def archive_full_sync(target_date: Optional[str] = None, month_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Performs full archival of local DB data to S3:
    Fleet metadata, Daily generation, Monthly generation, Inverter snapshots, and SQLite DB backups.
    """
    if not target_date:
        target_date = datetime.date.today().isoformat()
    if not month_str:
        month_str = target_date[:7]

    logger.info("Starting full S3 archival sync for date=%s, month=%s", target_date, month_str)
    r_fleet = archive_fleet_plants(target_date)
    r_daily = archive_daily_generation(target_date)
    r_monthly = archive_monthly_generation(month_str)
    r_snaps = archive_inverter_snapshots(target_date)
    r_db = archive_database_backups(target_date)

    summary = {
        "target_date": target_date,
        "month": month_str,
        "fleet": r_fleet,
        "daily_generation": r_daily,
        "monthly_generation": r_monthly,
        "inverter_snapshots": r_snaps,
        "database_backups": r_db,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    logger.info("Full S3 sync completed successfully: %s", summary)
    return summary


def run_nightly_archive(target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Orchestrates nightly execution across all archival targets:
    Fleet, state, logs, daily gen, monthly gen, snapshots, and online database backups.
    """
    if not target_date:
        target_date = datetime.date.today().isoformat()
    month = target_date[:7]

    logger.info("Starting nightly bronze archive for date=%s, month=%s", target_date, month)
    r_fleet = archive_fleet_plants(target_date)
    r_state = archive_escalation_state(target_date)
    r_log = archive_escalation_log(month)
    r_inbound = archive_inbound_log(month)
    r_daily = archive_daily_generation(target_date)
    r_monthly = archive_monthly_generation(month)
    r_snaps = archive_inverter_snapshots(target_date)
    r_db = archive_database_backups(target_date)

    summary = {
        "target_date": target_date,
        "month": month,
        "fleet": r_fleet,
        "escalation_state": r_state,
        "escalation_log": r_log,
        "gupshup_inbound": r_inbound,
        "daily_generation": r_daily,
        "monthly_generation": r_monthly,
        "inverter_snapshots": r_snaps,
        "database_backups": r_db,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    logger.info("Nightly archive completed successfully.")
    return summary


def export_curated_parquet(granularity: str, period: Optional[str] = None) -> Dict[str, Any]:
    """
    Exports structured database tables to compressed columnar Parquet files using pyarrow,
    saving to local bronze and uploading to S3 with partition layout:
    curated/{granularity}/.../part.parquet
    """
    import io
    import pyarrow as pa
    import pyarrow.parquet as pq

    granularity = granularity.lower()
    sql = ""
    params = []
    s3_key = ""

    if granularity == "hourly":
        if period:
            sql = """
            SELECT h.plant_id, p.source, h.ts, h.power_kw, h.energy_kwh, h.source_type
            FROM hourly_generation h
            LEFT JOIN plants p ON h.plant_id = p.plant_id
            WHERE substr(h.ts, 1, 10) = ?
            """
            params = [period[:10]]
            s3_key = f"curated/hourly/date={period[:10]}/part.parquet"
        else:
            sql = """
            SELECT h.plant_id, p.source, h.ts, h.power_kw, h.energy_kwh, h.source_type
            FROM hourly_generation h
            LEFT JOIN plants p ON h.plant_id = p.plant_id
            """
            s3_key = f"curated/hourly/all/part.parquet"

    elif granularity == "daily":
        if period:
            sql = """
            SELECT d.plant_id, p.source, d.date, d.kwh, d.specific_yield, d.status, d.source_type
            FROM daily_generation d
            LEFT JOIN plants p ON d.plant_id = p.plant_id
            WHERE substr(d.date, 1, 7) = ?
            """
            params = [period[:7]]
            y, m = period[:7].split("-")
            s3_key = f"curated/daily/year={y}/month={m}/part.parquet"
        else:
            sql = """
            SELECT d.plant_id, p.source, d.date, d.kwh, d.specific_yield, d.status, d.source_type
            FROM daily_generation d
            LEFT JOIN plants p ON d.plant_id = p.plant_id
            """
            s3_key = "curated/daily/all/part.parquet"

    elif granularity == "monthly":
        if period:
            sql = """
            SELECT m.plant_id, p.source, m.month, m.kwh, m.specific_yield, m.pr_pct, m.tier, m.source_type
            FROM monthly_generation m
            LEFT JOIN plants p ON m.plant_id = p.plant_id
            WHERE m.month = ?
            """
            params = [period[:7]]
            s3_key = f"curated/monthly/month={period[:7]}/part.parquet"
        else:
            sql = """
            SELECT m.plant_id, p.source, m.month, m.kwh, m.specific_yield, m.pr_pct, m.tier, m.source_type
            FROM monthly_generation m
            LEFT JOIN plants p ON m.plant_id = p.plant_id
            """
            s3_key = "curated/monthly/all/part.parquet"

    elif granularity == "yearly":
        if period:
            sql = """
            SELECT y.plant_id, p.source, y.year, y.kwh, y.specific_yield, y.months_covered
            FROM yearly_generation y
            LEFT JOIN plants p ON y.plant_id = p.plant_id
            WHERE y.year = ?
            """
            params = [period[:4]]
            s3_key = f"curated/yearly/year={period[:4]}/part.parquet"
        else:
            sql = """
            SELECT y.plant_id, p.source, y.year, y.kwh, y.specific_yield, y.months_covered
            FROM yearly_generation y
            LEFT JOIN plants p ON y.plant_id = p.plant_id
            """
            s3_key = "curated/yearly/all/part.parquet"
    else:
        return {"status": "error", "error": f"Unsupported granularity: {granularity}"}

    df = db.query_df(sql, params, db="analytics")
    if df.empty:
        return {"status": "skipped", "reason": "No rows found for period", "granularity": granularity, "period": period}

    # Convert to PyArrow Table and serialize with snappy compression
    table = pa.Table.from_pandas(df)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    parquet_bytes = buf.getvalue()

    local_file = LOCAL_BRONZE_DIR / s3_key
    local_file.parent.mkdir(parents=True, exist_ok=True)
    with open(local_file, "wb") as f:
        f.write(parquet_bytes)

    client = get_s3_client()
    bucket = settings.s3_bucket_name or "solaron-dashboard-data"
    s3_target = None
    if client:
        try:
            client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=parquet_bytes,
                ContentType="application/vnd.apache.parquet",
                Metadata={
                    "granularity": granularity,
                    "rows": str(len(df)),
                    "created_at": datetime.datetime.now().isoformat(),
                },
            )
            s3_target = f"s3://{bucket}/{s3_key}"
            logger.info("Uploaded parquet to S3: %s (%d rows, %d bytes)", s3_target, len(df), len(parquet_bytes))
        except Exception as e:
            logger.warning("S3 parquet upload failed, retained locally at %s: %s", local_file, e)

    return {
        "status": "success",
        "granularity": granularity,
        "period": period,
        "rows": len(df),
        "size_bytes": len(parquet_bytes),
        "local_path": str(local_file),
        "s3_target": s3_target,
    }
