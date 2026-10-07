"""
Solaron AWS S3 Bronze Archival Service.

Implements nightly automated backup and bronze archiving to AWS S3:
1. Escalation state daily snapshots (JSON) -> s3://{bucket}/solaron/escalation/state/{date}.json
2. Escalation log audit stream (JSONL) -> s3://{bucket}/solaron/escalation/log/{year}-{month}.jsonl
3. Gupshup inbound log stream (JSONL) -> s3://{bucket}/solaron/gupshup/inbound/{year}-{month}.jsonl
4. Daily generation backup (JSON / Parquet) -> s3://{bucket}/solaron/bronze/daily_gen/{date}.json

Includes local bronze cache fallback when AWS credentials are absent or in development mode.
"""

import datetime
import json
import logging
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


def upload_content_to_s3(
    s3_key: str,
    content: str,
    content_type: str = "application/json"
) -> Dict[str, Any]:
    """
    Uploads string content to S3, or writes to local bronze directory if S3 is unavailable.
    """
    client = get_s3_client()
    bucket = settings.s3_bucket_name or "solaron-data"

    # Always ensure local bronze mirror
    local_path = LOCAL_BRONZE_DIR / s3_key
    local_path.parent.mkdir(parents=True, exist_ok=True)
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(content)

    if client:
        try:
            client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
            )
            logger.info("Successfully uploaded %s to S3 bucket %s", s3_key, bucket)
            return {"status": "uploaded", "target": f"s3://{bucket}/{s3_key}", "size_bytes": len(content)}
        except (ClientError, NoCredentialsError) as e:
            logger.warning("S3 upload failed for %s, cached locally: %s", s3_key, e)
            return {"status": "local_fallback", "target": str(local_path), "error": str(e)}

    return {"status": "local_mirror", "target": str(local_path), "size_bytes": len(content)}


def archive_escalation_state(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Snapshots all current escalation states to JSON:
    s3://{bucket}/solaron/escalation/state/{date}.json
    """
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
    res = upload_content_to_s3(s3_key, content)
    res["count"] = len(records)
    return res


def archive_escalation_log(month: Optional[str] = None) -> Dict[str, Any]:
    """
    Appends monthly escalation log transitions to JSONL:
    s3://{bucket}/solaron/escalation/log/{year}-{month}.jsonl
    """
    if not month:
        month = datetime.date.today().strftime("%Y-%m")

    sql = "SELECT * FROM escalation_log WHERE substr(created_at, 1, 7) = ? ORDER BY id ASC;"
    df = db.query_df(sql, [month], db="crm")
    records = df.to_dict(orient="records") if not df.empty else []

    lines = [json.dumps(r, default=str) for r in records]
    content = "\n".join(lines)
    s3_key = f"solaron/escalation/log/{month}.jsonl"
    res = upload_content_to_s3(s3_key, content, content_type="application/x-ndjson")
    res["count"] = len(records)
    return res


def archive_inbound_log(month: Optional[str] = None) -> Dict[str, Any]:
    """
    Archives Gupshup webhook inbound messages to monthly JSONL:
    s3://{bucket}/solaron/gupshup/inbound/{year}-{month}.jsonl
    """
    if not month:
        month = datetime.date.today().strftime("%Y-%m")

    sql = "SELECT * FROM gupshup_inbound_log WHERE substr(created_at, 1, 7) = ? ORDER BY id ASC;"
    df = db.query_df(sql, [month], db="crm")
    records = df.to_dict(orient="records") if not df.empty else []

    lines = [json.dumps(r, default=str) for r in records]
    content = "\n".join(lines)
    s3_key = f"solaron/gupshup/inbound/{month}.jsonl"
    res = upload_content_to_s3(s3_key, content, content_type="application/x-ndjson")
    res["count"] = len(records)
    return res


def archive_daily_generation(date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Backs up daily generation telemetry for date_str to bronze layer:
    s3://{bucket}/solaron/bronze/daily_gen/{date}.json
    """
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
    res = upload_content_to_s3(s3_key, content)
    res["count"] = len(records)
    return res


def run_nightly_archive(target_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Orchestrates nightly execution across all archival targets.
    """
    if not target_date:
        target_date = datetime.date.today().isoformat()
    month = target_date[:7]

    logger.info("Starting nightly bronze archive for date=%s, month=%s", target_date, month)
    r_state = archive_escalation_state(target_date)
    r_log = archive_escalation_log(month)
    r_inbound = archive_inbound_log(month)
    r_daily = archive_daily_generation(target_date)

    summary = {
        "target_date": target_date,
        "month": month,
        "escalation_state": r_state,
        "escalation_log": r_log,
        "gupshup_inbound": r_inbound,
        "daily_generation": r_daily,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    logger.info("Nightly archive completed: %s", summary)
    return summary
