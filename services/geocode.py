"""
Solaron Geocoding Module (Phase 1, Task 3).

Resolves plant coordinates and geocoding fidelity levels:
- 'exact': Platform reported precise GPS telemetry (e.g. iSolarCloud / SuryaLog)
- 'pincode_centroid': 6-digit Indian Postal Code matched to offline centroid dataset
- 'city_centroid': City/district matched to regional centroid coordinates
- 'state_default': State-level capital/regional default coordinate
- 'unresolved': Missing location telemetry, fell back to central India default
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from pipeline import db
except ImportError:
    try:
        from Solarondashboard.pipeline import db  # type: ignore[import-untyped,import-not-found]
    except ImportError:
        import db  # type: ignore[import-untyped,import-not-found]

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
PINCODE_CSV = BASE_DIR / "data" / "india_pincodes.csv"

# Global in-memory lookup cache: pincode -> dict
_PINCODE_MAP: Dict[str, Dict[str, Any]] = {}

# City Centroid Coordinates (Lat, Lon, State)
CITY_COORDINATES: Dict[str, Tuple[float, float, str]] = {
    "nagpur": (21.1458, 79.0882, "Maharashtra"),
    "gondia": (21.4624, 80.1961, "Maharashtra"),
    "pune": (18.5204, 73.8567, "Maharashtra"),
    "mumbai": (19.0760, 72.8777, "Maharashtra"),
    "thane": (19.2183, 72.9781, "Maharashtra"),
    "navi mumbai": (19.0330, 73.0297, "Maharashtra"),
    "chandrapur": (19.9583, 79.2961, "Maharashtra"),
    "raipur": (21.2514, 81.6296, "Chhattisgarh"),
    "gandai": (21.6500, 81.0167, "Chhattisgarh"),
    "durg": (21.1904, 81.3509, "Chhattisgarh"),
    "bhilai": (21.2100, 81.3800, "Chhattisgarh"),
    "bilaspur": (22.0797, 82.1409, "Chhattisgarh"),
    "rajnandgaon": (21.0961, 81.0322, "Chhattisgarh"),
    "nashik": (19.9975, 73.7898, "Maharashtra"),
    "dhule": (20.9042, 74.7749, "Maharashtra"),
    "jalgaon": (21.0077, 75.5626, "Maharashtra"),
    "aurangabad": (19.8762, 75.3433, "Maharashtra"),
    "chhatrapati sambhajinagar": (19.8762, 75.3433, "Maharashtra"),
    "kolhapur": (16.7050, 74.2433, "Maharashtra"),
    "solapur": (17.6599, 75.9064, "Maharashtra"),
    "amravati": (20.9320, 77.7523, "Maharashtra"),
    "akola": (20.7002, 77.0082, "Maharashtra"),
    "wardha": (20.7453, 78.6022, "Maharashtra"),
    "bhandara": (21.1667, 79.6500, "Maharashtra"),
    "palghar": (19.7042, 72.7758, "Maharashtra"),
    "bengaluru": (12.9716, 77.5946, "Karnataka"),
    "bangalore": (12.9716, 77.5946, "Karnataka"),
    "delhi": (28.6139, 77.2090, "Delhi"),
    "silvassa": (20.2763, 73.0083, "Dadra and Nagar Haveli"),
    "valsad": (20.3893, 72.9106, "Gujarat"),
    "surat": (21.1702, 72.8311, "Gujarat"),
    "pimpri chinchwad": (18.6298, 73.7997, "Maharashtra"),
    "pimpri-chinchwad": (18.6298, 73.7997, "Maharashtra"),
    "juhu, mumbai": (19.1075, 72.8263, "Maharashtra"),
}

# State Default Centroid Coordinates
STATE_COORDINATES: Dict[str, Tuple[float, float]] = {
    "maharashtra": (19.7515, 75.7139),
    "chhattisgarh": (21.2787, 81.8661),
    "gujarat": (22.2587, 71.1924),
    "karnataka": (15.3173, 75.7139),
    "madhya pradesh": (22.9734, 78.6569),
    "delhi": (28.7041, 77.1025),
    "dnh": (20.2763, 73.0083),
    "dadra and nagar haveli": (20.2763, 73.0083),
}

FALLBACK_INDIA_COORDS = (21.1458, 79.0882)  # Nagpur / Geographic Center of India


def _load_pincodes() -> Dict[str, Dict[str, Any]]:
    global _PINCODE_MAP
    if _PINCODE_MAP:
        return _PINCODE_MAP

    if not PINCODE_CSV.exists():
        logger.warning(f"Pincode file not found at {PINCODE_CSV}")
        return {}

    mapping = {}
    try:
        with open(PINCODE_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pin = str(row.get("pincode", "")).strip()
                if pin and len(pin) == 6 and pin.isdigit():
                    mapping[pin] = {
                        "pincode": pin,
                        "latitude": float(row["latitude"]),
                        "longitude": float(row["longitude"]),
                        "district": row.get("district", ""),
                        "state": row.get("state", ""),
                    }
        _PINCODE_MAP = mapping
    except Exception as e:
        logger.error(f"Error reading {PINCODE_CSV}: {e}")

    return _PINCODE_MAP


def extract_pincode(text: Any) -> Optional[str]:
    """Extract a 6-digit Indian PIN code (100000 - 999999) from address or plant text."""
    if not text:
        return None
    matches = re.findall(r"\b[1-9][0-9]{5}\b", str(text))
    return matches[0] if matches else None


def lookup_pincode(pincode: Optional[str]) -> Optional[Dict[str, Any]]:
    """Look up coordinates and metadata for a 6-digit PIN code."""
    if not pincode:
        return None
    pins = _load_pincodes()
    return pins.get(str(pincode).strip())


def lookup_city(city_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Look up centroid coordinates for a city or district name."""
    if not city_name:
        return None
    cleaned = str(city_name).lower().strip()
    # Normalize common variations
    cleaned = re.sub(r"^(city of|district of)\s+", "", cleaned)
    if cleaned in CITY_COORDINATES:
        lat, lon, st = CITY_COORDINATES[cleaned]
        return {"latitude": lat, "longitude": lon, "state": st, "city": city_name.strip()}

    # Prefix match if city string contains known city
    for known_city, (lat, lon, st) in CITY_COORDINATES.items():
        if known_city in cleaned or cleaned in known_city:
            return {"latitude": lat, "longitude": lon, "state": st, "city": known_city.title()}

    return None


