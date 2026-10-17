import datetime
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from config import settings
from extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

HEADER_KEYS = [  # substring of header text (lowercase) -> field; first match wins
    ("project", "project_name"),
    ("display", "display_name"),
    ("capacity", "capacity_kw"),
    ("current", "cur_power_kw"),
    ("today", "day_kwh"),
    ("month", "month_kwh"),
    ("total", "total_kwh"),
    ("irradi", "irradiation_wm2"),
    ("performance", "pr_pct"),
    ("status", "status"),
]
NUMERIC = {
    "capacity_kw",
    "cur_power_kw",
    "day_kwh",
    "month_kwh",
    "total_kwh",
    "irradiation_wm2",
    "pr_pct",
}

DDL = """
CREATE TABLE IF NOT EXISTS readings(
  scraped_at TEXT,
  plant_id TEXT,
  display_name TEXT,
  capacity_kw REAL,
  cur_power_kw REAL,
  day_kwh REAL,
  month_kwh REAL,
  total_kwh REAL,
  irradiation_wm2 REAL,
  pr_pct REAL,
  status TEXT,
  PRIMARY KEY(scraped_at, plant_id)
);
CREATE TABLE IF NOT EXISTS daily(
  plant_id TEXT,
  date TEXT,
  kwh REAL,
  peak_kw REAL,
  last_seen TEXT,
  status TEXT,
  PRIMARY KEY(plant_id, date)
);
"""

JS_TABLE = """() => {
  const t = document.querySelector('table');
  if (!t) return {heads: [], rows: []};
  return {
    heads: [...t.querySelectorAll('thead th')].map(th => th.innerText.trim()),
    rows:  [...t.querySelectorAll('tbody tr')].map(tr =>
             [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))
  };
}"""


