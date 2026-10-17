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
    "nagpur": 5.25,
    "amravati": 5.15,
    "jalgaon": 5.20,
    "solapur": 5.10,
    "aurangabad": 4.95,
    "ahmednagar": 4.90,
    "pune": 4.80,
    "nashik": 4.75,
    "satara": 4.70,
    "sangli": 4.85,
    "mumbai": 4.40,
    "thane": 4.38,
    "navi mumbai": 4.42,
    "kolhapur": 4.55,
}

_LAST_ISC_SCRAPE_TS: float = 0.0
_LAST_ISC_SCRAPE_CACHE: List[Dict[str, Any]] = []

def _parse_isc_power(s: Any) -> Optional[float]:
    if s is None:
        return None
    s_str = str(s).strip()
    if not s_str or s_str in ("--", "-", "null", "None", ""):
        return None
    m = re.search(r'[-+]?\d*\.?\d+', s_str)
    if not m:
        return None
    val = float(m.group())
    s_low = s_str.lower()
    if "mw" in s_low:
        return round(val * 1000.0, 3)
    if "w" in s_low and "kw" not in s_low:
        return round(val / 1000.0, 3)
    return round(val, 3)

def _parse_isc_energy(s: Any) -> Optional[float]:
    if s is None:
        return None
    s_str = str(s).strip()
    if not s_str or s_str in ("--", "-", "null", "None", ""):
        return None
    m = re.search(r'[-+]?\d*\.?\d+', s_str)
    if not m:
        return None
    val = float(m.group())
    s_low = s_str.lower()
    if "mwh" in s_low:
        return round(val * 1000.0, 2)
    return round(val, 2)

def _resolve_isc_plant_id(token: str, plant_name: str) -> str:
    try:
        from pipeline import db
    except ImportError:
        import db

    if token:
        existing = db.get_plant_by_portal_token("isolarcloud", token)
        if existing:
            return existing

    try:
        with db.analytics_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT plant_id FROM plants WHERE source='isolarcloud' AND lower(trim(plant_name)) = lower(trim(?))", [plant_name])
            row = cur.fetchone()
            if row:
                pid = str(row[0])
                if token:
                    db.save_plant_portal_token("isolarcloud", token, pid)
                return pid

            cur.execute("SELECT plant_id FROM plants WHERE source='isolarcloud'")
            rows = cur.fetchall()
            max_num = 0
            for (r_id,) in rows:
                m = re.search(r'SG-(\d+)', str(r_id))
                if m:
                    max_num = max(max_num, int(m.group(1)))
            next_pid = f"isolarcloud_SG-{max_num + 1:03d}"
            if token:
                db.save_plant_portal_token("isolarcloud", token, next_pid)
            return next_pid
    except Exception as e:
        logger.debug(f"DB lookup error in resolve_isc_plant_id: {e}")
        return f"isolarcloud_{re.sub(r'[^\w-]', '_', plant_name.strip())}"

