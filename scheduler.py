from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from config import settings
import pipeline
import analytics
import crm

scheduler = BackgroundScheduler()

def setup_scheduler():
    scheduler.add_job(
        pipeline.run_snapshots,
        trigger=IntervalTrigger(minutes=15),
        id="hourly_snapshots",
        name="15-Minute Live Inverter Snapshots",
        replace_existing=True
    )
    scheduler.add_job(
        pipeline.run_full_extract,
        trigger=CronTrigger(hour=0, minute=30),  # 06:00 IST
        id="daily_full_extract",
        name="Daily Full Extraction (Fleet, Daily, Monthly, Snapshots)",
        replace_existing=True
    )
    scheduler.add_job(
        analytics.classify_all,
        trigger=CronTrigger(day=1, hour=1, minute=30),  # 07:00 IST on 1st of month
        id="monthly_classification",
        name="Monthly Peer-Group Performance Classification",
        replace_existing=True
    )
    scheduler.add_job(
        crm.prepare_monthly_campaign,
        trigger=CronTrigger(day=1, hour=2, minute=30),  # 08:00 IST on 1st of month
        id="monthly_campaign_prep",
        name="Monthly WhatsApp Statement Campaign Preparation",
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
