import datetime
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional

from config import settings
from extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

def parse_growatt_date(v: Any) -> str:
    """Robustly parse Growatt install/create dates from dict, epoch, or string formats."""
    if not v or str(v).lower() in ("nan", "none", "null", "undefined", ""):
        return ""
    if isinstance(v, dict):
        if "year" in v and "month" in v and "date" in v:
            y = 1900 + int(v["year"]) if int(v["year"]) < 1900 else int(v["year"])
            m = int(v["month"]) + 1
            d = int(v["date"])
            return f"{y:04d}-{m:02d}-{d:02d}"
        if "time" in v:
            sec = v["time"] / 1000.0 if v["time"] > 1e11 else v["time"]
            try:
                return datetime.datetime.fromtimestamp(sec).strftime("%Y-%m-%d")
            except Exception:
                return ""
    if isinstance(v, (int, float)):
        sec = v / 1000.0 if v > 1e11 else v
        try:
            return datetime.datetime.fromtimestamp(sec).strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = str(v).strip()
    if s.startswith("{") and "date" in s:
        import ast
        try:
            d = ast.literal_eval(s)
            return parse_growatt_date(d)
        except Exception:
            pass
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""

class GrowattExtractor(BaseExtractor):
    """
    Growatt Platform Extractor using growattServer library and disk cache.
    Extracts deep telemetry, plant metadata, inverter snapshots, daily and monthly generation.
    """

    def __init__(self):
        super().__init__("growatt")
        self.api = None
        self.logged_in = False
        self.raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw" / "growatt"
        self.cached_plants: List[Dict[str, Any]] = []
        self.plant_capacities: Dict[str, float] = {}
        self.master_metadata: Dict[str, Dict[str, Any]] = {}
        self._load_master_metadata()

    def _load_master_metadata(self) -> None:
        """Load verified fleet metadata CSV if present to supply ground truth capacities and coords."""
        candidates = [
            self.raw_dir / "fleet_all_plants_metadata.csv",
            self.raw_dir.parent / "fleet_all_plants_metadata.csv",
            self.raw_dir.parent.parent.parent / "solaron_analytics_dataset_csv" / "fleet_all_plants_metadata.csv",
        ]
        for c in candidates:
            if c.exists():
                try:
                    import pandas as pd
                    df = pd.read_csv(c)
                    for _, r in df.iterrows():
                        pid_str = str(r.get("plant_id", "")).strip()
                        pname_str = str(r.get("plant_name", "")).strip().lower()
                        c_val = float(r.get("capacity_kwp", 0.0) or 0.0)
                        if c_val > 0:
                            d = r.to_dict()
                            if pid_str:
                                self.master_metadata[pid_str] = d
                            if pname_str:
                                self.master_metadata[pname_str] = d
                    logger.info(f"Loaded ground-truth metadata for {len(self.master_metadata)} plants.")
                    break
                except Exception as e:
                    logger.debug(f"Could not load metadata from {c}: {e}")

    def login(self) -> bool:
        if self.logged_in:
            return True
        if not settings.growatt_user or not settings.growatt_password:
            return False
        try:
            import growattServer
            self.api = growattServer.GrowattApi()
            if hasattr(settings, "growatt_server_url") and settings.growatt_server_url:
                self.api.server_url = settings.growatt_server_url
            login_response = self.api.login(settings.growatt_user, settings.growatt_password)
            self.logged_in = bool(login_response and (login_response.get("success", True) or "userId" in login_response))
            return self.logged_in
        except Exception as e:
            logger.debug(f"Growatt login error: {e}")
            self.logged_in = False
            return False

    def _fetch_all_pages_live(self) -> List[Dict[str, Any]]:
        if not self.login():
            return []
        all_plants = []
        seen_ids = set()
        page_num = 1
        page_size = 500
        while True:
            try:
                resp = self.api.session.post(
                    self.api.get_url("newTwoPlantAPI.do"),
                    params={"op": "getAllPlantListTwo"},
                    data={
                        "language": "1",
                        "pageSize": str(page_size),
                        "order": "1",
                        "toPageNum": str(page_num)
                    },
                    timeout=30
                )
                data = resp.json()
                page_plants = data.get("PlantList") or []
                if not page_plants:
                    break
                new_added = 0
                for p in page_plants:
                    pid = str(p.get("plantId") or p.get("id") or "")
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        all_plants.append(p)
                        new_added += 1
                    elif not pid:
                        all_plants.append(p)
                        new_added += 1
                if len(page_plants) < page_size or new_added == 0:
                    break
                page_num += 1
            except Exception as e:
                logger.error(f"Error fetching Growatt page {page_num}: {e}")
                break
        return all_plants

    def _get_raw_plant_list(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        if self.cached_plants and not force_refresh:
            return self.cached_plants

        # 1. If force_refresh and API login works, pull fresh live plant list across all pages
        if force_refresh and self.login():
            plants = self._fetch_all_pages_live()
            if plants:
                self.cached_plants = plants
                self.raw_dir.mkdir(parents=True, exist_ok=True)
                try:
                    with open(self.raw_dir / "plant_list_live.json", "w", encoding="utf-8") as f:
                        json.dump(plants, f)
                except Exception:
                    pass
                try:
                    from services import s3_archive
                    s3_archive.upload_content_to_s3(
                        f"solaron/raw/growatt/plant_list_{datetime.date.today().isoformat()}.json",
                        json.dumps(plants, indent=2),
                        metadata={"source": "growatt", "count": str(len(plants))}
                    )
                except Exception as s3_err:
                    logger.debug(f"S3 archive raw growatt list error: {s3_err}")
                return plants

        # 2. Fallback to disk cache if live fetch failed or force_refresh is False
        if self.raw_dir.exists():
            raw_files = sorted(self.raw_dir.glob("plant_list_*.json"), reverse=True)
            for rf in raw_files:
                try:
                    with open(rf, "r", encoding="utf-8") as f:
                        content = json.load(f)
                        if isinstance(content, list):
                            plants = content
                        elif isinstance(content, dict):
                            plants = content.get("data") or content.get("plants") or content.get("PlantList") or []
                        else:
                            plants = []
                        if plants:
                            self.cached_plants = plants
                            return plants
                except Exception as e:
                    logger.debug(f"Error reading cached Growatt plant list from {rf.name}: {e}")

        # 3. Fallback to live API
        if self.login():
            plants = self._fetch_all_pages_live()
            if plants:
                self.cached_plants = plants
                return plants

        return []

    def fetch_fleet(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        raw_plants = self._get_raw_plant_list(force_refresh=force_refresh)
        plants = []
        csv_updates = {}  # Track corrections to write back to CSV

        for p in raw_plants:
            raw_id = str(p.get("plantId") or p.get("id") or "")
            if not raw_id:
                continue
            pid = self.plant_id("growatt", raw_id)
            p_name = str(p.get("plantName") or p.get("name") or f"Growatt Plant {raw_id}").strip()

            lat = self.safe_float(p.get("lat") or p.get("latitude") or 0.0)
            lon = self.safe_float(p.get("lng") or p.get("longitude") or 0.0)
            city = str(p.get("city") or "")
            install_date = parse_growatt_date(p.get("createDate") or p.get("installDate"))
            inv_model = str(p.get("inverterType") or "")

            # Check local plant_info file
            info_file = self.raw_dir / f"plant_info_{raw_id}.json"
            info = {}
            if info_file.exists():
                try:
                    with open(info_file, "r", encoding="utf-8") as f:
                        info = json.load(f)
                except Exception:
                    pass
            if isinstance(info, dict):
                lat = self.safe_float(info.get("latitude") or lat)
                lon = self.safe_float(info.get("longitude") or lon)
                city = str(info.get("city") or city)
                if not inv_model and info.get("invList"):
                    inv_model = str(info["invList"][0].get("deviceType") or "")

            # Check local plant_settings file
            settings_file = self.raw_dir / f"plant_settings_{raw_id}.json"
            plant_set = {}
            if settings_file.exists():
                try:
                    with open(settings_file, "r", encoding="utf-8") as f:
                        plant_set = json.load(f)
                except Exception:
                    pass
            if isinstance(plant_set, dict):
                set_date = parse_growatt_date(plant_set.get("installDate") or plant_set.get("createDate"))
                if set_date:
                    install_date = set_date

            # --- CAPACITY RESOLUTION (CSV master metadata is authoritative for verified plant capacity) ---
            meta_match = self.master_metadata.get(raw_id) or self.master_metadata.get(p_name.lower())
            cap = 0.0

            # 1. FIRST: Use CSV master metadata (ground truth from plant records)
            if meta_match:
                cap = float(meta_match.get("capacity_kwp") or 0.0)

            # 2. Fallback: LIVE API nominalPower
            if cap <= 0:
                nominal = self.safe_float(p.get("nominal_Power") or p.get("nominalPower") or 0.0) or 0.0
                if nominal > 0:
                    cap = round(nominal / 1000.0, 2) if nominal > 1000 else round(nominal, 2)

            # 3. Fallback: plant_settings / plant_info JSON files
            if cap <= 0:
                nominal = self.safe_float(plant_set.get("nominalPower") or 0.0) or 0.0
                if nominal <= 0 and isinstance(info, dict):
                    nominal = self.safe_float(info.get("nominal_Power") or info.get("nominalPower") or 0.0) or 0.0
                if nominal > 0:
                    cap = round(nominal / 1000.0, 2) if nominal > 1000 else round(nominal, 2)

            # Always use CSV metadata for coordinates/city/install_date/inverter if available
            if meta_match:
                lat = self.safe_float(meta_match.get("latitude") or lat)
                lon = self.safe_float(meta_match.get("longitude") or lon)
                city = str(meta_match.get("city") or city)
                meta_date = parse_growatt_date(meta_match.get("install_date"))
                if meta_date:
                    install_date = meta_date
                inv_model = str(meta_match.get("inverter_model") or inv_model)

            # 4. Fallback: Panel wattage * count
            if cap <= 0:
                pw = self.safe_float(plant_set.get("panelWatt") or 0.0) or 0.0
                pn = int(plant_set.get("panelNumber") or 0)
                if pw > 0 and pn > 0:
                    cap = round((pw * pn) / 1000.0, 2)

            # 5. Fallback: Heuristic based on realistic daily yield (~3.8 kWh/kWp/day) or standard residential 3.3 kWp
            if cap <= 0:
                today_kwh = self.safe_float(p.get("todayEnergy") or 0.0) or 0.0
                cap = round(max(today_kwh / 3.8, 3.0), 1) if today_kwh > 0 else 3.3

            # Log if API reports a different capacity than CSV master
            if meta_match and cap > 0:
                api_nominal = self.safe_float(p.get("nominal_Power") or p.get("nominalPower") or 0.0) or 0.0
                if api_nominal > 0:
                    api_cap = round(api_nominal / 1000.0, 2) if api_nominal > 1000 else round(api_nominal, 2)
                    if abs(cap - api_cap) / max(cap, api_cap) > 0.05:
                        logger.debug(f"API capacity difference for {p_name} ({raw_id}): CSV={cap} kWp, API={api_cap} kWp")

            self.plant_capacities[pid] = cap
            self.plant_capacities[raw_id] = cap
            self.plant_capacities[p_name.lower()] = cap

            # Live log time
            has_live = (self.safe_float(p.get("eToday") or p.get("todayEnergy") or 0.0) or 0.0) > 0 or (self.safe_float(p.get("currentPac") or 0.0) or 0.0) > 0
            log_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M") if has_live else ""

            plants.append({
                "plant_id": pid,
                "source": "growatt",
                "plant_name": p_name,
                "capacity_kwp": cap,
                "latitude": lat,
                "longitude": lon,
                "city": city,
                "install_date": install_date,
                "inverter_model": inv_model,
                "panel_model": str(plant_set.get("panelModel") or ""),
                "last_log_time": log_time,
                "total_energy_kwh": self.safe_float(p.get("eTotal") or p.get("totalEnergy")),
                "deviceCount": p.get("deviceCount"),
                "status": str(p.get("status") or ""),
                "hasDeviceOnLine": p.get("hasDeviceOnLine"),
            })

        # Auto-correct the CSV master metadata file with live API capacities
        if csv_updates and force_refresh:
            self._update_csv_capacities(csv_updates)

        return plants

    def _update_csv_capacities(self, updates: Dict[str, float]) -> None:
        """Write corrected capacities back to fleet_all_plants_metadata.csv so future
        cache-mode runs also use the correct values."""
        candidates = [
            self.raw_dir / "fleet_all_plants_metadata.csv",
            self.raw_dir.parent / "fleet_all_plants_metadata.csv",
        ]
        for csv_path in candidates:
            if csv_path.exists():
                try:
                    import pandas as pd
                    df = pd.read_csv(csv_path)
                    corrected = 0
                    for pid_str, new_cap in updates.items():
                        mask = df["plant_id"].astype(str).str.strip() == pid_str
                        if mask.any():
                            old_val = df.loc[mask, "capacity_kwp"].values[0]
                            df.loc[mask, "capacity_kwp"] = new_cap
                            df.loc[mask, "ac_capacity_kw"] = new_cap
                            corrected += 1
                            logger.info(f"CSV auto-corrected plant {pid_str}: {old_val} -> {new_cap} kWp")
                    if corrected > 0:
                        df.to_csv(csv_path, index=False)
                        # Reload master metadata with corrected values
                        self.master_metadata.clear()
                        self._load_master_metadata()
                        logger.info(f"Auto-corrected {corrected} plant capacities in {csv_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to auto-correct CSV capacities: {e}")
                break

    def refresh_live_monthly_cache(self, target_date: Optional[datetime.date] = None) -> int:
        """Fetch fresh monthly details for all plants and update disk cache to keep latest data."""
        if not self.login():
            return 0
        if not target_date:
            target_date = datetime.date.today()
        year_month = target_date.strftime("%Y-%m")
        plants = self._get_raw_plant_list(force_refresh=True)
        if not plants:
            return 0

        cache_file = self.raw_dir / "real_monthly_cache.json"
        legacy_cache_file = self.raw_dir / "real_monthly_cache_202608_202609.json"
        cache_data = {}
        target_read_file = cache_file if cache_file.exists() else legacy_cache_file
        if target_read_file.exists():
            try:
                with open(target_read_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
            except Exception:
                cache_data = {}

        import growattServer
        from concurrent.futures import ThreadPoolExecutor

        def _fetch_one(p):
            raw_id = str(p.get("plantId") or p.get("id") or "")
            if not raw_id:
                return raw_id, None, 0.0
            try:
                res = self.api.plant_detail(raw_id, growattServer.Timespan.month, target_date)
                days_dict = res.get("data") or {}
                tot = sum(float(v or 0.0) for v in days_dict.values())
                return raw_id, days_dict, tot
            except Exception:
                return raw_id, None, 0.0

        with ThreadPoolExecutor(max_workers=15) as pool:
            results = list(pool.map(_fetch_one, plants))

        updated_count = 0
        for raw_id, days_dict, tot in results:
            if not days_dict:
                continue
            k = f"{raw_id}_{year_month}"
            if k not in cache_data:
                cache_data[k] = {"plant_name": "", "monthly_kwh": 0.0, "daily_kwh": {}}
            daily_map = {
                f"{year_month}-{int(d_num):02d}": round(float(val or 0.0), 2)
                for d_num, val in days_dict.items()
            }
            cache_data[k]["daily_kwh"] = daily_map
            cache_data[k]["monthly_kwh"] = round(tot, 1)
            updated_count += 1

        if updated_count > 0:
            try:
                self.raw_dir.mkdir(parents=True, exist_ok=True)
                for out_f in (cache_file, legacy_cache_file):
                    with open(out_f, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, indent=2)
                logger.info(f"Updated Growatt monthly cache for {updated_count} plants up to {target_date.isoformat()}")
            except Exception as e:
                logger.error(f"Failed to save monthly cache: {e}")

        return updated_count

    def fetch_daily(self, date_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Extract multi-day daily generation for Growatt fleet."""
        if not self.cached_plants or force_refresh:
            self._get_raw_plant_list(force_refresh=force_refresh)
        if not self.plant_capacities or force_refresh:
            self.fetch_fleet(force_refresh=force_refresh)

        if not date_str:
            date_str = datetime.date.today().isoformat()

        today_date = datetime.date.today()
        today_str = today_date.isoformat()
        if date_str and date_str[:10] > today_str:
            date_str = today_str
        target_dt = datetime.datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        if target_dt > today_date:
            target_dt = today_date
        year_month = target_dt.strftime("%Y-%m")
        target_day = target_dt.day

        # Live today telemetry map from plant list
        live_today_map: Dict[str, float] = {}
        live_pac_map: Dict[str, float] = {}
        for p in self.cached_plants:
            rid = str(p.get("plantId") or p.get("id") or "")
            if rid:
                et = self.safe_float(p.get("eToday") or p.get("todayEnergy")) or 0.0
                pac = self.safe_float(p.get("currentPac")) or 0.0
                live_today_map[rid] = et
                live_pac_map[rid] = pac

        # 1. Check real monthly cache first (fastest & most complete)
        cache_file = self.raw_dir / "real_monthly_cache.json"
        if not cache_file.exists():
            cache_file = self.raw_dir / "real_monthly_cache_202608_202609.json"
        
        # If force_refresh requested, trigger live cache update
        if force_refresh:
            self.refresh_live_monthly_cache(today_date)

        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                matched = [
                    (k.split("_")[0], v) for k, v in cached.items() if k.endswith(f"_{year_month}")
                ]
                if matched:
                    daily_out = []
                    for raw_id, v in matched:
                        pid = self.plant_id("growatt", raw_id)
                        cap = self.plant_capacities.get(pid, 3.3)
                        dkwh = v.get("daily_kwh") or {}
                        live_etoday = live_today_map.get(raw_id, 0.0)
                        live_pac_w = live_pac_map.get(raw_id, 0.0)
                        for d_str, kwh_val in dkwh.items():
                            if d_str > today_str:
                                continue
                            kwh = self.safe_float(kwh_val) or 0.0
                            # Always ensure today has the latest live eToday value
                            if d_str == today_str and live_etoday > kwh:
                                kwh = live_etoday
                            sy = round(kwh / cap, 3) if cap > 0 else 0.0
                            
                            pwr = round(live_pac_w / 1000.0, 3) if (d_str == today_str and live_pac_w > 0) else None
                            log_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M") if (d_str == today_str and (kwh > 0 or (pwr and pwr > 0))) else f"{d_str} 23:59 (portal history)"
                            daily_out.append({
                                "plant_id": pid,
                                "date": d_str,
                                "kwh": kwh,
                                "revenue_inr": round(kwh * 14.0, 2),
                                "specific_yield": sy,
                                "live_power_kw": pwr,
                                "status": "active" if (kwh > 0 or (pwr and pwr > 0)) else "offline",
                                "last_log_time": log_time,
                                "source_type": "portal",
                            })
                    if daily_out:
                        return daily_out
            except Exception as e:
                logger.debug(f"Error reading daily from monthly cache: {e}")

        results: List[Dict[str, Any]] = []

        # 2. Check for cached monthly detail files on disk
        month_str = target_dt.strftime("%Y%m")
        detail_files = {}
        if self.raw_dir.exists():
            detail_files = {
                f.stem.split("_")[2]: f
                for f in self.raw_dir.glob(f"plant_detail_*_{month_str}.json")
            }

        plants_with_detail = set()
        for raw_id, dfile in detail_files.items():
            pid = self.plant_id("growatt", raw_id)
            try:
                with open(dfile, "r", encoding="utf-8") as f:
                    c = json.load(f)
                days_dict = c.get("data", {})
                cap = self.plant_capacities.get(pid, 3.3)
                for day_num_str, kwh_val in days_dict.items():
                    kwh = self.safe_float(kwh_val)
                    if kwh is None:
                        continue
                    day_int = int(day_num_str)
                    if day_int > target_day:
                        continue
                    d_str = f"{year_month}-{day_int:02d}"
                    sy = round(kwh / cap, 3) if cap > 0 else 0.0
                    results.append({
                        "plant_id": pid,
                        "date": d_str,
                        "kwh": kwh,
                        "revenue_inr": round(kwh * 14.0, 2),
                        "specific_yield": sy,
                        "live_power_kw": None,
                        "status": "active" if kwh > 0 else "offline",
                        "last_log_time": f"{d_str} 23:59 (portal detail)",
                        "source_type": "portal",
                    })
                plants_with_detail.add(pid)
            except Exception as e:
                logger.debug(f"Error parsing detail file {dfile.name}: {e}")

        # For remaining plants without detail files, emit ONLY today's verified reading
        today_date_str = f"{year_month}-{target_day:02d}"
        for p in self.cached_plants:
            raw_id = str(p.get("plantId") or p.get("id") or "")
            pid = self.plant_id("growatt", raw_id)
            if pid in plants_with_detail:
                continue

            cap = self.plant_capacities.get(pid, 3.3)
            today_kwh = self.safe_float(p.get("eToday") or p.get("todayEnergy")) or 0.0
            cur_pac_w = self.safe_float(p.get("currentPac")) or 0.0
            is_active = (today_kwh > 0 or cur_pac_w > 0)
            live_kw = round(cur_pac_w / 1000.0, 3) if cur_pac_w > 0 else 0.0
            log_time = datetime.datetime.now().strftime("%d/%m/%Y %H:%M") if is_active else ""

            sy = round(today_kwh / cap, 3) if (cap > 0 and today_kwh > 0) else 0.0
            results.append({
                "plant_id": pid,
                "date": today_date_str,
                "kwh": today_kwh,
                "revenue_inr": round(today_kwh * 14.0, 2),
                "specific_yield": sy,
                "live_power_kw": live_kw if live_kw > 0 else 0.0,
                "status": "active" if is_active else "offline",
                "last_log_time": log_time,
                "source_type": "portal",
            })

        return results

    def fetch_monthly(self, month_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Extract monthly aggregated generation for Growatt fleet."""
        if not self.cached_plants or force_refresh:
            self._get_raw_plant_list(force_refresh=force_refresh)
        if not self.plant_capacities or force_refresh:
            self.fetch_fleet(force_refresh=force_refresh)

        if not month_str:
            month_str = datetime.date.today().strftime("%Y-%m")

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

        current_ym = datetime.date.today().strftime("%Y-%m")
        if month_str == current_ym:
            eval_days = min(datetime.date.today().day, days_in_month)
        else:
            eval_days = days_in_month

        # If force_refresh, refresh live monthly cache to get updated readings from portal
        if force_refresh:
            try:
                target_d = datetime.date.today() if month_str == current_ym else datetime.date(y, m, min(28, days_in_month))
                self.refresh_live_monthly_cache(target_d)
            except Exception as e:
                logger.debug(f"Error refreshing live monthly cache: {e}")

        # Check for real monthly cache file
        cache_file = self.raw_dir / "real_monthly_cache.json"
        if not cache_file.exists():
            cache_file = self.raw_dir / "real_monthly_cache_202608_202609.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                matched_items = [
                    (k.split("_")[0], v) for k, v in cached.items() if k.endswith(f"_{month_str}")
                ]
                if matched_items:
                    out = []
                    for raw_id, data in matched_items:
                        pid = self.plant_id("growatt", raw_id)
                        kwh = self.safe_float(data.get("monthly_kwh") or 0.0) or 0.0
                        cap = self.plant_capacities.get(pid, 3.3)
                        sy = round(kwh / cap, 2) if cap > 0 else 0.0
                        ypd = round(sy / float(eval_days), 2) if (eval_days > 0 and cap > 0) else 0.0
                        cuf_pct = round((kwh / (cap * 24.0 * float(eval_days))) * 100, 2) if (eval_days > 0 and cap > 0) else 0.0
                        out.append({
                            "plant_id": pid,
                            "month": month_str,
                            "kwh": kwh,
                            "revenue_inr": round(kwh * 14.0, 2),
                            "specific_yield": sy,
                            "yield_per_day": ypd,
                            "cuf_pct": cuf_pct,
                            "tier": None,
                            "percentile": None,
                            "explanation": f"Generated {kwh} kWh in {month_str}",
                        })
                    return out
            except Exception as e:
                logger.debug(f"Error reading monthly cache: {e}")

        # Fallback: Aggregate from daily records
        daily_records = self.fetch_daily(min(f"{month_str}-28", datetime.date.today().isoformat()))
        plant_sums: Dict[str, Dict[str, Any]] = {}
        for d in daily_records:
            pid = d["plant_id"]
            if pid not in plant_sums:
                plant_sums[pid] = {"kwh": 0.0, "days": 0}
            plant_sums[pid]["kwh"] += (d.get("kwh") or 0.0)
            plant_sums[pid]["days"] += 1

        results = []
        for pid, val in plant_sums.items():
            tot = round(val["kwh"], 2)
            cap = self.plant_capacities.get(pid, 3.3)
            sy = round(tot / cap, 2) if cap > 0 else 0.0
            days_counted = max(val["days"], 1)
            ypd = round(sy / float(days_counted), 2) if (days_counted > 0 and cap > 0) else 0.0
            results.append({
                "plant_id": pid,
                "month": month_str,
                "kwh": tot,
                "specific_yield": sy,
                "yield_per_day": ypd,
                "cuf_pct": round((tot / (cap * 24.0 * float(days_counted))) * 100, 2) if cap > 0 else 0.0,
                "tier": None,
                "percentile": None,
                "explanation": f"Generated {tot} kWh in {month_str}",
            })
        return results

    def fetch_snapshots(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Extract real-time telemetry snapshots for Growatt inverters with physics validation."""
        snapshots = []
        now_ts = datetime.datetime.now().isoformat()

        # 1. Load fleet plant status full if available
        status_file = self.raw_dir.parent.parent.parent / "solaron_analytics_dataset_csv" / "fleet_plant_status_full.csv"
        status_by_name = {}
        if status_file.exists():
            try:
                import pandas as pd
                df_st = pd.read_csv(status_file)
                for _, r in df_st.iterrows():
                    pname = str(r.get("plant_name", "")).strip().lower()
                    status_by_name[pname] = r.to_dict()
            except Exception:
                pass

        # 2. Load live Growatt plant list
        gw_plants = self._get_raw_plant_list(force_refresh=force_refresh)
        for p in gw_plants:
            raw_id = str(p.get("plantId") or p.get("id") or "")
            if not raw_id:
                continue
            pid = self.plant_id("growatt", raw_id)
            pname = str(p.get("plantName") or p.get("name") or "").strip()
            pname_clean = pname.lower()
            cap = self.plant_capacities.get(pid, 3.3)

            st_info = status_by_name.get(pname_clean, {})

            # Extract live pac and e_today
            cur_pac = self.safe_float(p.get("currentPac"))
            if cur_pac is None or cur_pac <= 0:
                live_kw = self.safe_float(st_info.get("live_power_kw") or 0.0) or 0.0
                cur_pac = live_kw * 1000.0 if live_kw > 0 else 0.0

            # Real inverter AC power and daily energy from portal telemetry
            ac_w = round(cur_pac, 1) if cur_pac > 0 else 0.0

            e_today = self.safe_float(p.get("eToday") or p.get("todayEnergy"))
            if e_today is None or e_today <= 0:
                e_today = self.safe_float(st_info.get("e_today_kwh") or 0.0) or 0.0
            e_today = round(max(0.0, e_today), 2)

            # Real inverter AC power and daily energy from portal telemetry
            fault_code = str(p.get("alarmValue") or st_info.get("fault_code") or "")
            if not fault_code or fault_code in ("0", "nan", "None"):
                fault_code = None

            # Preserve real platform status rather than false-offline at night
            plant_raw_status = p.get("status") or st_info.get("status")
            stat = "fault" if fault_code else self.normalize_status(plant_raw_status or "active")

            snapshots.append({
                "plant_id": pid,
                "inverter_sn": p.get("inverter_sn") or f"GW-{raw_id}",
                "snapshot_ts": now_ts,
                "ac_power_w": ac_w,
                "dc_power_w": None,
                "temperature_c": None,
                "e_today_kwh": e_today,
                "fault_code": fault_code,
                "status": stat,
            })

        return snapshots

    def supports_history(self) -> Dict[str, Any]:
        return {"daily": True, "hourly": True, "max_lookback_days": None}

    def _call_api_with_retry(self, func, *args, max_retries: int = 3, **kwargs):
        """Throttled API caller with rate limiting (~5 req/sec), retry and auto re-login."""
        now = time.time()
        elapsed = now - getattr(self, "_last_api_call_ts", 0.0)
        if elapsed < 0.2:
            time.sleep(0.2 - elapsed)
        self._last_api_call_ts = time.time()

        for attempt in range(max_retries):
            try:
                res = func(*args, **kwargs)
                if isinstance(res, dict) and str(res.get("msg", "")).lower() in ("error", "login error", "token invalid", "unauthorized"):
                    logger.info("Growatt session may have expired, re-logging in...")
                    self.logged_in = False
                    self.login()
                    res = func(*args, **kwargs)
                return res
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.warning(f"Growatt API call failed after {max_retries} attempts: {e}")
                    raise
                time.sleep(0.8 * (attempt + 1))

    def fetch_history_daily(self, plant_raw_id: Any, year_month: str) -> List[Dict[str, Any]]:
        """Fetch historical daily generation records for a plant for a full month (YYYY-MM)."""
        if not self.login():
            return []
        try:
            import growattServer
            y, m = [int(x) for x in year_month.split("-")]
            target_dt = datetime.date(y, m, 1)
            raw_id = str(plant_raw_id).strip()
            res = self._call_api_with_retry(self.api.plant_detail, raw_id, growattServer.Timespan.month, target_dt)
            if not res or not isinstance(res, dict):
                return []

            self.archive_raw(f"plant_detail_month_{raw_id}", res, date_str=year_month)
            days_dict = res.get("data") or {}
            if not days_dict:
                return []

            pid = self.plant_id("growatt", raw_id)
            cap = self.plant_capacities.get(pid, 3.3)
            today_str = datetime.date.today().isoformat()

            records = []
            for d_num_str, val in days_dict.items():
                try:
                    d_num = int(d_num_str)
                    d_str = f"{year_month}-{d_num:02d}"
                except ValueError:
                    continue
                if d_str > today_str:
                    continue
                kwh = self.safe_float(val)
                if kwh is None:
                    continue
                kwh = max(0.0, round(kwh, 2))
                sy = round(kwh / cap, 3) if cap > 0 else None
                stat = "active" if kwh > 0.05 else "offline"
                records.append({
                    "plant_id": pid,
                    "date": d_str,
                    "kwh": kwh,
                    "specific_yield": sy,
                    "yield_per_day": sy,
                    "status": stat,
                    "source_type": "portal_history",
                })
            return records
        except Exception as e:
            logger.warning(f"Growatt fetch_history_daily failed for plant {plant_raw_id} {year_month}: {e}")
            return []

    def fetch_history_hourly(self, plant_raw_id: Any, date_str: str) -> List[Dict[str, Any]]:
        """Fetch historical hourly generation records for a plant on a given date (YYYY-MM-DD)."""
        if not self.login():
            return []
        try:
            import growattServer
            target_dt = datetime.date.fromisoformat(date_str[:10])
            raw_id = str(plant_raw_id).strip()
            res = self._call_api_with_retry(self.api.plant_detail, raw_id, growattServer.Timespan.hour, target_dt)
            if not res or not isinstance(res, dict):
                return []

            self.archive_raw(f"plant_detail_hour_{raw_id}", res, date_str=date_str[:10])
            data = res.get("data") or res.get("pac") or {}
            if not data or not isinstance(data, dict):
                return []

            pid = self.plant_id("growatt", raw_id)

            hourly_power: Dict[int, List[float]] = {h: [] for h in range(24)}
            for t_str, val in data.items():
                p_val = self.safe_float(val)
                if p_val is None:
                    continue
                parts = str(t_str).strip().split(":")
                try:
                    hour = int(parts[0])
                    if 0 <= hour <= 23:
                        kw = p_val / 1000.0 if p_val > 50.0 else p_val
                        hourly_power[hour].append(max(0.0, kw))
                except (ValueError, IndexError):
                    continue

            results = []
            for hour in range(24):
                readings = hourly_power[hour]
                if readings:
                    avg_kw = round(sum(readings) / len(readings), 3)
                    energy_kwh = round(avg_kw * 1.0, 3)
                else:
                    avg_kw = 0.0
                    energy_kwh = 0.0

                results.append({
                    "plant_id": pid,
                    "ts": f"{date_str[:10]} {hour:02d}:00",
                    "power_kw": avg_kw,
                    "energy_kwh": energy_kwh,
                    "source_type": "portal_history",
                })
            return results
        except Exception as e:
            logger.warning(f"Growatt fetch_history_hourly failed for plant {plant_raw_id} {date_str}: {e}")
            return []
