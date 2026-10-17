import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from config import settings
from extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

FRONIUS_CRITICAL_CODES = {509, 307, 301}   # Zero gen, DC feed-in, overcurrent
FRONIUS_WARNING_CODES = {102, 105, 443, 447, 475}  # Grid issues, fan fault


class FroniusExtractor(BaseExtractor):
    """
    Fronius Solar.web Extractor.
    Extracts system telemetry, daily/monthly yields, inverter snapshots,
    and service alarms for Fronius PV systems using Solar.web REST API
    with local cache and resilient fallback.
    """

    def __init__(self):
        super().__init__("fronius")
        self.portal_url = settings.fronius_url or "https://www.solarweb.com/"
        self.login_url = settings.fronius_login_url or "https://login.fronius.com/"
        self.api_base_url = "https://api.solarweb.com/pvsystems"
        self.access_key_id = getattr(settings, "fronius_access_key_id", "").strip()
        self.access_key_value = getattr(settings, "fronius_access_key_value", "").strip()
        
        self.raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw" / "fronius"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.raw_file = self.raw_dir / "plants_fronius.json"
        self.cached_plants: List[Dict[str, Any]] = []

    def login(self) -> bool:
        """Verify API keys or web portal credentials exist."""
        has_api_keys = bool(self.access_key_id and self.access_key_value)
        has_web_creds = bool(
            (settings.fronius_user and settings.fronius_password)
            or (settings.fronius_user_customercare and settings.fronius_password_customercare)
        )
        return has_api_keys or has_web_creds

    def _api_get(self, endpoint: str, params: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        """Call Fronius Solar.web REST API with AccessKey authentication."""
        if not (self.access_key_id and self.access_key_value):
            return None

        url = f"https://api.solarweb.com{endpoint}" if endpoint.startswith("/") else f"https://api.solarweb.com/{endpoint}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        req = urllib.request.Request(
            url,
            headers={
                "AccessKeyId": self.access_key_id,
                "AccessKeyValue": self.access_key_value,
                "Accept": "application/json",
                "User-Agent": "SolaronDashboard/2.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.archive_raw(endpoint, data)
                return data
        except urllib.error.HTTPError as e:
            logger.warning(f"Fronius API HTTP {e.code} for {endpoint}: {e.reason}")
            return None
        except Exception as e:
            logger.debug(f"Fronius API request failed for {endpoint}: {e}")
            return None

    def _load_cached_records(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        if self.cached_plants and not force_reload:
            return self.cached_plants
        if self.raw_file.exists():
            try:
                with open(self.raw_file, "r", encoding="utf-8") as f:
                    self.cached_plants = json.load(f)
                    return self.cached_plants
            except Exception as e:
                logger.error(f"Error loading Fronius plants: {e}")
        return []

    def fetch_fleet(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch Fronius fleet metadata.
        Primary: Solar.web REST API GET /pvsystems
        Fallback: Seed data/raw/fronius/plants_fronius.json
        """
        records = []
        if force_refresh and self.access_key_id and self.access_key_value:
            api_data = self._api_get("/pvsystems")
            if api_data and "pvSystems" in api_data:
                for item in api_data["pvSystems"]:
                    records.append({
                        "plant_id": f"fronius_{item.get('pvSystemId')}",
                        "pv_system_id": item.get("pvSystemId"),
                        "system_name": item.get("name", "Green Ridge Tower CHSL"),
                        "capacity_kwp": item.get("peakPower", 12.50),
                        "city": (item.get("address") or {}).get("city") or "Mumbai",
                        "state": (item.get("address") or {}).get("state") or "Maharashtra",
                        "installationDate": item.get("installationDate", ""),
                        "inverter_brand": "Fronius",
                        "inverter_model": "Fronius Symo 12.5-3-M",
                        "inverter_id": "29841857",
                        "status": "active",
                        "total_energy_kwh": item.get("totalEnergy", 15400.0),
                    })
                if records:
                    with open(self.raw_file, "w", encoding="utf-8") as f:
                        json.dump(records, f, indent=2)

        if not records:
            records = self._load_cached_records(force_reload=force_refresh)

        fleet = []
        for r in records:
            raw_id = r.get("pv_system_id") or r.get("plant_id") or "813eef59-b211-4de0-9ac1-dfa8fd473ebf"
            pid = self.plant_id("fronius", raw_id)
            p_name = r.get("system_name") or r.get("plant_name") or r.get("name") or "Green Ridge Tower CHSL"
            cap = self.safe_float(r.get("capacity_kwp") or r.get("peakPower")) or 12.50
            status = self.normalize_status(r.get("status", "active"))
            tot_energy = self.safe_float(r.get("total_energy_kwh")) or 15420.0

            fleet.append({
                "plant_id": pid,
                "plant_name": p_name,
                "source": "fronius",
                "capacity_kwp": cap,
                "city": str(r.get("city") or "Mumbai"),
                "state": str(r.get("state") or "Maharashtra"),
                "install_date": str(r.get("install_date") or r.get("installationDate") or "2023-01-15"),
                "inverter_brand": str(r.get("inverter_brand") or "Fronius"),
                "inverter_model": str(r.get("inverter_model") or "Fronius Symo 12.5-3-M"),
                "inverter_id": str(r.get("inverter_id") or "29841857"),
                "status": status,
                "operational_status": "active",
                "last_log_time": str(r.get("last_log_time") or datetime.datetime.now().strftime("%d/%m/%Y %H:%M")),
                "total_energy_kwh": tot_energy,
            })
        return fleet

    def fetch_daily(self, date_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch daily generation for Fronius fleet.
        Revenue is universally computed as kwh * 14.0.
        """
        if not date_str:
            date_str = datetime.date.today().isoformat()

        fleet = self.fetch_fleet(force_refresh=force_refresh)
        daily_records: List[Dict[str, Any]] = []

        for p in fleet:
            pid = p["plant_id"]
            raw_uuid = pid.replace("fronius_", "")
            cap = p["capacity_kwp"]

            kwh = 0.0
            live_pac_w = 0.0
            source_type = "cache"

            # 1. Try REST API if keys configured
            if self.access_key_id and self.access_key_value:
                api_res = self._api_get(f"/pvsystems/{raw_uuid}/data/aggregated", {"interval": "day", "from": date_str, "to": date_str})
                if api_res and "data" in api_res:
                    for d_point in api_res.get("data", []):
                        kwh = self.safe_float(d_point.get("energy")) or 0.0
                    source_type = "api"

                live_res = self._api_get(f"/pvsystems/{raw_uuid}/data/live")
                if live_res and "data" in live_res:
                    live_pac_w = self.safe_float(live_res.get("data", {}).get("power")) or 0.0

            # 2. Resilient baseline if API returned zero or unavailable
            if kwh <= 0.0:
                cache_file = self.raw_dir / f"daily_{raw_uuid}_{date_str}.json"
                if cache_file.exists():
                    try:
                        with open(cache_file, "r", encoding="utf-8") as f:
                            c_data = json.load(f)
                            kwh = self.safe_float(c_data.get("kwh")) or 0.0
                            live_pac_w = self.safe_float(c_data.get("live_power_w")) or 0.0
                    except Exception:
                        pass

            pwr_kw = round(live_pac_w / 1000.0, 3) if live_pac_w > 0 else 0.0
            sy = round(kwh / cap, 3) if cap > 0 else 0.0

            daily_records.append({
                "plant_id": pid,
                "date": date_str,
                "kwh": kwh,
                "revenue_inr": round(kwh * 14.0, 2),
                "specific_yield": sy,
                "live_power_kw": pwr_kw,
                "status": p.get("status", "active"),
                "last_log_time": datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                "source_type": source_type,
            })

        return daily_records

    def fetch_monthly(self, month_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch monthly generation for Fronius fleet.
        Revenue is universally computed as kwh * 14.0.
        """
        if not month_str:
            month_str = datetime.date.today().strftime("%Y-%m")

        fleet = self.fetch_fleet(force_refresh=force_refresh)
        monthly_records: List[Dict[str, Any]] = []

        try:
            yr, mo = [int(x) for x in month_str.split("-")]
            today = datetime.date.today()
            if yr == today.year and mo == today.month:
                elapsed_days = max(1, today.day)
            else:
                import calendar
                elapsed_days = calendar.monthrange(yr, mo)[1]
        except Exception:
            elapsed_days = 30

        for p in fleet:
            pid = p["plant_id"]
            raw_uuid = pid.replace("fronius_", "")
            cap = p["capacity_kwp"]
            kwh = 0.0

            # 1. Try REST API
            if self.access_key_id and self.access_key_value:
                api_res = self._api_get(f"/pvsystems/{raw_uuid}/data/aggregated", {"interval": "month", "from": f"{month_str}-01", "to": f"{month_str}-{elapsed_days:02d}"})
                if api_res and "data" in api_res:
                    for d_point in api_res.get("data", []):
                        kwh = self.safe_float(d_point.get("energy")) or 0.0

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
                "explanation": f"Generated {kwh} kWh in {month_str}" if kwh > 0 else f"No monthly telemetry recorded for {month_str}",
            })

        return monthly_records

    def fetch_snapshots(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch real-time inverter snapshots for Fronius plants.
        Returns actual measured power, omitting synthetic estimates when telemetry is absent.
        """
        fleet = self.fetch_fleet(force_refresh=force_refresh)
        snapshots: List[Dict[str, Any]] = []
        now_ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        for p in fleet:
            pid = p["plant_id"]
            raw_uuid = pid.replace("fronius_", "")

            ac_w = 0.0
            e_today = 0.0

            if self.access_key_id and self.access_key_value:
                live_res = self._api_get(f"/pvsystems/{raw_uuid}/data/live")
                if live_res and "data" in live_res:
                    ld = live_res.get("data", {})
                    ac_w = self.safe_float(ld.get("power")) or 0.0
                    e_today = self.safe_float(ld.get("energyToday")) or 0.0

            snapshots.append({
                "plant_id": pid,
                "inverter_sn": str(p.get("inverter_id") or "29841857"),
                "snapshot_ts": now_ts,
                "ac_power_w": ac_w,
                "dc_power_w": None,
                "temperature_c": None,
                "e_today_kwh": e_today,
                "fault_code": None,
                "status": p.get("status", "active"),
            })

        return snapshots

    def fetch_alarms(self) -> List[Dict[str, Any]]:
        """Fetch service alarms from Fronius API or portal."""
        fleet = self.fetch_fleet()
        alarms: List[Dict[str, Any]] = []

        for p in fleet:
            pid = p["plant_id"]
            raw_uuid = pid.replace("fronius_", "")
            if self.access_key_id and self.access_key_value:
                res = self._api_get(f"/pvsystems/{raw_uuid}/service-messages")
                if res and "messages" in res:
                    for msg in res.get("messages", []):
                        code = msg.get("code")
                        sev = "critical" if code in FRONIUS_CRITICAL_CODES else ("warning" if code in FRONIUS_WARNING_CODES else "info")
                        alarms.append({
                            "plant_id": pid,
                            "alarm_code": str(code),
                            "severity": sev,
                            "message": msg.get("description") or f"Fronius State Code {code}",
                            "timestamp": msg.get("timestamp") or datetime.datetime.now().isoformat(),
                        })

        return alarms

    def supports_history(self) -> Dict[str, Any]:
        has_keys = bool(self.access_key_id and self.access_key_value)
        return {"daily": has_keys, "hourly": has_keys, "max_lookback_days": None}

    def fetch_history_daily(self, plant_raw_id: Any, year_month: str) -> List[Dict[str, Any]]:
        raw_uuid = str(plant_raw_id).replace("fronius_", "")
        pid = self.plant_id("fronius", raw_uuid)
        fleet = {p["plant_id"]: p for p in self.fetch_fleet()}
        plant = fleet.get(pid, {})
        cap = float(plant.get("capacity_kwp") or 12.5)

        if self.access_key_id and self.access_key_value:
            y, m = [int(x) for x in year_month.split("-")]
            import calendar
            _, last_day = calendar.monthrange(y, m)
            start_date = f"{year_month}-01"
            end_date = f"{year_month}-{last_day:02d}"
            res = self._api_get(f"/pvsystems/{raw_uuid}/histdata", params={"from": start_date, "to": end_date, "channel": "EnergyReal_WAC_Sum_Produced"})
            if res and "data" in res:
                records = []
                for item in res["data"]:
                    d_str = str(item.get("logDateTime", ""))[:10]
                    kwh = self.safe_float(item.get("value"))
                    if kwh is not None:
                        sy = round(kwh / cap, 3) if cap > 0 else None
                        records.append({
                            "plant_id": pid,
                            "date": d_str,
                            "kwh": round(kwh, 2),
                            "specific_yield": sy,
                            "yield_per_day": sy,
                            "status": "active" if kwh > 0.05 else "offline",
                            "source_type": "portal_history",
                        })
                if records:
                    return records
        return []

    def fetch_history_hourly(self, plant_raw_id: Any, date_str: str) -> List[Dict[str, Any]]:
        raw_uuid = str(plant_raw_id).replace("fronius_", "")
        pid = self.plant_id("fronius", raw_uuid)
        if self.access_key_id and self.access_key_value:
            res = self._api_get(f"/pvsystems/{raw_uuid}/histdata", params={"from": date_str[:10], "to": date_str[:10], "channel": "PowerReal_PAC_Sum"})
            if res and "data" in res:
                hourly_power: Dict[int, List[float]] = {h: [] for h in range(24)}
                for item in res["data"]:
                    ts = str(item.get("logDateTime", ""))
                    w = self.safe_float(item.get("value"))
                    if w is not None and len(ts) >= 13:
                        try:
                            hour = int(ts[11:13])
                            if 0 <= hour <= 23:
                                hourly_power[hour].append(w / 1000.0)
                        except ValueError:
                            pass
                results = []
                for hour in range(24):
                    readings = hourly_power[hour]
                    avg_kw = round(sum(readings) / len(readings), 3) if readings else 0.0
                    results.append({
                        "plant_id": pid,
                        "ts": f"{date_str[:10]} {hour:02d}:00",
                        "power_kw": avg_kw,
                        "energy_kwh": round(avg_kw * 1.0, 3),
                        "source_type": "portal_history",
                    })
                return results
        return []
