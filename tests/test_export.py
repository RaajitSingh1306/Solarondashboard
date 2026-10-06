"""Tests for Solaron Export Endpoints and Column Selection System."""
import io
import asyncio
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from app import app
from routes.export import (
    MONTHLY_COLUMNS,
    DAILY_COLUMNS,
    get_export_columns,
    export_fleet_monthly,
    export_fleet_daily,
)

client = TestClient(app)

def test_columns_metadata_endpoint():
    """Verify /api/export/columns returns correct structures for monthly and daily."""
    res_m = client.get("/api/export/columns?dataset=monthly")
    assert res_m.status_code == 200
    m_cols = res_m.json()
    assert len(m_cols) == len(MONTHLY_COLUMNS)
    assert any(c["key"] == "plant_name" for c in m_cols)
    assert any(c["group"] == "Loss Attribution (NASA Benchmark)" for c in m_cols)
    assert any(c["key"] == "expected_kwh" for c in m_cols)

    res_d = client.get("/api/export/columns?dataset=daily")
    assert res_d.status_code == 200
    d_cols = res_d.json()
    assert len(d_cols) == len(DAILY_COLUMNS)
    assert any(c["key"] == "date" for c in d_cols)

def test_fleet_monthly_default_export():
    """Verify monthly export defaults to standard monthly columns and returns CSV."""
    res = client.get("/api/export/fleet-monthly?fmt=csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment; filename=fleet_monthly_" in res.headers["content-disposition"]
    
    # Check that CSV has content and header
    csv_text = res.text
    assert len(csv_text.strip()) > 0
    lines = csv_text.strip().split("\n")
    headers = [h.strip() for h in lines[0].split(",")]
    assert "Plant ID" in headers
    assert "Plant Name" in headers
    assert "Total Generation (kWh)" in headers
    assert "Performance Ratio (%)" in headers

def test_fleet_monthly_custom_columns_and_ordering():
    """Verify custom cols parameter selects and orders requested columns accurately."""
    cols = "plant_id,month,kwh,pr_pct,expected_kwh,shortfall_kwh"
    res = client.get(f"/api/export/fleet-monthly?fmt=csv&cols={cols}")
    assert res.status_code == 200
    
    df = pd.read_csv(io.StringIO(res.text))
    expected_cols = [
        "Plant ID",
        "Month (YYYY-MM)",
        "Total Generation (kWh)",
        "Performance Ratio (%)",
        "Expected Baseline (kWh)",
        "Net Shortfall (kWh)",
    ]
    assert list(df.columns) == expected_cols

def test_fleet_monthly_filters():
    """Verify month filter, range filter, and source platform filter."""
    # Filter single month
    res = client.get("/api/export/fleet-monthly?fmt=csv&month=2026-09&cols=plant_id,month,source")
    assert res.status_code == 200
    df = pd.read_csv(io.StringIO(res.text))
    if not df.empty:
        assert (df["Month (YYYY-MM)"] == "2026-09").all()

    # Filter source platform
    res_growatt = client.get("/api/export/fleet-monthly?fmt=csv&source=growatt&cols=plant_id,source")
    assert res_growatt.status_code == 200
    df_g = pd.read_csv(io.StringIO(res_growatt.text))
    if not df_g.empty:
        assert (df_g["Platform"].str.lower() == "growatt").all()

def test_fleet_monthly_excel_export():
    """Verify Excel XLSX export produces valid spreadsheet bytes."""
    res = client.get("/api/export/fleet-monthly?fmt=xlsx&cols=plant_id,plant_name,month,kwh")
    assert res.status_code == 200
    assert "spreadsheetml.sheet" in res.headers["content-type"]
    
    excel_bytes = io.BytesIO(res.content)
    df = pd.read_excel(excel_bytes, sheet_name="Data")
    assert "Plant ID" in df.columns
    assert "Total Generation (kWh)" in df.columns

def test_fleet_daily_month_filter_bugfix():
    """Verify fleet-daily accepts month param and properly constrains daily dates."""
    res = client.get("/api/export/fleet-daily?fmt=csv&month=2026-08&cols=plant_id,date,kwh")
    assert res.status_code == 200
    df = pd.read_csv(io.StringIO(res.text))
    if not df.empty:
        # All rows should belong to 2026-08
        assert df["Date (YYYY-MM-DD)"].str.startswith("2026-08").all()

def test_invalid_columns_ignored_safely():
    """Verify SQL injection or unknown column keys are safely ignored."""
    malicious_cols = "plant_id,plant_name; DROP TABLE plants;--,invalid_nonexistent_col,kwh"
    res = client.get(f"/api/export/fleet-monthly?fmt=csv&cols={malicious_cols}")
    assert res.status_code == 200
    df = pd.read_csv(io.StringIO(res.text))
    assert "Plant ID" in df.columns
    assert "Total Generation (kWh)" in df.columns
    assert len(df.columns) == 2


def test_export_presets_validity():
    """Verify all column presets reference existing columns in the registries."""
    from ui.export_dialog import MONTHLY_PRESETS, DAILY_PRESETS

    for name, cols in MONTHLY_PRESETS.items():
        for col in cols:
            assert col in MONTHLY_COLUMNS, f"Invalid column {col} in monthly preset '{name}'"

    for name, cols in DAILY_PRESETS.items():
        for col in cols:
            assert col in DAILY_COLUMNS, f"Invalid column {col} in daily preset '{name}'"


def test_export_preferences_persistence(tmp_path, monkeypatch):
    """Verify loading and saving export preferences to JSON file."""
    import ui.export_dialog as ed

    test_file = tmp_path / "test_export_preferences.json"
    monkeypatch.setattr(ed, "PREFS_FILE", test_file)

    # Save custom preferences
    test_prefs = {
        "monthly": {"plant_id", "month", "kwh"},
        "daily": {"plant_id", "date", "kwh"},
    }
    ed._save_persisted_cols(test_prefs)
    assert test_file.exists()

    loaded = ed._load_persisted_cols()
    assert loaded["monthly"] == {"plant_id", "month", "kwh"}
    assert loaded["daily"] == {"plant_id", "date", "kwh"}
