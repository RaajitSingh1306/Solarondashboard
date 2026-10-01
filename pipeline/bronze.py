"""
Solaron Bronze Storage Engine (Phase 2, Task 6).

Implements the immutable raw data lake (Bronze Layer) for vendor API responses:
- Partitions by: source={source}/ingest_date={YYYY-MM-DD}/
- File naming: {endpoint}_{timestamp}_{content_hash}.json.gz
- Idempotent: Content-addressable SHA-256 deduplication
- Zero data loss: Preserves raw responses before any normalization or transformation
"""

import datetime
import gzip
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
BRONZE_ROOT = BASE_DIR / "data" / "lake" / "bronze"


def get_bronze_dir(source: str, date_str: Optional[str] = None) -> Path:
    """Return the partitioned directory path for source and date."""
    if not date_str:
        date_str = datetime.date.today().isoformat()
    clean_source = source.lower().strip()
    target_dir = BRONZE_ROOT / f"source={clean_source}" / f"ingest_date={date_str}"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def archive_raw_response(
    source: str,
    endpoint: str,
    data: Union[Dict[str, Any], List[Any], str, bytes],
    date_str: Optional[str] = None,
    compress: bool = True,
) -> Path:
    """
    Archive raw API response into immutable bronze partition.
    
    Args:
        source: Vendor platform ('growatt', 'isolarcloud', 'suryalog', 'weather', etc.)
        endpoint: API endpoint or payload identifier ('fleet', 'daily', 'monthly', 'snapshots')
        data: Raw JSON-serializable object, string, or bytes
        date_str: Ingest date partition (defaults to today)
        compress: Whether to compress with gzip (.json.gz)
        
    Returns:
        Path to the persisted immutable bronze file.
    """
    if not date_str:
        date_str = datetime.date.today().isoformat()

    # Serialize payload to bytes
    if isinstance(data, (dict, list)):
        payload_bytes = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    elif isinstance(data, str):
        payload_bytes = data.encode("utf-8")
    elif isinstance(data, bytes):
        payload_bytes = data
    else:
        payload_bytes = str(data).encode("utf-8")

    # Content-based hash for deduplication
    content_hash = hashlib.sha256(payload_bytes).hexdigest()[:12]
    now_ts = datetime.datetime.now().strftime("%H%M%S")
    clean_endpoint = endpoint.lower().replace("/", "_").replace("\\", "_").strip()

    target_dir = get_bronze_dir(source, date_str)

    if compress:
        file_path = target_dir / f"{clean_endpoint}_{now_ts}_{content_hash}.json.gz"
        # Check if identical hash file already exists in partition
        existing = list(target_dir.glob(f"{clean_endpoint}_*_{content_hash}.json.gz"))
        if existing:
            return existing[0]

        with gzip.open(file_path, "wb") as f:
            f.write(payload_bytes)
    else:
        file_path = target_dir / f"{clean_endpoint}_{now_ts}_{content_hash}.json"
        existing = list(target_dir.glob(f"{clean_endpoint}_*_{content_hash}.json"))
        if existing:
            return existing[0]

        with open(file_path, "wb") as f:
            f.write(payload_bytes)

    logger.info(f"Archived bronze record: {file_path}")
    return file_path


def read_bronze_archive(file_path: Union[str, Path]) -> Any:
    """Read and deserialize a bronze archive file (.json or .json.gz)."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Bronze archive not found: {p}")

    if p.suffix == ".gz":
        with gzip.open(p, "rt", encoding="utf-8") as f:
            content = f.read()
    else:
        with open(p, "rt", encoding="utf-8") as f:
            content = f.read()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def list_bronze_archives(
    source: Optional[str] = None, date_str: Optional[str] = None
) -> List[Path]:
    """List archived raw responses matching optional source and date filters."""
    if not BRONZE_ROOT.exists():
        return []

    pattern = ""
    if source:
        pattern += f"source={source.lower()}/"
    else:
        pattern += "source=*/"

    if date_str:
        pattern += f"ingest_date={date_str}/*"
    else:
        pattern += "ingest_date=*/*"

    return sorted(list(BRONZE_ROOT.glob(pattern)))


def backfill_existing_raw_files() -> int:
    """
    Bootstrap the Bronze layer by copying and indexing existing raw vendor files from data/raw/.
    """
    raw_dir = BASE_DIR / "data" / "raw"
    if not raw_dir.exists():
        return 0

    count = 0
    today_str = datetime.date.today().isoformat()

    # 1. Growatt plant list
    gw_plant_list = raw_dir / "growatt" / "plant_list_live.json"
    if gw_plant_list.exists():
        try:
            with open(gw_plant_list, "r", encoding="utf-8") as f:
                data = json.load(f)
            archive_raw_response("growatt", "fleet_list_live", data, date_str=today_str)
            count += 1
        except Exception as e:
            logger.error(f"Error archiving {gw_plant_list}: {e}")

    # 2. iSolarCloud raw files
    iso_dir = raw_dir / "isolarcloud"
    if iso_dir.exists():
        for jf in iso_dir.glob("*.json"):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                archive_raw_response("isolarcloud", jf.stem, data, date_str=today_str)
                count += 1
            except Exception:
                pass

    # 3. SuryaLog raw files
    surya_dir = raw_dir / "suryalog"
    if surya_dir.exists():
        for jf in surya_dir.glob("*.json"):
            try:
                with open(jf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                archive_raw_response("suryalog", jf.stem, data, date_str=today_str)
                count += 1
            except Exception:
                pass

    return count
