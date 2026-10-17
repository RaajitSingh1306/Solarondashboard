"""
Solaron Fleet Intelligence Engine.

Pure analytics layer (no UI) that powers the Fleet, Analytics and Intelligence tabs and the
period exports. All maths follows IEC 61724-1 conventions and is written to be robust to the
telemetry gaps that real inverter portals produce.

Contents
--------
1. Period aggregation (daily / weekly / monthly / yearly) at plant, platform or fleet level.
   - Specific yield  Yf = E / P0                                   [kWh/kWp]
   - Reference yield Yr = H / G_stc  (≈ GHI kWh/m² ⇒ peak-sun-hours)[h]
   - Performance ratio PR = Yf / Yr                                [%]
   - CUF = E / (P0 · 24 · days)                                    [%]
   - Availability = producing days / reported days                 [%]
   Group-level PR is *capacity weighted*  PR = ΣE / Σ(P0·Yr)  (never a mean of ratios).

2. Coverage-aware fleet daily series
   - per-day reporting coverage vs. installed capacity, gap-day detection
   - Hampel filter (rolling median ± 3·1.4826·MAD) for spike rejection
   - fleet specific yield normalises away plants that did not report

3. Forecasting
   - Damped-trend Holt / ETS(A,Ad,N) fitted by vectorised grid search on one-step SSE
   - analytic h-step prediction intervals  σ_h² = σ²(1 + Σ c_j²),  c_j = α + β·Σφ^i
   - rolling-origin backtest vs. naive and 7-day-mean baselines (MAE, MAPE, skill score)
   - month-end energy projection via moving-block bootstrap (P10 / P50 / P90)

4. Plant health diagnostics
   - Relative Performance Index  RPI = Yf(plant, d) / median(Yf(producing peers, d))
   - OLS drift of RPI (slope per 30 days, p-value) + CUSUM change detection
   - robust z-score within capacity-bracket peer groups
   - K-Means behavioural clustering (silhouette-validated) with auto-named clusters

5. Platform benchmarking (capacity-weighted PR, Tukey box-plot statistics of daily yield)
"""

from __future__ import annotations

import calendar
import datetime as _dt
import logging
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from pipeline import db
    from core import platforms
    from core.analytics import INDIA_MONTHLY_GHI_DEFAULTS
    from core.data_quality import get_capacity_bracket
except ImportError:  # pragma: no cover - fallback for flat imports
    import db  # type: ignore
    import platforms  # type: ignore
    from analytics import INDIA_MONTHLY_GHI_DEFAULTS  # type: ignore
    from data_quality import get_capacity_bracket  # type: ignore

logger = logging.getLogger(__name__)

GRANULARITIES = ("daily", "weekly", "monthly", "yearly")
LEVELS = ("plant", "platform", "fleet")
BENCHMARK_PR = 0.75          # IEC benchmark PR used for the expected-energy baseline
CO2_KG_PER_KWH = 0.82        # CEA CO₂ baseline database v20
PRODUCING_KWH = 0.05         # noise floor for a "producing" plant-day
INVALID_FLAGS = ("SY_IMPOSSIBLE", "STUCK_VALUE")
Z80 = 1.2815515655446004     # standard-normal quantile for an 80 % (P10–P90) interval


