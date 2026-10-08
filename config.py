from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    growatt_user: str = ""
    growatt_password: str = ""
    growatt_server_url: str = "https://server-api.growatt.com/"
    isolarcloud_user: str = ""
    isolarcloud_password: str = ""
    isolarcloud_url: str = "https://web3.isolarcloud.in/"
    suryalog_user: str = ""
    suryalog_password: str = ""
    suryalog_url: str = "https://cloud.suryalog.ae/"
    database_url: str = ""
    solar_analytics_db_path: str = str(BASE_DIR / "data" / "solar_analytics.db")
    crm_db_path: str = str(BASE_DIR / "data" / "crm_data.db")
    aisensy_api_key: str = ""
    freshworks_api_key: str = ""
    gupshup_api_key: str = ""
    gupshup_app_name: str = "SolaronHomes"
    gupshup_source_number: str = "919619455207"
    gupshup_webhook_secret: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "ap-south-1"
    s3_bucket_name: str = "solaron-data"
    support_phone: str = ""
    test_phone_number: str = ""
    price_per_unit: float = 14.0
    scheduler_enabled: bool = False
    playwright_headless: bool = True
    app_port: int = 8000
    export_api_key: str = ""
    gupshup_send_mode: str = "test_only"  # off | test_only | live

    # --- Gupshup Approved Template IDs ---
    gupshup_tpl_active: str = "solaron_active"
    gupshup_tpl_average: str = "solaron_average"
    gupshup_tpl_critical_perf: str = "solaron_critical_perf"
    gupshup_tpl_offline: str = "solaron_offline"
    gupshup_tpl_inactive: str = "solaron_inactive"
    gupshup_tpl_plant_critical: str = "solaron_plant_critical"
    gupshup_tpl_offer_visit: str = "solaron_offer_visit"
    gupshup_tpl_wait_recheck: str = "solaron_wait_recheck"
    gupshup_tpl_reminder: str = "solaron_reminder"
    gupshup_tpl_monthly: str = "solaron_monthly_statement"

    # --- Message Templates ---
    msg_active: str = ""
    msg_offline: str = ""
    msg_monsoon: str = ""
    msg_daily: str = ""
    msg_weekly: str = ""
    msg_yearly: str = ""

    @property
    def resolved_solar_analytics_db_path(self) -> str:
        p = Path(self.solar_analytics_db_path)
        if not p.is_absolute():
            return str((BASE_DIR / p).resolve())
        return str(p)

    @property
    def resolved_crm_db_path(self) -> str:
        p = Path(self.crm_db_path)
        if not p.is_absolute():
            return str((BASE_DIR / p).resolve())
        return str(p)

    class Config:
        env_file = (
            str(BASE_DIR / ".env")
            if (BASE_DIR / ".env").exists()
            else (str(BASE_DIR.parent / ".env") if (BASE_DIR.parent / ".env").exists() else ".env")
        )
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
