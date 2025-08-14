"""
Discord integration module for Ultimate Coach.
This module initializes the Discord integration and provides functions for interacting with Discord.
"""
import logging
from flask import Flask

# Set up logging
logger = logging.getLogger(__name__)

def init_discord_integration(app: Flask):
    """
    Initialize Discord integration with the Flask application.
    
    Parameters:
    -----------
    app: Flask
        The Flask application
    """
    try:
        # Initialize Discord configuration
        from app.discord.config import init_discord
        init_discord(app)
        
        
        # Add Discord ID field to User model
        from app.models.discord_user import add_discord_fields_to_user
        add_discord_fields_to_user(app)
        
        logger.info("Discord integration initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing Discord integration: {str(e)}")
        logger.exception(e)