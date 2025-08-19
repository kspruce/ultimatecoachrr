import logging
from flask import current_app
from datetime import datetime
import functools

# Set up logging
logger = logging.getLogger(__name__)

# Global flag to track if listeners have been registered
_listeners_registered = False

def register_event_listeners(app):
    """Register event listeners for Discord integration
    
    Parameters:
    -----------
    app: Flask
        The Flask application
    """
    global _listeners_registered
    
    # Only register listeners once
    if _listeners_registered:
        logger.debug("Event listeners already registered, skipping")
        return
    
    logger.info("Registering Discord event listeners")
    
    from app.discord.notifications import notification_service
    from sqlalchemy import event
    
    # Register session listeners
    try:
        from app.models.session import SessionPlan
        
        @event.listens_for(SessionPlan, 'after_insert', once=True)
        def session_after_insert(mapper, connection, target):
            """Listen for new session creation"""
            logger.info(f"New session created: {target.title}")
            # Pass team_organization_id to notification service
            notification_service.notify_new_database_item('session', target, target.team_organization_id)
        
        logger.info("Session listeners registered")
    except Exception as e:
        logger.error(f"Error setting up session listeners: {str(e)}")
    
    # Register tournament listeners
    try:
        from app.models.tournament import Tournament
        
        @event.listens_for(Tournament, 'after_insert', once=True)
        def tournament_after_insert(mapper, connection, target):
            """Listen for new tournament creation"""
            logger.info(f"New tournament created: {target.name}")
            # Pass team_organization_id to notification service
            notification_service.notify_new_database_item('tournament', target, target.team_organization_id)
        
        logger.info("Tournament listeners registered")
    except Exception as e:
        logger.error(f"Error setting up tournament listeners: {str(e)}")
    
    # Register game listeners
    try:
        from app.models.game import Game
        
        @event.listens_for(Game, 'after_insert', once=True)
        def game_after_insert(mapper, connection, target):
            """Listen for new game creation"""
            logger.info(f"New game created: vs {target.opponent if hasattr(target, 'opponent') else 'TBD'}")
            # Pass team_organization_id to notification service
            notification_service.notify_new_event('game', target, target.team_organization_id)
        
        logger.info("Game listeners registered")
    except Exception as e:
        logger.error(f"Error setting up game listeners: {str(e)}")
    
    # Register clip listeners
    try:
        from app.models.clip import Clip
        
        @event.listens_for(Clip, 'after_insert', once=True)
        def clip_after_insert(mapper, connection, target):
            """Listen for new clip creation"""
            logger.info(f"New clip created: ID {target.id}")
            # Pass team_organization_id to notification service
            notification_service.notify_new_database_item('clip', target, target.team_organization_id)
        
        logger.info("Clip listeners registered")
    except Exception as e:
        logger.error(f"Error setting up clip listeners: {str(e)}")
    
    # Register theory listeners
    try:
        from app.models.theory import TheoryTopic
        
        @event.listens_for(TheoryTopic, 'after_insert', once=True)
        def theory_topic_after_insert(mapper, connection, target):
            """Listen for new theory topic creation"""
            logger.info(f"New theory topic created: {target.title}")
            # Pass team_organization_id to notification service
            notification_service.notify_new_database_item('theory', target, target.team_organization_id)
        
        from app.models.theory import TheorySection
        
        @event.listens_for(TheorySection, 'after_insert', once=True)
        def theory_section_after_insert(mapper, connection, target):
            """Listen for new theory section creation"""
            logger.info(f"New theory section created: {target.title}")
            # Pass team_organization_id to notification service
            notification_service.notify_new_database_item('theory', target, target.team_organization_id)
        
        logger.info("Theory listeners registered")
    except Exception as e:
        logger.error(f"Error setting up theory listeners: {str(e)}")
    
    # Mark listeners as registered
    _listeners_registered = True
    logger.info("All Discord event listeners registered successfully")
