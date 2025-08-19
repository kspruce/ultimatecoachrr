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
    # ... (existing code)

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
    # ... (existing code)

@discord_bp.route('/sync-calendar', methods=['POST'])
@login_required
def sync_calendar():
    """Manually trigger calendar synchronization"""
    # ... (existing code)
