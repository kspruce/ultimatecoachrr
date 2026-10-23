"""Background jobs for training, run inside the web process:

- every night, training schedules make their next dates (open-ended ones
  roll forward);
- every hour, players on Maybe (or with no answer) get their reminder, and
  teams that want it get their weekly Discord post on their chosen day;
- every hour from 9am, players who haven't replied to a tournament whose
  reply-by date is two days away get one reminder.

The scheduler starts on the first request, so `flask` commands (migrations,
imports) never start it. Everything it does is safe to repeat, and
`flask training-jobs` runs the same jobs by hand or from cron (set
SCHEDULER_ENABLED=0 to rely on that instead).
"""
import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)
_started = False
_lock = threading.Lock()


def run_jobs(app, daily=True):
    """Run the jobs once. Returns a short summary."""
    from app import db
    from app.discord.notify import due_week_posts
    from app.utils.reminders import send_all
    from app.utils.event_notify import send_due_reminders
    from app.utils.schedules import extend_all

    def tournament_reminders():
        # Not in the middle of the night; each tournament is reminded once
        return send_due_reminders()[1] if datetime.now().hour >= 9 else 0

    out = {}
    with app.app_context():
        for name, job in (('dates', extend_all if daily else None), ('reminded', send_all),
                          ('week posts', lambda: len(due_week_posts())),
                          ('tournament reminders', tournament_reminders)):
            if job is None:
                continue
            try:
                out[name] = job()
            except Exception:
                logger.exception('Training job %s failed', name)
                db.session.rollback()
        db.session.remove()
    return out


def init_scheduler(app):
    if app.config.get('TESTING') or not app.config.get('SCHEDULER_ENABLED', True):
        return

    @app.before_request
    def _start_once():
        global _started
        if _started:
            return
        with _lock:
            if _started:
                return
            _started = True
            _start(app)


def _start(app):
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(run_jobs, 'cron', hour=3, minute=17, args=[app], id='training-daily',
                      replace_existing=True)
    scheduler.add_job(run_jobs, 'cron', minute=7, args=[app], kwargs={'daily': False},
                      id='training-hourly', replace_existing=True)
    scheduler.start()
    logger.info('Training jobs scheduled')