def lookup_state(state_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Look up regional centroid coordinates for an Indian state."""
    if not state_name:
        return None
    cleaned = str(state_name).lower().strip()
    if cleaned in STATE_COORDINATES:
        lat, lon = STATE_COORDINATES[cleaned]
        return {"latitude": lat, "longitude": lon, "state": state_name.strip()}
    return None


def geocode_plant(plant_record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Determine coordinates and geocoding fidelity level for a plant record.
    
    Resolution hierarchy:
    1. 'exact': Valid non-zero GPS coordinates already provided
    2. 'pincode_centroid': 6-digit PIN code resolved from address/name
    3. 'city_centroid': City/district resolved from city field or address
    4. 'state_default': State-level centroid match
    5. 'unresolved': Default central India coordinate
    """
    out = dict(plant_record)

    # 1. Check existing GPS coordinates
    raw_lat = out.get("latitude")
    raw_lon = out.get("longitude")
    try:
        if raw_lat is not None and raw_lon is not None:
            lat_f = float(raw_lat)
            lon_f = float(raw_lon)
            if abs(lat_f) > 0.5 and abs(lon_f) > 0.5:
                out["latitude"] = round(lat_f, 4)
                out["longitude"] = round(lon_f, 4)
                out["geocode_level"] = "exact"
                return out
    except (ValueError, TypeError):
        pass

    # 2. Try Pincode extraction from address or plant name
    addr = str(out.get("plantAddress") or out.get("address") or out.get("plant_name") or "")
    pin = extract_pincode(addr)
    if pin:
        pin_info = lookup_pincode(pin)
        if pin_info:
            out["latitude"] = pin_info["latitude"]
            out["longitude"] = pin_info["longitude"]
            if not out.get("city") or str(out["city"]).strip().lower() in ("", "nan", "none"):
                out["city"] = pin_info["district"]
            out["geocode_level"] = "pincode_centroid"
            return out

    # 3. Try City lookup
    city_candidate = str(out.get("city") or "")
    city_info = lookup_city(city_candidate)
    if not city_info and addr:
        # Check if address text contains any known cities
        for c in CITY_COORDINATES:
            if re.search(r"\b" + re.escape(c) + r"\b", addr.lower()):
                city_info = lookup_city(c)
                break

    if city_info:
        out["latitude"] = city_info["latitude"]
        out["longitude"] = city_info["longitude"]
        if not out.get("city") or str(out["city"]).strip().lower() in ("", "nan", "none"):
            out["city"] = city_info["city"]
        out["geocode_level"] = "city_centroid"
        return out

    # 4. Try State lookup
    state_candidate = str(out.get("state") or "")
    state_info = lookup_state(state_candidate)
    if state_info:
        out["latitude"] = state_info["latitude"]
        out["longitude"] = state_info["longitude"]
        out["geocode_level"] = "state_default"
        return out

    # 5. Fallback to unresolved
    out["latitude"] = FALLBACK_INDIA_COORDS[0]
    out["longitude"] = FALLBACK_INDIA_COORDS[1]
    out["geocode_level"] = "unresolved"
    return out


def geocode_all_plants_in_db(db_name: str = "analytics") -> Dict[str, int]:
    """
    Backfill geocode levels and centroid coordinates across all plants in database.
    Leverages raw Growatt live addresses if available.
    """
    _load_pincodes()

    # Load raw growatt live plant addresses
    gw_live_path = BASE_DIR / "data" / "raw" / "growatt" / "plant_list_live.json"
    gw_addresses: Dict[str, str] = {}
    gw_cities: Dict[str, str] = {}
    if gw_live_path.exists():
        try:
            with open(gw_live_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for p in data:
                    pid = f"growatt_{p.get('id')}"
                    addr = str(p.get("plantAddress", "")).strip()
                    city = str(p.get("city", "")).strip()
                    if addr:
                        gw_addresses[pid] = addr
                    if city:
                        gw_cities[pid] = city
        except Exception:
            pass

    plants = db.get_plants(include_decommissioned=True)
    counts = {
        "exact": 0,
        "pincode_centroid": 0,
        "city_centroid": 0,
        "state_default": 0,
        "unresolved": 0,
    }

    updates = []
    for p in plants:
        pid = str(p["plant_id"])
        p_copy = dict(p)
        if pid in gw_addresses:
            p_copy["plantAddress"] = gw_addresses[pid]
        if pid in gw_cities and (not p_copy.get("city") or str(p_copy["city"]) in ("nan", "None", "")):
            p_copy["city"] = gw_cities[pid]

        geocoded = geocode_plant(p_copy)
        lvl = geocoded["geocode_level"]
        counts[lvl] = counts.get(lvl, 0) + 1

        updates.append({
            "plant_id": pid,
            "latitude": geocoded["latitude"],
            "longitude": geocoded["longitude"],
            "city": geocoded.get("city"),
            "geocode_level": lvl,
        })

    with db.get_conn(db_name) as conn:
        cur = conn.cursor()
        cur.executemany("""
            UPDATE plants
            SET latitude = :latitude,
                longitude = :longitude,
                city = coalesce(:city, plants.city),
                geocode_level = :geocode_level
            WHERE plant_id = :plant_id
        """, updates)

    return counts
