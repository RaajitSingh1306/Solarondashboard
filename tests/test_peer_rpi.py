"""
Unit tests for Peer Groups, RPI, and Sawtooth Detection (Phase 3, Tasks 10-12).

Validates peer group clustering, peer reference yields, RPI time series,
baseline calculation, and soiling sawtooth detection.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import baseline
import peer_group
import rpi


def test_peer_group_assignment():
    test_plants = [
        {"plant_id": f"p_ngp_{i}", "city": "Nagpur", "state": "Maharashtra"} for i in range(10)
    ] + [
        {"plant_id": "p_isolated_1", "city": "Remote Hamlet", "state": "Maharashtra"}
    ]
    groups = peer_group.build_fleet_peer_groups(test_plants)

    # Nagpur plant gets city-level group (>= 5 peers)
    ngp_group = groups["p_ngp_0"]
    assert ngp_group["level"] == "city"
    assert "Nagpur" in ngp_group["label"]
    assert ngp_group["peer_count"] == 9

    # Isolated plant gets state-level group
    iso_group = groups["p_isolated_1"]
    assert iso_group["level"] == "state"
    assert "Maharashtra" in iso_group["label"]


def test_rpi_math_and_tier_classification():
    # Peer reference = 4.0 kWh/kWp
    # Plant 1: 4.0 kWh/kWp -> RPI 1.0 -> Best
    assert rpi.classify_rpi_tier(1.0) == "Best"

    # Plant 2: 3.4 kWh/kWp -> RPI 0.85 -> Good
    assert rpi.classify_rpi_tier(0.85) == "Good"

    # Plant 3: 2.8 kWh/kWp -> RPI 0.70 -> Could Be Better
    assert rpi.classify_rpi_tier(0.70) == "Could Be Better"

    # Plant 4: 1.8 kWh/kWp -> RPI 0.45 -> Needs Attention
    assert rpi.classify_rpi_tier(0.45) == "Needs Attention"

    # Plant 5: 0.8 kWh/kWp -> RPI 0.20 -> Critical
    assert rpi.classify_rpi_tier(0.20) == "Critical"


def test_baseline_and_sawtooth_detection():
    # Construct a synthetic 30-day timeseries showing gradual soiling decay
    # followed by an abrupt cleaning reset on day 20
    dates = [f"2026-09-{i:02d}" for i in range(1, 31)]
    rpi_vals = []
    for i in range(1, 21):
        # Gradual decline from 1.0 down to 0.75
        rpi_vals.append(1.0 - (i - 1) * 0.013)
    # Day 21 cleaning jump up to 0.98
    for i in range(21, 31):
        rpi_vals.append(0.98 - (i - 21) * 0.01)

    df = pd.DataFrame({
        "date": dates,
        "kwh": [15.0] * 30,
        "rpi": rpi_vals,
        "rolling_rpi": rpi_vals,
    })

    base_rpi = baseline.compute_plant_baseline_rpi(df)
    assert 0.90 <= base_rpi <= 1.05

    sawtooth_events = baseline.detect_soiling_sawtooth(df, min_decay_days=10, min_reset_jump=0.15)
    assert len(sawtooth_events) >= 1
    event = sawtooth_events[0]
    assert event["pre_reset_rpi"] < 0.80
    assert event["post_reset_rpi"] >= 0.90
    assert event["recovered_rpi_pct"] >= 15.0
