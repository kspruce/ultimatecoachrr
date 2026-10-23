"""Reminding players to firm up their answers, and telling them about
cancellations.

A week before a session (each team picks how many days), everyone it's
for who is on Maybe, or hasn't answered, gets one reminder listing every
such session in that window: a Discord direct message with Yes / Maybe /
No buttons if they connected Discord, otherwise an email. Each player is
reminded about each session once (SessionReminder).
"""
import logging
from datetime import date, timedelta

from app import db
from app.models.schedule import SessionReminder
from app.models.team_organization import TeamOrganization
from app.models.team_settings import TeamSettings
from app.utils import rsvp

logger = logging.getLogger(__name__)

KIND_ANSWER = 'answer'


def due(team_id, today=None, settings=None, session_ids=None):
    """{player: [sessions]} still owed a reminder: sessions from tomorrow to
    `reminder_days` ahead where they're on Maybe or haven't answered."""
    today = today or date.today()
    settings = settings or TeamSettings.query.filter_by(team_id=team_id).first()
    days = settings.reminder_days if settings and settings.reminder_days else 7
    sessions = rsvp.upcoming_sessions(team_id, today + timedelta(days=1), today + timedelta(days=days))
    if session_ids is not None:
        sessions = [s for s in sessions if s.id in session_ids]
    if not sessions:
        return {}
    players = rsvp.team_players(team_id)
    squads = rsvp.player_squads(team_id)
    answers = rsvp.answers(sessions)
    sent = {(r.session_id, r.player_id) for r in SessionReminder.query.filter(
        SessionReminder.session_id.in_([s.id for s in sessions]), SessionReminder.kind == KIND_ANSWER)}
    out = {}
    for session in sessions:
        answered = {pid for (sid, pid) in answers if sid == session.id}
        for player in rsvp.expected_players(session, players, squads, answered):
            answer = answers.get((session.id, player.id))
            if (answer is None or answer.status == rsvp.MAYBE) and (session.id, player.id) not in sent:
                out.setdefault(player, []).append(session)
    return out


def _account(player):
    return player.user_account


def deliver(player, sessions, statuses):
    """Send one player their reminder. Returns 'discord', 'email' or None."""
    from app.discord import messages, notify
    from app.utils.email import send_email

    user = _account(player)
    discord_id = user.discord_id if user else None
    if discord_id and notify.dm(discord_id, messages.reminder(sessions, statuses)):
        return 'discord'
    address = (user.email if user else None) or player.email
    lines = []
    for s in sessions:
        said = rsvp.LABELS.get(statuses.get(s.id))
        lines.append(f"- {s.title}, {messages.when(s)}" + (f" (you said {said})" if said else ' (no answer yet)'))
    body = (f"Hi {player.name.split()[0]},\n\nCan you let your coaches know whether you're coming?\n\n"
            + '\n'.join(lines) + f"\n\nAnswer here: {messages.link('training.availability')}\n")
    subject = 'Are you coming to training?' if len(sessions) == 1 else 'Are you coming to these sessions?'
    if address and send_email(address, subject, body):
        return 'email'
    return None


def send_for_team(team_id, today=None, settings=None, session_ids=None):
    """Send everything due for one team. Commits. Returns (reminded, unreachable)."""
    owed = due(team_id, today, settings, session_ids)
    if not owed:
        return 0, 0
    answers = rsvp.answers({s for sessions in owed.values() for s in sessions})
    reached = missed = 0
    for player, sessions in owed.items():
        statuses = {s.id: a.status for s in sessions if (a := answers.get((s.id, player.id)))}
        try:
            how = deliver(player, sessions, statuses)
        except Exception as e:
            logger.warning('Reminder to player %s failed: %s', player.id, e)
            how = None
        reached += how is not None
        missed += how is None
        # Recorded either way: someone with no Discord or email isn't retried hourly
        for s in sessions:
            db.session.add(SessionReminder(session_id=s.id, player_id=player.id, kind=KIND_ANSWER,
                                           team_organization_id=team_id))
    db.session.commit()
    return reached, missed


def send_all(today=None):
    """Every team with reminders on. Returns how many players were reminded."""
    total = 0
    teams = (db.session.query(TeamOrganization.id, TeamSettings)
             .outerjoin(TeamSettings, TeamSettings.team_id == TeamOrganization.id).all())
    for team_id, settings in teams:
        if settings is not None and not settings.reminders_enabled:
            continue
        try:
            total += send_for_team(team_id, today, settings)[0]
        except Exception:
            logger.exception('Reminders for team %s failed', team_id)
            db.session.rollback()
    return total


def nudge(session):
    """A coach's "remind them now" for one session: everyone on Maybe or with
    no answer, whether or not they've been reminded before. Returns
    (reminded, unreachable)."""
    answers = rsvp.answers([session])
    answered = {pid for (_, pid) in answers}
    reached = missed = 0
    for player in rsvp.expected_players(session, answered=answered):
        answer = answers.get((session.id, player.id))
        if answer is not None and answer.status != rsvp.MAYBE:
            continue
        how = deliver(player, [session], {session.id: answer.status} if answer else {})
        reached += how is not None
        missed += how is None
    return reached, missed


def tell_cancelled(session):
    """Tell the team a session is off: in its Discord channel, and directly
    anyone who said Yes or Maybe. Returns how many players were told."""
    from app.discord import messages, notify
    from app.utils.email import send_email

    notify.post(session.team_organization_id, messages.cancelled(session))
    told = 0
    answers = rsvp.answers([session])
    for (_, player_id), answer in answers.items():
        if answer.status == rsvp.NOT_ATTENDING:
            continue
        from app.models.player import Player
        player = db.session.get(Player, player_id)
        user = _account(player) if player else None
        if user and user.discord_id and notify.dm(user.discord_id, messages.plain(
                f"❌ {session.title} on {messages.when(session)} is cancelled."
                + (f" {session.cancel_reason}" if session.cancel_reason else ''))):
            told += 1
            continue
        address = (user.email if user else None) or (player.email if player else None)
        if address and send_email(address, f'Cancelled: {session.title}, {messages.when(session)}',
                                  f"{session.title} on {messages.when(session)} is cancelled."
                                  + (f"\n\n{session.cancel_reason}" if session.cancel_reason else '')
                                  + f"\n\n{messages.link('training.availability')}\n"):
            told += 1
    return told
