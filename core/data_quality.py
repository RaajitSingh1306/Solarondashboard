"""
Solaron Data Quality & Physics Validation Module.

Enforces physical boundaries, solar physics rules, noise reduction,
specific yield recomputation, yield-per-day calculation, and
decommissioned plant detection across the entire Solaron fleet.
"""

import calendar
import datetime
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Solar Physics Constants for India (lat 8°N to 37°N)
# Max daily peak sun hours in India rarely exceeds 7.5 kWh/m2/day.
# With ~80% PR, max daily yield = 7.5 * 0.8 ≈ 6.0 - 7.5 kWh/kWp/day.
MAX_DAILY_YIELD_KWH_KWP = 8.0
MIN_DAILY_YIELD_KWH_KWP = 0.0

# Max monthly yield in peak months: 31 days * 6.5 ≈ 200 kWh/kWp/month.
# Absolute physical upper bound: 220 kWh/kWp/month.
MAX_MONTHLY_YIELD_KWH_KWP = 220.0
MIN_MONTHLY_YIELD_KWH_KWP = 0.0

# Noise floor: any generation <= 0.05 kWh/day or <= 0.5 kWh/month is considered zero/noise
NOISE_FLOOR_DAILY_KWH = 0.05
NOISE_FLOOR_MONTHLY_KWH = 1.0

# Bootstrap seed set used strictly for initial database provisioning when plants table is empty.
# In production, operational status is dynamically fetched from servers & stored in SQLite.
BOOTSTRAP_DECOMMISSIONED_PLANT_IDS = {
    'growatt_10016308', 'growatt_10067274', 'growatt_100699', 'growatt_10074506', 'growatt_10085629',
    'growatt_10133666', 'growatt_10137127', 'growatt_10169390', 'growatt_10179736', 'growatt_10200210',
    'growatt_10241129', 'growatt_102732', 'growatt_10273523', 'growatt_10371862', 'growatt_10377849',
    'growatt_10377858', 'growatt_10409807', 'growatt_10409838', 'growatt_10467594', 'growatt_10489129',
    'growatt_104913', 'growatt_104920', 'growatt_10513532', 'growatt_10518199', 'growatt_10537447',
    'growatt_10547502', 'growatt_10569506', 'growatt_105833', 'growatt_10585419', 'growatt_10592496',
    'growatt_10597273', 'growatt_105994', 'growatt_10617829', 'growatt_10657084', 'growatt_10664929',
    'growatt_10664961', 'growatt_10674290', 'growatt_10674488', 'growatt_10721028', 'growatt_10739359',
    'growatt_10773259', 'growatt_10792266', 'growatt_10794257', 'growatt_10805431', 'growatt_10833636',
    'growatt_10856830', 'growatt_10878830', 'growatt_10892345', 'growatt_10898585', 'growatt_10898708',
    'growatt_10905660', 'growatt_10905724', 'growatt_10917250', 'growatt_10929459', 'growatt_10937803',
    'growatt_10939541', 'growatt_10940614', 'growatt_10944752', 'growatt_10946846', 'growatt_10946850',
    'growatt_10950151', 'growatt_10955172', 'growatt_11022463', 'growatt_11038083', 'growatt_11040520',
    'growatt_11061765', 'growatt_11063863', 'growatt_11073618', 'growatt_11097958', 'growatt_11115804',
    'growatt_11115963', 'growatt_11120267', 'growatt_11120425', 'growatt_11136038', 'growatt_11151904',
    'growatt_11176283', 'growatt_11176497', 'growatt_11187649', 'growatt_11189560', 'growatt_11199467', 'growatt_112461',
    'growatt_116506', 'growatt_118819', 'growatt_125955', 'growatt_125974', 'growatt_148593',
    'growatt_152294', 'growatt_152554', 'growatt_1551079', 'growatt_1574691', 'growatt_159167',
    'growatt_159282', 'growatt_163413', 'growatt_164727', 'growatt_166151', 'growatt_1692484',
    'growatt_173054', 'growatt_175589', 'growatt_1808976', 'growatt_1835707', 'growatt_1852934',
    'growatt_1870138', 'growatt_1990859', 'growatt_2018663', 'growatt_213085', 'growatt_214430',
    'growatt_215699', 'growatt_2164749', 'growatt_2179005', 'growatt_2210768', 'growatt_222498',
    'growatt_2227745', 'growatt_2240330', 'growatt_2264705', 'growatt_226965', 'growatt_2293081',
    'growatt_2308879', 'growatt_2330408', 'growatt_2352137', 'growatt_2422345', 'growatt_2428454',
    'growatt_2485302', 'growatt_2492014', 'growatt_2510341', 'growatt_259691', 'growatt_2617351',
    'growatt_2622552', 'growatt_263311', 'growatt_264273', 'growatt_264753', 'growatt_2668359',
    'growatt_272452', 'growatt_2727484', 'growatt_2749591', 'growatt_2749655', 'growatt_2755685',
    'growatt_2841378', 'growatt_302419', 'growatt_313088', 'growatt_329097', 'growatt_338755',
    'growatt_360956', 'growatt_381822', 'growatt_408402', 'growatt_539509', 'growatt_59824',
    'growatt_601868', 'growatt_60476', 'growatt_62656', 'growatt_632638', 'growatt_64575',
    'growatt_66019', 'growatt_67433', 'growatt_69964', 'growatt_70271', 'growatt_70975',
    'growatt_70987', 'growatt_71082', 'growatt_723353', 'growatt_73224', 'growatt_741623',
    'growatt_757614', 'growatt_757622', 'growatt_77769', 'growatt_84382', 'growatt_851184',
    'growatt_855921', 'growatt_863493', 'growatt_89638', 'growatt_9193975', 'growatt_9207345',
    'growatt_9209507', 'growatt_9209516', 'growatt_9224724', 'growatt_9235471', 'growatt_9270889',
    'growatt_9327048', 'growatt_942273', 'growatt_9902885', 'growatt_9965160', 'growatt_9965193',
    'isolarcloud_SG-002', 'isolarcloud_SG-005', 'isolarcloud_SG-009', 'isolarcloud_SG-011',
    'isolarcloud_SG-014', 'isolarcloud_SG-017', 'isolarcloud_SG-021', 'isolarcloud_SG-022',
    'isolarcloud_SG-023', 'isolarcloud_SG-024', 'isolarcloud_SG-025', 'suryalog_SL-001',
    'suryalog_SL-004', 'suryalog_SL-005', 'suryalog_SL-009'
}

