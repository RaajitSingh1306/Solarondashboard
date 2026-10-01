"""
Unit and integration tests for Phase 6 (PV Physics, Loss Ranges, Robust Stats)
and Phase 7 (Forecasting).
"""

import math
import sys
from pathlib import Path
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import analytics
import db
import forecasting
import ml_analytics
import physics


def test_cell_temperature_estimation():
    # At 25°C ambient and 800 W/m2, cell should be 25 + (25/800)*800 = 50°C
    t_cell = physics.estimate_cell_temperature(ambient_temp_c=25.0, irradiance_w_m2=800.0)
    assert t_cell == pytest.approx(50.0, abs=0.5)

    # At 35°C ambient and 0 W/m2 (night/dark), cell equals ambient
    t_cell_night = physics.estimate_cell_temperature(ambient_temp_c=35.0, irradiance_w_m2=0.0)
    assert t_cell_night == pytest.approx(35.0, abs=0.1)


def test_temperature_derating():
    # At STC (25°C), derate factor should be exactly 1.00
    derate_stc = physics.calculate_temperature_derate(cell_temp_c=25.0)
    assert derate_stc == pytest.approx(1.000, abs=0.001)

    # At 45°C cell temp (20°C above STC), gamma = 0.38%/°C -> 1 - 20 * 0.0038 = 0.924
    derate_hot = physics.calculate_temperature_derate(cell_temp_c=45.0)
    assert derate_hot == pytest.approx(0.924, abs=0.005)


def test_poa_irradiance_transposition():
    # Zero or missing tilt returns raw GHI
    poa_flat = physics.calculate_poa_irradiance(ghi_kwh_m2_day=5.0, tilt_deg=0.0)
    assert poa_flat == pytest.approx(5.0, abs=0.05)

    # Winter month (month 12) with 20° tilt at 20°N latitude should have transposition gain > 1.0
    poa_winter = physics.calculate_poa_irradiance(ghi_kwh_m2_day=4.5, tilt_deg=20.0, latitude=20.0, month=12)
    assert poa_winter >= 4.5  # Winter sun is low in southern sky; south-facing tilt increases POA


def test_physics_expected_energy():
    res = physics.calculate_physics_expected_energy(
        capacity_kwp=10.0,
        ghi_kwh_m2_day=5.0,
        days=30,
        ambient_temp_c=35.0,
        tilt_deg=18.0,
        latitude=20.0,
        month=9,
    )
    assert "base_expected_kwh" in res
    assert "adjusted_expected_kwh" in res
    assert "thermal_loss_kwh" in res
    assert res["base_expected_kwh"] == pytest.approx(1500.0, abs=1.0)
    assert res["adjusted_expected_kwh"] > 0
    assert res["thermal_loss_kwh"] >= 0


def test_loss_waterfall_uncertainty_ranges():
    wf = analytics.get_loss_waterfall("2026-09")
    assert "loss_ranges" in wf
    ranges = wf["loss_ranges"]

    # Check that measured buckets have identical min and max
    assert ranges["comm_loss"]["type"] == "measured"
    assert ranges["comm_loss"]["min_kwh"] == ranges["comm_loss"]["max_kwh"]
    assert ranges["shutdown_loss"]["type"] == "measured"
    assert ranges["shutdown_loss"]["min_kwh"] == ranges["shutdown_loss"]["max_kwh"]

    # Check that estimated buckets have bounded ranges
    assert ranges["weather_loss"]["type"] == "estimated"
    assert ranges["weather_loss"]["min_kwh"] <= ranges["weather_loss"]["point_kwh"] <= ranges["weather_loss"]["max_kwh"]
    assert ranges["soiling_loss"]["type"] == "estimated"
    assert ranges["soiling_loss"]["min_kwh"] <= ranges["soiling_loss"]["point_kwh"] <= ranges["soiling_loss"]["max_kwh"]
    assert ranges["shading_loss"]["type"] == "estimated"
    assert ranges["shading_loss"]["min_kwh"] <= ranges["shading_loss"]["point_kwh"] <= ranges["shading_loss"]["max_kwh"]

    # Check unattributed residual bucket
    assert ranges["unattributed_loss"]["type"] == "residual"


def test_rpi_to_tier_mapping():
    assert ml_analytics.rpi_to_tier(1.05, 0.98) == "Best"
    assert ml_analytics.rpi_to_tier(0.90, 0.95) == "Good"
    assert ml_analytics.rpi_to_tier(0.78, 0.95) == "Needs Attention"
    assert ml_analytics.rpi_to_tier(0.55, 0.95) == "Critical"
    assert ml_analytics.rpi_to_tier(1.00, 0.40) == "Critical"  # Poor availability forces Critical
    assert ml_analytics.rpi_to_tier(None) == "Critical"


def test_robust_z_score():
    peers = [1.0, 1.02, 0.98, 1.01, 0.99, 1.00, 1.03]
    # Value close to median should have near-zero z-score
    z_med = ml_analytics.robust_z_score(1.00, peers)
    assert abs(z_med) < 0.5

    # Outlier should have large magnitude z-score
    z_outlier = ml_analytics.robust_z_score(0.60, peers)
    assert z_outlier < -3.0


def test_cusum_drift_detector():
    # Healthy stable series followed by progressive degradation
    stable = [1.0] * 10
    drift_down = [0.95, 0.90, 0.85, 0.75, 0.65, 0.50]
    series = stable + drift_down
    alarms = ml_analytics.cusum_drift_detector(series, threshold=3.5, drift=0.3)
    assert len(alarms) > 0
    # Alarm should trigger during the degradation phase
    assert alarms[0] >= 10


def test_forecasting_scaffold():
    forecaster = forecasting.ExpectedGenerationForecaster()
    # Baseline forecast check
    pred = forecaster.baseline_predict(capacity_kwp=5.0, ghi_kwh_m2=5.0, rpi_baseline=1.0)
    assert "forecast_kwh" in pred
    assert pred["p10_kwh"] <= pred["forecast_kwh"] <= pred["p90_kwh"]

    # Fleet forecast check
    fleet_fc = forecasting.forecast_fleet_generation(target_date="2026-10-02")
    assert "forecast_total_mwh" in fleet_fc
    assert fleet_fc["total_plants"] > 0
