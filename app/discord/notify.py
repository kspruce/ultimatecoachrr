"""Posting to a team's Discord: its channel (through the site's bot, with
buttons) or its webhook (without), and direct messages to players who
connected their Discord account.

Nothing here raises: a failed post is logged and reported as False, so a
Discord outage never breaks a page.
"""
import logging
from datetime import date, timedelta

from app.discord import api, messages

logger = logging.getLogger(__name__)


def team_settings(team_id):
    from app.models.team_settings import TeamSettings
    return TeamSettings.query.filter_by(team_id=team_id).first()


def channel_target(settings):
    """('bot', channel id), ('webhook', url) or None."""
    if settings is None or not settings.discord_enabled:
        return None
    if settings.discord_guild_id and settings.discord_notification_channel_id and api.bot_ready():
        return 'bot', settings.discord_notification_channel_id
    if api.is_webhook_url(settings.discord_webhook_url):
        return 'webhook', settings.discord_webhook_url
    return None


def post(team_id, payload, settings=None):
    """Post to the team's channel. True if it went."""
    target = channel_target(settings or team_settings(team_id))
    if target is None:
        return False
    kind, where = target
    try:
        if kind == 'bot':
            api.send_channel(where, payload)
        else:
            api.send_webhook(where, payload)
        return True
    except api.DiscordError as e:
        logger.warning('Discord post for team %s failed: %s', team_id, e)
        return False


def dm(discord_user_id, payload):
    """Direct-message someone through the site's bot. True if it went."""
    if not discord_user_id or not api.bot_ready():
        return False
    try:
        api.send_dm(discord_user_id, payload)
        return True
    except api.DiscordError as e:
        logger.info('Discord DM to %s failed: %s', discord_user_id, e)
        return False


def post_week(team, today=None, settings=None):
    """The coming week's training (today to six days on), one post per
    session with its buttons. Returns how many sessions went out."""
    from app.utils.rsvp import upcoming_sessions

    today = today or date.today()
    settings = settings or team_settings(team.id)
    sessions = upcoming_sessions(team.id, today, today + timedelta(days=6))
    if not sessions or channel_target(settings) is None:
        return 0
    if not post(team.id, messages.week_intro(team.name, len(sessions)), settings):
        return 0
    sent = 0
    for session in sessions:
        sent += post(team.id, messages.session_post(session), settings)
    return sent


def due_week_posts(now=None):
    """Post each team's week on its chosen day (from 9am), once a day.
    Commits. Returns the teams posted for."""
    from datetime import datetime

    from app import db
    from app.models.team_organization import TeamOrganization
    from app.models.team_settings import TeamSettings

    now = now or datetime.now()
    today = now.date()
    posted = []
    if now.hour < 9:
        return posted
    for settings in TeamSettings.query.filter_by(discord_enabled=True, discord_notify_upcoming_events=True):
        day = settings.discord_week_post_day if settings.discord_week_post_day is not None else 0
        if day != today.weekday() or settings.discord_week_posted_on == today:
            continue
        team = db.session.get(TeamOrganization, settings.team_id)
        if team is None:
            continue
        settings.discord_week_posted_on = today  # once a day, even if nothing went
        db.session.commit()
        if post_week(team, today, settings):
            posted.append(team)
            # While the join link is on, the weekly post also says who still needs to sign up
            if team.join_enabled:
                from app.onboarding import post_signup_note
                post_signup_note(team, settings)
    return posted
