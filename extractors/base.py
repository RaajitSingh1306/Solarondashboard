import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseExtractor(ABC):
    def __init__(self, source_name: str):
        self.source_name = source_name

    @property
    def source(self) -> str:
        return self.source_name

    @abstractmethod
    def login(self) -> bool:
        """Authenticate with platform."""
        pass

    @abstractmethod
    def fetch_fleet(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch all plants matching plants schema."""
        pass

    @abstractmethod
    def fetch_daily(self, date_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch daily generation records matching daily_generation schema."""
        pass

    @abstractmethod
    def fetch_monthly(self, month_str: Optional[str] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch monthly generation records matching monthly_generation schema."""
        pass

    @abstractmethod
    def fetch_snapshots(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch inverter snapshots matching inverter_snapshots schema."""
        pass

    @staticmethod
    def safe_float(val: Any) -> Optional[float]:
        """Parse numeric field, return None on null/empty/dash."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip()
        if not s or s in ("-", "--", "null", "None", "N/A", "nan"):
            return None
        clean = re.sub(r"[^\d.-]", "", s)
        try:
            return float(clean)
        except ValueError:
            return None

    @staticmethod
    def normalize_status(raw: Any) -> str:
        """Map platform codes -> active | offline | fault | unknown."""
        if raw is None:
            return "unknown"
        s = str(raw).strip().lower()
        if s in ("1", "normal", "active", "online", "connected", "ok"):
            return "active"
        if s in ("0", "offline", "disconnected", "communication interrupted", "lost"):
            return "offline"
        if s in ("3", "fault", "abnormal", "alarm", "error", "warning"):
            return "fault"
        return "unknown"

    @classmethod
    def plant_id(cls, source_prefix: str, raw_id: Any) -> str:
        """Generate unique plant ID with prefix: growatt_12345, isc_Name, syr_Name."""
        raw_clean = re.sub(r"[^\w-]", "_", str(raw_id).strip())
        return f"{source_prefix}_{raw_clean}"
