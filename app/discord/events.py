import logging
from flask import current_app
from datetime import datetime

# Set up logging
logger = logging.getLogger(__name__)

def register_event_listeners(app):
    """Register event listeners for Discord integration
    
    Parameters:
    -----------
    app: Flask
        The Flask application
    """
    from app.discord.notifications import notification_service
    
    # Session events
    @app.before_request
    def setup_session_listeners():
        """Set up session event listeners"""
        try:
            from app.models.session import SessionPlan as Session
            from sqlalchemy import event
            
            @event.listens_for(Session, 'after_insert')
            def session_after_insert(mapper, connection, target):
                """Listen for new session creation"""
                logger.info(f"New session created: {target.title}")
                notification_service.notify_new_event('session', target)
        
        except Exception as e:
            logger.error(f"Error setting up session listeners: {str(e)}")
    
    # Tournament events
    @app.before_request
    def setup_tournament_listeners():
        """Set up tournament event listeners"""
        try:
            from app.models.tournament import Tournament
            from sqlalchemy import event
            
            @event.listens_for(Tournament, 'after_insert')
            def tournament_after_insert(mapper, connection, target):
                """Listen for new tournament creation"""
                logger.info(f"New tournament created: {target.name}")
                notification_service.notify_new_event('tournament', target)
        
        except Exception as e:
            logger.error(f"Error setting up tournament listeners: {str(e)}")
    
    # Game events
    @app.before_request
    def setup_game_listeners():
        """Set up game event listeners"""
        try:
            from app.models.game import Game
            from sqlalchemy import event
            
            @event.listens_for(Game, 'after_insert')
            def game_after_insert(mapper, connection, target):
                """Listen for new game creation"""
                logger.info(f"New game created: vs {target.opponent if hasattr(target, 'opponent') else 'TBD'}")
                notification_service.notify_new_event('game', target)
        
        except Exception as e:
            logger.error(f"Error setting up game listeners: {str(e)}")