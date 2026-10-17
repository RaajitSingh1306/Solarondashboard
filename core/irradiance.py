"""
NASA POWER Daily GHI & Ambient Temperature Integration with SQLite Caching.
Provides 0.5-degree grid resolution irradiance and temperature for expected energy calculations.
"""

import datetime
import logging
from typing import Any, Dict, Optional, Tuple
import requests

try:
    from pipeline import db
except ImportError:
    import db

logger = logging.getLogger(__name__)

# In-memory fast cache: (round_lat, round_lon, date_str) -> {"ghi_kwh_m2": float, "temp_c": float}
_DAILY_IRR_CACHE: Dict[Tuple[float, float, str], Dict[str, float]] = {}

INDIA_SEASONAL_GHI_DEFAULTS = {
    1: 4.6, 2: 5.2, 3: 5.9, 4: 6.3, 5: 6.5, 6: 4.8,
    7: 3.8, 8: 3.7, 9: 4.5, 10: 5.0, 11: 4.8, 12: 4.4,
}

INDIA_SEASONAL_TEMP_DEFAULTS = {
    1: 22.0, 2: 25.0, 3: 29.0, 4: 33.0, 5: 35.0, 6: 31.0,
    7: 28.0, 8: 27.5, 9: 28.0, 10: 27.0, 11: 24.5, 12: 22.5,
}


def round_cell(coord: float) -> float:
    """Round latitude or longitude to nearest 0.5 degree grid cell."""
    return round(float(coord) * 2.0) / 2.0


def get_daily_irradiance_and_temp(
    latitude: Optional[float],
    longitude: Optional[float],
    date_str: str,
) -> Dict[str, float]:
    """
    Returns daily GHI (kWh/m2/day) and ambient temperature (°C) for a location and date.
    Checks memory cache -> SQLite cache -> NASA POWER daily API -> Seasonal fallback.
    """
    try:
        dt = datetime.date.fromisoformat(date_str[:10])
    except Exception:
        dt = datetime.date.today()
    m_int = dt.month

    default_ghi = INDIA_SEASONAL_GHI_DEFAULTS.get(m_int, 4.8)
    default_temp = INDIA_SEASONAL_TEMP_DEFAULTS.get(m_int, 28.0)

    if latitude is None or longitude is None or abs(float(latitude)) < 0.1:
        return {"ghi_kwh_m2": default_ghi, "temp_c": default_temp, "source": "default_geo"}

    cell_lat = round_cell(latitude)
    cell_lon = round_cell(longitude)
    d_clean = date_str[:10]

    cache_key = (cell_lat, cell_lon, d_clean)
    if cache_key in _DAILY_IRR_CACHE:
        return dict(_DAILY_IRR_CACHE[cache_key])

    # 1. Check SQLite cache
    cached_db = db.get_cached_nasa_power_daily(cell_lat, cell_lon, d_clean)
    if cached_db and cached_db.get("ghi_kwh_m2") is not None:
        ghi_val = float(cached_db["ghi_kwh_m2"])
        temp_val = float(cached_db.get("temp_c") or default_temp)
        res = {"ghi_kwh_m2": ghi_val, "temp_c": temp_val, "source": "sqlite_cache"}
        _DAILY_IRR_CACHE[cache_key] = res
        return res

    # 2. Fetch from NASA POWER daily point API
    try:
        date_param = d_clean.replace("-", "")
        url = "https://power.larc.nasa.gov/api/temporal/daily/point"
        params = {
            "parameters": "ALLSKY_SFC_SW_DWN,T2M",
            "community": "RE",
            "longitude": cell_lon,
            "latitude": cell_lat,
            "start": date_param,
            "end": date_param,
            "format": "JSON",
        }
        resp = requests.get(url, params=params, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            props = data.get("properties", {}).get("parameter", {})
            ghi_series = props.get("ALLSKY_SFC_SW_DWN", {})
            temp_series = props.get("T2M", {})

            raw_ghi = ghi_series.get(date_param)
            raw_temp = temp_series.get(date_param)

            if raw_ghi is not None and float(raw_ghi) >= 0.0:
                ghi_val = float(raw_ghi)
                temp_val = float(raw_temp) if (raw_temp is not None and float(raw_temp) > -50) else default_temp

                # Store in SQLite cache
                db.upsert_nasa_power_daily_cache([{
                    "cell_lat": cell_lat,
                    "cell_lon": cell_lon,
                    "date": d_clean,
                    "ghi_kwh_m2": ghi_val,
                    "temp_c": temp_val,
                }])

                res = {"ghi_kwh_m2": ghi_val, "temp_c": temp_val, "source": "nasa_power_api"}
                _DAILY_IRR_CACHE[cache_key] = res
                return res
    except Exception as e:
        logger.debug(f"NASA POWER daily API request failed for ({cell_lat}, {cell_lon}, {d_clean}): {e}")

    # 3. Fallback
    res = {"ghi_kwh_m2": default_ghi, "temp_c": default_temp, "source": "seasonal_fallback"}
    _DAILY_IRR_CACHE[cache_key] = res
    return res