# Backward compatibility alias
DECOMMISSIONED_PLANT_IDS = BOOTSTRAP_DECOMMISSIONED_PLANT_IDS
DECOMMISSIONED_PLANT_IDS_LOWER = {p.lower() for p in BOOTSTRAP_DECOMMISSIONED_PLANT_IDS}

# Dynamic in-memory cache for operational status retrieved from servers / SQLite
_DECOMMISSIONED_CACHE: Optional[set] = None
_DECOMMISSIONED_CACHE_TS: float = 0.0
_CACHE_TTL_SEC: float = 60.0


def invalidate_decommissioned_cache() -> None:
    """Clear in-memory decommissioned plant cache to force fresh DB/server resolution."""
    global _DECOMMISSIONED_CACHE, _DECOMMISSIONED_CACHE_TS
    _DECOMMISSIONED_CACHE = None
    _DECOMMISSIONED_CACHE_TS = 0.0


def get_decommissioned_plant_ids(force_reload: bool = False) -> set:
    """
    Dynamically retrieve decommissioned plant IDs from the SQLite database
    (operational_status = 'decommissioned').
    Falls back to bootstrap seed set if the database is uninitialized.
    """
    global _DECOMMISSIONED_CACHE, _DECOMMISSIONED_CACHE_TS
    import time
    now = time.time()
    if _DECOMMISSIONED_CACHE is not None and not force_reload and (now - _DECOMMISSIONED_CACHE_TS < _CACHE_TTL_SEC):
        return _DECOMMISSIONED_CACHE

    try:
        try:
            from pipeline import db
        except ImportError:
            import db
        with db.analytics_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT lower(plant_id) FROM plants WHERE operational_status = 'decommissioned'")
            rows = cur.fetchall()
            if rows:
                _DECOMMISSIONED_CACHE = {r[0] for r in rows}
                _DECOMMISSIONED_CACHE_TS = now
                return _DECOMMISSIONED_CACHE
    except Exception as e:
        logger.debug(f"Could not load decommissioned plants dynamically from DB: {e}")

    # Fallback to bootstrap seed set during initial database provisioning
    _DECOMMISSIONED_CACHE = set(DECOMMISSIONED_PLANT_IDS_LOWER)
    _DECOMMISSIONED_CACHE_TS = now
    return _DECOMMISSIONED_CACHE


