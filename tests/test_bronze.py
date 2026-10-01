"""
Unit tests for Bronze Storage Engine (Phase 2, Task 6).

Validates immutable raw partitioning, SHA-256 deduplication, gzip compression,
and retrieval integrity.
"""

import datetime
import shutil
import sys
from pathlib import Path
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import bronze


def test_archive_and_read_bronze_roundtrip(tmp_path):
    test_source = "test_vendor"
    test_endpoint = "telemetry_test"
    test_payload = {
        "status": "success",
        "plant_id": 9999,
        "energy_kwh": 45.2,
        "timestamp": "2026-10-01T12:00:00",
    }
    date_str = "2026-10-01"

    archived_path = bronze.archive_raw_response(
        test_source, test_endpoint, test_payload, date_str=date_str, compress=True
    )
    assert archived_path.exists()
    assert str(archived_path).endswith(".json.gz")
    assert f"source={test_source}" in str(archived_path)
    assert f"ingest_date={date_str}" in str(archived_path)

    # Read back and verify exact JSON fidelity
    data_back = bronze.read_bronze_archive(archived_path)
    assert data_back == test_payload


def test_bronze_idempotency_content_hash():
    test_source = "test_vendor"
    test_endpoint = "idempotent_test"
    test_payload = {"key": "unique_reading_123", "value": 100}
    date_str = "2026-10-01"

    path1 = bronze.archive_raw_response(test_source, test_endpoint, test_payload, date_str=date_str)
    path2 = bronze.archive_raw_response(test_source, test_endpoint, test_payload, date_str=date_str)

    # Must return exact same file without duplication
    assert path1 == path2


def test_list_bronze_archives_filtering():
    test_source = "test_filter"
    bronze.archive_raw_response(test_source, "ep1", {"data": 1}, date_str="2026-10-01")
    bronze.archive_raw_response(test_source, "ep2", {"data": 2}, date_str="2026-10-01")

    filtered = bronze.list_bronze_archives(source=test_source, date_str="2026-10-01")
    assert len(filtered) >= 2


def test_uncompressed_bronze_archive():
    test_source = "test_vendor"
    test_endpoint = "uncompressed"
    test_payload = {"status": "ok"}
    date_str = "2026-10-01"

    path = bronze.archive_raw_response(
        test_source, test_endpoint, test_payload, date_str=date_str, compress=False
    )
    assert path.exists()
    assert str(path).endswith(".json")

    data = bronze.read_bronze_archive(path)
    assert data == test_payload
