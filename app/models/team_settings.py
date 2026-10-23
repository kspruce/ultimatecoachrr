# app/models/team_settings.py
import sqlalchemy as sa

from app import db

class TeamSettings(db.Model):
    __tablename__ = 'team_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Discord (app/discord): the server the site's bot was added to and the
    # channel it posts in, or just a webhook URL for posts without buttons
    discord_enabled = db.Column(db.Boolean, default=False)
    discord_webhook_url = db.Column(db.String(255))
    discord_guild_id = db.Column(db.String(255))
    discord_guild_name = db.Column(db.String(100))
    discord_notification_channel_id = db.Column(db.String(255))
    # New one-off sessions, tournaments and games
    discord_notify_new_events = db.Column(db.Boolean, default=False)
    # The weekly "this week's training" post with RSVP buttons
    discord_notify_upcoming_events = db.Column(db.Boolean, default=False)
    # New clips and theory
    discord_notify_new_items = db.Column(db.Boolean, default=False)
    discord_week_post_day = db.Column(db.Integer, default=0, server_default='0')  # 0 = Monday
    discord_week_posted_on = db.Column(db.Date)  # the last weekly post, so it goes once

    # Sessions: what players see and when they're reminded
    ATTENDEE_VISIBILITY = [('names', 'Names of who is coming'), ('counts', 'Just the numbers'),
                           ('hidden', 'Nothing (coaches only)')]
    attendee_visibility = db.Column(db.String(10), nullable=False, default='names', server_default='names')
    # Players see a published plan this many days before (None: once published)
    plan_visible_days = db.Column(db.Integer)
    # Remind players on Maybe (or with no answer) this many days before
    reminders_enabled = db.Column(db.Boolean, nullable=False, default=True, server_default=sa.true())
    reminder_days = db.Column(db.Integer, nullable=False, default=7, server_default='7')
    
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

    # Off by default: only teams that import a season plan switch it on
    season_plan_enabled = db.Column(db.Boolean, default=False, server_default=sa.false(), nullable=False)
    # Off by default: leaders-only pages, switched on per team
    leadership_handbook_enabled = db.Column(db.Boolean, default=False, server_default=sa.false(), nullable=False)

    # Team colours (#RRGGBB); empty means the default Ultimate Coach colours
    primary_color = db.Column(db.String(7))
    accent_color = db.Column(db.String(7))
    show_kit_stripe = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        return f'<TeamSettings id={self.id} team_id={self.team_id}>'