def is_decommissioned(plant_id: str) -> bool:
    """
    Dynamically check if a plant is decommissioned by querying the live
    operational_status recorded in the database, with in-memory caching.
    """
    if not plant_id:
        return False
    pid_clean = str(plant_id).lower().strip()
    return pid_clean in get_decommissioned_plant_ids()


def determine_operational_status(plant_record: Dict[str, Any]) -> str:
    """
    Determine a plant's operational status dynamically from live server attributes.
    Returns 'decommissioned' if:
      - Explicitly flagged as decommissioned by server
      - Reported as 'Commissioning unfinished' or 'Offline' with 0 lifetime energy
      - Reported with 0 connected devices and 0 lifetime energy
      - Pre-existing database record has operational_status = 'decommissioned'
    Otherwise returns 'active'.
    """
    if not plant_record:
        return "active"

    # 1. Explicit status passed in record
    op = str(plant_record.get("operational_status", "")).lower().strip()
    if op in ("decommissioned", "retired", "inactive"):
        return "decommissioned"

    source = str(plant_record.get("source", "")).lower().strip()
    status_raw = str(plant_record.get("status", "")).lower().strip()
    tot_energy = plant_record.get("total_energy_kwh")
    try:
        tot_kwh = float(tot_energy) if tot_energy is not None else None
    except (ValueError, TypeError):
        tot_kwh = None

    # 2. Portal-specific live server heuristics
    if "isolarcloud" in source:
        if status_raw in ("commissioning unfinished", "offline") and (tot_kwh is None or tot_kwh <= 0.0):
            return "decommissioned"

    if "suryalog" in source:
        if status_raw == "offline" and (tot_kwh is None or tot_kwh <= 0.0):
            return "decommissioned"

    if "growatt" in source:
        dev_count = plant_record.get("deviceCount")
        try:
            dev_cnt = int(dev_count) if dev_count is not None else None
        except (ValueError, TypeError):
            dev_cnt = None
        if dev_cnt == 0 and (tot_kwh is None or tot_kwh <= 0.0):
            return "decommissioned"

    # 3. Dynamic lookup from database
    pid = str(plant_record.get("plant_id", ""))
    if is_decommissioned(pid):
        return "decommissioned"

    return "active"


def clean_plant_name(name: Any) -> str:
    """Normalize and trim plant names, collapsing multiple whitespace characters."""
    if not name:
        return ""
    cleaned = re.sub(r"\s+", " ", str(name)).strip()
    return cleaned


def normalize_capacity(
    cap: Any,
    default: Optional[float] = None,
    plant_type: Optional[str] = None,
    plant_name: Optional[str] = None,
) -> Optional[float]:
    """
    Validate and normalize plant capacity in kWp.
    Solar plants in this fleet range from ~1 kWp to ~500 kWp (with utility up to 2,000 kWp).
    
    Disambiguation rules:
    - Values > 5,000 are unambiguously in Watts (e.g. 300,000 W -> 300 kWp, 6,000 W -> 6 kWp).
    - Values between 1,000 and 5,000:
      - Residential systems in India are commonly entered in Watts (e.g. 1000, 2000, 3000, 3300, 4000, 5000 W).
      - If marked as Commercial/Industrial/Utility or plant name contains commercial keywords,
        and is an exact commercial kWp rating, keep as kWp.
      - Otherwise divide by 1000.0 to convert Watts -> kWp.
    - Values <= 500 are in kWp (e.g. 3.3, 5.0, 100.0, 194.4 kWp).
    - Bounds check: 0.1 kWp to 10,000 kWp.
    """
    if cap is None:
        return default
    try:
        val = float(cap)
        if val <= 0:
            return default

        # If value > 5,000: unambiguously Watts -> convert to kWp
        if val > 5000:
            val = val / 1000.0
        elif val >= 1000:
            # Check for commercial / industrial indicators
            is_comm = False
            if plant_type and any(k in str(plant_type).lower() for k in ("commercial", "industrial", "utility", "mw")):
                is_comm = True
            if plant_name and any(k in str(plant_name).lower() for k in (
                "pvt", "ltd", "industries", "factory", "hospital", "pharma", "mill", "mall", "works", "infra", "park"
            )):
                is_comm = True

            # If not clearly commercial rooftop, treat as Watts (e.g. 3000 W -> 3 kWp)
            if not is_comm:
                val = val / 1000.0

        # Bounds check: 0.1 kWp to 10,000 kWp
        if 0.1 <= val <= 10000.0:
            return round(val, 2)
        return default
    except (ValueError, TypeError):
        return default


