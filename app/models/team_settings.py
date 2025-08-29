# Example fix for team_settings.py
from app.models.base import db

class TeamSettings(db.Model):
    __tablename__ = 'team_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Add other fields here
    discord_enabled = db.Column(db.Boolean, default=False)
    discord_webhook_url = db.Column(db.String(255))
    discord_bot_token = db.Column(db.String(255))
    discord_guild_id = db.Column(db.String(255))
    discord_calendar_channel_id = db.Column(db.String(255))
    discord_notification_channel_id = db.Column(db.String(255))
    discord_sync_calendar = db.Column(db.Boolean, default=False)
    discord_notify_new_events = db.Column(db.Boolean, default=False)
    discord_notify_upcoming_events = db.Column(db.Boolean, default=False)
    discord_notify_new_items = db.Column(db.Boolean, default=False)
    
    # Add relationship
    team = db.relationship('TeamOrganization', back_populates='settings')