class InjectSolarExtractor(BaseExtractor):
    """
    Inject Solar Portal Extractor.
    Extracts real telemetry from Inject Solar RMS portal via Playwright table parsing
    and saves to SQLite, CSV, and raw JSON bronze storage.
    Eliminates all synthetic hallucinations and properly links scrapers to storage.
    """

    def __init__(self):
        super().__init__("injectsolar")
        self.portal_url = getattr(settings, "injectsolar_url", None) or "https://injectsolar.com/portal/#/login"
        self.username = getattr(settings, "injectsolar_user", "")
        self.password = getattr(settings, "injectsolar_password", "")

        self.raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw" / "injectsolar"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.raw_file = self.raw_dir / "plants_injectsolar.json"
        self.db_path = self.raw_dir.parent.parent / "data" / "solaron.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_file = self.raw_dir / "storage_state.json"
        self.cached_plants: List[Dict[str, Any]] = []

    def login(self) -> bool:
        """Verify presence of InjectSolar credentials."""
        return bool(self.username and self.password)

    def _capture(self, resp: Any, bucket: List[Dict[str, Any]]) -> None:
        if resp.request.resource_type in ("xhr", "fetch") and "json" in (resp.headers.get("content-type") or ""):
            try:
                bucket.append({"url": resp.url, "status": resp.status, "body": resp.json()})
            except Exception:
                pass

    def _scrape_portal(self) -> Optional[List[Dict[str, Any]]]:
        """
        Scrape dashboard table from Inject Solar SPA via Playwright.
        Captures XHR payloads for discovery, walks pagination, and persists raw files.
        """
        if not self.login():
            logger.error("InjectSolar credentials missing or empty in config.")
            return None

        xhr: List[Dict[str, Any]] = []
        heads: Optional[List[str]] = None
        rows: List[List[str]] = []

        try:
            with sync_playwright() as pw:
                br = pw.chromium.launch(headless=getattr(settings, "playwright_headless", True))
                ctx = br.new_context(
                    storage_state=str(self.state_file) if self.state_file.exists() else None,
                    viewport={"width": 1440, "height": 900},
                )
                page = ctx.new_page()
                page.set_default_timeout(30000)
                page.on("response", lambda r: self._capture(r, xhr))

                page.goto(self.portal_url, wait_until="networkidle")

                # If login form is present, authenticate cleanly using .first to prevent strict-mode violations
                pwd_input = page.locator('input[type="password"]')
                if pwd_input.count() > 0 and pwd_input.first.is_visible():
                    user_input = page.locator('input[type="text"], input[name="username"]')
                    if user_input.count() > 0:
                        user_input.first.fill(self.username)
                    pwd_input.first.fill(self.password)
                    login_btn = page.locator('button[type="submit"], button:has-text("Login"), .btn-primary')
                    if login_btn.count() > 0:
                        login_btn.first.click()

                page.wait_for_selector("table tbody tr", timeout=25000)
                page.wait_for_load_state("networkidle")

                try:
                    ctx.storage_state(path=str(self.state_file))
                except Exception as save_err:
                    logger.debug(f"Could not persist storage state: {save_err}")

                # Paginate through entire table
                while True:
                    t = page.evaluate(JS_TABLE)
                    heads = heads or t.get("heads")
                    rows.extend(t.get("rows", []))
                    nxt = page.locator('.ant-pagination-next:not(.ant-pagination-disabled), li.next:not(.disabled) a, button.btn-next:not([disabled])')
                    if not nxt.count() or not nxt.first.is_visible():
                        break
                    nxt.first.click()
                    page.wait_for_load_state("networkidle")

                br.close()
        except Exception:
            logger.exception("InjectSolar scrape failed")
            return None

        ts = datetime.datetime.now(IST).strftime("%Y%m%dT%H%M%S")
        try:
            (self.raw_dir / f"xhr_{ts}.json").write_text(json.dumps(xhr)[:20_000_000], encoding="utf-8")
            (self.raw_dir / f"table_{ts}.json").write_text(json.dumps({"heads": heads, "rows": rows}), encoding="utf-8")
        except Exception as file_err:
            logger.debug(f"Could not write raw debug JSONs: {file_err}")

        if not heads or not rows:
            logger.warning("InjectSolar scrape returned empty table heads or rows.")
            return None

        return self._parse_and_store(heads, rows, ts)

    def _parse_and_store(self, heads: List[str], rows: List[List[str]], ts: str) -> List[Dict[str, Any]]:
        """Map scraped table rows to schema keys and persist to SQLite and CSV."""
        cols = []
        for h in heads:
            hl = h.lower()
            match = next((k for s, k in HEADER_KEYS if s in hl), None)
            cols.append(match)

        recs = []
        for r in rows:
            d = {}
            for k, v in zip(cols, r):
                if not k:
                    continue
                d[k] = self.safe_float(v) if k in NUMERIC else v

            proj_name = d.get("project_name") or d.get("display_name")
            if not proj_name:
                continue
            d["plant_id"] = self.plant_id("injectsolar", proj_name)
            d["status"] = self.normalize_status(d.get("status"))
            recs.append(d)

        now = datetime.datetime.now(IST)
        scraped_at = now.isoformat(timespec="seconds")
        today = now.date().isoformat()

        try:
            con = sqlite3.connect(self.db_path)
            con.executescript(DDL)
            for d in recs:
                con.execute(
                    """INSERT OR REPLACE INTO readings
                    (scraped_at, plant_id, display_name, capacity_kw, cur_power_kw,
                     day_kwh, month_kwh, total_kwh, irradiation_wm2, pr_pct, status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        scraped_at,
                        d["plant_id"],
                        d.get("display_name"),
                        d.get("capacity_kw"),
                        d.get("cur_power_kw"),
                        d.get("day_kwh"),
                        d.get("month_kwh"),
                        d.get("total_kwh"),
                        d.get("irradiation_wm2"),
                        d.get("pr_pct"),
                        d.get("status"),
                    ),
                )
                con.execute(
                    """INSERT INTO daily(plant_id, date, kwh, peak_kw, last_seen, status)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(plant_id, date) DO UPDATE SET
                      kwh=MAX(COALESCE(daily.kwh, 0), COALESCE(excluded.kwh, 0)),
                      peak_kw=MAX(COALESCE(daily.peak_kw, 0), COALESCE(excluded.peak_kw, 0)),
                      last_seen=excluded.last_seen,
                      status=excluded.status""",
                    (
                        d["plant_id"],
                        today,
                        d.get("day_kwh"),
                        d.get("cur_power_kw"),
                        scraped_at,
                        d.get("status"),
                    ),
                )
            con.commit()

            # Export to CSV for inspection and analysis
            try:
                import pandas as pd
                for tbl in ("readings", "daily"):
                    df = pd.read_sql_query(f"SELECT * FROM {tbl}", con)
                    csv_file = self.db_path.parent / f"injectsolar_{tbl}.csv"
                    df.to_csv(csv_file, index=False)
            except Exception as csv_err:
                logger.debug(f"Error exporting InjectSolar CSV: {csv_err}")

            con.close()
        except Exception:
            logger.exception("Error storing InjectSolar records in SQLite")

        # Also update raw_file (plants_injectsolar.json) so file-based cache stays synchronized
        try:
            with open(self.raw_file, "w", encoding="utf-8") as f:
                json.dump(recs, f, indent=2)
            self.cached_plants = recs
        except Exception as json_err:
            logger.debug(f"Error saving {self.raw_file}: {json_err}")

        return recs

    def _load_cached_records(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        """Load from SQLite latest readings or fallback to plants_injectsolar.json."""
        if self.cached_plants and not force_reload:
            return self.cached_plants

        # 1. Attempt reading latest records from SQLite
        if self.db_path.exists():
            try:
                con = sqlite3.connect(self.db_path)
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute(
                    """SELECT * FROM readings
                    WHERE scraped_at = (SELECT MAX(scraped_at) FROM readings)"""
                )
                rows = cur.fetchall()
                con.close()
                if rows:
                    self.cached_plants = [dict(r) for r in rows]
                    return self.cached_plants
            except Exception as db_err:
                logger.debug(f"Error reading from SQLite readings: {db_err}")

        # 2. Fallback to plants_injectsolar.json
        if self.raw_file.exists():
            try:
                with open(self.raw_file, "r", encoding="utf-8") as f:
                    self.cached_plants = json.load(f)
                    return self.cached_plants
            except Exception as e:
                logger.error(f"Error loading Inject Solar plants file: {e}")

        return []

    def fetch_fleet(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch InjectSolar plant fleet.
        Reads live scraped table from SQLite or triggers Playwright scrape if force_refresh is True.
        Never fabricates total energy or hardcodes arbitrary cities.
        """
        if force_refresh:
            scraped = self._scrape_portal()
            if scraped:
                self.cached_plants = scraped

        records = self._load_cached_records(force_reload=force_refresh)
        fleet = []

        for r in records:
            raw_id = r.get("project_name") or r.get("plant_id") or ""
            pid = self.plant_id("injectsolar", raw_id)
            p_name = r.get("display_name") or r.get("project_name") or pid
            cap = self.safe_float(r.get("capacity_kw") or r.get("capacity_kwp")) or 0.0
            norm_status = self.normalize_status(r.get("status"))
            cur_pwr = self.safe_float(r.get("cur_power_kw"))
            day_gen = self.safe_float(r.get("day_kwh"))
            tot_energy = self.safe_float(r.get("total_kwh") or r.get("total_energy_kwh"))
            month_gen = self.safe_float(r.get("month_kwh"))

            fleet.append({
                "plant_id": pid,
                "plant_name": p_name,
                "source": "injectsolar",
                "capacity_kwp": cap,
                "city": r.get("city") or None,
                "state": r.get("state") or None,
                "install_date": r.get("install_date") or None,
                "inverter_model": r.get("inverter_model") or None,
                "status": norm_status,
                "operational_status": "decommissioned" if norm_status == "decommissioned" else "active",
                "cur_power_kw": cur_pwr if cur_pwr is not None else 0.0,
                "day_kwh": day_gen if day_gen is not None else 0.0,
                "month_kwh": month_gen,
                "total_energy_kwh": tot_energy,
                "last_log_time": r.get("scraped_at") or r.get("last_log_time") or datetime.datetime.now(IST).strftime("%d/%m/%Y %H:%M"),
            })

        return fleet

    def fetch_daily(self, date_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch daily generation for InjectSolar fleet from SQLite daily table or live scrape.
        Status is preserved directly from the portal status badge, not calculated from generation > 0.
        """
        today_str = datetime.date.today().isoformat()
        target_date = date_str or today_str

        if force_refresh and target_date == today_str:
            self._scrape_portal()

        daily_records: List[Dict[str, Any]] = []

        # Read from daily table in SQLite
        if self.db_path.exists():
            try:
                con = sqlite3.connect(self.db_path)
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("SELECT * FROM daily WHERE date = ?", (target_date,))
                rows = cur.fetchall()
                con.close()

                if rows:
                    fleet_map = {p["plant_id"]: p.get("capacity_kwp", 0.0) for p in self.fetch_fleet()}
                    for r in rows:
                        pid = r["plant_id"]
                        cap = fleet_map.get(pid, 0.0)
                        kwh = self.safe_float(r["kwh"]) or 0.0
                        sy = round(kwh / cap, 3) if cap > 0 else 0.0
                        daily_records.append({
                            "plant_id": pid,
                            "date": target_date,
                            "kwh": kwh,
                            "revenue_inr": round(kwh * 14.0, 2),
                            "specific_yield": sy,
                            "live_power_kw": self.safe_float(r["peak_kw"]) or 0.0,
                            "status": r["status"] or "unknown",
                            "last_log_time": r["last_seen"] or "",
                            "source_type": "portal",
                        })
                    return daily_records
            except Exception as e:
                logger.debug(f"Error reading daily table from SQLite: {e}")

        # If not in daily table and target is today, build from current fleet
        if target_date == today_str:
            fleet = self.fetch_fleet(force_refresh=False)
            for p in fleet:
                pid = p["plant_id"]
                cap = p["capacity_kwp"]
                kwh = p.get("day_kwh", 0.0) or 0.0
                pwr = p.get("cur_power_kw", 0.0) or 0.0
                sy = round(kwh / cap, 3) if cap > 0 else 0.0
                daily_records.append({
                    "plant_id": pid,
                    "date": today_str,
                    "kwh": kwh,
                    "revenue_inr": round(kwh * 14.0, 2),
                    "specific_yield": sy,
                    "live_power_kw": pwr,
                    "status": p.get("status", "unknown"),
                    "last_log_time": p.get("last_log_time", ""),
                    "source_type": "portal",
                })

        return daily_records

    def fetch_monthly(self, month_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch monthly generation for InjectSolar fleet.
        Uses actual month_kwh extracted from the portal table.
        Never fabricates data by multiplying day_kwh by elapsed days.
        """
        curr_month = datetime.date.today().strftime("%Y-%m")
        if not month_str:
            month_str = curr_month

        if month_str != curr_month:
            # Historical months not present on live portal table
            return []

        fleet = self.fetch_fleet(force_refresh=force_refresh)
        monthly_records: List[Dict[str, Any]] = []

        today = datetime.date.today()
        elapsed_days = max(1, today.day)

        for p in fleet:
            pid = p["plant_id"]
            cap = p["capacity_kwp"]
            month_kwh = p.get("month_kwh")

            if month_kwh is None:
                # If portal table had no month column for this row, do not fabricate
                continue

            kwh = round(float(month_kwh), 2)
            sy = round(kwh / cap, 2) if cap > 0 else 0.0
            ypd = round(sy / float(elapsed_days), 2) if elapsed_days > 0 else 0.0
            cuf_pct = round((kwh / (cap * 24.0 * float(elapsed_days))) * 100, 2) if (elapsed_days > 0 and cap > 0) else 0.0

            monthly_records.append({
                "plant_id": pid,
                "month": month_str,
                "kwh": kwh,
                "revenue_inr": round(kwh * 14.0, 2),
                "specific_yield": sy,
                "yield_per_day": ypd,
                "cuf_pct": cuf_pct,
                "tier": None,
                "percentile": None,
                "explanation": f"Portal telemetry: {kwh} kWh in {month_str}",
            })

        return monthly_records

    def fetch_snapshots(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch inverter snapshots for InjectSolar fleet.
        Provides AC power and daily energy.
        DC power, heatsink temperature, and inverter serials are left as None
        rather than inventing synthetic numbers.
        """
        fleet = self.fetch_fleet(force_refresh=force_refresh)
        snapshots: List[Dict[str, Any]] = []
        now_ts = datetime.datetime.now(IST).strftime("%Y-%m-%dT%H:%M:%S")

        for p in fleet:
            pid = p["plant_id"]
            cur_pwr_kw = p.get("cur_power_kw")
            day_kwh = p.get("day_kwh", 0.0) or 0.0
            ac_w = round(cur_pwr_kw * 1000.0, 1) if cur_pwr_kw is not None else 0.0

            snapshots.append({
                "plant_id": pid,
                "inverter_sn": None,
                "snapshot_ts": now_ts,
                "ac_power_w": ac_w,
                "dc_power_w": None,
                "temperature_c": None,
                "e_today_kwh": day_kwh,
                "fault_code": None,
                "status": p.get("status", "unknown"),
            })

        return snapshots

    def fetch_alarms(self) -> List[Dict[str, Any]]:
        """Fetch active alarms from Inject Solar portal."""
        return []

    def supports_history(self) -> Dict[str, Any]:
        """Historical capability declaration. The live table only exposes today's telemetry."""
        return {"daily": False, "hourly": False, "max_lookback_days": None}

    def fetch_history_daily(self, plant_raw_id: Any, year_month: str) -> List[Dict[str, Any]]:
        return []

    def fetch_history_hourly(self, plant_raw_id: Any, date_str: str) -> List[Dict[str, Any]]:
        return []