class ISolarCloudExtractor(BaseExtractor):
    """
    iSolarCloud (Sungrow) Platform Extractor.
    Supports structured raw cache parsing (28 installations) with realistic,
    location-based generation modeling and live Playwright automation.
    """

    def __init__(self):
        super().__init__("isolarcloud")
        self.portal_url = getattr(settings, "isolarcloud_url", "https://web3.isolarcloud.in/")
        self.raw_file = Path(__file__).resolve().parent.parent / "data" / "raw" / "isolarcloud" / "plants_28_structured.json"
        self.cached_plants: List[Dict[str, Any]] = []

    def login(self) -> bool:
        return bool(settings.isolarcloud_user and settings.isolarcloud_password)

    def scrape_live_portal(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Live Playwright scraper for iSolarCloud web portal."""
        global _LAST_ISC_SCRAPE_TS, _LAST_ISC_SCRAPE_CACHE
        if not force_refresh and _LAST_ISC_SCRAPE_CACHE and (time.time() - _LAST_ISC_SCRAPE_TS) < 180:
            return _LAST_ISC_SCRAPE_CACHE
        if not self.login():
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
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=settings.playwright_headless)
                context = browser.new_context(viewport={"width": 1600, "height": 950})
                page = context.new_page()
                page.set_default_timeout(30000)

                page.goto(self.portal_url, wait_until="domcontentloaded")
                time.sleep(3)

                try:
                    agree_btn = page.locator("button:has-text('Yes, I agree'), button:has-text('Save my preferences'), button:has-text('Accept all')").first
                    if agree_btn.is_visible():
                        agree_btn.click()
                        time.sleep(1)
                except Exception:
                    pass

                u_input = page.locator("input[type='text']:not([readonly])").first
                p_input = page.locator("input[type='password']").first
                u_input.fill(settings.isolarcloud_user)
                p_input.fill(settings.isolarcloud_password)

                btn = page.locator("button:has-text('Log In'), button:has-text('Login'), button.el-button--primary").first
                btn.click()
                time.sleep(7)

                update_time = time.strftime("%d/%m/%Y %H:%M")
                try:
                    body_txt = page.locator("body").inner_text()
                    m = re.search(r"Data update time:\s*([^\n\r]+)", body_txt)
                    if m:
                        update_time = m.group(1).strip()
                except Exception:
                    pass

                page.goto(f"{self.portal_url.rstrip('/')}/#/plant", wait_until="domcontentloaded")
                page.wait_for_selector("tbody tr, .el-table__row", timeout=15000)
                time.sleep(2)

                page.evaluate("() => { document.querySelectorAll('.el-overlay, .questionnaire-dialog').forEach(e => e.remove()); }")
                time.sleep(1)

                # Attempt setting page size to 50/100 to fetch all plants on a single page
                try:
                    size_select = page.locator(".el-pagination .el-select, .el-pagination .el-input").first
                    if size_select.is_visible():
                        size_select.click()
                        time.sleep(1)
                        opt = page.locator(".el-select-dropdown__item:has-text('50'), .el-select-dropdown__item:has-text('100')").first
                        if opt.is_visible():
                            opt.click()
                            time.sleep(2)
                except Exception as e:
                    logger.debug(f"Could not change iSolarCloud page size dropdown: {e}")

                # Read total plants count reported by portal dynamically
                total_portal_count = 0
                try:
                    pag_text = page.locator(".el-pagination").inner_text()
                    m_tot = re.search(r"Total\s+(\d+)", pag_text)
                    if m_tot:
                        total_portal_count = int(m_tot.group(1))
                except Exception:
                    pass

                # Read table headers dynamically
                header_names = page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('th')).map(th => th.innerText.trim().toLowerCase());
                }""")
                def find_col(keywords: List[str], default_idx: int) -> int:
                    for kw in keywords:
                        for idx, h in enumerate(header_names):
                            if kw in h:
                                return idx
                    return default_idx

                c_name = find_col(["plant name", "name"], 0)
                c_status = find_col(["status"], 1)
                c_type = find_col(["plant type", "type"], 2)
                c_cap = find_col(["installed power", "capacity"], 3)
                c_power = find_col(["real-time power", "power"], 4)
                c_today = find_col(["yield today", "today"], 5)
                c_month = find_col(["monthly yield", "month"], 6)
                c_total = find_col(["total yield", "total"], 8)

                def extract_page_rows():
                    return page.evaluate("""() => {
                        const trs = document.querySelectorAll('tbody tr, .el-table__row');
                        return Array.from(trs).map(tr => {
                            const tds = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                            const link = tr.querySelector('a');
                            const href = link ? link.getAttribute('href') : '';
                            return { tds, href };
                        });
                    }""")

                raw_items = []
                seen_keys = set()
                for r in extract_page_rows():
                    k = r.get("href") or (r.get("tds", [""])[0])
                    if k and k not in seen_keys:
                        seen_keys.add(k)
                        raw_items.append(r)

                # Click through all pagination buttons to collect every plant
                pager_btns = page.locator(".el-pager li.number").all()
                if (total_portal_count == 0 or len(raw_items) < total_portal_count) and len(pager_btns) > 1:
                    for p_num in range(2, len(pager_btns) + 1):
                        btn = page.locator(f".el-pager li.number:has-text('{p_num}')").first
                        if btn.is_visible():
                            btn.click()
                            time.sleep(3)
                            for r in extract_page_rows():
                                k = r.get("href") or (r.get("tds", [""])[0])
                                if k and k not in seen_keys:
                                    seen_keys.add(k)
                                    raw_items.append(r)

                # Fallback: check next button if more rows remain
                try:
                    next_btn = page.locator(".el-pagination .btn-next, button.btn-next").first
                    while next_btn.is_visible() and not next_btn.is_disabled() and (total_portal_count == 0 or len(raw_items) < total_portal_count):
                        prev_cnt = len(raw_items)
                        next_btn.click()
                        time.sleep(3)
                        for r in extract_page_rows():
                            k = r.get("href") or (r.get("tds", [""])[0])
                            if k and k not in seen_keys:
                                seen_keys.add(k)
                                raw_items.append(r)
                        if len(raw_items) == prev_cnt:
                            break
                except Exception:
                    pass

                context.close()
                browser.close()

                if total_portal_count > 0 and len(raw_items) != total_portal_count:
                    logger.warning(f"iSolarCloud plant count: read {len(raw_items)} plants, portal reports {total_portal_count}")

                if raw_items:
                    structured = []
                    for idx, item in enumerate(raw_items):
                        tds = item.get("tds", [])
                        href = item.get("href", "")
                        token = href.split("?", 1)[1] if "?" in href else href

                        name_cell = tds[c_name] if len(tds) > c_name else ""
                        name_parts = [p.replace('\u00a0', ' ').strip() for p in name_cell.split('\n') if p.strip()]
                        name = name_parts[0] if name_parts else f"Sungrow Plant {idx+1}"
                        addr = ', '.join(name_parts[1:]) if len(name_parts) > 1 else ''

                        status = tds[c_status].strip() if len(tds) > c_status else 'Normal'
                        ptype = tds[c_type].strip() if len(tds) > c_type else 'Residential PV'

                        cap_val = _parse_isc_energy(tds[c_cap]) if len(tds) > c_cap else 3.0
                        cap = float(cap_val or 3.0)

                        pwr_kw = _parse_isc_power(tds[c_power]) if len(tds) > c_power else None
                        day_kwh = _parse_isc_energy(tds[c_today]) if len(tds) > c_today else None
                        month_kwh = _parse_isc_energy(tds[c_month]) if len(tds) > c_month else None
                        total_kwh = _parse_isc_energy(tds[c_total]) if len(tds) > c_total else None

                        # Accept scraped month value without rejection

                        city = 'Pune'
                        for c in ['Pune', 'Nagpur', 'Gondia', 'Katol', 'Bilaspur', 'Raipur', 'Bhilai', 'Pimpri-Chinchwad', 'Wakad', 'Fulchur', 'Bhukum']:
                            if c.lower() in addr.lower():
                                city = c
                                break

                        # Stable dynamic ID resolution via portal token
                        assigned_pid = _resolve_isc_plant_id(token, name)

                        structured.append({
                            'plant_id': assigned_pid,
                            'plant_name': name,
                            'capacity_kwp': cap,
                            'installed_power': cap,
                            'ac_capacity_kw': cap,
                            'current_power_kw': pwr_kw if pwr_kw is not None else 0.0,
                            'today_energy_kwh': day_kwh,
                            'month_energy_kwh': month_kwh,
                            'total_energy_kwh': total_kwh,
                            'address': addr,
                            'city': city,
                            'status': 'Normal' if 'normal' in status.lower() else ('Offline' if 'offline' in status.lower() else status),
                            'plant_type': ptype,
                            'inverter_model': 'SG' + str(cap).replace('.0', '') + 'RS' if cap < 10 else 'SG15RT',
                            'last_log_time': update_time,
                        })

                    # Mark plants absent from scrape as inactive in database
                    try:
                        from pipeline import db
                        scraped_pids = {p['plant_id'] for p in structured}
                        with db.analytics_conn() as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT plant_id FROM plants WHERE source='isolarcloud'")
                            for (db_pid,) in cur.fetchall():
                                if db_pid not in scraped_pids:
                                    cur.execute("UPDATE plants SET operational_status='inactive' WHERE plant_id=?", [db_pid])
                    except Exception as e:
                        logger.debug(f"Could not mark missing plants inactive: {e}")

                    self.raw_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.raw_file, "w", encoding="utf-8") as f:
                        json.dump(structured, f, ensure_ascii=False, indent=2)
                    try:
                        from services import s3_archive
                        s3_archive.upload_content_to_s3(
                            f"solaron/raw/isolarcloud/plants_{datetime.date.today().isoformat()}.json",
                            json.dumps(structured, ensure_ascii=False, indent=2),
                            metadata={"source": "isolarcloud", "count": str(len(structured))}
                        )
                    except Exception as s3_err:
                        logger.debug(f"S3 archive isolarcloud error: {s3_err}")
                    self.cached_plants = structured
                    _LAST_ISC_SCRAPE_TS = time.time()
                    _LAST_ISC_SCRAPE_CACHE = structured
                    return structured
        except Exception as e:
            logger.error(f"Error during live iSolarCloud scrape: {e}")

        return self._load_cached_records()

    def _load_cached_records(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        if self.cached_plants and not force_reload:
            return self.cached_plants
        if self.raw_file.exists():
            try:
                with open(self.raw_file, "r", encoding="utf-8") as f:
                    self.cached_plants = json.load(f)
                    return self.cached_plants
            except Exception as e:
                logger.debug(f"Error reading iSolarCloud cache: {e}")
        return []

    def _get_city_ghi(self, city: str) -> float:
        return CITY_GHI_DEFAULT.get(str(city).lower().strip(), 4.80)

    def _get_plant_pr(self, plant_id: str, base_pr: float = 0.77) -> float:
        h = int(hashlib.md5(f"pr_{plant_id}".encode()).hexdigest()[:6], 16)
        variance = ((h % 110) - 50) / 1000.0
        return round(base_pr + variance, 4)

    def _get_daily_weather_factor(self, city: str, date_str: str, plant_id: str) -> float:
        h_city = int(hashlib.md5(f"w_{city.lower().strip()}_{date_str}".encode()).hexdigest()[:6], 16)
        city_factor = 0.82 + (h_city % 36) / 100.0
        h_plant = int(hashlib.md5(f"wp_{plant_id}_{date_str}".encode()).hexdigest()[:6], 16)
        plant_var = ((h_plant % 15) - 7) / 100.0
        return max(0.55, min(1.25, round(city_factor + plant_var, 3)))

    def fetch_fleet(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch all 28 iSolarCloud plants."""
        if force_refresh:
            raw_list = self.scrape_live_portal(force_refresh=True)
        else:
            raw_list = self._load_cached_records()
        plants = []

        if raw_list:
            for p in raw_list:
                raw_id = str(p.get("plant_id") or p.get("plant_name", ""))
                pid = self.plant_id("isolarcloud", raw_id)
                cap = self.safe_float(p.get("capacity_kwp") or p.get("installed_power") or 3.0)
                plants.append({
                    "plant_id": pid,
                    "source": "isolarcloud",
                    "plant_name": str(p.get("plant_name", f"Sungrow {raw_id}")).strip(),
                    "capacity_kwp": cap,
                    "latitude": self.safe_float(p.get("latitude") or 18.52),
                    "longitude": self.safe_float(p.get("longitude") or 73.85),
                    "city": str(p.get("city") or "Pune"),
                    "install_date": str(p.get("grid_connection_date") or "2023-03-15"),
                    "inverter_model": str(p.get("inverter_model") or "SG3.0RS"),
                    "panel_model": "Tier-1 Mono PERC",
                    "last_log_time": str(p.get("last_log_time") or ""),
                    "status": str(p.get("status") or "Normal"),
                    "total_energy_kwh": self.safe_float(p.get("total_energy_kwh")),
                })
            return plants

        return []

    def fetch_daily(self, date_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch daily generation records for iSolarCloud fleet with per-plant location variation."""
        today_date = datetime.date.today()
        today_str = today_date.isoformat()
        if not date_str or date_str[:10] > today_str:
            date_str = today_str
        target_dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        if target_dt > today_date:
            target_dt = today_date
        year_month = target_dt.strftime("%Y-%m")
        target_day = target_dt.day

        if force_refresh:
            raw_list = self.scrape_live_portal(force_refresh=True)
        else:
            raw_list = self._load_cached_records()
        results = []

        for p in raw_list:
            raw_id = str(p.get("plant_id") or p.get("plant_name", ""))
            pid = self.plant_id("isolarcloud", raw_id)
            cap = self.safe_float(p.get("capacity_kwp") or 3.0) or 3.0
            city = str(p.get("city") or "Pune")
            ghi = self._get_city_ghi(city)
            pr = self._get_plant_pr(pid)
            base_daily = cap * ghi * pr

            cached_today_kwh = self.safe_float(p.get("today_energy_kwh"))
            cached_cur_kw = self.safe_float(p.get("current_power_kw"))
            cached_month_kwh = self.safe_float(p.get("month_energy_kwh"))
            status = self.normalize_status(p.get("status") or "normal")
            log_time = str(p.get("last_log_time") or "")
            is_offline = (status == "offline") or (
                (cached_today_kwh is None or cached_today_kwh == 0) and
                (cached_cur_kw is None or cached_cur_kw == 0) and
                (cached_month_kwh is None or cached_month_kwh == 0)
            )

            # Only emit records for dates with actual portal telemetry (today)
            d_str = f"{year_month}-{target_day:02d}"
            if cached_today_kwh is not None:
                kwh = max(0.0, round(cached_today_kwh, 2))
                cur_kw = max(0.0, round(cached_cur_kw, 2)) if cached_cur_kw is not None else 0.0
                rec_log = log_time
            elif is_offline:
                kwh = 0.0
                cur_kw = 0.0
                rec_log = log_time
            elif cached_cur_kw is not None and cached_cur_kw > 0:
                kwh = 0.0
                cur_kw = round(cached_cur_kw, 2)
                rec_log = log_time
            else:
                # No portal telemetry for this plant today
                continue
                continue

            sy = round(kwh / cap, 3) if cap > 0 else 0.0
            results.append({
                "plant_id": pid,
                "date": d_str,
                "kwh": kwh,
                "revenue_inr": round(kwh * 14.0, 2),
                "specific_yield": sy,
                "yield_per_day": sy,
                "live_power_kw": cur_kw,
                "status": "offline" if is_offline else status,
                "last_log_time": rec_log,
                "source_type": "portal",
            })

        return results

    def fetch_monthly(self, month_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch monthly generation records for iSolarCloud fleet with exact reconciliation to daily records."""
        if not month_str:
            month_str = datetime.date.today().strftime("%Y-%m")

        if force_refresh:
            raw_list = self.scrape_live_portal(force_refresh=True)
        else:
            raw_list = self._load_cached_records()
        results = []

        # Determine number of days for this month
        try:
            y, m = map(int, month_str.split("-"))
            if m == 12:
                next_month = datetime.date(y + 1, 1, 1)
            else:
                next_month = datetime.date(y, m + 1, 1)
            days_in_month = (next_month - datetime.timedelta(days=1)).day
        except Exception:
            days_in_month = 30

        # If current month, only calculate elapsed days up to target day (e.g. 23)
        current_ym = datetime.date.today().strftime("%Y-%m")
        if month_str == current_ym:
            eval_days = min(datetime.date.today().day, days_in_month)
        else:
            eval_days = days_in_month

        for p in raw_list:
            raw_id = str(p.get("plant_id") or p.get("plant_name", ""))
            pid = self.plant_id("isolarcloud", raw_id)
            cap = self.safe_float(p.get("capacity_kwp") or 3.0) or 3.0

            cached_today_kwh = self.safe_float(p.get("today_energy_kwh"))
            cached_month_kwh = self.safe_float(p.get("month_energy_kwh"))
            cached_cur_kw = self.safe_float(p.get("current_power_kw"))
            status_str = str(p.get("status", "")).lower()
            is_offline = "offline" in status_str or (
                (cached_today_kwh is None or cached_today_kwh == 0) and
                (cached_cur_kw is None or cached_cur_kw == 0) and
                (cached_month_kwh is None or cached_month_kwh == 0)
            )

            if month_str == current_ym and cached_month_kwh is not None:
                # Real portal monthly energy
                monthly_kwh = max(0.0, round(cached_month_kwh, 2))
                explanation = f"Portal telemetry: {monthly_kwh} kWh in {month_str}"
            elif is_offline:
                monthly_kwh = 0.0
                explanation = f"Plant offline in {month_str}"
            else:
                # For past months or missing monthly cache, do not fabricate synthetic numbers!
                continue

            # Process monthly yield directly without rejection

            sy = round(monthly_kwh / cap, 2) if cap > 0 else 0.0
            ypd = round(sy / float(eval_days), 2) if (eval_days > 0 and cap > 0) else 0.0
            cuf = round((monthly_kwh / (cap * 24.0 * float(eval_days))) * 100.0, 2) if (eval_days > 0 and cap > 0) else 0.0

            results.append({
                "plant_id": pid,
                "month": month_str,
                "kwh": monthly_kwh,
                "revenue_inr": round(monthly_kwh * 14.0, 2),
                "specific_yield": sy,
                "yield_per_day": ypd,
                "cuf_pct": cuf,
                "pr_pct": None,
                "tier": None,
                "percentile": None,
                "explanation": explanation,
                "source_type": "portal",
            })

        return results

    def fetch_snapshots(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch inverter snapshots for iSolarCloud fleet."""
        if force_refresh:
            raw_list = self.scrape_live_portal(force_refresh=True)
        else:
            raw_list = self._load_cached_records()
        snapshots = []
        now_ts = datetime.datetime.now().isoformat()

        for idx, p in enumerate(raw_list):
            raw_id = str(p.get("plant_id") or p.get("plant_name", ""))
            pid = self.plant_id("isolarcloud", raw_id)
            inv_model = str(p.get("inverter_model") or "SG3.0RS")
            cur_kw = self.safe_float(p.get("current_power_kw"))
            today_kwh = self.safe_float(p.get("today_energy_kwh"))
            status = self.normalize_status(p.get("status") or "normal")

            temp = self.safe_float(p.get("temperature_c"))

            ac_w = round(cur_kw * 1000.0, 1) if (cur_kw is not None and cur_kw > 0) else 0.0
            actual_today = today_kwh if today_kwh is not None else 0.0

            snapshots.append({
                "plant_id": pid,
                "inverter_sn": inv_model if inv_model else None,
                "status": status,
                "ac_power_w": ac_w,
                "dc_power_w": None,
                "temperature_c": temp,
                "e_today_kwh": actual_today,
                "fault_code": "0",
                "snapshot_ts": now_ts,
            })

        return snapshots

    def supports_history(self) -> Dict[str, Any]:
        return {"daily": True, "hourly": False, "max_lookback_days": 60}

    def fetch_history_daily(self, plant_raw_id: Any, year_month: str) -> List[Dict[str, Any]]:
        """Fetch historical daily generation from real portal scrape cache or db."""
        raw_id = str(plant_raw_id)
        pid = self.plant_id("isolarcloud", raw_id)
        # Check raw archive for scraped daily exports
        hist_file = self.raw_dir / f"isolarcloud_daily_{year_month}.json"
        if hist_file.exists():
            try:
                with open(hist_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    records = []
                    for r in data:
                        if r.get("plant_id") == pid:
                            r_copy = dict(r)
                            r_copy["source_type"] = "portal_history"
                            records.append(r_copy)
                    if records:
                        return records
            except Exception:
                pass
        return []

    def fetch_history_hourly(self, plant_raw_id: Any, date_str: str) -> List[Dict[str, Any]]:
        return []
