"""
Solaron Peer Group Engine (Phase 3, Task 10).

Groups solar installations into statistically valid regional cohorts for peer-relative
performance benchmarking (RPI):
- Level 1: Same city / municipality (requires >= 5 healthy peers)
- Level 2: Same 2-digit / 3-digit postal circle / district (requires >= 5 peers)
- Level 3: Same state (e.g. Maharashtra, Chhattisgarh)
- Level 4: Fleet-wide fallback

Filters out decommissioned, offline, and STUCK_VALUE plant-days to preserve a clean reference.
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import pandas as pd
try:
    from pipeline import db
    from core import data_quality
except ImportError:
    import db
    import data_quality

logger = logging.getLogger(__name__)

MIN_HEALTHY_PEERS = 5
_PEER_GROUP_CACHE: Optional[Dict[str, Dict[str, Any]]] = None


def get_plant_peer_hierarchy(p: Dict[str, Any]) -> Tuple[str, str, str]:
    """Extract (city, pincode_prefix, state) hierarchy keys from plant metadata."""
    city = str(p.get("city") or "").lower().strip()
    if city in ("nan", "none"):
        city = ""

    # Extract 2-digit or 3-digit pincode circle from city or address
    lat = float(p.get("latitude") or 0.0)
    lon = float(p.get("longitude") or 0.0)

    state = str(p.get("state") or "").lower().strip()
    if not state or state in ("nan", "none"):
        # Infer state from city or coordinates
        if any(c in city for c in ("raipur", "durg", "bhilai", "gandai", "bilaspur", "rajnandgaon")):
            state = "chhattisgarh"
        elif any(c in city for c in ("bengaluru", "bangalore")):
            state = "karnataka"
        elif any(c in city for c in ("delhi",)):
            state = "delhi"
        else:
            state = "maharashtra"

    return city, city[:4] if city else "", state


def build_fleet_peer_groups(plants: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Cluster all active plants in the fleet into hierarchical peer groups.
    Returns mapping: plant_id -> peer_group_metadata.
    """
    global _PEER_GROUP_CACHE
    if plants is None:
        plants = db.get_plants(include_decommissioned=False)

    active_plants = [p for p in plants if str(p.get("operational_status", "")).lower() != "decommissioned"]

    # Index by city and state
    by_city: Dict[str, List[str]] = {}
    by_state: Dict[str, List[str]] = {}
    all_pids = [str(p["plant_id"]) for p in active_plants]

    meta_map = {}
    for p in active_plants:
        pid = str(p["plant_id"])
        city, _, state = get_plant_peer_hierarchy(p)
        meta_map[pid] = (city, state)
        if city:
            by_city.setdefault(city, []).append(pid)
        if state:
            by_state.setdefault(state, []).append(pid)

    assignments = {}
    for pid in all_pids:
        city, state = meta_map[pid]

        # 1. Level 1: City
        if city and len(by_city.get(city, [])) >= MIN_HEALTHY_PEERS:
            peers = [x for x in by_city[city] if x != pid]
            assignments[pid] = {
                "group_id": f"city_{city}",
                "level": "city",
                "label": f"City: {city.title()}",
                "peer_count": len(peers),
                "peers": peers,
            }
        # 2. Level 2: State
        elif state and len(by_state.get(state, [])) >= MIN_HEALTHY_PEERS:
            peers = [x for x in by_state[state] if x != pid]
            assignments[pid] = {
                "group_id": f"state_{state}",
                "level": "state",
                "label": f"State: {state.title()}",
                "peer_count": len(peers),
                "peers": peers,
            }
        # 3. Level 3: Fleet fallback
        else:
            peers = [x for x in all_pids if x != pid]
            assignments[pid] = {
                "group_id": "fleet_national",
                "level": "fleet",
                "label": "National Fleet Baseline",
                "peer_count": len(peers),
                "peers": peers,
            }

    _PEER_GROUP_CACHE = assignments
    return assignments


def get_plant_peer_group(plant_id: str) -> Dict[str, Any]:
    """Retrieve peer group assignment for a specific plant."""
    global _PEER_GROUP_CACHE
    if not _PEER_GROUP_CACHE or plant_id not in _PEER_GROUP_CACHE:
        build_fleet_peer_groups()
    return _PEER_GROUP_CACHE.get(str(plant_id), {
        "group_id": "fleet_national",
        "level": "fleet",
        "label": "National Fleet Baseline",
        "peer_count": 0,
        "peers": [],
    })


def get_healthy_peer_yields_for_date(peer_plant_ids: List[str], date_str: str) -> List[float]:
    """
    Fetch specific yield values of active, generating, non-stuck peers for a specific date.
    Strictly excludes STUCK_VALUE and noise floor (< 0.05) days.
    """
    if not peer_plant_ids:
        return []

    placeholders = ",".join(["?"] * len(peer_plant_ids))
    sql = f"""
    SELECT specific_yield
    FROM daily_generation
    WHERE plant_id IN ({placeholders})
      AND date = ?
      AND kwh > 0.05
      AND (quality_flags IS NULL OR quality_flags NOT LIKE '%STUCK_VALUE%');
    """
    params = list(peer_plant_ids) + [date_str]
    df = db.query_df(sql, params, db="analytics")
    if df.empty:
        return []

    return [float(y) for y in df["specific_yield"].dropna() if float(y) > 0.0]
