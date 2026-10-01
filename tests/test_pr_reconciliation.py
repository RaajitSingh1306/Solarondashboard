"""
Unit tests for Performance Ratio (PR) Reconciliation & Hardening (Phase 1, Task 2).

Validates PR formulation, specific yield, CUF, CO2 reduction, and revenue calculations
against 3 hand-computed plant configurations and edge cases.
"""

import math
import sys
from pathlib import Path
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import analytics
from config import settings


def test_hand_calc_plant_1_residential_5kw():
    """
    Plant 1: Residential 5.0 kWp rooftop in Mumbai (September, 30 days).
    GHI = 4.80 kWh/m2/day.
    Actual generation = 576.0 kWh.
    Expected generation = 5.0 * 4.80 * 30 = 720.0 kWh.
    """
    cap = 5.0
    ghi = 4.80
    days = 30
    kwh = 576.0

    pr = analytics.calc_pr(kwh, cap, ghi, days)
    assert pr == 80.0, f"Expected PR 80.0%, got {pr}%"

    sy = analytics.specific_yield(kwh, cap)
    assert sy == 115.2, f"Expected specific yield 115.2, got {sy}"

    rev = analytics.revenue(kwh)
    expected_rev = round(576.0 * settings.price_per_unit, 2)
    assert rev == expected_rev, f"Expected revenue {expected_rev}, got {rev}"

    cuf_val = analytics.cuf(kwh, cap, hours=30 * 24)
    assert cuf_val == 16.0, f"Expected CUF 16.0%, got {cuf_val}%"

    co2 = analytics.co2_saved(kwh)
    assert co2 == 472.32, f"Expected CO2 saved 472.32 kg, got {co2}"


def test_hand_calc_plant_2_commercial_100kw():
    """
    Plant 2: Commercial 100.0 kWp rooftop in Delhi (June, 30 days).
    GHI = 5.20 kWh/m2/day.
    Actual generation = 11,700.0 kWh.
    Expected generation = 100.0 * 5.20 * 30 = 15,600.0 kWh.
    """
    cap = 100.0
    ghi = 5.20
    days = 30
    kwh = 11700.0

    pr = analytics.calc_pr(kwh, cap, ghi, days)
    assert pr == 75.0, f"Expected PR 75.0%, got {pr}%"

    sy = analytics.specific_yield(kwh, cap)
    assert sy == 117.0, f"Expected specific yield 117.0, got {sy}"

    rev = analytics.revenue(kwh)
    expected_rev = round(11700.0 * settings.price_per_unit, 2)
    assert rev == expected_rev, f"Expected revenue {expected_rev}, got {rev}"

    cuf_val = analytics.cuf(kwh, cap, hours=30 * 24)
    assert cuf_val == 16.25, f"Expected CUF 16.25%, got {cuf_val}%"

    co2 = analytics.co2_saved(kwh)
    assert co2 == 9594.0, f"Expected CO2 saved 9594.0 kg, got {co2}"


def test_hand_calc_plant_3_small_residential_3_3kw():
    """
    Plant 3: Small Residential 3.3 kWp in Pune (January, 31 days).
    GHI = 4.60 kWh/m2/day.
    Actual generation = 329.406 kWh.
    Expected generation = 3.3 * 4.60 * 31 = 470.58 kWh.
    """
    cap = 3.3
    ghi = 4.60
    days = 31
    kwh = 329.406

    pr = analytics.calc_pr(kwh, cap, ghi, days)
    assert pr == 70.0, f"Expected PR 70.0%, got {pr}%"

    sy = analytics.specific_yield(kwh, cap)
    assert sy == 99.82, f"Expected specific yield 99.82, got {sy}"

    rev = analytics.revenue(kwh)
    expected_rev = round(329.406 * settings.price_per_unit, 2)
    assert rev == expected_rev, f"Expected revenue {expected_rev}, got {rev}"

    cuf_val = analytics.cuf(kwh, cap, hours=31 * 24)
    assert cuf_val == 13.42, f"Expected CUF 13.42%, got {cuf_val}%"

    co2 = analytics.co2_saved(kwh)
    assert co2 == 270.11, f"Expected CO2 saved 270.11 kg, got {co2}"


def test_revenue_tariff_consistency():
    """Verify revenue uses settings.price_per_unit by default, and respects override."""
    assert settings.price_per_unit == 14.0

    # Default tariff: 100 kWh * 14.0 = 1400.0 INR
    assert analytics.revenue(100.0) == 1400.0

    # Custom tariff override: 100 kWh * 7.5 = 750.0 INR
    assert analytics.revenue(100.0, tariff_inr=7.5) == 750.0

    # None and zero generation
    assert analytics.revenue(None) is None
    assert analytics.revenue(0.0) == 0.0


def test_pr_edge_cases():
    """Verify mathematical boundaries and edge case handling in calc_pr."""
    # Zero or negative capacity
    assert analytics.calc_pr(100.0, 0.0, 4.8, 30) is None
    assert analytics.calc_pr(100.0, -5.0, 4.8, 30) is None

    # Zero or negative GHI
    assert analytics.calc_pr(100.0, 5.0, 0.0, 30) is None
    assert analytics.calc_pr(100.0, 5.0, -1.0, 30) is None

    # Zero or negative days
    assert analytics.calc_pr(100.0, 5.0, 4.8, 0) is None
    assert analytics.calc_pr(100.0, 5.0, 4.8, -10) is None

    # Negative generation is clamped to 0
    assert analytics.calc_pr(-50.0, 5.0, 4.8, 30) == 0.0

    # Zero generation
    assert analytics.calc_pr(0.0, 5.0, 4.8, 30) == 0.0

    # None parameters
    assert analytics.calc_pr(None, 5.0, 4.8, 30) is None
    assert analytics.calc_pr(100.0, None, 4.8, 30) is None
    assert analytics.calc_pr(100.0, 5.0, None, 30) is None
    assert analytics.calc_pr(100.0, 5.0, 4.8, None) is None
