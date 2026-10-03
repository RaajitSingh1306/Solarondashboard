from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from config import settings
try:
    from pipeline import pipeline
    from core import analytics
    from services import crm
except ImportError:
    import pipeline
    import analytics
    import crm

scheduler = BackgroundScheduler()

import logging

logger = logging.getLogger(__name__)

def setup_scheduler():
    # 1. High-frequency residential sync: Growatt API is fast (~45s), run every 15 min with force_refresh
    scheduler.add_job(
        pipeline.run_snapshots,
        trigger=IntervalTrigger(minutes=15),
        kwargs={"sources": ["growatt"], "force_refresh": True},
        id="growatt_live_snapshots",
        name="15-Minute Growatt Live Snapshots",
        coalesce=True,
        max_instances=1,
        replace_existing=True
    )
    # 2. Hourly full fleet snapshot sync across all 3 portals
    scheduler.add_job(
        pipeline.run_snapshots,
        trigger=IntervalTrigger(hours=1),
        kwargs={"force_refresh": True},
        id="hourly_fleet_snapshots",
        name="Hourly All-Portal Fleet Snapshots",
        coalesce=True,
        max_instances=1,
        replace_existing=True
    )
    # 3. Daily full extract + historical ingestion at 06:00 IST (00:30 UTC)
    scheduler.add_job(
        pipeline.run_full_extract,
        trigger=CronTrigger(hour=0, minute=30),  # 06:00 IST
        kwargs={"force_refresh": True},
        id="daily_full_extract",
        name="Daily Full Extraction (Fleet, Daily, Monthly, Snapshots)",
        coalesce=True,
        max_instances=1,
        replace_existing=True
    )
    # 4. Monthly peer classification on the 1st of every month
    scheduler.add_job(
        analytics.classify_all,
        trigger=CronTrigger(day=1, hour=1, minute=30),  # 07:00 IST on 1st of month
        id="monthly_classification",
        name="Monthly Peer-Group Performance Classification",
        coalesce=True,
        max_instances=1,
        replace_existing=True
    )
    # 5. Monthly WhatsApp CRM statement generation
    scheduler.add_job(
        crm.prepare_monthly_campaign,
        trigger=CronTrigger(day=1, hour=2, minute=30),  # 08:00 IST on 1st of month
        id="monthly_campaign_prep",
        name="Monthly WhatsApp Statement Campaign Preparation",
        coalesce=True,
        max_instances=1,
        replace_existing=True
    )

def start():
    if not scheduler.running:
        setup_scheduler()
        scheduler.start()

def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)

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
    }
