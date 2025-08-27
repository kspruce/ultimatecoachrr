from apscheduler.schedulers.blocking import BlockingScheduler
from app.tasks.stats_calculation import run_stats_recalculation_task

scheduler = BlockingScheduler()

# Schedule the task to run every 6 hours
@scheduler.scheduled_job('interval', hours=6)
def scheduled_recalculation():
    print("Starting scheduled statistics recalculation...")
    run_stats_recalculation_task()
    print("Scheduled statistics recalculation finished.")

print("Scheduler started. Waiting for jobs to run...")
scheduler.start()
