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


def run_nightly_archive(target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Orchestrates nightly execution across all archival targets:
    State, logs, daily gen, monthly gen, and online database backups.
    """
    if not target_date:
        target_date = datetime.date.today().isoformat()
    month = target_date[:7]

    logger.info("Starting nightly bronze archive for date=%s, month=%s", target_date, month)
    r_state = archive_escalation_state(target_date)
    r_log = archive_escalation_log(month)
    r_inbound = archive_inbound_log(month)
    r_daily = archive_daily_generation(target_date)
    r_monthly = archive_monthly_generation(month)
    r_db = archive_database_backups(target_date)

    summary = {
        "target_date": target_date,
        "month": month,
        "escalation_state": r_state,
        "escalation_log": r_log,
        "gupshup_inbound": r_inbound,
        "daily_generation": r_daily,
        "monthly_generation": r_monthly,
        "database_backups": r_db,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    logger.info("Nightly archive completed successfully.")
    return summary
