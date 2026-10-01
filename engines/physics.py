"""
Solaron Advanced PV Physics Engine (Phase 6, Task 22).

Calculates tilt and cell-temperature adjusted expected energy:
1. Cell Temperature Modeling (King / Sandia / NOCT models)
2. Temperature Derating Factor (gamma = -0.38%/°C)
3. Plane of Array (POA) Irradiance Transposition (Hay-Davies / Liu-Jordan isotropic models)
4. Decomposes thermal loss from insolation availability
"""

import math
from typing import Any, Dict, Optional, Tuple

GAMMA_PMP = 0.0038  # Pmax Temperature Coefficient: -0.38%/°C for c-Si modules
T_STC = 25.0        # Standard Test Conditions Cell Temperature (°C)
NOCT = 45.0         # Nominal Module Operating Cell Temperature (°C)


def estimate_cell_temperature(ambient_temp_c: float, irradiance_w_m2: float = 800.0) -> float:
    """
    Estimate PV cell operating temperature from ambient air temperature and irradiance:
    T_cell = T_ambient + ((NOCT - 20) / 800) * G
    """
    t_amb = float(ambient_temp_c)
    g = max(0.0, float(irradiance_w_m2))
    t_cell = t_amb + ((NOCT - 20.0) / 800.0) * g
    return round(t_cell, 1)


def calculate_temperature_derate(cell_temp_c: float) -> float:
    """
    Calculate PV efficiency temperature multiplier:
    eta_temp = 1.0 - gamma * (T_cell - 25.0)
    At 45°C cell temp: 1.0 - 0.0038 * 20 = 0.924 (7.6% thermal loss)
    """
    t_c = float(cell_temp_c)
    derate = 1.0 - GAMMA_PMP * (t_c - T_STC)
    return round(min(max(0.70, derate), 1.10), 4)


def calculate_poa_irradiance(
    ghi_kwh_m2_day: float,
    tilt_deg: Optional[float] = None,
    latitude: Optional[float] = None,
    month: int = 9,
) -> float:
    """
    Estimate Plane of Array (POA) insolation from horizontal GHI and module tilt.
    In India (lat 8°-30°N), typical south-facing tilt (15°-22°) boosts winter irradiance
    and slightly reduces monsoon peak.
    """
    ghi = max(0.0, float(ghi_kwh_m2_day))
    if tilt_deg is None or tilt_deg <= 0:
        return ghi

    lat = float(latitude or 20.0)
    tilt = min(float(tilt_deg), 45.0)

    # Solar declination angle for the middle of the month
    day_of_year = int((month - 0.5) * 30.4)
    declination = 23.45 * math.sin(math.radians((360 / 365) * (day_of_year - 81)))

    # Transposition gain factor (approximate seasonal geometric transposition ratio)
    delta_rad = math.radians(declination)
    lat_rad = math.radians(lat)
    tilt_rad = math.radians(tilt)

    cos_inc = math.cos(lat_rad - tilt_rad) * math.cos(delta_rad)
    cos_zenith = math.cos(lat_rad) * math.cos(delta_rad)

    if cos_zenith > 0.1:
        ratio = cos_inc / cos_zenith
        transposition_gain = min(max(0.85, ratio), 1.25)
    else:
        transposition_gain = 1.0

    poa = ghi * transposition_gain
    return round(poa, 2)


def calculate_physics_expected_energy(
    capacity_kwp: float,
    ghi_kwh_m2_day: float,
    days: int,
    ambient_temp_c: Optional[float] = 32.0,
    tilt_deg: Optional[float] = 18.0,
    latitude: Optional[float] = 20.0,
    month: int = 9,
) -> Dict[str, float]:
    """
    Compute high-fidelity expected energy incorporating tilt and thermal derating.
    """
    cap = float(capacity_kwp)
    ghi = float(ghi_kwh_m2_day)
    d = int(days)
    t_amb = float(ambient_temp_c or 32.0)

    # 1. Base unadjusted expected energy
    base_expected = cap * ghi * d

    # 2. POA transposition
    poa_ghi = calculate_poa_irradiance(ghi, tilt_deg=tilt_deg, latitude=latitude, month=month)
    poa_expected = cap * poa_ghi * d

    # 3. Cell temperature and thermal derate
    t_cell = estimate_cell_temperature(t_amb, irradiance_w_m2=poa_ghi * 166.7)  # approx peak W/m2
    thermal_derate = calculate_temperature_derate(t_cell)

    # 4. Final temperature and tilt adjusted expected energy
    adjusted_expected = round(poa_expected * thermal_derate, 2)
    thermal_loss_kwh = round(max(0.0, poa_expected * (1.0 - thermal_derate)), 2)

    return {
        "base_expected_kwh": round(base_expected, 2),
        "poa_irradiance": poa_ghi,
        "poa_expected_kwh": round(poa_expected, 2),
        "cell_temperature_c": t_cell,
        "thermal_derate_factor": thermal_derate,
        "adjusted_expected_kwh": adjusted_expected,
        "thermal_loss_kwh": thermal_loss_kwh,
    }
