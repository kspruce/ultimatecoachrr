from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, session
from flask_login import login_required, current_user
from app import db
from app.discord.bot import discord_bot
from app.discord.webhooks import discord_webhook
import logging
import sqlalchemy.exc

# Set up logging
logger = logging.getLogger(__name__)

# Create blueprint
discord_bp = Blueprint('discord', __name__, url_prefix='/discord')

@discord_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Discord integration settings page"""
    if not current_user.is_admin:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('main.index'))
    
    # Get current team ID
    team_id = None
    if hasattr(current_user, 'team_organization_id'):
        team_id = current_user.team_organization_id
    elif 'current_team_id' in session:
        team_id = session['current_team_id']
    
    # Default settings dictionary
    settings_dict = {
        'discord_enabled': current_app.config.get('DISCORD_ENABLED', False),
        'discord_sync_calendar': current_app.config.get('DISCORD_SYNC_CALENDAR', True),
        'discord_notify_new_events': current_app.config.get('DISCORD_NOTIFY_NEW_EVENTS', True),
        'discord_notify_upcoming_events': current_app.config.get('DISCORD_NOTIFY_UPCOMING_EVENTS', True),
        'discord_notify_new_items': current_app.config.get('DISCORD_NOTIFY_NEW_ITEMS', True),
        'discord_bot_token': current_app.config.get('DISCORD_BOT_TOKEN', ''),
        'discord_guild_id': current_app.config.get('DISCORD_GUILD_ID', ''),
        'discord_calendar_channel_id': current_app.config.get('DISCORD_CALENDAR_CHANNEL_ID', ''),
        'discord_notification_channel_id': current_app.config.get('DISCORD_NOTIFICATION_CHANNEL_ID', ''),
        'discord_webhook_url': current_app.config.get('DISCORD_WEBHOOK_URL', '')
    }
    
    # Try to import TeamSettings, but handle the case where it doesn't exist yet
    try:
        from app.models.team_settings import TeamSettings
        
        # Check if the table exists
        try:
            # Get team settings
            if team_id:
                team_settings = TeamSettings.query.filter_by(team_id=team_id).first()
                
                if not team_settings and team_id:
                    # Create default settings if they don't exist
                    team_settings = TeamSettings(
                        team_id=team_id,
                        discord_enabled=current_app.config.get('DISCORD_ENABLED', False),
                        discord_webhook_url=current_app.config.get('DISCORD_WEBHOOK_URL', ''),
                        discord_bot_token=current_app.config.get('DISCORD_BOT_TOKEN', ''),
                        discord_guild_id=current_app.config.get('DISCORD_GUILD_ID', ''),
                        discord_calendar_channel_id=current_app.config.get('DISCORD_CALENDAR_CHANNEL_ID', ''),
                        discord_notification_channel_id=current_app.config.get('DISCORD_NOTIFICATION_CHANNEL_ID', ''),
                        discord_sync_calendar=current_app.config.get('DISCORD_SYNC_CALENDAR', True),
                        discord_notify_new_events=current_app.config.get('DISCORD_NOTIFY_NEW_EVENTS', True),
                        discord_notify_upcoming_events=current_app.config.get('DISCORD_NOTIFY_UPCOMING_EVENTS', True),
                        discord_notify_new_items=current_app.config.get('DISCORD_NOTIFY_NEW_ITEMS', True)
                    )
                    db.session.add(team_settings)
                    db.session.commit()
                
                # Update settings_dict with team-specific settings
                if team_settings:
                    settings_dict = {
                        'discord_enabled': team_settings.discord_enabled,
                        'discord_sync_calendar': team_settings.discord_sync_calendar,
                        'discord_notify_new_events': team_settings.discord_notify_new_events,
                        'discord_notify_upcoming_events': team_settings.discord_notify_upcoming_events,
                        'discord_notify_new_items': team_settings.discord_notify_new_items,
                        'discord_bot_token': team_settings.discord_bot_token,
                        'discord_guild_id': team_settings.discord_guild_id,
                        'discord_calendar_channel_id': team_settings.discord_calendar_channel_id,
                        'discord_notification_channel_id': team_settings.discord_notification_channel_id,
                        'discord_webhook_url': team_settings.discord_webhook_url
                    }
            
            if request.method == 'POST':
                # Update Discord settings for this team
                if team_id:
                    team_settings = TeamSettings.query.filter_by(team_id=team_id).first()
                    
                    if team_settings:
                        team_settings.discord_enabled = 'discord_enabled' in request.form
                        team_settings.discord_sync_calendar = 'discord_sync_calendar' in request.form
                        team_settings.discord_notify_new_events = 'discord_notify_new_events' in request.form
                        team_settings.discord_notify_upcoming_events = 'discord_notify_upcoming_events' in request.form
                        team_settings.discord_notify_new_items = 'discord_notify_new_items' in request.form
                        
                        # Update Discord bot settings
                        team_settings.discord_bot_token = request.form.get('discord_bot_token', '')
                        team_settings.discord_guild_id = request.form.get('discord_guild_id', '')
                        team_settings.discord_calendar_channel_id = request.form.get('discord_calendar_channel_id', '')
                        team_settings.discord_notification_channel_id = request.form.get('discord_notification_channel_id', '')
                        
                        # Update Discord webhook settings
                        team_settings.discord_webhook_url = request.form.get('discord_webhook_url', '')
                        
                        db.session.commit()
                
                # Update application config with these settings
                current_app.config['DISCORD_ENABLED'] = 'discord_enabled' in request.form
                current_app.config['DISCORD_SYNC_CALENDAR'] = 'discord_sync_calendar' in request.form
                current_app.config['DISCORD_NOTIFY_NEW_EVENTS'] = 'discord_notify_new_events' in request.form
                current_app.config['DISCORD_NOTIFY_UPCOMING_EVENTS'] = 'discord_notify_upcoming_events' in request.form
                current_app.config['DISCORD_NOTIFY_NEW_ITEMS'] = 'discord_notify_new_items' in request.form
                
                # Update Discord bot settings
                current_app.config['DISCORD_BOT_TOKEN'] = request.form.get('discord_bot_token', '')
                current_app.config['DISCORD_GUILD_ID'] = request.form.get('discord_guild_id', '')
                current_app.config['DISCORD_CALENDAR_CHANNEL_ID'] = request.form.get('discord_calendar_channel_id', '')
                current_app.config['DISCORD_NOTIFICATION_CHANNEL_ID'] = request.form.get('discord_notification_channel_id', '')
                
                # Update Discord webhook settings
                current_app.config['DISCORD_WEBHOOK_URL'] = request.form.get('discord_webhook_url', '')
                
                # Reinitialize Discord integration
                from app.discord.config import init_discord
                init_discord(current_app)
                
                flash('Discord settings updated successfully.', 'success')
                return redirect(url_for('discord.settings'))
                
        except sqlalchemy.exc.ProgrammingError as e:
            # Table doesn't exist yet
            logger.warning(f"TeamSettings table doesn't exist yet: {e}")
            db.session.rollback()
            
            # Create the table
            try:
                TeamSettings.__table__.create(db.engine)
                db.session.commit()
                flash('Team settings table created. Please refresh the page.', 'info')
            except Exception as e:
                logger.error(f"Error creating TeamSettings table: {e}")
                flash('Error creating team settings table. Please contact an administrator.', 'danger')
            
            # POST handling for when table doesn't exist
            if request.method == 'POST':
                # Update global settings
                current_app.config['DISCORD_ENABLED'] = 'discord_enabled' in request.form
                current_app.config['DISCORD_SYNC_CALENDAR'] = 'discord_sync_calendar' in request.form
                current_app.config['DISCORD_NOTIFY_NEW_EVENTS'] = 'discord_notify_new_events' in request.form
                current_app.config['DISCORD_NOTIFY_UPCOMING_EVENTS'] = 'discord_notify_upcoming_events' in request.form
                current_app.config['DISCORD_NOTIFY_NEW_ITEMS'] = 'discord_notify_new_items' in request.form
                
                # Update Discord bot settings
                current_app.config['DISCORD_BOT_TOKEN'] = request.form.get('discord_bot_token', '')
                current_app.config['DISCORD_GUILD_ID'] = request.form.get('discord_guild_id', '')
                current_app.config['DISCORD_CALENDAR_CHANNEL_ID'] = request.form.get('discord_calendar_channel_id', '')
                current_app.config['DISCORD_NOTIFICATION_CHANNEL_ID'] = request.form.get('discord_notification_channel_id', '')
                
                # Update Discord webhook settings
                current_app.config['DISCORD_WEBHOOK_URL'] = request.form.get('discord_webhook_url', '')
                
                # Reinitialize Discord integration
                from app.discord.config import init_discord
                init_discord(current_app)
                
                flash('Discord settings updated successfully.', 'success')
                return redirect(url_for('discord.settings'))
                
    except ImportError:
        # TeamSettings model doesn't exist yet, use app config
        logger.warning("TeamSettings model not found, using app config")
        
        if request.method == 'POST':
            # Update global settings
            current_app.config['DISCORD_ENABLED'] = 'discord_enabled' in request.form
            current_app.config['DISCORD_SYNC_CALENDAR'] = 'discord_sync_calendar' in request.form
            current_app.config['DISCORD_NOTIFY_NEW_EVENTS'] = 'discord_notify_new_events' in request.form
            current_app.config['DISCORD_NOTIFY_UPCOMING_EVENTS'] = 'discord_notify_upcoming_events' in request.form
            current_app.config['DISCORD_NOTIFY_NEW_ITEMS'] = 'discord_notify_new_items' in request.form
            
            # Update Discord bot settings
            current_app.config['DISCORD_BOT_TOKEN'] = request.form.get('discord_bot_token', '')
            current_app.config['DISCORD_GUILD_ID'] = request.form.get('discord_guild_id', '')
            current_app.config['DISCORD_CALENDAR_CHANNEL_ID'] = request.form.get('discord_calendar_channel_id', '')
            current_app.config['DISCORD_NOTIFICATION_CHANNEL_ID'] = request.form.get('discord_notification_channel_id', '')
            
            # Update Discord webhook settings
            current_app.config['DISCORD_WEBHOOK_URL'] = request.form.get('discord_webhook_url', '')
            
            # Reinitialize Discord integration
            from app.discord.config import init_discord
            init_discord(current_app)
            
            flash('Discord settings updated successfully.', 'success')
            return redirect(url_for('discord.settings'))
    
    # Always return a response at the end of the function
    return render_template(
        'discord/settings.html',
        title='Discord Settings',
        **settings_dict
    )


@discord_bp.route('/link-account', methods=['GET', 'POST'])
@login_required
def link_account():
    """Link Discord account to Ultimate Coach account"""
    if request.method == 'POST':
        discord_id = request.form.get('discord_id', '')
        
        if not discord_id:
            flash('Please enter your Discord ID.', 'danger')
            return redirect(url_for('discord.link_account'))
        
        # Update user's Discord ID
        current_user.discord_id = discord_id
        db.session.commit()
        
        flash('Your Discord account has been linked successfully.', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template(
        'discord/link_account.html',
        title='Link Discord Account'
    )

@discord_bp.route('/test-notification', methods=['POST'])
@login_required
def test_notification():
    """Send a test notification to Discord"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    notification_type = request.form.get('type', 'webhook')
    
    try:
        if notification_type == 'webhook':
            # Test webhook
            success = discord_webhook.send_message(
                content="This is a test notification from Ultimate Coach.",
                embeds=[{
                    "title": "Test Notification",
                    "description": "If you can see this, your Discord webhook is working correctly!",
                    "color": 3066993  # Green color
                }]
            )
            
            if success:
                return jsonify({'success': True, 'message': 'Test notification sent successfully via webhook.'})
            else:
                return jsonify({'success': False, 'message': 'Failed to send test notification via webhook. Check your webhook URL and settings.'})
        
        elif notification_type == 'bot':
            # Test bot
            if not discord_bot.bot:
                return jsonify({'success': False, 'message': 'Discord bot is not initialized. Check your bot token and settings.'})
            
            try:
                import discord
                success = discord_bot.send_notification(
                    title="Test Notification",
                    message="This is a test notification from Ultimate Coach.",
                    embed=discord.Embed(
                        title="Test Notification",
                        description="If you can see this, your Discord bot is working correctly!",
                        color=discord.Color.green()
                    )
                )
                
                if success:
                    return jsonify({'success': True, 'message': 'Test notification sent successfully via bot.'})
                else:
                    return jsonify({'success': False, 'message': 'Failed to send test notification via bot. Check your bot settings and channel ID.'})
            except ImportError:
                return jsonify({'success': False, 'message': 'Discord.py library not installed or not properly imported.'})
        
        else:
            return jsonify({'success': False, 'message': 'Invalid notification type.'}), 400
    
    except Exception as e:
        logger.error(f"Error sending test notification: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@discord_bp.route('/sync-calendar', methods=['POST'])
@login_required
def sync_calendar():
    """Manually trigger calendar synchronization"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Permission denied'}), 403
    
    try:
        # Trigger calendar sync
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Create a future to run the sync_calendar method
        future = asyncio.ensure_future(discord_bot.sync_calendar())
        
        # Run the future to completion
        try:
            loop.run_until_complete(future)
        finally:
            loop.close()
        
        return jsonify({'success': True, 'message': 'Calendar synchronization started successfully.'})
    
    except Exception as e:
        logger.error(f"Error syncing calendar: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

