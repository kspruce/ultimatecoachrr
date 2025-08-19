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
        if self.scheduler and self.scheduler.running:
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
            from app.models.team_organization import TeamOrganization
            
            now = datetime.now()
            
            # Check for events in 3 days
            target_date = now.date() + timedelta(days=3)
            
            # Get all team organizations
            teams = TeamOrganization.query.all()
            
            for team in teams:
                team_id = team.id
                
                # Check sessions for this team
                sessions = Session.query.filter(
                    Session.date >= datetime.combine(target_date, datetime.min.time()),
                    Session.date < datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
                    Session.team_organization_id == team_id
                ).all()
                
                for session in sessions:
                    discord_webhook.notify_upcoming_session(session, 3, team_id)
                
                # Check tournaments for this team
                tournaments = Tournament.query.filter(
                    Tournament.start_date == target_date,
                    Tournament.team_organization_id == team_id
                ).all()
                
                for tournament in tournaments:
                    discord_webhook.notify_upcoming_tournament(tournament, 3, team_id)
                
                # Check games for this team
                games = Game.query.filter(
                    Game.date >= datetime.combine(target_date, datetime.min.time()),
                    Game.date < datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
                    Game.team_organization_id == team_id
                ).all()
                
                for game in games:
                    discord_webhook.notify_upcoming_game(game, 3, team_id)
    
    def check_today_events(self):
        """Check for today's events and send notifications"""
        logger.info("Checking for today's events")
        
        with self.app.app_context():
            from app.models.session import Session
            from app.models.tournament import Tournament
            from app.models.game import Game
            from app.discord.webhooks import discord_webhook
            from app.models.team_organization import TeamOrganization
            
            now = datetime.now()
            today = now.date()
            
            # Get all team organizations
            teams = TeamOrganization.query.all()
            
            for team in teams:
                team_id = team.id
                
                # Check sessions for this team
                sessions = Session.query.filter(
                    Session.date >= datetime.combine(today, datetime.min.time()),
                    Session.date < datetime.combine(today + timedelta(days=1), datetime.min.time()),
                    Session.team_organization_id == team_id
                ).all()
                
                for session in sessions:
                    discord_webhook.notify_upcoming_session(session, 0, team_id)
                
                # Check tournaments for this team
                tournaments = Tournament.query.filter(
                    Tournament.start_date == today,
                    Tournament.team_organization_id == team_id
                ).all()
                
                for tournament in tournaments:
                    discord_webhook.notify_upcoming_tournament(tournament, 0, team_id)
                
                # Check games for this team
                games = Game.query.filter(
                    Game.date >= datetime.combine(today, datetime.min.time()),
                    Game.date < datetime.combine(today + timedelta(days=1), datetime.min.time()),
                    Game.team_organization_id == team_id
                ).all()
                
                for game in games:
                    discord_webhook.notify_upcoming_game(game, 0, team_id)
    
    def notify_new_event(self, event_type, event, team_id=None):
        """Send notification for a new event
        
        Parameters:
        -----------
        event_type: str
            The type of event (session, tournament, game)
        event: object
            The event object
        team_id: int
            The team organization ID
        """
        from app.discord.webhooks import discord_webhook
        from flask import current_app
        
        if not current_app.config.get('DISCORD_NOTIFY_NEW_EVENTS', True):
            return
        
        # Get team_id from event if not provided
        if team_id is None and hasattr(event, 'team_organization_id'):
            team_id = event.team_organization_id
        
        if event_type == 'session':
            discord_webhook.notify_new_session(event, team_id)
        elif event_type == 'tournament':
            discord_webhook.notify_new_tournament(event, team_id)
        elif event_type == 'game':
            discord_webhook.notify_new_game(event, team_id)
        else:
            logger.error(f"Unknown event type: {event_type}")
    
    def notify_new_database_item(self, item_type, item, team_id=None):
        """Send notification about a new database item
        
        Parameters:
        -----------
        item_type: str
            The type of item ('tournament', 'session', 'clip', 'theory')
        item: object
            The database item object
        team_id: int
            The team organization ID
        """
        from app.discord.webhooks import discord_webhook
        from flask import current_app
        
        if not current_app.config.get('DISCORD_NOTIFY_NEW_ITEMS', True):
            return
        
        # Get team_id from item if not provided
        if team_id is None and hasattr(item, 'team_organization_id'):
            team_id = item.team_organization_id
        
        if item_type == 'tournament':
            discord_webhook.notify_new_tournament(item, team_id)
        elif item_type == 'session':
            discord_webhook.notify_new_session(item, team_id)
        elif item_type == 'clip':
            discord_webhook.notify_new_clip(item, team_id)
        elif item_type == 'theory':
            discord_webhook.notify_new_theory(item, team_id)
        else:
            logger.warning(f"Unknown item type for notification: {item_type}")


# Create a global instance
notification_service = NotificationService()
