# app/models/team_settings.py
from app_factory import db

class TeamSettings(db.Model):
    __tablename__ = 'team_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, unique=True)
    
    # Discord settings
    discord_enabled = db.Column(db.Boolean, default=False)
    discord_webhook_url = db.Column(db.String(255), nullable=True)
    discord_bot_token = db.Column(db.String(255), nullable=True)
    discord_guild_id = db.Column(db.String(64), nullable=True)
    discord_calendar_channel_id = db.Column(db.String(64), nullable=True)
    discord_notification_channel_id = db.Column(db.String(64), nullable=True)
    discord_sync_calendar = db.Column(db.Boolean, default=True)
    discord_notify_new_events = db.Column(db.Boolean, default=True)
    discord_notify_upcoming_events = db.Column(db.Boolean, default=True)
    discord_notify_new_items = db.Column(db.Boolean, default=True)
    
    # Relationships
    team = db.relationship('TeamOrganization', backref=db.backref('settings', uselist=False))
    
    def __repr__(self):
        return f'<TeamSettings {self.id} for team {self.team_id}>'
