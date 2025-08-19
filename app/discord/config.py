import os
import logging

# Set up logging
logger = logging.getLogger(__name__)

class DiscordConfig:
    """Discord configuration settings"""
    
    # Discord Bot
    DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
    DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID', '')
    DISCORD_CALENDAR_CHANNEL_ID = os.environ.get('DISCORD_CALENDAR_CHANNEL_ID', '')
    DISCORD_NOTIFICATION_CHANNEL_ID = os.environ.get('DISCORD_NOTIFICATION_CHANNEL_ID', '')
    
    # Discord Webhook
    DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL', '')
    
    # Discord Integration Settings
    DISCORD_ENABLED = os.environ.get('DISCORD_ENABLED', 'False').lower() == 'true'
    DISCORD_SYNC_CALENDAR = os.environ.get('DISCORD_SYNC_CALENDAR', 'True').lower() == 'true'
    DISCORD_NOTIFY_NEW_EVENTS = os.environ.get('DISCORD_NOTIFY_NEW_EVENTS', 'True').lower() == 'true'
    DISCORD_NOTIFY_UPCOMING_EVENTS = os.environ.get('DISCORD_NOTIFY_UPCOMING_EVENTS', 'True').lower() == 'true'
    DISCORD_NOTIFY_NEW_ITEMS = os.environ.get('DISCORD_NOTIFY_NEW_ITEMS', 'True').lower() == 'true'


def init_discord(app):
    """Initialize Discord integration
    
    Parameters:
    -----------
    app: Flask
        The Flask application
    """
    # Add Discord configuration to app config
    app.config.from_object(DiscordConfig)
    
    # Only initialize if Discord is enabled
    if not app.config.get('DISCORD_ENABLED', False):
        logger.info("Discord integration is disabled")
        return
    
    # Load team-specific Discord settings from database
    with app.app_context():
        try:
            from app.models.team_organization import TeamOrganization
            from app.models.team_settings import TeamSettings
            
            # Create TeamSettings for teams that don't have it yet
            teams = TeamOrganization.query.all()
            for team in teams:
                settings = TeamSettings.query.filter_by(team_id=team.id).first()
                if not settings:
                    from app import db
                    settings = TeamSettings(
                        team_id=team.id,
                        discord_enabled=app.config.get('DISCORD_ENABLED', False),
                        discord_webhook_url=app.config.get('DISCORD_WEBHOOK_URL', ''),
                        discord_guild_id=app.config.get('DISCORD_GUILD_ID', ''),
                        discord_calendar_channel_id=app.config.get('DISCORD_CALENDAR_CHANNEL_ID', ''),
                        discord_notification_channel_id=app.config.get('DISCORD_NOTIFICATION_CHANNEL_ID', '')
                    )
                    db.session.add(settings)
                    db.session.commit()
        except ImportError:
            logger.warning("TeamSettings model not found, skipping team-specific Discord settings")
        except Exception as e:
            logger.error(f"Error loading team Discord settings: {str(e)}")
    
    # Initialize Discord bot
    from app.discord.bot import discord_bot
    discord_bot.init_app(app)
    
    # Initialize Discord webhook
    from app.discord.webhooks import discord_webhook
    discord_webhook.init_app(app)
    
    # Initialize notification service
    from app.discord.notifications import notification_service
    notification_service.init_app(app)
    
    # Register event listeners (only once)
    from app.discord.events import register_event_listeners
    with app.app_context():
        register_event_listeners(app)
    
    # Start Discord bot
    if app.config.get('DISCORD_BOT_TOKEN'):
        try:
            discord_bot.start_bot()
        except AttributeError:
            logger.warning("Discord bot doesn't have start_bot method, skipping bot start")
    else:
        logger.warning("Discord bot token not configured, bot will not start")
    
    logger.info("Discord integration initialized")

