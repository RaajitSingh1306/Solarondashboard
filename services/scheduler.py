import datetime
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings

try:
    from pipeline import pipeline, db
    from core import analytics
    from services import crm, s3_archive
    from engines import escalation_state_machine
except ImportError:
    import pipeline
    import db
    import analytics
    import crm
    import s3_archive
    import escalation_state_machine

logger = logging.getLogger(__name__)

# Run lock so manual Live Sync and scheduled background jobs never overlap
_SYNC_LOCK = threading.Lock()
_CURRENT_SYNC_INFO: Dict[str, Any] = {
    "running": False,
    "job_name": None,
    "started_at": None,
}

# Explicit Indian Standard Time (IST) timezone
IST_TIMEZONE = "Asia/Kolkata"
scheduler = BackgroundScheduler(timezone=IST_TIMEZONE)


def acquire_sync_lock(job_name: str) -> bool:
    """Attempts to acquire the global sync lock non-blockingly."""
    acquired = _SYNC_LOCK.acquire(blocking=False)
    if acquired:
        _CURRENT_SYNC_INFO["running"] = True
        _CURRENT_SYNC_INFO["job_name"] = job_name
        _CURRENT_SYNC_INFO["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        logger.info(f"Sync lock acquired for: {job_name}")
    else:
        logger.warning(f"Could not acquire sync lock for '{job_name}'. Another sync ({_CURRENT_SYNC_INFO.get('job_name')}) is running.")
    return acquired


def release_sync_lock():
    """Releases the global sync lock."""
    _CURRENT_SYNC_INFO["running"] = False
    _CURRENT_SYNC_INFO["job_name"] = None
    _CURRENT_SYNC_INFO["started_at"] = None
    try:
        _SYNC_LOCK.release()
        logger.info("Sync lock released.")
    except RuntimeError:
        pass


def is_sync_running() -> bool:
    return bool(_CURRENT_SYNC_INFO["running"])


def get_sync_status() -> Dict[str, Any]:
    return dict(_CURRENT_SYNC_INFO)


# ---------------------------------------------------------------------------
# Daytime Sync Jobs
# ---------------------------------------------------------------------------

def run_growatt_daytime_sync():
    """High-frequency Growatt sync (15 min, 06:00-19:00 IST)."""
    if not acquire_sync_lock("growatt_daytime_sync"):
        return
    try:
        logger.info("Executing 15-minute Growatt daytime sync...")
        pipeline.run_fleet(sources=["growatt"], force_refresh=True)
        pipeline.run_daily(sources=["growatt"], force_refresh=True)
        cur_month = datetime.date.today().strftime("%Y-%m")
        pipeline.run_monthly(month_str=cur_month, sources=["growatt"], force_refresh=True)
        pipeline.run_snapshots(sources=["growatt"], force_refresh=True)
        analytics.classify_all(cur_month)
        logger.info("Growatt daytime sync completed successfully.")
    except Exception as e:
        logger.error(f"Error during Growatt daytime sync: {e}", exc_info=True)
    finally:
        release_sync_lock()


def run_browser_portals_daytime_sync():
    """Mid-frequency browser scrapes for iSolarCloud & SuryaLog (30 min, 06:00-19:00 IST)."""
    if not acquire_sync_lock("browser_portals_daytime_sync"):
        return
    try:
        logger.info("Executing 30-minute iSolarCloud & SuryaLog daytime sync...")
        sources = ["isolarcloud", "suryalog"]
        pipeline.run_fleet(sources=sources, force_refresh=True)
        pipeline.run_daily(sources=sources, force_refresh=True)
        cur_month = datetime.date.today().strftime("%Y-%m")
        pipeline.run_monthly(month_str=cur_month, sources=sources, force_refresh=True)
        pipeline.run_snapshots(sources=sources, force_refresh=True)
        analytics.classify_all(cur_month)
        logger.info("Browser portals daytime sync completed successfully.")
    except Exception as e:
        logger.error(f"Error during browser portals daytime sync: {e}", exc_info=True)
    finally:
        release_sync_lock()


def run_nightly_daily_close():
    """Nightly close at 23:30 IST: full final extract, loss analysis, and classification."""
    if not acquire_sync_lock("nightly_daily_close"):
        return
    try:
        logger.info("Executing nightly daily close at 23:30 IST...")
        today_str = datetime.date.today().isoformat()
        cur_month = datetime.date.today().strftime("%Y-%m")
        pipeline.run_full_extract(month_str=cur_month, force_refresh=True)

        # On the 1st-3rd of each month, also perform final sync of previous month
        today_day = datetime.date.today().day
        if today_day <= 3:
            first_of_cur = datetime.date.today().replace(day=1)
            prev_month_dt = first_of_cur - datetime.timedelta(days=1)
            prev_month = prev_month_dt.strftime("%Y-%m")
            logger.info(f"Day {today_day} of month: performing final reconcile for previous month {prev_month}...")
            pipeline.run_monthly(month_str=prev_month, force_refresh=True)
            analytics.classify_all(prev_month)
            analytics.calculate_loss_analysis(prev_month)

        analytics.classify_all(cur_month)
        analytics.calculate_loss_analysis(cur_month)

        # Archive to S3 and database backups
        s3_archive.run_nightly_archive(today_str)
        logger.info("Nightly daily close completed.")
    except Exception as e:
        logger.error(f"Error during nightly daily close: {e}", exc_info=True)
    finally:
        release_sync_lock()


def setup_scheduler():
    # 1. Growatt daytime sync every 15 min between 06:00 and 19:00 IST
    scheduler.add_job(
        run_growatt_daytime_sync,
        trigger=CronTrigger(hour="6-19", minute="*/15", timezone=IST_TIMEZONE),
        id="growatt_daytime_sync",
        name="15-Minute Growatt Daytime Sync (06:00-19:00 IST)",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    # 2. iSolarCloud + SuryaLog browser scrapes every 30 min between 06:00 and 19:00 IST
    scheduler.add_job(
        run_browser_portals_daytime_sync,
        trigger=CronTrigger(hour="6-19", minute="*/30", timezone=IST_TIMEZONE),
        id="browser_portals_daytime_sync",
        name="30-Minute iSolarCloud & SuryaLog Daytime Sync (06:00-19:00 IST)",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    # 3. Nightly daily close at 23:30 IST
    scheduler.add_job(
        run_nightly_daily_close,
        trigger=CronTrigger(hour=23, minute=30, timezone=IST_TIMEZONE),
        id="nightly_daily_close",
        name="Nightly Full Daily Close (23:30 IST)",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    # 4. Nightly S3 bronze archive and DB backup at 02:00 IST
    scheduler.add_job(
        s3_archive.run_nightly_archive,
        trigger=CronTrigger(hour=2, minute=0, timezone=IST_TIMEZONE),
        id="nightly_s3_archive",
        name="Nightly S3 Archive & DB Backup (02:00 IST)",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    # 5. Daily plant categorization for escalation engine at 07:00 IST
    scheduler.add_job(
        escalation_state_machine.run_daily_categorization,
        trigger=CronTrigger(hour=7, minute=0, timezone=IST_TIMEZONE),
        id="daily_escalation_categorize",
        name="Daily Plant Categorization (07:00 IST)",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    # 6. Escalation state machine advancement every 2 hours
    scheduler.add_job(
        escalation_state_machine.advance_all_state_machines,
        trigger=IntervalTrigger(hours=2),
        id="escalation_state_advance",
        name="Escalation State Machine Advancement",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )

    # 7. Monthly WhatsApp CRM statement campaign preparation on 1st of month at 08:00 IST
    scheduler.add_job(
        crm.prepare_monthly_campaign,
        trigger=CronTrigger(day=1, hour=8, minute=0, timezone=IST_TIMEZONE),
        id="monthly_campaign_prep",
        name="Monthly WhatsApp Statement Campaign Preparation (08:00 IST)",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )


def start():
    if not scheduler.running:
        setup_scheduler()
        scheduler.start()
        logger.info(f"APScheduler started with {len(scheduler.get_jobs())} jobs in timezone {IST_TIMEZONE}")


def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")


def get_job_status():
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return {
        "running": scheduler.running,
        "job_count": len(jobs),
        "jobs": jobs,
        "sync_in_progress": is_sync_running(),
        "sync_info": get_sync_status(),
    }
