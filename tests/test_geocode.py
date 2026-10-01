"""
Unit tests for Pincode Geocoding Module (Phase 1, Task 3).

Validates PIN code extraction, local centroid lookup, resolution hierarchy,
and fleet coverage >= 90%.
"""

import sys
from pathlib import Path
import pytest

cur_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(cur_dir.parent))

import db
import geocode


def test_extract_pincode():
    # Standard address with PIN code
    addr1 = "Mathuradas Mill Compound, Sitaram Jadhav Marg, Lower Parel, Mumbai, Maharashtra 400013, India"
    assert geocode.extract_pincode(addr1) == "400013"

    # Address with punctuation and spaces
    addr2 = "Chandrapur - Anchaleshwar Gate Rd, Bazar Ward, Chandrapur, Maharashtra 442402, India"
    assert geocode.extract_pincode(addr2) == "442402"

    # Nagpur pin
    addr3 = "Plot 24, Ramdaspeth, Nagpur 440010"
    assert geocode.extract_pincode(addr3) == "440010"

    # No pin
    assert geocode.extract_pincode("Some generic plant name with no pin") is None
    assert geocode.extract_pincode("") is None
    assert geocode.extract_pincode(None) is None


def test_lookup_pincode():
    res = geocode.lookup_pincode("440001")
    assert res is not None
    assert res["district"] == "Nagpur"
    assert res["state"] == "Maharashtra"
    assert 21.0 <= res["latitude"] <= 21.3
    assert 79.0 <= res["longitude"] <= 79.2

    # Mumbai pin
    res_mum = geocode.lookup_pincode("400013")
    assert res_mum is not None
    assert res_mum["district"] == "Mumbai"
    assert 18.8 <= res_mum["latitude"] <= 19.2


def test_lookup_city():
    res = geocode.lookup_city("Nagpur")
    assert res is not None
    assert 21.0 <= res["latitude"] <= 21.3
    assert res["state"] == "Maharashtra"

    res_pune = geocode.lookup_city("pune")
    assert res_pune is not None
    assert 18.4 <= res_pune["latitude"] <= 18.7

    res_raipur = geocode.lookup_city("Raipur")
    assert res_raipur is not None
    assert res_raipur["state"] == "Chhattisgarh"


def test_geocode_plant_hierarchy():
    # 1. Exact GPS already present
    p1 = {"plant_id": "test_1", "latitude": 19.0760, "longitude": 72.8777}
    g1 = geocode.geocode_plant(p1)
    assert g1["geocode_level"] == "exact"
    assert g1["latitude"] == 19.0760

    # 2. Pincode centroid from address
    p2 = {
        "plant_id": "test_2",
        "latitude": 0.0,
        "longitude": 0.0,
        "plantAddress": "Bazar Ward, Chandrapur, Maharashtra 442402, India",
    }
    g2 = geocode.geocode_plant(p2)
    assert g2["geocode_level"] == "pincode_centroid"
    assert 19.8 <= g2["latitude"] <= 20.1
    assert 79.1 <= g2["longitude"] <= 79.4

    # 3. City centroid from city name
    p3 = {"plant_id": "test_3", "city": "Gondia"}
    g3 = geocode.geocode_plant(p3)
    assert g3["geocode_level"] == "city_centroid"
    assert 21.3 <= g3["latitude"] <= 21.6

    # 4. State default from state name
    p4 = {"plant_id": "test_4", "state": "Chhattisgarh"}
    g4 = geocode.geocode_plant(p4)
    assert g4["geocode_level"] == "state_default"

    # 5. Unresolved
    p5 = {"plant_id": "test_5"}
    g5 = geocode.geocode_plant(p5)
    assert g5["geocode_level"] == "unresolved"


def test_fleet_geocoding_coverage():
    """Verify acceptance criterion: >= 90% of plants have resolved geocoding."""
    db.init_db()
    counts = geocode.geocode_all_plants_in_db()

    total = sum(counts.values())
    assert total > 0, "No plants found in database"

    resolved = counts["exact"] + counts["pincode_centroid"] + counts["city_centroid"]
    coverage_pct = (resolved / total) * 100.0

    print(f"\nFleet Geocoding Stats: {counts}")
    print(f"Coverage: {resolved}/{total} ({coverage_pct:.1f}%)")

    assert coverage_pct >= 90.0, f"Expected >= 90% geocoding coverage, got {coverage_pct:.1f}%"
