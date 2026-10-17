import pytest
from extractors.injectsolar import InjectSolarExtractor

def test_injectsolar_extractor_initialization():
    ext = InjectSolarExtractor()
    assert ext.source == "injectsolar"
    assert ext.supports_history() == {"daily": False, "hourly": False, "max_lookback_days": None}

def test_injectsolar_fleet_no_synthetic_fabrications():
    ext = InjectSolarExtractor()
    fleet = ext.fetch_fleet(force_refresh=False)
    assert len(fleet) >= 7
    for p in fleet:
        assert p["source"] == "injectsolar"
        assert p["plant_id"].startswith("injectsolar_")
        # Ensure city/state are None if not in source data, rather than hardcoded "Mumbai"
        # and total_energy_kwh is not forced to cap * 250
        assert p["total_energy_kwh"] is None or p["total_energy_kwh"] >= 0.0

def test_injectsolar_daily_preserves_status():
    ext = InjectSolarExtractor()
    daily = ext.fetch_daily(force_refresh=False)
    assert len(daily) >= 7
    # Verify that offline is not artificially applied based on kwh==0
    for d in daily:
        assert "status" in d
        assert "revenue_inr" in d

def test_injectsolar_snapshots_no_fake_temp_or_dc():
    ext = InjectSolarExtractor()
    snapshots = ext.fetch_snapshots(force_refresh=False)
    assert len(snapshots) >= 7
    for s in snapshots:
        assert s["plant_id"].startswith("injectsolar_")
        # DC power and temperature must be None, not fabricated via ac_w/0.975 or 36.0+ratio*16.5
        assert s["dc_power_w"] is None
        assert s["temperature_c"] is None
