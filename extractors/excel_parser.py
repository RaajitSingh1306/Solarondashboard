"""
solaron/extractors/excel_parser.py

Parses monthly SolarOn Excel reports (.xls, .xlsx) into structured plant records
and ingests them into the Solaron analytics database.
"""

import calendar
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from extractors.base import BaseExtractor
import db

logger = logging.getLogger(__name__)

def _find_col(columns: List[str], *keywords: str) -> Optional[str]:
    """Return the first column name whose lowercase form contains ALL given keywords."""
    for col in columns:
        col_lower = col.lower()
        if all(kw in col_lower for kw in keywords):
            return col
    return None

def _safe_float(val: Any) -> float:
    try:
        f = float(val)
        return 0.0 if np.isnan(f) else f
    except (ValueError, TypeError):
        return 0.0

def _extract_month_year(filepath: str, df_raw: Optional[pd.DataFrame] = None) -> Tuple[str, str]:
    """
    Extract YYYY-MM and human readable month name from filename or raw rows.
    E.g. 'SolarOn - 2026-07.xls' -> ('2026-07', 'July 2026')
    """
    basename = os.path.basename(filepath)
    m = re.search(r"(\d{4})-(\d{2})", basename)
    if m:
        year_str = m.group(1)
        month_num = int(m.group(2))
        if 1 <= month_num <= 12:
            return f"{year_str}-{month_num:02d}", f"{calendar.month_name[month_num]} {year_str}"

    if df_raw is not None and not df_raw.empty:
        for row_idx in range(min(10, len(df_raw))):
            for val in df_raw.iloc[row_idx].values:
                if pd.isna(val):
                    continue
                m2 = re.search(r"(\d{4})-(\d{2})", str(val))
                if m2:
                    year_str = m2.group(1)
                    month_num = int(m2.group(2))
                    if 1 <= month_num <= 12:
                        return f"{year_str}-{month_num:02d}", f"{calendar.month_name[month_num]} {year_str}"

    now = pd.Timestamp.now()
    return f"{now.year}-{now.month:02d}", f"{calendar.month_name[now.month]} {now.year}"

def parse_and_ingest_excel(filepath: str) -> Dict[str, Any]:
    """
    Parse an uploaded SolarOn Excel report (.xls, .xlsx) and ingest records into Solaron DB.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Excel file not found: {filepath}")

    # Read raw table first to detect month and header row
    engine = "openpyxl" if path.suffix.lower() == ".xlsx" else "xlrd"
    try:
        df_raw = pd.read_excel(filepath, sheet_name=0, header=None, engine=engine)
    except Exception as e:
        # Fallback without engine specification
        df_raw = pd.read_excel(filepath, sheet_name=0, header=None)

    month_str, month_label = _extract_month_year(filepath, df_raw)

    # Detect header row index
    header_idx = 0
    for idx, row in df_raw.iterrows():
        row_str = " ".join([str(v).lower() for v in row.values if pd.notna(v)])
        if "plant" in row_str and ("energy" in row_str or "power" in row_str or "income" in row_str):
            header_idx = idx
            break

    # Re-read with proper header row
    df = pd.read_excel(filepath, sheet_name=0, header=header_idx)
    df.columns = [str(c).strip() for c in df.columns]
    cols = list(df.columns)

    plant_col = _find_col(cols, "plant", "name") or _find_col(cols, "plant") or cols[0]
    m_energy_col = _find_col(cols, "energy this month") or _find_col(cols, "energy", "month") or _find_col(cols, "this month")
    m_income_col = _find_col(cols, "income this month") or _find_col(cols, "income", "month") or _find_col(cols, "savings")
    cap_col = _find_col(cols, "capacity") or _find_col(cols, "peak power") or _find_col(cols, "kwp")
    status_col = _find_col(cols, "status")

    monthly_rows = []
    plants_updated = 0

    for _, row in df.iterrows():
        p_name = str(row.get(plant_col, "")).strip()
        if not p_name or p_name.lower() in ("total", "average", "nan", "summary"):
            continue

        pid = BaseExtractor.plant_id("excel", p_name)
        kwh = _safe_float(row.get(m_energy_col, 0.0))
        income = _safe_float(row.get(m_income_col, 0.0))
        cap = _safe_float(row.get(cap_col, 0.0))
        if cap <= 0 and kwh > 0:
            cap = round(max(kwh / 90.0, 3.0), 1)

        sy = round(kwh / cap, 2) if cap > 0 else 0.0
        tier = "Best" if sy >= 100 else "Good" if sy >= 75 else "Could Be Better" if sy >= 45 else "Critical" if sy > 0 else "Offline"

        # Check existing plant in DB
        existing = db.query_df("SELECT plant_id, capacity_kwp FROM plants WHERE plant_name = ?", [p_name], db="analytics")
        if not existing.empty:
            pid = str(existing.iloc[0]["plant_id"])
            if cap <= 0 and existing.iloc[0]["capacity_kwp"]:
                cap = float(existing.iloc[0]["capacity_kwp"])
                sy = round(kwh / cap, 2) if cap > 0 else sy

        monthly_rows.append({
            "plant_id": pid,
            "month": month_str,
            "kwh": kwh,
            "revenue_inr": income if income > 0 else round(kwh * 14.0, 2),
            "specific_yield": sy,
            "pr_pct": 75.0,
            "tier": tier,
            "percentile": 50.0,
        })
        plants_updated += 1

    if monthly_rows:
        db.upsert_monthly(monthly_rows)

    return {
        "status": "success",
        "month": month_str,
        "month_label": month_label,
        "plants_ingested": plants_updated,
        "file": str(path.name),
    }
