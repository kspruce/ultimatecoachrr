# app/models/team_settings.py
from app import db

class TeamSettings(db.Model):
    __tablename__ = 'team_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
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
    
    # Feature toggles (UI modules)
    stats_enabled = db.Column(db.Boolean, default=True)
    gameday_enabled = db.Column(db.Boolean, default=True)

    playbook_enabled = db.Column(db.Boolean, default=True)
    theory_enabled = db.Column(db.Boolean, default=True)
    drills_enabled = db.Column(db.Boolean, default=True)
    sessions_enabled = db.Column(db.Boolean, default=True)

    clip_enabled = db.Column(db.Boolean, default=True)
    scouting_enabled = db.Column(db.Boolean, default=True)
    fitness_enabled = db.Column(db.Boolean, default=True)

    
    def __repr__(self):
        return f'<TeamSettings id={self.id} team_id={self.team_id}>'