# ---------------------------------------------------------------------------
# Small TTL cache (keeps the UI snappy; cleared after every sync / manual refresh)
# ---------------------------------------------------------------------------
_CACHE: Dict[Tuple, Tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_S = 180.0


def _cached(fn: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        key = (fn.__name__, args, tuple(sorted(kwargs.items())))
        now = time.time()
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit and now - hit[0] < _CACHE_TTL_S:
                return hit[1]
        val = fn(*args, **kwargs)
        with _CACHE_LOCK:
            _CACHE[key] = (now, val)
        return val

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _tariff() -> float:
    try:
        from config import settings
        return float(getattr(settings, "price_per_unit", 14.0) or 14.0)
    except Exception:
        return 14.0


def _today() -> _dt.date:
    return _dt.date.today()


def _month_default_ghi(month: str) -> float:
    try:
        return float(INDIA_MONTHLY_GHI_DEFAULTS.get(f"{int(str(month)[5:7]):02d}", 4.8))
    except Exception:
        return 4.8


def _days_in_month(month: str) -> int:
    y, m = int(month[:4]), int(month[5:7])
    return calendar.monthrange(y, m)[1]


def _elapsed_days_in_month(month: str) -> int:
    t = _today()
    total = _days_in_month(month)
    if month == t.strftime("%Y-%m"):
        return max(1, min(t.day, total))
    return total


def _src_clause(alias: str, source: Optional[str], params: list) -> str:
    if source and str(source).lower() != "all":
        params.append(str(source).lower())
        return f" AND lower({alias}.source) = ?"
    return ""


def _effective_capacity(df: pd.DataFrame) -> pd.Series:
    """Mirror classify_all(): prefer telemetry-derived capacity when the portal value is suspect."""
    nom = pd.to_numeric(df.get("capacity_kwp"), errors="coerce")
    eff = pd.to_numeric(df.get("capacity_effective"), errors="coerce")
    sus = pd.to_numeric(df.get("capacity_suspect"), errors="coerce").fillna(0)
    use_eff = (eff > 0) & ((sus == 1) | (eff.notna() & (eff != nom)))
    cap = nom.where(~use_eff, eff)
    return cap.where(cap > 0)


def _safe_div(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(b > 0, a / b, np.nan)
    return out


def _r(x, nd=2):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return round(float(x), nd)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------
def _ghi_lookup() -> Dict[Tuple[str, str], float]:
    """(plant_id, month) → GHI kWh/m²/day, persisted by the NASA POWER loss engine."""
    df = db.query_df("SELECT plant_id, month, ghi_kwh_m2_day FROM expected_generation", db="analytics")
    if df.empty:
        return {}
    df = df[pd.to_numeric(df["ghi_kwh_m2_day"], errors="coerce") > 0]
    return {(r.plant_id, r.month): float(r.ghi_kwh_m2_day) for r in df.itertuples(index=False)}


def load_daily(
    start: Optional[str] = None,
    end: Optional[str] = None,
    source: Optional[str] = None,
    include_decom: bool = False,
) -> pd.DataFrame:
    """Plant-day telemetry joined with plant metadata and effective capacity."""
    params: list = []
    sql = """
    SELECT d.plant_id, d.date, d.kwh, d.status, d.quality_flags,
           p.plant_name, lower(p.source) AS source, p.capacity_kwp, p.capacity_effective,
           p.capacity_suspect, p.city, coalesce(p.operational_status, 'active') AS operational_status
    FROM daily_generation d
    JOIN plants p ON d.plant_id = p.plant_id
    WHERE 1=1
    """
    if start:
        sql += " AND d.date >= ?"
        params.append(start)
    if end:
        sql += " AND d.date <= ?"
        params.append(end)
    sql += _src_clause("p", source, params)
    if not include_decom:
        sql += " AND coalesce(p.operational_status, 'active') != 'decommissioned'"
    df = db.query_df(sql, params, db="analytics")
    if df.empty:
        return df
    df["cap"] = _effective_capacity(df)
    df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce").fillna(0.0).clip(lower=0.0)
    flags = df["quality_flags"].fillna("").astype(str)
    df["valid"] = ~flags.str.contains("|".join(INVALID_FLAGS), regex=True)
    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date_dt"].notna()].copy()
    df["month"] = df["date_dt"].dt.strftime("%Y-%m")
    return df


def load_monthly(
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    source: Optional[str] = None,
    include_decom: bool = False,
) -> pd.DataFrame:
    """Reconciled monthly ledger (portal / Excel) with plant metadata + daily availability stats."""
    params: list = []
    sql = """
    SELECT m.plant_id, m.month, m.kwh, m.pr_pct, m.tier, m.anomaly_flag, m.anomaly_score,
           p.plant_name, lower(p.source) AS source, p.capacity_kwp, p.capacity_effective,
           p.capacity_suspect, p.city, coalesce(p.operational_status, 'active') AS operational_status,
           eg.ghi_kwh_m2_day AS ghi
    FROM monthly_generation m
    JOIN plants p ON m.plant_id = p.plant_id
    LEFT JOIN expected_generation eg ON eg.plant_id = m.plant_id AND eg.month = m.month
    WHERE 1=1
    """
    if start_month:
        sql += " AND m.month >= ?"
        params.append(start_month)
    if end_month:
        sql += " AND m.month <= ?"
        params.append(end_month)
    sql += _src_clause("p", source, params)
    if not include_decom:
        sql += " AND coalesce(p.operational_status, 'active') != 'decommissioned'"
    df = db.query_df(sql, params, db="analytics")
    if df.empty:
        return df
    df["cap"] = _effective_capacity(df)
    df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce").fillna(0.0).clip(lower=0.0)
    df["pr_pct"] = pd.to_numeric(df["pr_pct"], errors="coerce")
    ghi = pd.to_numeric(df["ghi"], errors="coerce")
    df["ghi"] = ghi.where(ghi > 0, df["month"].map(_month_default_ghi))

    # Daily availability statistics per plant-month
    dparams: list = []
    dsql = """
    SELECT plant_id, substr(date, 1, 7) AS month,
           count(*) AS days_reported,
           sum(CASE WHEN kwh > ? THEN 1 ELSE 0 END) AS producing_days,
           sum(CASE WHEN status = 'fault' THEN 1 ELSE 0 END) AS fault_days,
           sum(CASE WHEN quality_flags LIKE '%SY_IMPOSSIBLE%' OR quality_flags LIKE '%STUCK_VALUE%' THEN 1 ELSE 0 END) AS flagged_days,
           max(CASE WHEN quality_flags IS NULL OR quality_flags = '' THEN kwh END) AS peak_day_kwh
    FROM daily_generation WHERE 1=1
    """
    dparams.append(PRODUCING_KWH)
    if start_month:
        dsql += " AND date >= ?"
        dparams.append(f"{start_month}-01")
    if end_month:
        dsql += " AND date <= ?"
        dparams.append(f"{end_month}-31")
    dsql += " GROUP BY plant_id, substr(date, 1, 7)"
    dstats = db.query_df(dsql, dparams, db="analytics")
    if not dstats.empty:
        df = df.merge(dstats, on=["plant_id", "month"], how="left")
    for c in ("days_reported", "producing_days", "fault_days", "flagged_days", "peak_day_kwh"):
        if c not in df.columns:
            df[c] = np.nan
    df["days_elapsed"] = df["month"].map(_elapsed_days_in_month)
    return df


def load_plants(source: Optional[str] = None, include_decom: bool = True) -> pd.DataFrame:
    params: list = []
    sql = """
    SELECT plant_id, plant_name, lower(source) AS source, capacity_kwp, capacity_effective, capacity_suspect,
           city, latitude, longitude, coalesce(operational_status, 'active') AS operational_status
    FROM plants p WHERE 1=1
    """
    sql += _src_clause("p", source, params)
    if not include_decom:
        sql += " AND coalesce(operational_status, 'active') != 'decommissioned'"
    df = db.query_df(sql, params, db="analytics")
    if not df.empty:
        df["cap"] = _effective_capacity(df)
    return df


# ---------------------------------------------------------------------------
# 1. Period aggregation
# ---------------------------------------------------------------------------
AGG_COLUMNS: Dict[str, Dict[str, Any]] = {
    "period": {"label": "Period", "group": "Period", "default": True},
    "period_start": {"label": "Period Start", "group": "Period", "default": True},
    "period_end": {"label": "Period End", "group": "Period", "default": True},
    "days_elapsed": {"label": "Days in Period", "group": "Period", "default": False},
    "plant_id": {"label": "Plant ID", "group": "Scope", "default": True, "levels": ("plant",)},
    "plant_name": {"label": "Plant Name", "group": "Scope", "default": True, "levels": ("plant",)},
    "source": {"label": "Platform", "group": "Scope", "default": True, "levels": ("plant", "platform")},
    "city": {"label": "City", "group": "Scope", "default": False, "levels": ("plant",)},
    "phone": {"label": "Phone Number", "group": "Customer & Contact", "default": False, "levels": ("plant",)},
    "customer_name": {"label": "Customer Name", "group": "Customer & Contact", "default": False, "levels": ("plant",)},
    "plants": {"label": "Plants", "group": "Scope", "default": True, "levels": ("platform", "fleet")},
    "capacity_kwp": {"label": "Capacity (kWp)", "group": "Scope", "default": True},
    "kwh": {"label": "Generation (kWh)", "group": "Energy", "default": True},
    "specific_yield": {"label": "Specific Yield (kWh/kWp)", "group": "Energy", "default": True},
    "yield_per_day": {"label": "Yield per Day (kWh/kWp/day)", "group": "Energy", "default": True},
    "cuf_pct": {"label": "CUF (%)", "group": "Energy", "default": True},
    "peak_day_kwh": {"label": "Peak Day (kWh)", "group": "Energy", "default": False},
    "ghi_kwh_m2_day": {"label": "Avg GHI (kWh/m²/day)", "group": "Performance", "default": False},
    "reference_yield_h": {"label": "Reference Yield Yr (h)", "group": "Performance", "default": False},
    "pr_pct": {"label": "Performance Ratio (%)", "group": "Performance", "default": True},
    "expected_kwh": {"label": "Expected @75% PR (kWh)", "group": "Performance", "default": True},
    "realization_pct": {"label": "Realization (%)", "group": "Performance", "default": True},
    "days_reported": {"label": "Days Reported", "group": "Reliability", "default": False},
    "producing_days": {"label": "Producing Days", "group": "Reliability", "default": False},
    "availability_pct": {"label": "Availability (%)", "group": "Reliability", "default": True},
    "flagged_days": {"label": "Quality-Flagged Days", "group": "Reliability", "default": False},
    "revenue_inr": {"label": "Savings (INR)", "group": "Financial & ESG", "default": True},
    "co2_kg": {"label": "CO₂ Avoided (kg)", "group": "Financial & ESG", "default": False},
}


def agg_columns_for_level(level: str) -> Dict[str, Dict[str, Any]]:
    return {k: v for k, v in AGG_COLUMNS.items() if level in v.get("levels", LEVELS)}


def _period_frame(dates: pd.Series, granularity: str) -> pd.DataFrame:
    d = pd.to_datetime(dates)
    if granularity == "daily":
        start = d.dt.normalize()
        end = start
        label = start.dt.strftime("%Y-%m-%d")
    elif granularity == "weekly":
        start = (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.normalize()
        end = start + pd.Timedelta(days=6)
        iso = start.dt.isocalendar()
        label = iso["year"].astype(str) + "-W" + iso["week"].astype(int).map("{:02d}".format)
    elif granularity == "monthly":
        start = d.dt.to_period("M").dt.start_time
        end = d.dt.to_period("M").dt.end_time.dt.normalize()
        label = start.dt.strftime("%Y-%m")
    else:
        start = d.dt.to_period("Y").dt.start_time
        end = d.dt.to_period("Y").dt.end_time.dt.normalize()
        label = start.dt.strftime("%Y")
    return pd.DataFrame({"period": label.values, "ps": start.values, "pe": end.values}, index=dates.index)


def _days_elapsed(ps: pd.Series, pe: pd.Series, start: Optional[str], end: Optional[str]) -> pd.Series:
    """Calendar days of each period that fall inside the requested window and not in the future."""
    lo = pd.to_datetime(ps)
    hi = pd.to_datetime(pe)
    if start:
        lo = lo.where(lo >= pd.Timestamp(start), pd.Timestamp(start))
    cap_hi = pd.Timestamp(_today())
    if end:
        cap_hi = min(cap_hi, pd.Timestamp(end))
    hi = hi.where(hi <= cap_hi, cap_hi)
    return ((hi - lo).dt.days + 1).clip(lower=0)


def _finalise(df: pd.DataFrame, level: str) -> pd.DataFrame:
    """Derive ratio KPIs from summed energy terms (capacity-weighted, IEC 61724)."""
    t = _tariff()
    cap = df["capacity_kwp"].astype(float)
    kwh = df["kwh"].astype(float)
    days = df["days_elapsed"].astype(float)
    theo = df["theo_kwh"].astype(float)              # Σ P0 · Yr  (reference energy)
    df["specific_yield"] = _safe_div(kwh, cap)
    df["yield_per_day"] = _safe_div(kwh, cap * days)
    df["cuf_pct"] = _safe_div(kwh * 100.0, cap * 24.0 * days)
    df["pr_pct"] = np.clip(_safe_div(kwh * 100.0, theo), 0, 150)
    df["expected_kwh"] = theo * BENCHMARK_PR
    df["realization_pct"] = _safe_div(kwh * 100.0, theo * BENCHMARK_PR)
    df["reference_yield_h"] = _safe_div(theo, cap)
    df["availability_pct"] = _safe_div(df["producing_days"].astype(float) * 100.0, df["days_reported"].astype(float))
    df["revenue_inr"] = kwh * t
    df["co2_kg"] = kwh * CO2_KG_PER_KWH
    df["period_start"] = pd.to_datetime(df["ps"]).dt.strftime("%Y-%m-%d")
    df["period_end"] = pd.to_datetime(df["pe"]).dt.strftime("%Y-%m-%d")
    round_map = {
        "capacity_kwp": 2, "kwh": 2, "specific_yield": 2, "yield_per_day": 3, "cuf_pct": 2, "pr_pct": 1,
        "expected_kwh": 1, "realization_pct": 1, "reference_yield_h": 1, "availability_pct": 1,
        "revenue_inr": 0, "co2_kg": 1, "ghi_kwh_m2_day": 2, "peak_day_kwh": 2,
    }
    for c, nd in round_map.items():
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round(nd)
    for c in ("days_reported", "producing_days", "flagged_days", "days_elapsed", "plants"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    order = [k for k in agg_columns_for_level(level) if k in df.columns]
    sort_cols = ["period_start"] + (["plant_name"] if level == "plant" else ["source"] if level == "platform" else [])
    df = df.sort_values(sort_cols, ascending=[False] + [True] * (len(sort_cols) - 1))
    return df[order].reset_index(drop=True)


def _empty_agg(level: str) -> pd.DataFrame:
    return pd.DataFrame(columns=list(agg_columns_for_level(level).keys()))


def _rollup(plant_df: pd.DataFrame, level: str, keys: List[str]) -> pd.DataFrame:
    grp_keys = keys + (["source"] if level == "platform" else [])
    agg = plant_df.groupby(grp_keys, dropna=False).agg(
        plants=("plant_id", "nunique"),
        capacity_kwp=("capacity_kwp", "sum"),
        kwh=("kwh", "sum"),
        theo_kwh=("theo_kwh", "sum"),
        days_reported=("days_reported", "sum"),
        producing_days=("producing_days", "sum"),
        flagged_days=("flagged_days", "sum"),
        ghi_w=("ghi_w", "sum"),
    ).reset_index()
    agg["ghi_kwh_m2_day"] = _safe_div(agg["ghi_w"], agg["capacity_kwp"])
    return agg


def aggregate_generation(
    granularity: str = "monthly",
    start: Optional[str] = None,
    end: Optional[str] = None,
    level: str = "plant",
    source: Optional[str] = None,
    include_decom: bool = True,
) -> pd.DataFrame:
    """
    Aggregate generation into daily / weekly / monthly / yearly periods.

    Daily & weekly periods are built from plant-day telemetry (quality-flagged days excluded from
    energy and counted in ``flagged_days``). Monthly & yearly periods use the reconciled monthly
    ledger so Excel uploads and portal month totals are honoured.

    ``start`` / ``end`` accept 'YYYY-MM-DD' or 'YYYY-MM'.
    """
    g = (granularity or "monthly").lower()
    lvl = (level or "plant").lower()
    if g not in GRANULARITIES:
        raise ValueError(f"granularity must be one of {GRANULARITIES}")
    if lvl not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")

    s_date = f"{start}-01" if start and len(start) == 7 else start
    e_date = None
    if end:
        e_date = f"{end}-{_days_in_month(end):02d}" if len(end) == 7 else end
    keys = ["period", "ps", "pe"]

    if g in ("daily", "weekly"):
        d = load_daily(s_date, e_date, source, include_decom)
        if d.empty:
            return _empty_agg(lvl)
        ghi_map = _ghi_lookup()
        d["ghi"] = [ghi_map.get((p, m), _month_default_ghi(m)) for p, m in zip(d["plant_id"], d["month"])]
        d = pd.concat([d, _period_frame(d["date_dt"], g)], axis=1)
        d["kwh_c"] = d["kwh"].where(d["valid"], 0.0)
        d["theo"] = (d["cap"].fillna(0) * d["ghi"]).where(d["valid"], 0.0)
        d["producing"] = (d["valid"] & (d["kwh"] > PRODUCING_KWH)).astype(int)
        d["flagged"] = (~d["valid"]).astype(int)
        d["valid_i"] = d["valid"].astype(int)

        plant = d.groupby(keys + ["plant_id", "plant_name", "source", "city"], dropna=False).agg(
            capacity_kwp=("cap", "max"),
            kwh=("kwh_c", "sum"),
            theo_kwh=("theo", "sum"),
            days_reported=("valid_i", "sum"),
            producing_days=("producing", "sum"),
            flagged_days=("flagged", "sum"),
            peak_day_kwh=("kwh_c", "max"),
            ghi_kwh_m2_day=("ghi", "mean"),
        ).reset_index()
        plant["days_elapsed"] = _days_elapsed(plant["ps"], plant["pe"], s_date, e_date)
        if lvl == "plant":
            return _finalise(plant, lvl)

        plant["ghi_w"] = plant["ghi_kwh_m2_day"] * plant["capacity_kwp"].fillna(0)
        out = _rollup(plant, lvl, keys)
        # Peak day of the group = max over the daily group totals
        day_keys = keys + (["source"] if lvl == "platform" else []) + ["date"]
        daily_tot = d.groupby(day_keys)["kwh_c"].sum().reset_index()
        peak = daily_tot.groupby([k for k in day_keys if k != "date"])["kwh_c"].max().rename("peak_day_kwh").reset_index()
        out = out.merge(peak, on=[k for k in day_keys if k != "date"], how="left")
        out["days_elapsed"] = _days_elapsed(out["ps"], out["pe"], s_date, e_date)
        return _finalise(out, lvl)

    # Monthly / yearly from the reconciled ledger
    sm = start[:7] if start else None
    em = end[:7] if end else None
    m = load_monthly(sm, em, source, include_decom)
    if m.empty:
        return _empty_agg(lvl)
    # Reference energy: back out per-plant theoretical energy from the stored PR so the
    # source-specific evaluation windows used by classify_all() are respected.
    pr = m["pr_pct"]
    theo_from_pr = _safe_div(m["kwh"], pr / 100.0)
    theo_from_ghi = m["cap"].fillna(0) * m["ghi"] * m["days_elapsed"]
    m["theo_kwh"] = np.where((pr > 0) & (m["kwh"] > 1.0), theo_from_pr, theo_from_ghi)
    m["date_dt"] = pd.to_datetime(m["month"] + "-01")
    m = pd.concat([m, _period_frame(m["date_dt"], g)], axis=1)
    m["capacity_kwp"] = m["cap"]
    m["ghi_kwh_m2_day"] = m["ghi"]
    for c in ("days_reported", "producing_days", "flagged_days"):
        m[c] = pd.to_numeric(m[c], errors="coerce").fillna(0)

    plant = m.groupby(keys + ["plant_id", "plant_name", "source", "city"], dropna=False).agg(
        capacity_kwp=("capacity_kwp", "max"),
        kwh=("kwh", "sum"),
        theo_kwh=("theo_kwh", "sum"),
        days_reported=("days_reported", "sum"),
        producing_days=("producing_days", "sum"),
        flagged_days=("flagged_days", "sum"),
        peak_day_kwh=("peak_day_kwh", "max"),
        ghi_kwh_m2_day=("ghi_kwh_m2_day", "mean"),
        days_elapsed=("days_elapsed", "sum"),
    ).reset_index()
    if g == "monthly":
        plant["days_elapsed"] = _days_elapsed(plant["ps"], plant["pe"], s_date, e_date)
    if lvl == "plant":
        return _finalise(plant, lvl)
    plant["ghi_w"] = plant["ghi_kwh_m2_day"] * plant["capacity_kwp"].fillna(0)
    out = _rollup(plant, lvl, keys)
    de = plant.groupby(keys + (["source"] if lvl == "platform" else []))["days_elapsed"].max().reset_index()
    out = out.merge(de, on=keys + (["source"] if lvl == "platform" else []), how="left")
    out["peak_day_kwh"] = np.nan
    return _finalise(out, lvl)


# ---------------------------------------------------------------------------
# 2. Coverage-aware fleet daily series
# ---------------------------------------------------------------------------
def hampel_mask(x: Sequence[float], window: int = 7, n_sigma: float = 3.0) -> np.ndarray:
    """True where a point is an outlier vs. its centred rolling median (Hampel identifier)."""
    s = pd.Series(np.asarray(x, dtype=float))
    med = s.rolling(window, center=True, min_periods=3).median()
    mad = (s - med).abs().rolling(window, center=True, min_periods=3).median()
    thresh = n_sigma * 1.4826 * mad
    out = (s - med).abs() > thresh.where(thresh > 1e-9, np.inf)
    return out.fillna(False).to_numpy()


@_cached
def fleet_daily_series(
    start: Optional[str] = None,
    end: Optional[str] = None,
    source: Optional[str] = None,
) -> pd.DataFrame:
    """
    Per-day fleet energy with reporting coverage and data-quality masks.

    Columns: date, kwh, producing_cap, active_cap, coverage, fleet_sy, ghi, pr_pct, plants_producing,
             is_gap, is_outlier, usable, kwh_adjusted
    """
    d = load_daily(start, end, source, include_decom=False)
    if d.empty:
        return pd.DataFrame()
    plants = load_plants(source, include_decom=False)
    active_cap = float(plants["cap"].fillna(0).sum()) if not plants.empty else 0.0
    ghi_map = _ghi_lookup()
    d["ghi"] = [ghi_map.get((p, m), _month_default_ghi(m)) for p, m in zip(d["plant_id"], d["month"])]
    v = d[d["valid"] & d["cap"].notna()].copy()
    v["producing"] = v["kwh"] > PRODUCING_KWH
    v["cap_prod"] = v["cap"].where(v["producing"], 0.0)
    v["ghi_cap"] = v["ghi"] * v["cap_prod"]
    v["kwh_prod"] = v["kwh"].where(v["producing"], 0.0)

    s = v.groupby("date").agg(
        kwh=("kwh", "sum"),
        kwh_prod=("kwh_prod", "sum"),
        producing_cap=("cap_prod", "sum"),
        reporting_cap=("cap", "sum"),
        ghi_cap=("ghi_cap", "sum"),
        plants_producing=("producing", "sum"),
        plants_reporting=("plant_id", "nunique"),
    ).reset_index().sort_values("date")
    s["active_cap"] = active_cap
    s["coverage"] = _safe_div(s["producing_cap"], active_cap if active_cap > 0 else s["producing_cap"].max())
    s["fleet_sy"] = _safe_div(s["kwh_prod"], s["producing_cap"])
    s["ghi"] = _safe_div(s["ghi_cap"], s["producing_cap"])
    s["pr_pct"] = np.clip(_safe_div(s["fleet_sy"] * 100.0, s["ghi"]), 0, 150)

    med_cov = float(np.nanmedian(s["coverage"])) if len(s) else 0.0
    s["is_gap"] = (s["coverage"] < 0.5 * med_cov) | (s["producing_cap"] <= 0)
    sy = s["fleet_sy"].fillna(0.0).to_numpy()
    out_mask = np.zeros(len(s), dtype=bool)
    ok_idx = np.where(~s["is_gap"].to_numpy())[0]
    if len(ok_idx) >= 5:
        out_mask[ok_idx] = hampel_mask(sy[ok_idx])
    s["is_outlier"] = out_mask
    s["usable"] = ~s["is_gap"] & ~s["is_outlier"] & (s["fleet_sy"] > 0)
    typical_cap = float(np.nanmedian(s.loc[s["usable"], "producing_cap"])) if s["usable"].any() else active_cap
    s["typical_cap"] = typical_cap
    s["kwh_adjusted"] = s["fleet_sy"] * typical_cap
    return s.reset_index(drop=True)


# ---------------------------------------------------------------------------
# 3. Forecasting — damped Holt (ETS(A,Ad,N)) with analytic intervals
# ---------------------------------------------------------------------------
_ALPHAS = np.arange(0.05, 0.96, 0.05)
_BETAS = np.array([0.0, 0.02, 0.05, 0.1, 0.2, 0.3])
_PHIS = np.array([0.80, 0.88, 0.94, 0.98])
_GRID = np.array(np.meshgrid(_ALPHAS, _BETAS, _PHIS, indexing="ij")).reshape(3, -1).T  # (G, 3)


def _holt_run(y: np.ndarray, params: np.ndarray, burn: int = 3):
    """Vectorised ETS(A,Ad,N) over a parameter grid. params: (G,3) [alpha, beta*, phi]."""
    a, bs, ph = params[:, 0], params[:, 1], params[:, 2]
    beta = a * bs                                  # Hyndman β = α·β*
    lvl = np.full(len(params), y[0], dtype=float)
    trd = np.zeros(len(params), dtype=float)
    sse = np.zeros(len(params), dtype=float)
    fitted = np.zeros((len(y), len(params)))
    for t in range(len(y)):
        yhat = lvl + ph * trd
        fitted[t] = yhat
        e = y[t] - yhat
        if t >= burn:
            sse += e * e
        lvl = yhat + a * e
        trd = ph * trd + beta * e
    return sse, fitted, lvl, trd


def holt_fit(y: Sequence[float]) -> Dict[str, Any]:
    arr = np.asarray(y, dtype=float)
    if len(arr) < 8:
        raise ValueError("Need at least 8 observations for Holt fitting")
    sse, fitted, lvl, trd = _holt_run(arr, _GRID)
    i = int(np.argmin(sse))
    alpha, beta_s, phi = _GRID[i]
    resid = arr[3:] - fitted[3:, i]
    sigma = float(np.sqrt(np.mean(resid ** 2))) if len(resid) else 0.0
    return {
        "alpha": float(alpha), "beta_star": float(beta_s), "phi": float(phi),
        "level": float(lvl[i]), "trend": float(trd[i]), "sigma": sigma,
        "fitted": fitted[:, i], "n": len(arr),
    }


def holt_forecast(fit: Dict[str, Any], horizon: int) -> Dict[str, np.ndarray]:
    a, phi = fit["alpha"], fit["phi"]
    beta = a * fit["beta_star"]
    h = np.arange(1, horizon + 1)
    phi_cum = np.cumsum(phi ** h)                                   # Σ_{i=1..h} φ^i
    point = fit["level"] + phi_cum * fit["trend"]
    c = a + beta * phi_cum                                          # c_j, j = 1..h
    var_mult = 1.0 + np.concatenate([[0.0], np.cumsum(c[:-1] ** 2)])
    sd = fit["sigma"] * np.sqrt(var_mult)
    return {"point": point, "sd": sd, "lo": point - Z80 * sd, "hi": point + Z80 * sd}


def _backtest(y: np.ndarray, n_test: int = 14) -> Dict[str, Any]:
    """Rolling-origin one-step-ahead evaluation vs. naive and 7-day mean baselines."""
    n_test = min(n_test, max(0, len(y) - 10))
    if n_test < 4:
        return {"n_test": 0}
    err_m, err_n, err_s, actual = [], [], [], []
    for t in range(len(y) - n_test, len(y)):
        train = y[:t]
        try:
            f = holt_fit(train)
            pm = holt_forecast(f, 1)["point"][0]
        except ValueError:
            continue
        err_m.append(y[t] - pm)
        err_n.append(y[t] - train[-1])
        err_s.append(y[t] - float(np.mean(train[-7:])))
        actual.append(y[t])
    if not err_m:
        return {"n_test": 0}
    em, en, es, act = map(np.asarray, (err_m, err_n, err_s, actual))
    mae_m, mae_n, mae_s = (float(np.mean(np.abs(e))) for e in (em, en, es))
    mape = float(np.mean(np.abs(em) / np.where(act > 0, act, np.nan)) * 100.0)
    return {
        "n_test": len(em),
        "mae_model": mae_m, "mae_naive": mae_n, "mae_mean7": mae_s,
        "mape_model_pct": mape,
        "skill_vs_naive": 1.0 - mae_m / mae_n if mae_n > 0 else 0.0,
        "skill_vs_mean7": 1.0 - mae_m / mae_s if mae_s > 0 else 0.0,
        "rmse_model": float(np.sqrt(np.mean(em ** 2))),
    }


@_cached
def forecast_fleet(horizon: int = 7, source: Optional[str] = None, lookback_days: int = 75) -> Dict[str, Any]:
    """Forecast fleet specific yield (kWh/kWp/day) and energy for the next ``horizon`` days."""
    end = _today()
    start = end - _dt.timedelta(days=lookback_days)
    s = fleet_daily_series(start.isoformat(), end.isoformat(), source)
    if s.empty or int(s["usable"].sum()) < 10:
        return {"status": "insufficient_data", "reason": "Fewer than 10 clean telemetry days for this scope."}

    u = s[s["usable"]].copy()
    u["date_dt"] = pd.to_datetime(u["date"])
    # Exclude today (partial day) from training
    u = u[u["date_dt"].dt.date < end]
    if len(u) < 10:
        return {"status": "insufficient_data", "reason": "Fewer than 10 completed clean days."}
    full_idx = pd.date_range(u["date_dt"].min(), u["date_dt"].max(), freq="D")
    y_series = u.set_index("date_dt")["fleet_sy"].reindex(full_idx).interpolate(limit_direction="both")
    y = y_series.to_numpy(dtype=float)

    fit = holt_fit(y)
    fc = holt_forecast(fit, horizon)
    cap = float(u["producing_cap"].tail(7).median())
    last_day = full_idx[-1].date()
    f_dates = [(last_day + _dt.timedelta(days=i)).isoformat() for i in range(1, horizon + 1)]
    clip = lambda a: np.clip(a, 0.0, 8.0)
    bt = _backtest(y)
    return {
        "status": "ok",
        "method": "Damped-trend Holt · ETS(A,Ad,N)",
        "params": {k: round(fit[k], 3) for k in ("alpha", "beta_star", "phi", "sigma")},
        "train_days": int(fit["n"]),
        "interpolated_days": int(len(full_idx) - len(u)),
        "typical_capacity_kwp": round(cap, 1),
        "history_dates": [d.strftime("%Y-%m-%d") for d in full_idx],
        "history_sy": [round(v, 3) for v in y],
        "fitted_sy": [round(v, 3) for v in fit["fitted"]],
        "forecast_dates": f_dates,
        "forecast_sy": [round(v, 3) for v in clip(fc["point"])],
        "forecast_lo_sy": [round(v, 3) for v in clip(fc["lo"])],
        "forecast_hi_sy": [round(v, 3) for v in clip(fc["hi"])],
        "forecast_kwh": [round(v * cap, 1) for v in clip(fc["point"])],
        "forecast_lo_kwh": [round(v * cap, 1) for v in clip(fc["lo"])],
        "forecast_hi_kwh": [round(v * cap, 1) for v in clip(fc["hi"])],
        "next_7d_kwh": round(float(np.sum(clip(fc["point"]))) * cap, 0),
        "backtest": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in bt.items()},
    }


def _block_bootstrap_sums(x: np.ndarray, n_days: int, n_boot: int = 4000, block: int = 3, seed: int = 42) -> np.ndarray:
    """Moving-block bootstrap of ``n_days`` future daily values (keeps weather persistence)."""
    if n_days <= 0 or len(x) == 0:
        return np.zeros(n_boot)
    rng = np.random.default_rng(seed)
    block = max(1, min(block, len(x)))
    n_blocks = math.ceil(n_days / block)
    starts = rng.integers(0, len(x) - block + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)).reshape(n_boot, -1)[:, :n_days]
    return x[idx].sum(axis=1)


@_cached
def project_month_end(month: Optional[str] = None, source: Optional[str] = None) -> Dict[str, Any]:
    """Probabilistic month-end energy projection (P10 / P50 / P90) for the selected scope."""
    t = _today()
    month = month or t.strftime("%Y-%m")
    dim = _days_in_month(month)
    params: list = [month]
    sql = """
    SELECT coalesce(sum(m.kwh), 0) AS kwh,
           coalesce(sum(CASE WHEN m.pr_pct > 0 AND m.kwh > 1 THEN m.kwh / (m.pr_pct / 100.0) END), 0) AS theo
    FROM monthly_generation m JOIN plants p ON p.plant_id = m.plant_id
    WHERE m.month = ? AND coalesce(p.operational_status, 'active') != 'decommissioned'
    """
    sql += _src_clause("p", source, params)
    led = db.query_df(sql, params, db="analytics")
    actual = float(led.iloc[0]["kwh"]) if not led.empty else 0.0

    lparams: list = [month]
    lsql = """
    SELECT coalesce(sum(l.expected_kwh), 0) AS exp_elapsed
    FROM loss_analysis l JOIN plants p ON p.plant_id = l.plant_id
    WHERE l.month = ? AND coalesce(p.operational_status, 'active') != 'decommissioned'
    """
    lsql += _src_clause("p", source, lparams)
    lo = db.query_df(lsql, lparams, db="analytics")
    exp_elapsed = float(lo.iloc[0]["exp_elapsed"]) if not lo.empty else 0.0
    elapsed = _elapsed_days_in_month(month)
    expected_full = exp_elapsed / max(1, elapsed) * dim if exp_elapsed > 0 else 0.0

    is_current = month == t.strftime("%Y-%m")
    remaining = max(0, dim - t.day) if is_current else 0
    base = {
        "month": month, "days_in_month": dim, "elapsed_days": elapsed, "remaining_days": remaining,
        "actual_to_date_kwh": round(actual, 1), "expected_full_month_kwh": round(expected_full, 1),
    }
    if remaining == 0:
        base.update({"status": "closed" if not is_current else "ok", "p10_kwh": round(actual, 1),
                     "p50_kwh": round(actual, 1), "p90_kwh": round(actual, 1),
                     "prob_meet_expected": 1.0 if expected_full and actual >= expected_full else 0.0,
                     "method": "Month closed — actual ledger value"})
        return base

    start = (t - _dt.timedelta(days=45)).isoformat()
    s = fleet_daily_series(start, t.isoformat(), source)
    if s.empty or int(s["usable"].sum()) < 5:
        base.update({"status": "insufficient_data", "reason": "Fewer than 5 clean days to bootstrap from."})
        return base
    u = s[s["usable"] & (pd.to_datetime(s["date"]).dt.date < t)].tail(21)
    cap = float(u["producing_cap"].tail(7).median())
    daily_kwh = (u["fleet_sy"] * cap).to_numpy(dtype=float)
    sims = actual + _block_bootstrap_sums(daily_kwh, remaining)
    p10, p50, p90 = np.percentile(sims, [10, 50, 90])
    base.update({
        "status": "ok",
        "method": f"Moving-block bootstrap (block=3, n=4000) over last {len(u)} clean days",
        "p10_kwh": round(float(p10), 1), "p50_kwh": round(float(p50), 1), "p90_kwh": round(float(p90), 1),
        "daily_mean_kwh": round(float(np.mean(daily_kwh)), 1),
        "daily_std_kwh": round(float(np.std(daily_kwh, ddof=1)), 1) if len(daily_kwh) > 1 else 0.0,
        "prob_meet_expected": round(float(np.mean(sims >= expected_full)), 3) if expected_full > 0 else None,
        "sample_days": int(len(u)),
    })
    # Cumulative trajectory for charting (daily telemetry scaled to the ledger total)
    month_s = s[pd.to_datetime(s["date"]).dt.strftime("%Y-%m") == month].copy()
    if not month_s.empty:
        raw = month_s["kwh"].to_numpy(dtype=float)
        scale = actual / raw.sum() if raw.sum() > 0 else 1.0
        base["cum_dates"] = month_s["date"].tolist()
        base["cum_actual_kwh"] = [round(v, 1) for v in np.cumsum(raw * scale)]
    fut_dates = [(t + _dt.timedelta(days=i)).isoformat() for i in range(1, remaining + 1)]
    m_d = float(np.mean(daily_kwh))
    sd_d = float(np.std(daily_kwh, ddof=1)) if len(daily_kwh) > 1 else 0.0
    k = np.arange(1, remaining + 1)
    base["proj_dates"] = fut_dates
    base["proj_p50"] = [round(actual + m_d * i, 1) for i in k]
    base["proj_p10"] = [round(actual + m_d * i - Z80 * sd_d * math.sqrt(i * 3), 1) for i in k]
    base["proj_p90"] = [round(actual + m_d * i + Z80 * sd_d * math.sqrt(i * 3), 1) for i in k]
    return base


# ---------------------------------------------------------------------------
# 4. Plant health diagnostics (RPI, drift, CUSUM, robust z, K-Means)
# ---------------------------------------------------------------------------
def _cusum_neg(x: np.ndarray, k: float = 0.5, h: float = 4.0) -> Tuple[int, int]:
    """One-sided lower CUSUM on standardised series. Returns (alarm_count, last_alarm_index)."""
    if len(x) < 6:
        return 0, -1
    mu = float(np.median(x[: max(5, len(x) // 2)]))
    sd = float(np.std(x)) or 1.0
    s, alarms, last = 0.0, 0, -1
    for i, v in enumerate(x):
        s = max(0.0, s - (v - mu) / sd - k)
        if s > h:
            alarms += 1
            last = i
            s = 0.0
    return alarms, last


def _name_clusters(centroids: pd.DataFrame) -> Dict[int, str]:
    """Assign interpretable unique names to K-Means clusters from their centroids."""
    names: Dict[int, str] = {}
    remaining = list(centroids.index)

    def take(idx, name):
        names[idx] = name
        remaining.remove(idx)

    if remaining:
        take(centroids.loc[remaining, "availability_pct"].idxmin(), "Intermittent / Comm Gaps")
    if remaining:
        take(centroids.loc[remaining, "rpi_producing"].idxmax(), "Stable High Performers")
    if remaining:
        take(centroids.loc[remaining, "rpi_producing"].idxmin(), "Chronic Underperformers")
    if remaining:
        take(centroids.loc[remaining, "rpi_slope_30d"].idxmin(), "Drifting / Degrading")
    for i in list(remaining):
        take(i, "Typical Performers")
    return names


@_cached
def plant_health_matrix(lookback_days: int = 30, source: Optional[str] = None, n_clusters: int = 4) -> Dict[str, Any]:
    """Per-plant diagnostics over the last ``lookback_days`` of clean telemetry."""
    from scipy import stats
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    end = _today()
    start = end - _dt.timedelta(days=lookback_days + 14)
    series = fleet_daily_series(start.isoformat(), end.isoformat(), None)  # fleet-wide peer baseline
    if series.empty:
        return {"status": "insufficient_data", "plants": pd.DataFrame()}
    usable_dates = set(series.loc[series["usable"], "date"].tolist()[-lookback_days:])
    d = load_daily(start.isoformat(), end.isoformat(), source, include_decom=False)
    if d.empty:
        return {"status": "insufficient_data", "plants": pd.DataFrame()}
    d = d[d["valid"] & d["cap"].notna() & d["date"].isin(usable_dates)].copy()
    if d.empty:
        return {"status": "insufficient_data", "plants": pd.DataFrame()}
    d["sy"] = d["kwh"] / d["cap"]
    # Peer median per day is always computed on the whole fleet (weather normaliser)
    all_d = load_daily(start.isoformat(), end.isoformat(), None, include_decom=False)
    all_d = all_d[all_d["valid"] & all_d["cap"].notna() & all_d["date"].isin(usable_dates)]
    all_d = all_d.assign(sy=all_d["kwh"] / all_d["cap"])
    peer_med = all_d[all_d["sy"] > PRODUCING_KWH].groupby("date")["sy"].median()
    d["peer_sy"] = d["date"].map(peer_med)
    d = d[d["peer_sy"] > 0]
    d["rpi"] = (d["sy"] / d["peer_sy"]).clip(0, 3)
    d["producing"] = d["kwh"] > PRODUCING_KWH
    date_idx = {dt: i for i, dt in enumerate(sorted(usable_dates))}
    d["t"] = d["date"].map(date_idx)

    rows = []
    for pid, g in d.groupby("plant_id"):
        g = g.sort_values("t")
        prod = g[g["producing"]]
        n, n_prod = len(g), len(prod)
        rpi_all = float(g["rpi"].mean())
        rpi_prod = float(prod["rpi"].median()) if n_prod else 0.0
        cv = float(prod["rpi"].std(ddof=1) / prod["rpi"].mean()) if n_prod > 2 and prod["rpi"].mean() > 0 else np.nan
        slope30 = p_val = np.nan
        if n_prod >= 8 and prod["t"].nunique() > 2:
            lr = stats.linregress(prod["t"].to_numpy(float), prod["rpi"].to_numpy(float))
            slope30, p_val = float(lr.slope * 30.0), float(lr.pvalue)
        alarms, last_alarm = _cusum_neg(prod["rpi"].to_numpy(float)) if n_prod >= 6 else (0, -1)
        recent_alarm = bool(last_alarm >= 0 and last_alarm >= n_prod - 7)
        first = g.iloc[0]
        rows.append({
            "plant_id": pid, "plant_name": first["plant_name"], "source": first["source"],
            "capacity_kwp": round(float(first["cap"]), 2), "bracket": get_capacity_bracket(float(first["cap"])),
            "days": n, "producing_days": n_prod,
            "availability_pct": round(100.0 * n_prod / n, 1) if n else 0.0,
            "rpi_mean": round(rpi_all, 3), "rpi_producing": round(rpi_prod, 3),
            "rpi_cv": round(cv, 3) if not np.isnan(cv) else None,
            "rpi_slope_30d": round(slope30, 3) if not np.isnan(slope30) else None,
            "slope_p_value": round(p_val, 4) if not np.isnan(p_val) else None,
            "cusum_alarms": alarms, "cusum_recent": recent_alarm,
            "avg_daily_kwh": round(float(g["kwh"].mean()), 2),
            "lost_kwh_vs_peer": round(float(((g["peer_sy"] - g["sy"]).clip(lower=0) * g["cap"]).sum()), 1),
        })
    P = pd.DataFrame(rows)
    if P.empty:
        return {"status": "insufficient_data", "plants": P}

    # Robust z within capacity-bracket peer group (fallback fleet-wide for tiny groups)
    def robust_z(x: pd.Series) -> pd.Series:
        med = x.median()
        mad = (x - med).abs().median()
        return (x - med) / (1.4826 * mad) if mad > 1e-6 else x * 0.0

    P["robust_z"] = np.nan
    for _, idx in P.groupby("bracket").groups.items():
        grp = P.loc[idx, "rpi_producing"]
        P.loc[idx, "robust_z"] = robust_z(grp if len(grp) >= 5 else P["rpi_producing"]).loc[idx] if len(grp) >= 5 else robust_z(P["rpi_producing"]).loc[idx]
    P["robust_z"] = P["robust_z"].astype(float).round(2)
    P["drift_flag"] = (P["rpi_slope_30d"].fillna(0) <= -0.05) & (P["slope_p_value"].fillna(1) < 0.05)
    P["outlier_flag"] = P["robust_z"] <= -2.5

    # K-Means behavioural clustering
    feats = ["rpi_producing", "availability_pct", "rpi_cv", "rpi_slope_30d"]
    X = P[feats].astype(float)
    X = X.fillna(X.median())
    cluster_info: Dict[str, Any] = {"k": 0}
    P["cluster"] = "Insufficient data"
    if len(P) >= max(12, n_clusters * 3):
        Xs = StandardScaler().fit_transform(X)
        best = None
        for k in range(3, min(6, len(P) // 4) + 1):
            km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(Xs)
            sil = float(silhouette_score(Xs, km.labels_))
            if best is None or sil > best[0]:
                best = (sil, k, km)
        sil, k, km = best  # type: ignore[misc]
        P["cluster_id"] = km.labels_
        cent = X.assign(cluster_id=km.labels_).groupby("cluster_id")[feats].mean()
        names = _name_clusters(cent)
        P["cluster"] = P["cluster_id"].map(names)
        summary = P.groupby("cluster").agg(
            plants=("plant_id", "count"), capacity_kwp=("capacity_kwp", "sum"),
            rpi_producing=("rpi_producing", "median"), availability_pct=("availability_pct", "median"),
            lost_kwh=("lost_kwh_vs_peer", "sum"),
        ).reset_index().round(3)
        cluster_info = {"k": int(k), "silhouette": round(sil, 3), "features": feats,
                        "summary": summary.to_dict(orient="records")}

    return {
        "status": "ok",
        "window_days": len(usable_dates),
        "window_start": min(usable_dates) if usable_dates else None,
        "window_end": max(usable_dates) if usable_dates else None,
        "plants": P.sort_values("rpi_producing"),
        "clusters": cluster_info,
        "n_drifting": int(P["drift_flag"].sum()),
        "n_outliers": int(P["outlier_flag"].sum()),
        "n_cusum_recent": int(P["cusum_recent"].sum()),
        "lost_kwh_total": round(float(P["lost_kwh_vs_peer"].sum()), 1),
    }


# ---------------------------------------------------------------------------
# 5. KPIs & platform benchmarking
# ---------------------------------------------------------------------------
def _box_stats(x: np.ndarray) -> List[float]:
    """Tukey box-plot [low whisker, Q1, median, Q3, high whisker]."""
    if len(x) == 0:
        return [0, 0, 0, 0, 0]
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    iqr = q3 - q1
    lo = float(np.min(x[x >= q1 - 1.5 * iqr])) if np.any(x >= q1 - 1.5 * iqr) else float(q1)
    hi = float(np.max(x[x <= q3 + 1.5 * iqr])) if np.any(x <= q3 + 1.5 * iqr) else float(q3)
    return [round(v, 3) for v in (lo, q1, med, q3, hi)]


@_cached
def fleet_kpis(month: str, source: Optional[str] = None) -> Dict[str, Any]:
    """Headline KPIs + per-platform breakdown for the selected month."""
    params: list = [month]
    sql = """
    SELECT p.plant_id, lower(p.source) AS source, p.capacity_kwp, p.capacity_effective, p.capacity_suspect,
           coalesce(p.operational_status, 'active') AS op,
           coalesce(m.kwh, 0) AS kwh, m.pr_pct, coalesce(m.anomaly_flag, 0) AS anomaly_flag, m.tier,
           m.yield_per_day
    FROM plants p
    LEFT JOIN monthly_generation m ON m.plant_id = p.plant_id AND m.month = ?
    WHERE 1=1
    """
    sql += _src_clause("p", source, params)
    df = db.query_df(sql, params, db="analytics")
    if df.empty:
        return {"month": month, "platforms": []}
    df["cap"] = _effective_capacity(df).fillna(0)
    df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce").fillna(0)
    df["pr_pct"] = pd.to_numeric(df["pr_pct"], errors="coerce")
    active = df[df["op"] != "decommissioned"]

    dparams: list = [f"{month}-01", f"{month}-31"]
    dsql = """
    SELECT lower(p.source) AS source, d.plant_id, d.date, d.kwh, d.status
    FROM daily_generation d JOIN plants p ON p.plant_id = d.plant_id
    WHERE d.date >= ? AND d.date <= ? AND coalesce(p.operational_status, 'active') != 'decommissioned'
    """
    dsql += _src_clause("p", source, dparams)
    dd = db.query_df(dsql, dparams, db="analytics")
    latest = pd.DataFrame()
    if not dd.empty:
        dd["kwh"] = pd.to_numeric(dd["kwh"], errors="coerce").fillna(0)
        latest = dd.sort_values("date").groupby("plant_id").tail(1).set_index("plant_id")

    def summarise(sub: pd.DataFrame, dsub: pd.DataFrame) -> Dict[str, Any]:
        act = sub[sub["op"] != "decommissioned"]
        gen = act[act["kwh"] > 1.0]
        prod = gen[gen["pr_pct"] > 0]
        theo = float((prod["kwh"] / (prod["pr_pct"] / 100.0)).sum())
        kwh = float(act["kwh"].sum())
        cap = float(act["cap"].sum())
        elapsed = _elapsed_days_in_month(month)
        rep = len(dsub)
        producing = int((dsub["kwh"] > PRODUCING_KWH).sum()) if rep else 0
        fault_ids = set()
        if not latest.empty:
            l = latest.loc[latest.index.intersection(act["plant_id"])]
            fault_ids = set(l[l["status"] == "fault"].index)
        return {
            "plants_total": int(len(sub)),
            "plants_active": int(len(act)),
            "plants_decom": int((sub["op"] == "decommissioned").sum()),
            "plants_generating": int(len(gen)),
            "plants_offline": int(len(act) - len(gen) - len(fault_ids & set(act.loc[act["kwh"] <= 1.0, "plant_id"]))),
            "plants_fault": int(len(fault_ids & set(act.loc[act["kwh"] <= 1.0, "plant_id"]))),
            "capacity_kwp": round(cap, 1),
            "kwh": round(kwh, 1),
            "revenue_inr": round(kwh * _tariff(), 0),
            "co2_t": round(kwh * CO2_KG_PER_KWH / 1000.0, 2),
            "pr_weighted_pct": round(float(prod["kwh"].sum()) / theo * 100.0, 1) if theo > 0 else None,
            "specific_yield": round(kwh / cap, 2) if cap > 0 else None,
            "cuf_pct": round(kwh / (cap * 24 * elapsed) * 100.0, 2) if cap > 0 else None,
            "availability_pct": round(producing / rep * 100.0, 1) if rep else None,
            "anomalies": int(act["anomaly_flag"].fillna(0).astype(int).sum()),
            "median_ypd": round(float(gen["yield_per_day"].median()), 2) if len(gen) and gen["yield_per_day"].notna().any() else None,
        }

    out = summarise(df, dd if not dd.empty else pd.DataFrame(columns=["kwh", "source"]))
    out["month"] = month
    out["elapsed_days"] = _elapsed_days_in_month(month)
    plats = []
    for key in platforms.platform_keys():
        sub = df[df["source"] == key]
        if sub.empty and source and source.lower() not in ("all", key):
            continue
        dsub = dd[dd["source"] == key] if not dd.empty else pd.DataFrame(columns=["kwh", "source"])
        item = summarise(sub, dsub)
        item.update({"key": key, "label": platforms.label(key), "color": platforms.color(key)})
        plats.append(item)
    out["platforms"] = plats
    return out


@_cached
def platform_benchmark(month: str) -> Dict[str, Any]:
    """Capacity-weighted PR and yield distribution per platform for a month."""
    m = load_monthly(month, month, None, include_decom=False)
    res: Dict[str, Any] = {"month": month, "platforms": []}
    if m.empty:
        return res
    m = m[m["kwh"] > 1.0]
    for key in platforms.platform_keys():
        sub = m[m["source"] == key]
        ypd = _safe_div(sub["kwh"], sub["cap"] * sub["days_elapsed"])
        ypd = ypd[~np.isnan(ypd)]
        prod = sub[sub["pr_pct"] > 0]
        theo = float((prod["kwh"] / (prod["pr_pct"] / 100.0)).sum())
        res["platforms"].append({
            "key": key, "label": platforms.label(key), "color": platforms.color(key),
            "plants": int(len(sub)), "capacity_kwp": round(float(sub["cap"].sum()), 1),
            "kwh": round(float(sub["kwh"].sum()), 1),
            "pr_weighted_pct": round(float(prod["kwh"].sum()) / theo * 100.0, 1) if theo > 0 else None,
            "pr_median_pct": round(float(prod["pr_pct"].median()), 1) if len(prod) else None,
            "ypd_box": _box_stats(np.asarray(ypd, dtype=float)),
            "ypd_median": round(float(np.median(ypd)), 3) if len(ypd) else None,
            "anomalies": int(pd.to_numeric(sub["anomaly_flag"], errors="coerce").fillna(0).sum()),
        })
    return res


@_cached
def capacity_bracket_analysis(month: str, source: Optional[str] = None) -> List[Dict[str, Any]]:
    m = load_monthly(month, month, source, include_decom=False)
    if m.empty:
        return []
    m = m[m["kwh"] > 1.0].copy()
    m["bracket"] = m["cap"].map(lambda c: get_capacity_bracket(c if pd.notna(c) else None))
    m["ypd"] = _safe_div(m["kwh"], m["cap"] * m["days_elapsed"])
    order = ["0-3 kWp", "3-5 kWp", "5-10 kWp", "10-50 kWp", "50+ kWp"]
    out = []
    for b in order:
        sub = m[m["bracket"] == b]
        if sub.empty:
            continue
        prod = sub[sub["pr_pct"] > 0]
        theo = float((prod["kwh"] / (prod["pr_pct"] / 100.0)).sum())
        out.append({
            "bracket": b, "plants": int(len(sub)), "capacity_kwp": round(float(sub["cap"].sum()), 1),
            "kwh": round(float(sub["kwh"].sum()), 1),
            "ypd_median": round(float(sub["ypd"].median()), 3),
            "pr_weighted_pct": round(float(prod["kwh"].sum()) / theo * 100.0, 1) if theo > 0 else None,
        })
    return out


@_cached
def scatter_capacity_yield(month: str, source: Optional[str] = None) -> Dict[str, List[List[Any]]]:
    """Per-platform scatter points [capacity_kwp, yield_per_day, plant_name, pr_pct]."""
    m = load_monthly(month, month, source, include_decom=False)
    out: Dict[str, List[List[Any]]] = {}
    if m.empty:
        return out
    m = m[m["kwh"] > 1.0].copy()
    m["ypd"] = _safe_div(m["kwh"], m["cap"] * m["days_elapsed"])
    for key, g in m.groupby("source"):
        out[str(key)] = [
            [round(float(r.cap), 2), round(float(r.ypd), 3), str(r.plant_name), _r(r.pr_pct, 1)]
            for r in g.itertuples() if pd.notna(r.cap) and pd.notna(r.ypd)
        ]
    return out


def model_card() -> List[Dict[str, str]]:
    """Human-readable catalogue of every model / formula used in the dashboard."""
    return [
        {"name": "Performance Ratio (PR)", "kind": "IEC 61724-1",
         "formula": "PR = Yf / Yr = (E / P₀) / (H_GHI / 1 kW·m⁻²)",
         "notes": "Group PR is capacity-weighted: ΣE / Σ(P₀·Yr). Ratios are never averaged."},
        {"name": "Expected energy", "kind": "Physics baseline",
         "formula": "E_exp = P₀ · GHI · days · 0.75",
         "notes": "NASA POWER monthly GHI per plant location; 75 % benchmark PR."},
        {"name": "Capacity Utilisation Factor", "kind": "MNRE / CEA",
         "formula": "CUF = E / (P₀ · 24 · days)", "notes": "Elapsed days only for the running month."},
        {"name": "Availability", "kind": "IEEE 762 style",
         "formula": "A = producing days / reported days", "notes": "Missing telemetry days are excluded, not counted as down."},
        {"name": "Relative Performance Index", "kind": "Peer-normalised",
         "formula": "RPI = Yf(plant,d) / median Yf(producing fleet, d)",
         "notes": "Cancels weather without pyranometers; gap days excluded."},
        {"name": "Drift detection", "kind": "OLS + CUSUM",
         "formula": "slope(RPI ~ t)·30, p < 0.05; lower CUSUM k=0.5σ, h=4σ",
         "notes": "Flags soiling / degradation / partial string loss."},
        {"name": "Peer outliers", "kind": "Robust statistics",
         "formula": "z = (x − median) / (1.4826·MAD) ≤ −2.5", "notes": "Within capacity-bracket peer groups."},
        {"name": "Anomaly detection", "kind": "Isolation Forest",
         "formula": "features: yield/day, PR, capacity, sin/cos(month)",
         "notes": "Underperforming outliers only (below monthly median)."},
        {"name": "Behaviour clusters", "kind": "K-Means",
         "formula": "k ∈ [3,6] chosen by silhouette; features standardised",
         "notes": "RPI (producing), availability, RPI CV, RPI slope."},
        {"name": "7-day forecast", "kind": "ETS(A,Ad,N)",
         "formula": "ŷ = ℓ + Σφⁱ·b; σ_h² = σ²(1+Σc_j²)",
         "notes": "Grid-searched α, β*, φ; rolling-origin backtest vs naive & 7-day mean."},
        {"name": "Month-end projection", "kind": "Block bootstrap",
         "formula": "E_month = E_to-date + Σ resampled clean days (block = 3)",
         "notes": "P10/P50/P90 and probability of meeting the expected baseline."},
        {"name": "Data quality", "kind": "Hampel + coverage",
         "formula": "|x − med₇| > 3·1.4826·MAD₇; coverage < 50 % of median ⇒ gap",
         "notes": "SY_IMPOSSIBLE / STUCK_VALUE plant-days excluded from energy."},
    ]
