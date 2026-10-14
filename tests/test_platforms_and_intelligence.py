"""
Tests for 5-platform support and Fleet Intelligence engine.
"""

import pytest
from fastapi.testclient import TestClient
from app import app
from core import platforms, fleet_intelligence
from core.contracts import PlantMetadataSchema, DailyGenerationSchema
import pandas as pd


@pytest.fixture
def client():
    return TestClient(app)


def test_platform_registry_completeness():
    keys = platforms.platform_keys()
    assert "growatt" in keys
    assert "isolarcloud" in keys
    assert "suryalog" in keys
    assert "fronius" in keys
    assert "injectsolar" in keys
    assert len(keys) == 5

    assert platforms.label("fronius") == "Fronius"
    assert platforms.label("injectsolar") == "InjectSolar"
    assert platforms.label("All") == "All Platforms"

    opts = platforms.options(include_all=True)
    assert "All" in opts
    assert "fronius" in opts
    assert "injectsolar" in opts

    sentence = platforms.names_sentence()
    assert "Fronius" in sentence
    assert "InjectSolar" in sentence


def test_contracts_allow_all_platforms():
    for plat in ["growatt", "isolarcloud", "suryalog", "fronius", "injectsolar"]:
        df_plant = pd.DataFrame([{
            "plant_id": f"{plat}_test_1",
            "source": plat,
            "plant_name": f"Test {plat.title()}",
            "capacity_kwp": 10.0,
            "operational_status": "active",
            "latitude": 28.6,
            "longitude": 77.2,
            "city": "Delhi",
            "geocode_level": "city_centroid",
        }])
        PlantMetadataSchema.validate(df_plant)


def test_fleet_intelligence_kpis_all_platforms():
    kpis = fleet_intelligence.fleet_kpis(month="2026-10")
    assert "pr_weighted_pct" in kpis
    assert "cuf_pct" in kpis
    assert "availability_pct" in kpis
    assert "platforms" in kpis
    plat_keys = [p["key"] for p in kpis["platforms"]]
    assert "growatt" in plat_keys
    assert "isolarcloud" in plat_keys
    assert "suryalog" in plat_keys
    assert "fronius" in plat_keys
    assert "injectsolar" in plat_keys


def test_fleet_intelligence_forecast():
    fc = fleet_intelligence.forecast_fleet(horizon=7)
    assert fc.get("status") == "ok"
    assert len(fc.get("forecast_dates", [])) == 7
    assert len(fc.get("forecast_sy", [])) == 7
    assert len(fc.get("forecast_lo_sy", [])) == 7
    assert len(fc.get("forecast_hi_sy", [])) == 7
    assert "backtest" in fc


def test_fleet_intelligence_month_projection():
    proj = fleet_intelligence.project_month_end(month="2026-10")
    assert proj.get("status") == "ok"
    assert "p10_kwh" in proj
    assert "p50_kwh" in proj
    assert "p90_kwh" in proj
    assert proj["p10_kwh"] <= proj["p50_kwh"] <= proj["p90_kwh"]


def test_export_weekly_and_yearly_endpoints(client):
    # Weekly export
    res_w = client.get("/api/export/fleet-weekly?fmt=csv")
    assert res_w.status_code == 200
    assert "text/csv" in res_w.headers["content-type"]
    assert "attachment" in res_w.headers["content-disposition"]
    assert "Period" in res_w.text

    # Yearly export
    res_y = client.get("/api/export/fleet-yearly?fmt=csv")
    assert res_y.status_code == 200
    assert "text/csv" in res_y.headers["content-type"]
    assert "Period" in res_y.text

    # Column definitions
    res_cols_w = client.get("/api/export/columns?dataset=weekly")
    assert res_cols_w.status_code == 200
    assert len(res_cols_w.json()) > 0

    res_cols_y = client.get("/api/export/columns?dataset=yearly")
    assert res_cols_y.status_code == 200
    assert len(res_cols_y.json()) > 0


def test_intelligence_api_endpoints(client):
    res_kpis = client.get("/api/data/intelligence/kpis?month=2026-10")
    assert res_kpis.status_code == 200
    assert "pr_weighted_pct" in res_kpis.json()

    res_fc = client.get("/api/data/intelligence/forecast?horizon=7")
    assert res_fc.status_code == 200
    assert res_fc.json().get("status") == "ok"

    res_proj = client.get("/api/data/intelligence/month-projection?month=2026-10")
    assert res_proj.status_code == 200
    assert res_proj.json().get("status") == "ok"

    res_health = client.get("/api/data/intelligence/health")
    assert res_health.status_code == 200
    assert res_health.json().get("status") == "ok"
