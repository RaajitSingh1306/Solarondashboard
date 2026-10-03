import datetime
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional

from config import settings
from extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

CITY_GHI_DEFAULT = {
    "raipur": 4.72,
    "bilaspur": 4.65,
    "bhilai": 4.68,
    "silvassa": 4.45,
    "athal": 4.45,
    "maharashtra": 4.85,
}

_LAST_LIVE_SCRAPE_TS: float = 0.0
_LAST_LIVE_SCRAPE_CACHE: List[Dict[str, Any]] = []

class SuryaLogExtractor(BaseExtractor):
    """
    SuryaLog Cloud Platform Extractor.
    Supports structured raw cache parsing (12 commercial installations) and live Playwright
    scraping directly from cloud.suryalog.ae for real-time telemetry (Day Gen, Power, Month Gen, CUF).
    """

    def __init__(self):
        super().__init__("suryalog")
        self.portal_url = "https://cloud.suryalog.ae"
        self.raw_file = Path(__file__).resolve().parent.parent / "data" / "raw" / "suryalog" / "plants_12_structured.json"
        self.cached_plants: List[Dict[str, Any]] = []

    def login(self) -> bool:
        return bool(settings.suryalog_user and settings.suryalog_password)

    def _load_cached_records(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        if self.cached_plants and not force_reload:
            return self.cached_plants
        if self.raw_file.exists():
            try:
                with open(self.raw_file, "r", encoding="utf-8") as f:
                    self.cached_plants = json.load(f)
                    return self.cached_plants
            except Exception as e:
                logger.debug(f"Error reading SuryaLog cache: {e}")
        return []

    def _get_city_ghi(self, city: str) -> float:
        return CITY_GHI_DEFAULT.get(str(city).lower().strip(), 4.70)

    def _get_plant_pr(self, plant_id: str, base_pr: float = 0.78) -> float:
        h = int(hashlib.md5(f"pr_{plant_id}".encode()).hexdigest()[:6], 16)
        variance = ((h % 110) - 50) / 1000.0
        return round(base_pr + variance, 4)

    def _get_daily_weather_factor(self, city: str, date_str: str, plant_id: str) -> float:
        h_city = int(hashlib.md5(f"w_{city.lower().strip()}_{date_str}".encode()).hexdigest()[:6], 16)
        city_factor = 0.82 + (h_city % 36) / 100.0
        h_plant = int(hashlib.md5(f"wp_{plant_id}_{date_str}".encode()).hexdigest()[:6], 16)
        plant_var = ((h_plant % 15) - 7) / 100.0
        return max(0.55, min(1.25, round(city_factor + plant_var, 3)))

    def scrape_live_portal(self, target_plant_name: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Log into cloud.suryalog.ae and scrape live telemetry for commercial plants."""
        global _LAST_LIVE_SCRAPE_TS, _LAST_LIVE_SCRAPE_CACHE
        if not force_refresh and not target_plant_name and (time.time() - _LAST_LIVE_SCRAPE_TS < 180.0) and _LAST_LIVE_SCRAPE_CACHE:
            logger.info("Using fresh live scrape from %.1fs ago.", time.time() - _LAST_LIVE_SCRAPE_TS)
            return _LAST_LIVE_SCRAPE_CACHE

        if not self.login():
            logger.warning("SuryaLog credentials not configured in .env, reading cached data.")
            return self._load_cached_records(force_reload=force_refresh)

        try:
            if sys.platform == "win32":
                import asyncio
                try:
                    loop = asyncio.ProactorEventLoop()
                    asyncio.set_event_loop(loop)
                except Exception:
                    pass

            from playwright.sync_api import sync_playwright
            logger.info("Connecting to SuryaLog portal to fetch live telemetry...")

            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=settings.playwright_headless)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                page = context.new_page()
                page.set_default_timeout(45000)

                page.goto(self.portal_url, wait_until="domcontentloaded")
                time.sleep(2)
                page.fill("#loginId, input[name='loginId'], input[name*='user']", settings.suryalog_user)
                page.fill("#password, input[name='password'], input[type='password']", settings.suryalog_password)
                page.click("#btnlogin, button[type='submit']")
                try:
                    page.wait_for_selector("#searchPlant option", timeout=25000)
                except Exception:
                    time.sleep(6)

                # Fetch dropdown options
                options = page.eval_on_selector_all(
                    "#searchPlant option",
                    "opts => opts.map(o => ({text: o.text.trim(), val: o.value}))"
                )

                if not options:
                    logger.warning("No plant options found on SuryaLog portal.")
                    _LAST_LIVE_SCRAPE_TS = time.time()
                    return self._load_cached_records()

                if target_plant_name:
                    filtered_opts = [o for o in options if target_plant_name.lower() in o.get('text', '').lower()]
                    if filtered_opts:
                        options = filtered_opts

                records = self._load_cached_records()

                def extract_clean_num(sel: str) -> float:
                    try:
                        txt = page.locator(sel).first.inner_text().strip()
                        m = re.search(r"[-+]?\d*\.?\d+", txt.replace(",", ""))
                        if not m:
                            return 0.0
                        v = float(m.group())
                        if "mwh" in txt.lower():
                            v *= 1000.0
                        return v
                    except Exception:
                        return 0.0

                def extract_text(sel: str) -> str:
                    try:
                        return page.locator(sel).first.inner_text().strip()
                    except Exception:
                        return ""

                for idx, opt in enumerate(options):
                    p_text = opt['text']
                    p_val = opt['val']
                    if not p_text:
                        continue

                    try:
                        page.select_option("#searchPlant", value=p_val)
                        page.evaluate("() => { if (typeof selectPlant === 'function') { selectPlant($('#searchPlant')[0]); } else if (window.$) { $('#searchPlant').trigger('change'); } }")
                        time.sleep(4.5)

                        live_power = extract_clean_num("#PSKW")
                        live_day = extract_clean_num("#PEKWH")
                        live_yest = extract_clean_num("#PYKWH")
                        live_month = extract_clean_num("#PMKWH")
                        live_cuf = extract_clean_num("#PCUF")
                        live_total = extract_clean_num("#PTKWH")
                        live_time = extract_text("#Lltime")

                        # Retry briefly if all values are zero/empty in case of delayed DOM update
                        if live_power == 0 and live_day == 0 and live_month == 0:
                            time.sleep(3.0)
                            live_power = extract_clean_num("#PSKW")
                            live_day = extract_clean_num("#PEKWH")
                            live_yest = extract_clean_num("#PYKWH")
                            live_month = extract_clean_num("#PMKWH")
                            live_cuf = extract_clean_num("#PCUF")
                            live_total = extract_clean_num("#PTKWH")
                            live_time = extract_text("#Lltime")

                        matched_rec = None
                        for r in records:
                            r_name = str(r.get("plant_name", "")).strip().lower()
                            if r_name == p_text.lower() or p_text.lower() in r_name or r_name in p_text.lower():
                                matched_rec = r
                                break

                        if matched_rec:
                            cap = float(matched_rec.get("capacity_kwp") or 10.0)

                            # Check date staleness (e.g. log from June 2026 when current is Sept 2026)
                            is_stale_date = False
                            if live_time:
                                m_date = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", live_time)
                                if m_date:
                                    _, m_num, y_num = m_date.groups()
                                    full_year = int(y_num) if len(y_num) == 4 else (2000 + int(y_num))
                                    current_now = datetime.datetime.now()
                                    if (full_year < current_now.year) or (full_year == current_now.year and int(m_num) < current_now.month):
                                        if live_power == 0 and live_day == 0:
                                            is_stale_date = True

                            if is_stale_date:
                                live_month = 0.0
                                live_day = 0.0
                                live_yest = 0.0

                            matched_rec["current_power_kw"] = live_power
                            matched_rec["today_energy_kwh"] = live_day
                            matched_rec["yesterday_energy_kwh"] = live_yest

                            # Sanity check: B1 - Prevent total lifetime energy from overwriting monthly energy
                            max_month_limit = cap * 220.0
                            if live_month is not None and (live_month > max_month_limit or (live_total is not None and live_total > 0 and abs(live_month - live_total) < 1.0 and live_month > max_month_limit)):
                                logger.warning(f"SuryaLog plant {p_text}: #PMKWH value {live_month} appears to be lifetime total, ignoring as monthly.")
                                matched_rec["total_energy_kwh"] = live_month
                                if (matched_rec.get("month_energy_kwh") or 0) > max_month_limit:
                                    matched_rec["month_energy_kwh"] = round(cap * 90.0, 1)
                            elif live_month is not None and live_month > 0:
                                matched_rec["month_energy_kwh"] = live_month
                            elif is_stale_date:
                                matched_rec["month_energy_kwh"] = 0.0

                            if live_cuf > 0 and live_cuf <= 100.0:
                                matched_rec["cuf_pct"] = live_cuf
                            if live_total > 0:
                                matched_rec["total_energy_kwh"] = live_total
                            if live_time:
                                matched_rec["last_log_time"] = live_time
                            matched_rec["last_scrape_time"] = datetime.datetime.now().isoformat()
                            if not is_stale_date and (live_power > 0 or live_day > 0 or (live_month is not None and live_month > 1.0)):
                                matched_rec["status"] = "Normal"
                            else:
                                matched_rec["status"] = "Offline"
                    except Exception as step_err:
                        logger.warning(f"Error scraping SuryaLog plant {p_text}: {step_err}")

                context.close()
                browser.close()

                try:
                    self.raw_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.raw_file, "w", encoding="utf-8") as f:
                        json.dump(records, f, indent=2)
                    logger.info("Successfully updated plants_12_structured.json with live SuryaLog data.")
                except Exception as save_err:
                    logger.error(f"Error saving updated SuryaLog cache: {save_err}")

                self.cached_plants = records
                _LAST_LIVE_SCRAPE_TS = time.time()
                _LAST_LIVE_SCRAPE_CACHE = records
                return records
        except Exception as e:
            logger.error(f"Failed to scrape SuryaLog live portal: {e}")
            return self._load_cached_records()

    def fetch_fleet(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch all 12 commercial SuryaLog plants."""
        if force_refresh and self.login():
            raw_list = self.scrape_live_portal(force_refresh=True)
        else:
            raw_list = self._load_cached_records(force_reload=force_refresh)

        plants = []
        if raw_list:
            for p in raw_list:
                raw_id = str(p.get("plant_id") or p.get("plant_name", ""))
                pid = self.plant_id("suryalog", raw_id)
                cap = self.safe_float(p.get("capacity_kwp") or 10.0) or 10.0
                p_name = str(p.get("plant_name", f"SuryaLog {raw_id}")).strip()
                p_name_clean = re.sub(r"^\d+\.\s*", "", p_name)

                plants.append({
                    "plant_id": pid,
                    "source": "suryalog",
                    "plant_name": p_name_clean,
                    "capacity_kwp": cap,
                    "latitude": self.safe_float(p.get("latitude") or 21.25),
                    "longitude": self.safe_float(p.get("longitude") or 81.63),
                    "city": str(p.get("city") or "Raipur"),
                    "install_date": str(p.get("install_date") or "2023-01-10"),
                    "inverter_model": str(p.get("inverter_model") or "Commercial"),
                    "panel_model": str(p.get("panel_model") or "Mono PERC 540W"),
                    "last_log_time": str(p.get("last_log_time") or ""),
                    "status": str(p.get("status") or "Normal"),
                    "total_energy_kwh": self.safe_float(p.get("total_energy_kwh")),
                })
            return plants

        return plants

    def fetch_daily(self, date_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch daily generation records for SuryaLog fleet."""
        today_date = datetime.date.today()
        today_str = today_date.isoformat()
        if not date_str or date_str[:10] > today_str:
            date_str = today_str
        target_dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        if target_dt > today_date:
            target_dt = today_date
        year_month = target_dt.strftime("%Y-%m")
        target_day = target_dt.day

        if force_refresh and self.login():
            raw_list = self.scrape_live_portal(force_refresh=True)
        else:
            raw_list = self._load_cached_records(force_reload=force_refresh)

        results = []

        for p in raw_list:
            raw_id = str(p.get("plant_id") or p.get("plant_name", ""))
            pid = self.plant_id("suryalog", raw_id)
            cap = self.safe_float(p.get("capacity_kwp") or 10.0) or 10.0
            city = str(p.get("city") or "Raipur")
            ghi = self._get_city_ghi(city)
            pr = self._get_plant_pr(pid, base_pr=0.78)
            base_daily = cap * ghi * pr

            cached_today_kwh = self.safe_float(p.get("today_energy_kwh"))
            cached_cur_kw = self.safe_float(p.get("current_power_kw"))
            cached_yest_kwh = self.safe_float(p.get("yesterday_energy_kwh"))
            cached_month_kwh = self.safe_float(p.get("month_energy_kwh"))
            status_raw = str(p.get("status", "")).lower()

            is_offline = (
                (cached_month_kwh is not None and cached_month_kwh <= 1.0) and
                (cached_today_kwh is None or cached_today_kwh <= 0.05) and
                (cached_yest_kwh is None or cached_yest_kwh <= 0.05)
            ) or ("offline" in status_raw and (cached_month_kwh is None or cached_month_kwh <= 1.0))

            # Only emit verified telemetry from portal (today and yesterday)
            log_time = str(p.get("last_log_time") or "")

            # 1. Today's record
            d_today = f"{year_month}-{target_day:02d}"
            if is_offline:
                kwh_today = 0.0
                cur_kw = 0.0
                stat_today = "offline"
            elif cached_today_kwh is not None:
                kwh_today = max(0.0, round(cached_today_kwh, 2))
                cur_kw = max(0.0, round(cached_cur_kw, 2)) if cached_cur_kw is not None else 0.0
                stat_today = "active" if (kwh_today > 0.05 or cur_kw > 0) else "offline"
            elif cached_cur_kw is not None and cached_cur_kw > 0:
                kwh_today = 0.0
                cur_kw = round(cached_cur_kw, 2)
                stat_today = "active"
            else:
                kwh_today = None
                cur_kw = None
                stat_today = "offline"

            if kwh_today is not None:
                sy_today = round(kwh_today / cap, 3) if cap > 0 else 0.0
                results.append({
                    "plant_id": pid,
                    "date": d_today,
                    "kwh": kwh_today,
                    "revenue_inr": round(kwh_today * 14.0, 2),
                    "specific_yield": sy_today,
                    "yield_per_day": sy_today,
                    "live_power_kw": cur_kw,
                    "status": stat_today,
                    "last_log_time": log_time,
                    "source_type": "portal",
                })

            # 2. Yesterday's record (from verified PYKWH)
            if target_day > 1:
                d_yest = f"{year_month}-{(target_day - 1):02d}"
                if is_offline:
                    kwh_yest = 0.0
                    stat_yest = "offline"
                elif cached_yest_kwh is not None:
                    kwh_yest = max(0.0, round(cached_yest_kwh, 2))
                    stat_yest = "active" if kwh_yest > 0.05 else "offline"
                else:
                    kwh_yest = None
                    stat_yest = "offline"

                if kwh_yest is not None:
                    sy_yest = round(kwh_yest / cap, 3) if cap > 0 else 0.0
                    results.append({
                        "plant_id": pid,
                        "date": d_yest,
                        "kwh": kwh_yest,
                        "revenue_inr": round(kwh_yest * 14.0, 2),
                        "specific_yield": sy_yest,
                        "yield_per_day": sy_yest,
                        "live_power_kw": None,
                        "status": stat_yest,
                        "last_log_time": f"{d_yest} 23:59 (portal PYKWH)",
                        "source_type": "portal",
                    })

        return results

    def fetch_monthly(self, month_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch monthly generation records for SuryaLog fleet."""
        if not month_str:
            month_str = datetime.date.today().strftime("%Y-%m")

        if force_refresh and self.login():
            raw_list = self.scrape_live_portal(force_refresh=True)
        else:
            raw_list = self._load_cached_records(force_reload=force_refresh)

        results = []

        try:
            y, m = map(int, month_str.split("-"))
            if m == 12:
                next_month = datetime.date(y + 1, 1, 1)
            else:
                next_month = datetime.date(y, m + 1, 1)
            days_in_month = (next_month - datetime.timedelta(days=1)).day
        except Exception:
            days_in_month = 30

        current_ym = datetime.date.today().strftime("%Y-%m")
        if month_str == current_ym:
            eval_days = min(datetime.date.today().day, days_in_month)
        else:
            eval_days = days_in_month

        for p in raw_list:
            raw_id = str(p.get("plant_id") or p.get("plant_name", ""))
            pid = self.plant_id("suryalog", raw_id)
            cap = self.safe_float(p.get("capacity_kwp") or 10.0) or 10.0
            city = str(p.get("city") or "Raipur")
            ghi = self._get_city_ghi(city)
            pr = self._get_plant_pr(pid, base_pr=0.78)
            base_daily = cap * ghi * pr

            cached_month_kwh = self.safe_float(p.get("month_energy_kwh"))
            cached_cuf = self.safe_float(p.get("cuf_pct"))
            cached_today_kwh = self.safe_float(p.get("today_energy_kwh"))
            cached_cur_kw = self.safe_float(p.get("current_power_kw"))
            cached_yest_kwh = self.safe_float(p.get("yesterday_energy_kwh"))

            # True offline for month check:
            # A plant is only 0-generation for the month if it has 0 monthly energy, stale log date,
            # or all telemetry metrics (month, today, yesterday, total) are zero/absent.
            is_zero_monthly = (
                (cached_month_kwh is not None and cached_month_kwh == 0.0) or
                (cached_month_kwh is None and (cached_today_kwh is None or cached_today_kwh == 0) and (cached_yest_kwh is None or cached_yest_kwh == 0))
            )

            # Physics clamp check: monthly energy cannot exceed cap * 220.0
            max_month_limit = cap * 220.0
            if cached_month_kwh is not None and cached_month_kwh > max_month_limit:
                logger.warning(f"Ignoring corrupted monthly value {cached_month_kwh} for SuryaLog plant {pid}")
                cached_month_kwh = None

            if cached_month_kwh is not None and cached_month_kwh > 0 and month_str == current_ym:
                monthly_kwh = round(cached_month_kwh, 2)
                sy = round(monthly_kwh / cap, 2) if cap > 0 else 0.0
                ypd = round(sy / float(eval_days), 2) if (eval_days > 0 and cap > 0) else 0.0
                cuf = cached_cuf if (cached_cuf is not None and cached_cuf > 0) else (round((monthly_kwh / (cap * 24.0 * float(eval_days))) * 100.0, 2) if (eval_days > 0 and cap > 0) else 0.0)
                pr_pct = None
                explanation = f"Portal telemetry {monthly_kwh} kWh (SY: {sy} kWh/kWp, {ypd} units/kWp/day)"
            elif is_zero_monthly:
                monthly_kwh = 0.0
                sy = 0.0
                ypd = 0.0
                cuf = 0.0
                pr_pct = None
                explanation = f"Plant offline in {month_str}"
            else:
                # For past months or missing monthly cache, do not fabricate synthetic numbers!
                continue

            results.append({
                "plant_id": pid,
                "month": month_str,
                "kwh": monthly_kwh,
                "revenue_inr": round(monthly_kwh * 14.0, 2),
                "specific_yield": sy,
                "yield_per_day": ypd,
                "cuf_pct": cuf,
                "pr_pct": pr_pct,
                "tier": None,
                "percentile": None,
                "explanation": explanation,
            })

        return results

    def fetch_snapshots(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch inverter snapshots for SuryaLog fleet."""
        if force_refresh and self.login():
            raw_list = self.scrape_live_portal(force_refresh=True)
        else:
            raw_list = self._load_cached_records(force_reload=force_refresh)

        snapshots = []
        now_ts = datetime.datetime.now().isoformat()

        for idx, p in enumerate(raw_list):
            raw_id = str(p.get("plant_id") or p.get("plant_name", ""))
            pid = self.plant_id("suryalog", raw_id)
            cap = self.safe_float(p.get("capacity_kwp") or 10.0) or 10.0

            cur_kw = self.safe_float(p.get("current_power_kw"))
            today_kwh = self.safe_float(p.get("today_energy_kwh"))

            ac_power_w = round(cur_kw * 1000.0, 1) if (cur_kw is not None and cur_kw > 0) else 0.0
            dc_power_w = round(ac_power_w / 0.975, 1) if ac_power_w > 0 else 0.0
            e_today_kwh = today_kwh if today_kwh is not None else 0.0
            status = "active" if (cur_kw and cur_kw > 0) or (today_kwh and today_kwh > 0) else "offline"
            temp = self.safe_float(p.get("temperature_c"))

            snapshots.append({
                "plant_id": pid,
                "inverter_sn": f"SYR-INV-{raw_id}-{idx+1}",
                "status": status,
                "ac_power_w": ac_power_w,
                "dc_power_w": dc_power_w,
                "temperature_c": temp,
                "e_today_kwh": e_today_kwh,
                "fault_code": "0",
                "snapshot_ts": now_ts,
            })

        return snapshots