def get_days_in_month(month_str: str) -> int:
    """Return number of days in YYYY-MM string."""
    try:
        parts = month_str.strip().split("-")
        year = int(parts[0])
        month = int(parts[1])
        return calendar.monthrange(year, month)[1]
    except Exception:
        return 30


def get_elapsed_days_in_month(month_str: str) -> int:
    """
    Return elapsed days for the given month.
    For the current ongoing month, returns the current day of the month (e.g. 25 on Sep 25).
    For past months, returns total days in that month (e.g. 31 for August).
    For future months, returns total days in that month.
    """
    total_days = get_days_in_month(month_str)
    try:
        today = datetime.date.today()
        current_ym = today.strftime("%Y-%m")
        clean_m = (month_str or "").strip()
        if clean_m == current_ym:
            return max(1, min(today.day, total_days))
        return max(1, total_days)
    except Exception:
        return total_days


def recompute_specific_yield(
    kwh: Optional[float], capacity_kwp: Optional[float], is_daily: bool = False, month_str: Optional[str] = None
) -> Optional[float]:
    """
    Recompute specific yield directly from actual energy and capacity.
    Eliminates discrepancies where platforms report generic or erroneous specific yields.
    """
    if kwh is None or capacity_kwp is None or capacity_kwp <= 0:
        return None

    # Clamp negative energy
    kwh_clean = max(0.0, float(kwh))
    if is_daily and kwh_clean < NOISE_FLOOR_DAILY_KWH:
        return 0.0
    if not is_daily and kwh_clean < NOISE_FLOOR_MONTHLY_KWH:
        return 0.0

    raw_sy = kwh_clean / float(capacity_kwp)
    if is_daily:
        raw_sy = min(raw_sy, MAX_DAILY_YIELD_KWH_KWP)
    else:
        raw_sy = min(raw_sy, MAX_MONTHLY_YIELD_KWH_KWP)
    return round(raw_sy, 2)


def compute_yield_per_day(
    kwh: Optional[float], capacity_kwp: Optional[float], days: int = 1
) -> Optional[float]:
    """
    Compute normalized generation yield per day: units / kWp / day.
    Explicitly requested metric for standardized plant comparison.
    Clamped to physical upper bound of 8.0 units/kWp/day.
    """
    if kwh is None or capacity_kwp is None or capacity_kwp <= 0 or days <= 0:
        return None

    kwh_clean = max(0.0, float(kwh))
    ypd = kwh_clean / (float(capacity_kwp) * float(days))
    ypd = min(ypd, MAX_DAILY_YIELD_KWH_KWP)
    return round(ypd, 2)


def get_capacity_bracket(capacity_kwp: Optional[float]) -> str:
    """
    Group plants into capacity brackets for fair peer-group comparisons:
    - 0-3 kWp: Small Residential
    - 3-5 kWp: Standard Residential
    - 5-10 kWp: Large Residential
    - 10-50 kWp: Commercial Rooftop
    - 50+ kWp: Industrial / Utility
    """
    if capacity_kwp is None or capacity_kwp <= 0:
        return "Unknown"
    if capacity_kwp <= 3.2:
        return "0-3 kWp"
    if capacity_kwp <= 5.2:
        return "3-5 kWp"
    if capacity_kwp <= 10.5:
        return "5-10 kWp"
    if capacity_kwp <= 50.0:
        return "10-50 kWp"
    return "50+ kWp"


def is_stuck_value(quality_flags: Optional[str]) -> bool:
    """Return True if quality_flags string contains STUCK_VALUE."""
    if not quality_flags:
        return False
    return "STUCK_VALUE" in [f.strip() for f in str(quality_flags).split(",")]


