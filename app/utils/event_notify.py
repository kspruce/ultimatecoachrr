# app/utils/event_notify.py
"""Telling players about tournaments: asked to reply, reminded, picked (or
not) and which games they play.

Messages go by email to players with an account who haven't turned
tournament emails off, and a short note goes to the team's Discord channel
when a webhook is set up. Every function returns how many players were
emailed, so the coach can be told.
"""
import logging
from datetime import date, datetime, timedelta

from flask import current_app, has_request_context, request, url_for

from app import db
from app.models.team_organization import TeamOrganization
from app.models.tournament import Tournament
from app.utils import tournament_rsvp as rsvps
from app.utils.email import send_email

logger = logging.getLogger(__name__)

# Automatic reminders go this many days before the reply-by date
REMINDER_DAYS_BEFORE = 2


def _base_url():
    if has_request_context():
        return request.host_url.rstrip('/')
    return (current_app.config.get('BASE_URL') or '').rstrip('/')


def tournament_link(tournament):
    base = _base_url()
    if not base:
        return ''
    if has_request_context():
        return url_for('tournament.detail', tournament_id=tournament.id, _external=True)
    return f'{base}/tournaments/{tournament.id}'


def _wants_email(player):
    user = player.user_account
    return bool(user and user.email and user.email_event_updates)


def _team_name(tournament):
    team = db.session.get(TeamOrganization, tournament.team_organization_id)
    return team.name if team else 'Your team'


def _when(tournament):
    return tournament.formatted_date_range + (f' at {tournament.location}' if tournament.location else '')


def _email(player, subject, lines):
    if not _wants_email(player):
        return False
    body = '\n'.join([f'Hi {player.name.split()[0]},', ''] + lines +
                     ['', 'You can turn these emails off on your profile page.'])
    return send_email(player.user_account.email, subject, body)


def _discord(tournament, content):
    """Post to the team's Discord channel if one is set up; never raises."""
    try:
        from app.discord import messages, notify
        notify.post(tournament.team_organization_id, messages.plain(content))
    except Exception as e:  # Discord is optional
        logger.warning('Discord message not sent: %s', e)


def _reply_line(tournament):
    if tournament.rsvp_deadline:
        return f'Please reply by {tournament.rsvp_deadline.strftime("%A %d %B")}.'
    return 'Please let the coaches know if you can make it.'


# ── Messages ───────────────────────────────────────────────────────────────

def ask_for_availability(tournament):
    """A new tournament: everyone it's for is asked to reply."""
    link = tournament_link(tournament)
    lines = [f'{_team_name(tournament)} is going to {tournament.name} ({_when(tournament)}).',
             _reply_line(tournament)]
    if tournament.notes:
        lines += ['', tournament.notes]
    if link:
        lines += ['', f'Reply here: {link}']
    sent = sum(_email(p, f'Can you make {tournament.name}?', lines)
               for p in rsvps.eligible_players(tournament))
    _discord(tournament, f'**{tournament.name}** ({_when(tournament)}) — {_reply_line(tournament)}'
                         + (f' {link}' if link else ''))
    return sent


def remind_no_replies(tournament):
    """Nudge players who haven't answered yet."""
    link = tournament_link(tournament)
    lines = [f'We haven\'t heard from you about {tournament.name} ({_when(tournament)}).',
             _reply_line(tournament)]
    if link:
        lines += ['', f'Reply here (one tap): {link}']
    players = rsvps.no_reply_players(tournament)
    sent = sum(_email(p, f'Reminder: can you make {tournament.name}?', lines) for p in players)
    if players:
        _discord(tournament, f'Reminder: {len(players)} still to reply for **{tournament.name}**.'
                             + (f' {link}' if link else ''))
    tournament.reminder_sent_at = datetime.utcnow()
    return sent


def announce_selection(tournament):
    """The squad is published: each player hears whether they're in."""
    link = tournament_link(tournament)
    sent = 0
    for row in rsvps.squad_rows(tournament):
        rsvp = row['rsvp']
        if rsvp is None or (not rsvp.status and not rsvp.selection):
            continue  # never replied and not picked: nothing to tell them
        selection = rsvp.selection or 'not_picked'
        first = {
            'picked': f'You\'re in the squad for {tournament.name} ({_when(tournament)}).',
            'reserve': f'You\'re a reserve for {tournament.name}: we\'ll let you know if a place opens up.',
            'not_picked': f'You haven\'t been picked for {tournament.name} this time.',
        }[selection]
        lines = [first]
        if link:
            lines += ['', f'Details: {link}']
        subject = {'picked': f'You\'re in for {tournament.name}',
                   'reserve': f'Reserve for {tournament.name}',
                   'not_picked': f'{tournament.name} squad'}[selection]
        sent += _email(row['player'], subject, lines)
    picked = len(rsvps.picked_players(tournament))
    _discord(tournament, f'The **{tournament.name}** squad is out ({picked} players).'
                         + (f' {link}' if link else ''))
    return sent


def send_schedule(tournament):
    """Each picked player gets the games they're down to play."""
    link = tournament_link(tournament)
    sent = 0
    for player in rsvps.picked_players(tournament):
        games = rsvps.player_games(tournament, player)
        if not games:
            continue
        lines = [f'Your games at {tournament.name}:', '']
        for game in games:
            when = ' '.join(filter(None, [game.date.strftime('%a %d %b') if game.date else None,
                                          game.start_time.strftime('%H:%M') if game.start_time else None]))
            where = f', {game.field}' if game.field else ''
            lines.append(f'  • {when or "TBC"} vs {game.opponent}{where}')
        if link:
            lines += ['', f'Full schedule: {link}']
        sent += _email(player, f'Your {tournament.name} schedule', lines)
    return sent


# ── Daily job ──────────────────────────────────────────────────────────────

def send_due_reminders(today=None):
    """Remind non-repliers once, a couple of days before each reply-by
    date. The background jobs (app/scheduler.py) run this every hour from
    9am; `flask send-rsvp-reminders` runs it by hand."""
    today = today or date.today()
    due = Tournament.query.filter(
        Tournament.rsvp_deadline.isnot(None),
        Tournament.rsvp_deadline >= today,
        Tournament.rsvp_deadline <= today + timedelta(days=REMINDER_DAYS_BEFORE),
        Tournament.reminder_sent_at.is_(None),
    ).all()
    total = 0
    for tournament in due:
        total += remind_no_replies(tournament)
    db.session.commit()
    return len(due), total

