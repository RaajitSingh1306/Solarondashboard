import datetime
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd
from config import settings

def _ensure_dir(path: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

class SafeRow:
    """Row wrapper that behaves like sqlite3.Row for iteration and indexing,
    while supporting .get(), dict conversion, and dictionary key access."""
    __slots__ = ('_cursor', '_row', '_fields', '_dict')
    def __init__(self, cursor, row):
        self._cursor = cursor
        self._row = row
        self._fields = [c[0] for c in cursor.description]
        self._dict = None

    def _get_dict(self):
        if self._dict is None:
            self._dict = dict(zip(self._fields, self._row))
        return self._dict

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._row[key]
        return self._get_dict()[key]

    def get(self, key, default=None):
        return self._get_dict().get(key, default)

    def keys(self):
        return self._fields

    def values(self):
        return self._row

    def items(self):
        return list(zip(self._fields, self._row))

    def __iter__(self):
        return iter(self._row)

    def __len__(self):
        return len(self._row)

    def __repr__(self):
        return repr(self._get_dict())

@contextmanager
def analytics_conn():
    _ensure_dir(settings.resolved_solar_analytics_db_path)
    conn = sqlite3.connect(settings.resolved_solar_analytics_db_path)
    conn.row_factory = lambda c, r: SafeRow(c, r)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def crm_conn():
    _ensure_dir(settings.resolved_crm_db_path)
    conn = sqlite3.connect(settings.resolved_crm_db_path)
    conn.row_factory = lambda c, r: SafeRow(c, r)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_conn(db: str = "analytics"):
    if db == "crm":
        return crm_conn()
    return analytics_conn()

get_connection = analytics_conn

def get_plants(source: Optional[str] = None, include_decommissioned: bool = False) -> List[Dict[str, Any]]:
    sql = "SELECT plant_id, source, plant_name, capacity_kwp, capacity_effective, capacity_suspect, latitude, longitude, city, install_date, inverter_model, panel_model, operational_status, geocode_level FROM plants WHERE 1=1"
    params: List[Any] = []
    if not include_decommissioned:
        sql += " AND (operational_status IS NULL OR operational_status != 'decommissioned')"
    if source and source.lower() != "all":
        sql += " AND lower(source) = ?"
        params.append(source.lower())
    sql += " ORDER BY plant_name ASC"
    df = query_df(sql, params, db="analytics")
    if df.empty:
        return []
    return df.to_dict(orient="records")

def query_df(sql: str, params: Optional[Union[tuple, list, dict]] = None, db: str = "analytics") -> pd.DataFrame:
    with get_conn(db) as conn:
        try:
            df = pd.read_sql_query(sql, conn, params=params or [])
            if not df.empty:
                return df.astype(object).where(pd.notnull(df), None)
            return df
        except Exception:
            return pd.DataFrame()

def execute(sql: str, params: Optional[Union[tuple, list, dict]] = None, db: str = "analytics") -> int:
    with get_conn(db) as conn:
        cur = conn.cursor()
        cur.execute(sql, params or [])
        return cur.rowcount

def executemany(sql: str, rows: List[Union[tuple, list, dict]], db: str = "analytics") -> int:
    if not rows:
        return 0
    with get_conn(db) as conn:
        cur = conn.cursor()
        cur.executemany(sql, rows)
        return cur.rowcount

def upsert_plant(row: Dict[str, Any]) -> None:
    try:
        from core import data_quality
    except ImportError:
        import data_quality
    row_copy = dict(row)
    if data_quality.is_decommissioned(row_copy.get("plant_id", "")) or row_copy.get("operational_status") == "decommissioned":
        row_copy["operational_status"] = "decommissioned"
    else:
        row_copy.setdefault("operational_status", "active")
    row_copy.setdefault("last_log_time", None)
    row_copy.setdefault("total_energy_kwh", None)
    row_copy.setdefault("geocode_level", None)
    row_copy.setdefault("capacity_effective", None)
    row_copy.setdefault("capacity_suspect", 0)
    for col in ("latitude", "longitude", "city", "install_date", "inverter_model", "panel_model"):
        row_copy.setdefault(col, None)
    sql = """
    INSERT INTO plants (
        plant_id, source, plant_name, capacity_kwp, capacity_effective, capacity_suspect, latitude, longitude,
        city, install_date, inverter_model, panel_model, operational_status, geocode_level, last_log_time, total_energy_kwh, updated_at
    ) VALUES (
        :plant_id, :source, :plant_name, :capacity_kwp, :capacity_effective, :capacity_suspect, :latitude, :longitude,
        :city, :install_date, :inverter_model, :panel_model, :operational_status, :geocode_level, :last_log_time, :total_energy_kwh, CURRENT_TIMESTAMP
    )
    ON CONFLICT(plant_id) DO UPDATE SET
        source = excluded.source,
        plant_name = excluded.plant_name,
        capacity_kwp = excluded.capacity_kwp,
        capacity_effective = coalesce(excluded.capacity_effective, plants.capacity_effective),
        capacity_suspect = coalesce(excluded.capacity_suspect, plants.capacity_suspect),
        latitude = coalesce(excluded.latitude, plants.latitude),
        longitude = coalesce(excluded.longitude, plants.longitude),
        city = coalesce(excluded.city, plants.city),
        install_date = coalesce(excluded.install_date, plants.install_date),
        inverter_model = coalesce(excluded.inverter_model, plants.inverter_model),
        panel_model = coalesce(excluded.panel_model, plants.panel_model),
        operational_status = CASE WHEN plants.operational_status = 'decommissioned' OR excluded.operational_status = 'decommissioned' THEN 'decommissioned' ELSE coalesce(excluded.operational_status, plants.operational_status) END,
        geocode_level = coalesce(excluded.geocode_level, plants.geocode_level),
        last_log_time = coalesce(nullif(excluded.last_log_time, ''), plants.last_log_time),
        total_energy_kwh = coalesce(excluded.total_energy_kwh, plants.total_energy_kwh),
        updated_at = CURRENT_TIMESTAMP;
    """
    execute(sql, row_copy, db="analytics")

def upsert_daily(rows: List[Dict[str, Any]]) -> int:
    import datetime
    if not rows:
        return 0
    today_str = datetime.date.today().isoformat()
    rows = [r for r in rows if str(r.get("date", "")) <= today_str]
    if not rows:
        return 0
    for r in rows:
        r.setdefault("revenue_inr", None)
        r.setdefault("specific_yield", None)
        r.setdefault("yield_per_day", r.get("specific_yield"))
        r.setdefault("live_power_kw", None)
        r.setdefault("status", "active")
        r.setdefault("last_log_time", None)
        r.setdefault("quality_flags", None)
        r.setdefault("source_type", "portal")
    sql = """
    INSERT INTO daily_generation (
        plant_id, date, kwh, revenue_inr, specific_yield, yield_per_day, live_power_kw, status, quality_flags, last_log_time, source_type
    ) VALUES (
        :plant_id, :date, :kwh, :revenue_inr, :specific_yield, :yield_per_day, :live_power_kw, :status, :quality_flags, :last_log_time, :source_type
    )
    ON CONFLICT(plant_id, date) DO UPDATE SET
        kwh = CASE 
            WHEN excluded.last_log_time IS NOT NULL AND trim(excluded.last_log_time) != '' THEN excluded.kwh
            WHEN daily_generation.last_log_time IS NULL OR trim(daily_generation.last_log_time) = '' THEN excluded.kwh
            ELSE daily_generation.kwh 
        END,
        revenue_inr = CASE 
            WHEN excluded.last_log_time IS NOT NULL AND trim(excluded.last_log_time) != '' THEN excluded.revenue_inr
            WHEN daily_generation.last_log_time IS NULL OR trim(daily_generation.last_log_time) = '' THEN excluded.revenue_inr
            ELSE daily_generation.revenue_inr 
        END,
        specific_yield = CASE 
            WHEN excluded.last_log_time IS NOT NULL AND trim(excluded.last_log_time) != '' THEN excluded.specific_yield
            WHEN daily_generation.last_log_time IS NULL OR trim(daily_generation.last_log_time) = '' THEN excluded.specific_yield
            ELSE daily_generation.specific_yield 
        END,
        yield_per_day = coalesce(excluded.yield_per_day, daily_generation.yield_per_day),
        live_power_kw = coalesce(excluded.live_power_kw, daily_generation.live_power_kw),
        status = excluded.status,
        quality_flags = coalesce(excluded.quality_flags, daily_generation.quality_flags),
        last_log_time = coalesce(nullif(excluded.last_log_time, ''), daily_generation.last_log_time),
        source_type = coalesce(excluded.source_type, daily_generation.source_type);
    """
    res = executemany(sql, rows, db="analytics")
    clear_available_months_cache()
    return res

def upsert_monthly(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO monthly_generation (
        plant_id, month, kwh, revenue_inr, specific_yield, yield_per_day, pr_pct, tier, percentile, anomaly_score, anomaly_flag, source_type
    ) VALUES (
        :plant_id, :month, :kwh, :revenue_inr, :specific_yield, :yield_per_day, :pr_pct, :tier, :percentile, :anomaly_score, :anomaly_flag, :source_type
    )
    ON CONFLICT(plant_id, month) DO UPDATE SET
        kwh = excluded.kwh,
        revenue_inr = excluded.revenue_inr,
        specific_yield = excluded.specific_yield,
        yield_per_day = excluded.yield_per_day,
        pr_pct = coalesce(excluded.pr_pct, monthly_generation.pr_pct),
        tier = coalesce(excluded.tier, monthly_generation.tier),
        percentile = coalesce(excluded.percentile, monthly_generation.percentile),
        anomaly_score = coalesce(excluded.anomaly_score, monthly_generation.anomaly_score),
        anomaly_flag = coalesce(excluded.anomaly_flag, monthly_generation.anomaly_flag),
        source_type = coalesce(excluded.source_type, monthly_generation.source_type);
    """
    # ensure default keys exist
    for r in rows:
        r.setdefault("tier", None)
        r.setdefault("percentile", None)
        r.setdefault("pr_pct", None)
        r.setdefault("revenue_inr", None)
        r.setdefault("specific_yield", None)
        r.setdefault("yield_per_day", None)
        r.setdefault("anomaly_score", None)
        r.setdefault("anomaly_flag", 0)
        r.setdefault("source_type", "portal")
    res = executemany(sql, rows, db="analytics")
    clear_available_months_cache()
    return res

def upsert_snapshots(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO inverter_snapshots (
        plant_id, inverter_sn, snapshot_ts, ac_power_w, dc_power_w,
        temperature_c, e_today_kwh, fault_code, status
    ) VALUES (
        :plant_id, :inverter_sn, :snapshot_ts, :ac_power_w, :dc_power_w,
        :temperature_c, :e_today_kwh, :fault_code, :status
    )
    ON CONFLICT(plant_id, inverter_sn, snapshot_ts) DO UPDATE SET
        ac_power_w = excluded.ac_power_w,
        dc_power_w = excluded.dc_power_w,
        temperature_c = excluded.temperature_c,
        e_today_kwh = excluded.e_today_kwh,
        fault_code = excluded.fault_code,
        status = excluded.status;
    """
    return executemany(sql, rows, db="analytics")

def upsert_expected_generation(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO expected_generation (
        plant_id, month, expected_kwh, ghi_kwh_m2_day, latitude, longitude, calculated_at
    ) VALUES (
        :plant_id, :month, :expected_kwh, :ghi_kwh_m2_day, :latitude, :longitude, CURRENT_TIMESTAMP
    )
    ON CONFLICT(plant_id, month) DO UPDATE SET
        expected_kwh = excluded.expected_kwh,
        ghi_kwh_m2_day = excluded.ghi_kwh_m2_day,
        latitude = coalesce(excluded.latitude, expected_generation.latitude),
        longitude = coalesce(excluded.longitude, expected_generation.longitude),
        calculated_at = CURRENT_TIMESTAMP;
    """
    return executemany(sql, rows, db="analytics")

def upsert_loss_analysis(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        return 0
    sql = """
    INSERT INTO loss_analysis (
        plant_id, month, expected_kwh, actual_kwh, shortfall_kwh,
        comm_loss_kwh, shutdown_loss_kwh, weather_loss_kwh,
        soiling_loss_kwh, shading_loss_kwh, unknown_loss_kwh,
        performance_ratio, realization_rate_pct, calculated_at
    ) VALUES (
        :plant_id, :month, :expected_kwh, :actual_kwh, :shortfall_kwh,
        :comm_loss_kwh, :shutdown_loss_kwh, :weather_loss_kwh,
        :soiling_loss_kwh, :shading_loss_kwh, :unknown_loss_kwh,
        :performance_ratio, :realization_rate_pct, CURRENT_TIMESTAMP
    )
    ON CONFLICT(plant_id, month) DO UPDATE SET
        expected_kwh = excluded.expected_kwh,
        actual_kwh = excluded.actual_kwh,
        shortfall_kwh = excluded.shortfall_kwh,
        comm_loss_kwh = excluded.comm_loss_kwh,
        shutdown_loss_kwh = excluded.shutdown_loss_kwh,
        weather_loss_kwh = excluded.weather_loss_kwh,
        soiling_loss_kwh = excluded.soiling_loss_kwh,
        shading_loss_kwh = excluded.shading_loss_kwh,
        unknown_loss_kwh = excluded.unknown_loss_kwh,
        performance_ratio = excluded.performance_ratio,
        realization_rate_pct = excluded.realization_rate_pct,
        calculated_at = CURRENT_TIMESTAMP;
    """
    return executemany(sql, rows, db="analytics")

_cached_available_months: Optional[List[str]] = None

def clear_available_months_cache() -> None:
    global _cached_available_months
    _cached_available_months = None

def get_available_months(force_refresh: bool = False) -> List[str]:
    global _cached_available_months
    if _cached_available_months and not force_refresh:
        return list(_cached_available_months)
    sql = """
    SELECT DISTINCT month FROM monthly_generation 
    WHERE month IS NOT NULL AND month != ''
    UNION
    SELECT DISTINCT substr(date, 1, 7) as month FROM daily_generation
    WHERE date IS NOT NULL AND length(date) >= 7
    ORDER BY month DESC;
    """
    df = query_df(sql, db="analytics")
    if not df.empty and len(df) > 0:
        months = [str(m) for m in df["month"].dropna().tolist() if re.match(r"^\d{4}-\d{2}$", str(m))]
        if months:
            res = sorted(list(set(months)), reverse=True)
            _cached_available_months = res
            return list(res)

    df_d = query_df("SELECT DISTINCT substr(date, 1, 7) as month FROM daily_generation ORDER BY month DESC", db="analytics")
    if not df_d.empty:
        months = [str(m) for m in df_d["month"].dropna().tolist() if re.match(r"^\d{4}-\d{2}$", str(m))]
        if months:
            res = sorted(list(set(months)), reverse=True)
            _cached_available_months = res
            return list(res)

    res = ["2026-09", "2026-08", "2026-07"]
    _cached_available_months = res
    return list(res)

def get_cache_metadata() -> Dict[str, Any]:
    """Returns latest dates, record counts, and sync timestamps for cached data across analytics db."""
    res = {
        "latest_daily_date": "N/A",
        "latest_month": "N/A",
        "last_sync_timestamp": "N/A",
        "plants_on_latest_day": 0,
        "total_daily_records": 0,
        "total_monthly_records": 0,
    }
    try:
        with analytics_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(date), COUNT(*) FROM daily_generation")
            row = cur.fetchone()
            if row and row[0]:
                res["latest_daily_date"] = str(row[0])
                res["total_daily_records"] = int(row[1] or 0)

            cur.execute("SELECT MAX(month), COUNT(*) FROM monthly_generation")
            row = cur.fetchone()
            if row and row[0]:
                res["latest_month"] = str(row[0])
                res["total_monthly_records"] = int(row[1] or 0)

            cur.execute("SELECT MAX(updated_at) FROM plants")
            row = cur.fetchone()
            if row and row[0]:
                res["last_sync_timestamp"] = str(row[0])

            if res["latest_daily_date"] != "N/A":
                cur.execute("SELECT COUNT(DISTINCT plant_id) FROM daily_generation WHERE date = ?", [res["latest_daily_date"]])
                row = cur.fetchone()
                if row and row[0]:
                    res["plants_on_latest_day"] = int(row[0])
    except Exception:
        pass
    return res


def log_anomaly_feedback(
    plant_id: str,
    date_or_month: str,
    flag_type: str,
    technician_label: str,
    notes: Optional[str] = None,
    logged_by: str = "operator",
) -> int:
    """Log ground-truth feedback / label on an algorithmic anomaly flag."""
    init_db()
    sql = """
    INSERT INTO anomaly_feedback (plant_id, date_or_month, flag_type, technician_label, notes, logged_by)
    VALUES (?, ?, ?, ?, ?, ?);
    """
    with analytics_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, [plant_id, date_or_month, flag_type, technician_label, notes, logged_by])
        return cur.lastrowid or 0


def get_anomaly_feedback(plant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve logged anomaly labels and ground-truth outcomes."""
    init_db()
    sql = "SELECT id, plant_id, date_or_month, flag_type, technician_label, notes, logged_by, created_at FROM anomaly_feedback"
    params = []
    if plant_id:
        sql += " WHERE plant_id = ?"
        params.append(plant_id)
    sql += " ORDER BY created_at DESC;"
    df = query_df(sql, params, db="analytics")
    if df.empty:
        return []
    return df.to_dict(orient="records")

def init_db() -> None:
    with analytics_conn() as conn:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS plants (
            plant_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            plant_name TEXT NOT NULL,
            capacity_kwp REAL,
            capacity_effective REAL,
            capacity_suspect INTEGER DEFAULT 0,
            latitude REAL,
            longitude REAL,
            city TEXT,
            install_date TEXT,
            inverter_model TEXT,
            panel_model TEXT,
            operational_status TEXT DEFAULT 'active',
            geocode_level TEXT,
            last_log_time TEXT,
            total_energy_kwh REAL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS daily_generation (
            plant_id TEXT NOT NULL,
            date TEXT NOT NULL,
            kwh REAL,
            revenue_inr REAL,
            specific_yield REAL,
            yield_per_day REAL,
            live_power_kw REAL,
            status TEXT,
            quality_flags TEXT,
            last_log_time TEXT,
            source_type TEXT DEFAULT 'portal',
            PRIMARY KEY (plant_id, date),
            FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
        );

        CREATE TABLE IF NOT EXISTS monthly_generation (
            plant_id TEXT NOT NULL,
            month TEXT NOT NULL,
            kwh REAL,
            revenue_inr REAL,
            specific_yield REAL,
            yield_per_day REAL,
            pr_pct REAL,
            tier TEXT,
            percentile REAL,
            anomaly_score REAL,
            anomaly_flag INTEGER DEFAULT 0,
            source_type TEXT DEFAULT 'portal',
            PRIMARY KEY (plant_id, month),
            FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
        );

        CREATE TABLE IF NOT EXISTS expected_generation (
            plant_id TEXT NOT NULL,
            month TEXT NOT NULL,
            expected_kwh REAL,
            ghi_kwh_m2_day REAL,
            latitude REAL,
            longitude REAL,
            calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (plant_id, month),
            FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
        );

        CREATE TABLE IF NOT EXISTS loss_analysis (
            plant_id TEXT NOT NULL,
            month TEXT NOT NULL,
            expected_kwh REAL,
            actual_kwh REAL,
            shortfall_kwh REAL,
            comm_loss_kwh REAL,
            shutdown_loss_kwh REAL,
            weather_loss_kwh REAL,
            soiling_loss_kwh REAL,
            shading_loss_kwh REAL,
            unknown_loss_kwh REAL,
            performance_ratio REAL,
            realization_rate_pct REAL,
            calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (plant_id, month),
            FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
        );

        CREATE TABLE IF NOT EXISTS inverter_snapshots (
            plant_id TEXT NOT NULL,
            inverter_sn TEXT NOT NULL,
            snapshot_ts TEXT NOT NULL,
            ac_power_w REAL,
            dc_power_w REAL,
            temperature_c REAL,
            e_today_kwh REAL,
            fault_code TEXT,
            status TEXT,
            PRIMARY KEY (plant_id, inverter_sn, snapshot_ts),
            FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
        );

        CREATE TABLE IF NOT EXISTS anomaly_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plant_id TEXT NOT NULL,
            date_or_month TEXT NOT NULL,
            flag_type TEXT NOT NULL,
            technician_label TEXT NOT NULL,
            notes TEXT,
            logged_by TEXT DEFAULT 'operator',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (plant_id) REFERENCES plants(plant_id)
        );

        CREATE INDEX IF NOT EXISTS idx_feedback_plant ON anomaly_feedback(plant_id);

        CREATE INDEX IF NOT EXISTS idx_plants_source ON plants(source);
        CREATE INDEX IF NOT EXISTS idx_plants_op_status ON plants(operational_status);
        CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_generation(date);
        CREATE INDEX IF NOT EXISTS idx_daily_status ON daily_generation(status);
        CREATE INDEX IF NOT EXISTS idx_daily_plant_date ON daily_generation(plant_id, date);
        CREATE INDEX IF NOT EXISTS idx_daily_plant_status ON daily_generation(plant_id, status);
        CREATE INDEX IF NOT EXISTS idx_monthly_month ON monthly_generation(month);
        CREATE INDEX IF NOT EXISTS idx_monthly_plant_month ON monthly_generation(plant_id, month);
        CREATE INDEX IF NOT EXISTS idx_expected_month ON expected_generation(month);
        CREATE INDEX IF NOT EXISTS idx_loss_month ON loss_analysis(month);
        CREATE INDEX IF NOT EXISTS idx_loss_plant_month ON loss_analysis(plant_id, month);
        CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON inverter_snapshots(snapshot_ts);
        CREATE INDEX IF NOT EXISTS idx_snapshots_plant_ts ON inverter_snapshots(plant_id, snapshot_ts);
        """)

        # Safe column migrations for existing databases
        for tbl, col, ctype in [
            ("plants", "operational_status", "TEXT DEFAULT 'active'"),
            ("plants", "last_log_time", "TEXT"),
            ("plants", "total_energy_kwh", "REAL"),
            ("plants", "geocode_level", "TEXT"),
            ("plants", "capacity_effective", "REAL"),
            ("plants", "capacity_suspect", "INTEGER DEFAULT 0"),
            ("daily_generation", "yield_per_day", "REAL"),
            ("daily_generation", "last_log_time", "TEXT"),
            ("daily_generation", "quality_flags", "TEXT"),
            ("daily_generation", "source_type", "TEXT DEFAULT 'portal'"),
            ("monthly_generation", "yield_per_day", "REAL"),
            ("monthly_generation", "anomaly_score", "REAL"),
            ("monthly_generation", "anomaly_flag", "INTEGER DEFAULT 0"),
            ("monthly_generation", "source_type", "TEXT DEFAULT 'portal'"),
        ]:
            try:
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {ctype};")
            except Exception:
                pass

    with crm_conn() as conn:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plant_id TEXT UNIQUE,
            customer_name TEXT,
            phone TEXT,
            email TEXT,
            preferred_lang TEXT DEFAULT 'english',
            opt_in_status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS campaign_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_name TEXT,
            month TEXT,
            status TEXT DEFAULT 'PENDING',
            total_messages INTEGER DEFAULT 0,
            sent_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS message_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER,
            customer_id INTEGER,
            phone TEXT,
            message_text TEXT,
            language TEXT DEFAULT 'english',
            status TEXT DEFAULT 'PENDING',
            FOREIGN KEY (campaign_id) REFERENCES campaign_log(id),
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        );

        CREATE TABLE IF NOT EXISTS alert_send_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plant_id TEXT,
            alert_type TEXT,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            cooldown_hours INTEGER DEFAULT 24
        );

        CREATE INDEX IF NOT EXISTS idx_customers_plant ON customers(plant_id);
        CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
        CREATE INDEX IF NOT EXISTS idx_queue_status ON message_queue(status);
        CREATE INDEX IF NOT EXISTS idx_alert_log_plant ON alert_send_log(plant_id, alert_type);
        """)

if __name__ == "__main__":
    init_db()
    print("Database schemas initialized successfully.")
