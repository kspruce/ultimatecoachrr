release: flask db upgrade && python populate_stats.py
web: gunicorn your_app_module:app
worker: python -m apscheduler -s your_scheduler_module:scheduler
