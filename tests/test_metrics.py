"""
Unit tests for Standard Metrics & KPI Specification Engine (Phase 1, Task 5).

Validates metric formulas, catalog definitions, bounds, RPI calculation,
revenue tariff consistency, and confidence score generation.
"""

import sys
from pathlib import Path
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import metrics
from config import settings


def test_metric_catalog_completeness():
    required_keys = ["name", "symbol", "unit", "formula", "description", "edge_cases"]
    required_metrics = [
        "specific_yield", "yield_per_day", "pr_pct", "cuf_pct",
        "rpi", "revenue_inr", "co2_saved_kg", "plant_availability_pct"
    ]
    for m in required_metrics:
        assert m in metrics.METRIC_CATALOG, f"Missing metric {m} in catalog"
        for k in required_keys:
            assert k in metrics.METRIC_CATALOG[m], f"Missing key {k} in metric {m}"


def test_specific_yield_and_yield_per_day():
    # Normal daily yield: 18.0 kWh / 4.0 kWp = 4.5 kWh/kWp
    sy = metrics.compute_specific_yield(18.0, 4.0, is_daily=True)
    assert sy == 4.5

    # Clamping daily at 8.0 max
    sy_high = metrics.compute_specific_yield(50.0, 4.0, is_daily=True)
    assert sy_high == 8.0

    # Yield per day over 10 days: 180 kWh / (4.0 * 10) = 4.5
    ypd = metrics.compute_yield_per_day(180.0, 4.0, days=10)
    assert ypd == 4.5


def test_pr_formulation():
    # 5 kWp, 4.8 GHI, 30 days, 576 kWh -> 80.0%
    pr = metrics.compute_pr(576.0, 5.0, 4.8, 30)
    assert pr == 80.0

    # Negative generation clamped to 0
    assert metrics.compute_pr(-10.0, 5.0, 4.8, 30) == 0.0

    # Missing/invalid inputs return None
    assert metrics.compute_pr(None, 5.0, 4.8, 30) is None
    assert metrics.compute_pr(500.0, 0.0, 4.8, 30) is None
    assert metrics.compute_pr(500.0, 5.0, 0.0, 30) is None


def test_cuf_formulation():
    # 100 kWp, 11700 kWh in June (30 days * 24 h = 720 h) -> 16.25%
    cuf = metrics.compute_cuf(11700.0, 100.0, hours=720)
    assert cuf == 16.25

    # Clamping at physical ceiling 35%
    assert metrics.compute_cuf(50000.0, 100.0, hours=720) == 35.0


def test_rpi_formulation():
    # Plant yield 4.0, peer median 4.0 -> RPI 1.0 (on par with peers)
    assert metrics.compute_rpi(4.0, 4.0) == 1.0

    # Plant yield 4.8, peer median 4.0 -> RPI 1.2 (+20% vs peers)
    assert metrics.compute_rpi(4.8, 4.0) == 1.2

    # Plant yield 2.0, peer median 4.0 -> RPI 0.5 (-50% vs peers, suspect issue)
    assert metrics.compute_rpi(2.0, 4.0) == 0.5

    # Edge cases
    assert metrics.compute_rpi(None, 4.0) is None
    assert metrics.compute_rpi(4.0, None) is None


def test_revenue_and_co2():
    # Revenue at default 14.0 INR: 200 kWh * 14.0 = 2800.0 INR
    assert metrics.compute_revenue(200.0) == 2800.0
    assert metrics.compute_revenue(200.0, tariff_inr=8.0) == 1600.0

    # CO2 saved: 200 kWh * 0.82 = 164.0 kg CO2
    assert metrics.compute_co2_saved(200.0) == 164.0


def test_availability():
    # 27 producing days, 3 fault days -> 90.0%
    assert metrics.compute_availability(27, 3) == 90.0
    assert metrics.compute_availability(30, 0) == 100.0
    assert metrics.compute_availability(0, 30) == 0.0


def test_confidence_indicator():
    # High confidence: exact GPS + strong peer group (>= 15 peers)
    hi = metrics.get_confidence_indicator("exact", peer_count=20)
    assert hi["confidence_tier"] == "High"
    assert hi["confidence_score"] >= 80

    # Medium confidence: city centroid + 8 peers
    med = metrics.get_confidence_indicator("city_centroid", peer_count=8)
    assert med["confidence_tier"] == "Medium"
    assert 50 <= med["confidence_score"] < 80

    # Low confidence: unresolved + 0 peers
    low = metrics.get_confidence_indicator("unresolved", peer_count=0)
    assert low["confidence_tier"] == "Low"
    assert low["confidence_score"] < 50
