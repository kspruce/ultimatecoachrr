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
    
    # Initialize Discord bot
    from app.discord.bot import discord_bot
    discord_bot.init_app(app)
    
    # Initialize Discord webhook
    from app.discord.webhooks import discord_webhook
    discord_webhook.init_app(app)
    
    # Initialize notification service
    from app.discord.notifications import notification_service
    notification_service.init_app(app)
    
    # Register event listeners
    from app.discord.events import register_event_listeners
    register_event_listeners(app)
    
    # Start Discord bot
    if app.config.get('DISCORD_BOT_TOKEN'):
        discord_bot.start_bot()
    else:
        logger.warning("Discord bot token not configured, bot will not start")
    
    logger.info("Discord integration initialized")