def detect_stuck_values(
    daily_records: List[Dict[str, Any]],
    consecutive_threshold: int = 3,
    tolerance: float = 0.05,
    peer_variance_check: bool = False,
    peer_daily_yields: Optional[Dict[str, float]] = None,
) -> List[Dict[str, Any]]:
    """
    Detect repeated identical non-zero kWh generation readings across consecutive days.
    
    A solar plant producing the exact same non-zero generation (within tolerance) for N
    consecutive days indicates stuck sensors, frozen loggers, or cached synthetic values.
    Real solar generation varies continuously with solar geometry and cloud cover.
    Zero-generation days (offline/decommissioned) are NOT flagged as stuck values.
    
    Args:
        daily_records: List of daily dicts containing at least 'date' and 'kwh'.
                       Can contain records for one or multiple plants (if 'plant_id' present).
        consecutive_threshold: Minimum consecutive days with identical non-zero value (default: 3).
        tolerance: kWh difference threshold to consider values identical (default: 0.05 kWh).
        peer_variance_check: If True and peer_daily_yields provided, verify peers varied >10%.
        peer_daily_yields: Dict mapping date -> median peer yield for cross-checking weather variance.
        
    Returns:
        The list of daily_records with 'quality_flags' updated to include 'STUCK_VALUE'
        where detected.
    """
    if not daily_records:
        return daily_records

    # Group by plant_id
    by_plant: Dict[str, List[Dict[str, Any]]] = {}
    for r in daily_records:
        pid = str(r.get("plant_id", "default"))
        by_plant.setdefault(pid, []).append(r)

    for pid, plant_recs in by_plant.items():
        # Sort chronologically by date
        plant_recs.sort(key=lambda x: str(x.get("date", "")))
        n = len(plant_recs)
        if n < consecutive_threshold:
            continue

        run_start = 0
        while run_start < n:
            kwh_start = plant_recs[run_start].get("kwh")
            if kwh_start is None or float(kwh_start) <= NOISE_FLOOR_DAILY_KWH:
                run_start += 1
                continue

            run_end = run_start + 1
            while run_end < n:
                kwh_next = plant_recs[run_end].get("kwh")
                if kwh_next is None or float(kwh_next) <= NOISE_FLOOR_DAILY_KWH:
                    break
                if abs(float(kwh_next) - float(kwh_start)) > tolerance:
                    break
                run_end += 1

            run_length = run_end - run_start
            if run_length >= consecutive_threshold:
                flag_it = True
                if peer_variance_check and peer_daily_yields:
                    run_dates = [str(plant_recs[idx].get("date", "")) for idx in range(run_start, run_end)]
                    peer_vals = [peer_daily_yields.get(d) for d in run_dates if peer_daily_yields.get(d) is not None]
                    if len(peer_vals) >= 2 and max(peer_vals) > 0:
                        variation = (max(peer_vals) - min(peer_vals)) / max(peer_vals)
                        if variation < 0.10:
                            flag_it = False

                if flag_it:
                    for idx in range(run_start, run_end):
                        rec = plant_recs[idx]
                        flags = rec.get("quality_flags") or ""
                        flag_list = [f.strip() for f in str(flags).split(",") if f.strip()]
                        if "STUCK_VALUE" not in flag_list:
                            flag_list.append("STUCK_VALUE")
                        rec["quality_flags"] = ",".join(flag_list)

            run_start = run_end

    return daily_records


def scan_and_flag_stuck_values(
    consecutive_threshold: int = 3,
    tolerance: float = 0.05,
    db_name: str = "analytics",
) -> int:
    """
    Scan all daily generation records in SQLite database, detect stuck values,
    and update quality_flags in place.
    Returns the count of flagged plant-days.
    """
    try:
        from pipeline import db
    except ImportError:
        import db
    with db.get_conn(db_name) as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT plant_id, date, kwh, quality_flags
            FROM daily_generation
            WHERE kwh > {NOISE_FLOOR_DAILY_KWH}
            ORDER BY plant_id, date ASC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            return 0

        flagged_recs = detect_stuck_values(
            rows, consecutive_threshold=consecutive_threshold, tolerance=tolerance
        )

        updates = []
        for r in flagged_recs:
            if is_stuck_value(r.get("quality_flags")):
                updates.append((r["quality_flags"], r["plant_id"], r["date"]))

        if updates:
            cur.executemany("""
                UPDATE daily_generation
                SET quality_flags = ?
                WHERE plant_id = ? AND date = ?
            """, updates)
            return len(updates)
        return 0


