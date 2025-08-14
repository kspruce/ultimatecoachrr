import logging
from datetime import datetime, timedelta
from flask import current_app
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Set up logging
logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, app=None):
        self.app = app
        self.scheduler = None
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app context"""
        self.app = app
        
        # Create scheduler
        self.scheduler = BackgroundScheduler()
        
        # Schedule jobs
        self.schedule_jobs()
        
        # Start scheduler
        self.scheduler.start()
        
        # Register shutdown with Flask
        app.teardown_appcontext(self.shutdown)
    
    def shutdown(self, exception=None):
        """Shutdown the scheduler"""
        if self.scheduler:
            self.scheduler.shutdown()
    
    def schedule_jobs(self):
        """Schedule all notification jobs"""
        # Check for upcoming events daily at 9 AM
        self.scheduler.add_job(
            self.check_upcoming_events,
            CronTrigger(hour=9, minute=0),
            id='check_upcoming_events',
            replace_existing=True
        )
        
        # Check for today's events daily at 8 AM
        self.scheduler.add_job(
            self.check_today_events,
            CronTrigger(hour=8, minute=0),
            id='check_today_events',
            replace_existing=True
        )
        
        logger.info("Notification jobs scheduled")
    
    def check_upcoming_events(self):
        """Check for upcoming events and send notifications"""
        logger.info("Checking for upcoming events")
        
        with self.app.app_context():
            from app.models.session import Session
            from app.models.tournament import Tournament
            from app.models.game import Game
            from app.discord.webhooks import discord_webhook
            
            now = datetime.now()
            
            # Check for events in 3 days
            target_date = now.date() + timedelta(days=3)
            
            # Check sessions
            sessions = Session.query.filter(
                Session.date >= datetime.combine(target_date, datetime.min.time()),
                Session.date < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            ).all()
            
            for session in sessions:
                discord_webhook.notify_upcoming_session(session, 3)
            
            # Check tournaments
            tournaments = Tournament.query.filter(
                Tournament.start_date == target_date
            ).all()
            
            for tournament in tournaments:
                discord_webhook.notify_upcoming_tournament(tournament, 3)
            
            # Check games
            games = Game.query.filter(
                Game.date >= datetime.combine(target_date, datetime.min.time()),
                Game.date < datetime.combine(target_date + timedelta(days=1), datetime.min.time())
            ).all()
            
            for game in games:
                discord_webhook.notify_upcoming_game(game, 3)
    
    def check_today_events(self):
        """Check for today's events and send notifications"""
        logger.info("Checking for today's events")
        
        with self.app.app_context():
            from app.models.session import Session
            from app.models.tournament import Tournament
            from app.models.game import Game
            from app.discord.webhooks import discord_webhook
            
            now = datetime.now()
            today = now.date()
            
            # Check sessions
            sessions = Session.query.filter(
                Session.date >= datetime.combine(today, datetime.min.time()),
                Session.date < datetime.combine(today + timedelta(days=1), datetime.min.time())
            ).all()
            
            for session in sessions:
                discord_webhook.notify_upcoming_session(session, 0)
            
            # Check tournaments
            tournaments = Tournament.query.filter(
                Tournament.start_date == today
            ).all()
            
            for tournament in tournaments:
                discord_webhook.notify_upcoming_tournament(tournament, 0)
            
            # Check games
            games = Game.query.filter(
                Game.date >= datetime.combine(today, datetime.min.time()),
                Game.date < datetime.combine(today + timedelta(days=1), datetime.min.time())
            ).all()
            
            for game in games:
                discord_webhook.notify_upcoming_game(game, 0)
    
    def notify_new_event(self, event_type, event):
        """Send notification for a new event
        
        Parameters:
        -----------
        event_type: str
            The type of event (session, tournament, game)
        event: object
            The event object
        """
        from app.discord.webhooks import discord_webhook
        
        if event_type == 'session':
            discord_webhook.notify_new_session(event)
        elif event_type == 'tournament':
            discord_webhook.notify_new_tournament(event)
        elif event_type == 'game':
            discord_webhook.notify_new_game(event)
        else:
            logger.error(f"Unknown event type: {event_type}")

# Create a global instance
notification_service = NotificationService()