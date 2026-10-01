"""
Solaron Pandera Data Contracts (Phase 2, Task 7).

Strict schema validation and data contracts enforcing physical boundaries,
type invariants, and solar engineering physical limits at ingest time.
"""

import datetime
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema
try:
    from core import data_quality
except ImportError:
    import data_quality

TODAY_STR = datetime.date.today().isoformat()

# 1. Plants Metadata Schema Contract
PlantMetadataSchema = DataFrameSchema(
    columns={
        "plant_id": Column(pa.String, Check(lambda s: s.str.len() > 0), nullable=False),
        "source": Column(pa.String, Check.isin(["growatt", "isolarcloud", "suryalog", "unknown", "test"]), nullable=False),
        "plant_name": Column(pa.String, nullable=True),
        "capacity_kwp": Column(pa.Float, Check.in_range(0.1, 10000.0), nullable=True),
        "latitude": Column(pa.Float, Check.in_range(-90.0, 90.0), nullable=True),
        "longitude": Column(pa.Float, Check.in_range(-180.0, 180.0), nullable=True),
        "city": Column(pa.String, nullable=True),
        "operational_status": Column(
            pa.String, Check.isin(["active", "offline", "decommissioned"]), nullable=True
        ),
        "geocode_level": Column(
            pa.String,
            Check.isin(["exact", "pincode_centroid", "city_centroid", "state_default", "unresolved"]),
            nullable=True,
        ),
    },
    coerce=True,
    strict=False,
)

# 2. Daily Generation Telemetry Schema Contract
DailyGenerationSchema = DataFrameSchema(
    columns={
        "plant_id": Column(pa.String, Check(lambda s: s.str.len() > 0), nullable=False),
        "date": Column(pa.String, Check(lambda s: s.str.match(r"^\d{4}-\d{2}-\d{2}$")), nullable=False),
        "kwh": Column(pa.Float, Check.greater_than_or_equal_to(0.0), nullable=False),
        "revenue_inr": Column(pa.Float, Check.greater_than_or_equal_to(0.0), nullable=True),
        "specific_yield": Column(
            pa.Float, Check.in_range(0.0, data_quality.MAX_DAILY_YIELD_KWH_KWP), nullable=True
        ),
        "yield_per_day": Column(
            pa.Float, Check.in_range(0.0, data_quality.MAX_DAILY_YIELD_KWH_KWP), nullable=True
        ),
        "status": Column(pa.String, Check.isin(["active", "offline", "fault", "decommissioned"]), nullable=True),
        "quality_flags": Column(pa.String, nullable=True),
    },
    coerce=True,
    strict=False,
)

# 3. Monthly Generation Telemetry Schema Contract
MonthlyGenerationSchema = DataFrameSchema(
    columns={
        "plant_id": Column(pa.String, Check(lambda s: s.str.len() > 0), nullable=False),
        "month": Column(pa.String, Check(lambda s: s.str.match(r"^\d{4}-\d{2}$")), nullable=False),
        "kwh": Column(pa.Float, Check.greater_than_or_equal_to(0.0), nullable=False),
        "revenue_inr": Column(pa.Float, Check.greater_than_or_equal_to(0.0), nullable=True),
        "specific_yield": Column(
            pa.Float, Check.in_range(0.0, data_quality.MAX_MONTHLY_YIELD_KWH_KWP), nullable=True
        ),
        "yield_per_day": Column(
            pa.Float, Check.in_range(0.0, data_quality.MAX_DAILY_YIELD_KWH_KWP), nullable=True
        ),
        "pr_pct": Column(pa.Float, Check.in_range(0.0, 150.0), nullable=True),
    },
    coerce=True,
    strict=False,
)

# 4. Inverter Snapshots Schema Contract
InverterSnapshotSchema = DataFrameSchema(
    columns={
        "plant_id": Column(pa.String, nullable=False),
        "inverter_sn": Column(pa.String, nullable=False),
        "snapshot_ts": Column(pa.String, nullable=False),
        "ac_power_w": Column(pa.Float, Check.greater_than_or_equal_to(0.0), nullable=True),
        "dc_power_w": Column(pa.Float, Check.greater_than_or_equal_to(0.0), nullable=True),
        "temperature_c": Column(pa.Float, Check.in_range(15.0, 85.0), nullable=True),
        "e_today_kwh": Column(pa.Float, Check.greater_than_or_equal_to(0.0), nullable=True),
        "status": Column(pa.String, nullable=True),
    },
    coerce=True,
    strict=False,
)


def validate_dataframe(schema: DataFrameSchema, df: pd.DataFrame) -> Tuple[bool, Optional[pd.DataFrame], List[str]]:
    """
    Validate dataframe against a pandera schema.
    Returns (is_valid, validated_df, list_of_error_messages).
    """
    if df.empty:
        return True, df, []
    try:
        validated = schema.validate(df, lazy=True)
        return True, validated, []
    except pa.errors.SchemaErrors as err:
        errors = [f"{e['column']}: {e['check']}" for e in err.failure_cases.to_dict(orient="records")]
        return False, None, errors
    except Exception as e:
        return False, None, [str(e)]


def validate_plants_df(df: pd.DataFrame) -> Tuple[bool, Optional[pd.DataFrame], List[str]]:
    return validate_dataframe(PlantMetadataSchema, df)


def validate_daily_df(df: pd.DataFrame) -> Tuple[bool, Optional[pd.DataFrame], List[str]]:
    return validate_dataframe(DailyGenerationSchema, df)


def validate_monthly_df(df: pd.DataFrame) -> Tuple[bool, Optional[pd.DataFrame], List[str]]:
    return validate_dataframe(MonthlyGenerationSchema, df)


def validate_snapshots_df(df: pd.DataFrame) -> Tuple[bool, Optional[pd.DataFrame], List[str]]:
    return validate_dataframe(InverterSnapshotSchema, df)