def validate_daily_record(
    record: Dict[str, Any], capacity_kwp: Optional[float] = None
) -> Optional[Dict[str, Any]]:
    """
    Validate and sanitize daily record: reject negative values, remove noise floor,
    reject future dates beyond today, and compute specific yield and yield_per_day.
    """
    out = dict(record)
    d_date = str(out.get("date", "")).strip()
    today_str = datetime.date.today().isoformat()
    if d_date and d_date > today_str:
        return None
    kwh = out.get("kwh")
    if kwh is not None:
        try:
            kwh_val = float(kwh)
            if kwh_val < NOISE_FLOOR_DAILY_KWH:
                kwh_val = 0.0
            out["kwh"] = round(kwh_val, 2)
        except (ValueError, TypeError):
            out["kwh"] = 0.0
    else:
        out["kwh"] = 0.0

    cap = normalize_capacity(capacity_kwp or out.get("capacity_kwp"))
    if cap and cap > 0 and out["kwh"] is not None:
        sy = recompute_specific_yield(out["kwh"], cap, is_daily=True)
        out["specific_yield"] = sy
        out["yield_per_day"] = sy
    else:
        out["specific_yield"] = out.get("specific_yield") or 0.0
        out["yield_per_day"] = out.get("specific_yield") or 0.0

    # Sanitize revenue: no negative revenue
    rev = out.get("revenue_inr")
    if rev is not None:
        try:
            out["revenue_inr"] = max(0.0, round(float(rev), 2))
        except (ValueError, TypeError):
            out["revenue_inr"] = 0.0

    # Preserve quality flags
    out["quality_flags"] = out.get("quality_flags")

    # Normalize status based on generation
    if out["kwh"] is not None and out["kwh"] > NOISE_FLOOR_DAILY_KWH:
        out["status"] = "active"
    elif out.get("status") != "fault":
        out["status"] = "offline"

    return out


def validate_monthly_record(
    record: Dict[str, Any], capacity_kwp: Optional[float] = None
) -> Dict[str, Any]:
    """
    Validate and sanitize monthly record: reject negative values, remove noise floor,
    and compute specific yield and yield_per_day directly from actual telemetry.
    """
    out = dict(record)
    month_str = str(out.get("month", ""))
    elapsed_days = get_elapsed_days_in_month(month_str)

    kwh = out.get("kwh")
    if kwh is not None:
        try:
            kwh_val = float(kwh)
            if kwh_val < NOISE_FLOOR_MONTHLY_KWH:
                kwh_val = 0.0
            out["kwh"] = round(kwh_val, 2)
        except (ValueError, TypeError):
            out["kwh"] = 0.0
    else:
        out["kwh"] = 0.0

    cap = normalize_capacity(capacity_kwp or out.get("capacity_kwp"))
    if cap and cap > 0 and out["kwh"] is not None:
        sy = recompute_specific_yield(out["kwh"], cap, is_daily=False, month_str=month_str)
        out["specific_yield"] = sy
        out["yield_per_day"] = compute_yield_per_day(out["kwh"], cap, days=elapsed_days)
    else:
        out["specific_yield"] = out.get("specific_yield") or 0.0
        out["yield_per_day"] = 0.0

    rev = out.get("revenue_inr")
    if rev is not None:
        try:
            out["revenue_inr"] = max(0.0, round(float(rev), 2))
        except (ValueError, TypeError):
            out["revenue_inr"] = 0.0

    return out


def is_plant_decommissioned(
    total_lifetime_kwh: float,
    months_with_zero: int,
    months_tracked: int,
    install_date_str: Optional[str] = None,
) -> bool:
    """
    Determine if a plant is permanently decommissioned or shut down.
    A plant is decommissioned if:
    1. It has 0 generation across all tracked months (>= 2 months tracked), OR
    2. Its lifetime recorded energy is <= 1.0 kWh despite being installed over 1 year ago.
    """
    if months_tracked >= 2 and months_with_zero == months_tracked:
        return True

    if install_date_str:
        try:
            inst_date = datetime.date.fromisoformat(install_date_str[:10])
            today = datetime.date.today()
            days_old = (today - inst_date).days
            if days_old > 365 and total_lifetime_kwh <= NOISE_FLOOR_MONTHLY_KWH:
                return True
        except Exception:
            pass

    return False
