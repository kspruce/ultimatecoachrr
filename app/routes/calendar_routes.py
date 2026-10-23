"""The team calendar: sessions, tournaments and games.

The page loads events for the dates on screen from /calendar/events, so
past months work too. Players answer from the event popup; coaches see how
many have replied and can click an empty day to add something on it. Anyone
can subscribe to their own calendar feed (/calendar/feed/<token>.ics) from
Google or Apple Calendar.
"""
import secrets
from datetime import date, datetime, timedelta

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.player import Player
from app.models.session import SessionPlan, SessionRSVP
from app.models.team_organization import TeamOrganization
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.models.user import User
from app.utils import rsvp as rsvps
from app.utils.season import team_squads
from app.utils.team_filter import get_current_team_id

calendar_bp = Blueprint('calendar', __name__)

TYPES = ('session', 'tournament', 'game')
# How far back and ahead the subscription feed reaches
FEED_PAST_DAYS = 60
FEED_FUTURE_DAYS = 400


def _day(value, default):
    try:
        return datetime.strptime((value or '')[:10], '%Y-%m-%d').date()
    except ValueError:
        return default


def _iso(day, time=None):
    return datetime.combine(day, time).isoformat() if time else day.isoformat()


def _session_counts(session_ids):
    counts = {}
    if session_ids:
        rows = (db.session.query(SessionRSVP.session_id, SessionRSVP.status, db.func.count(SessionRSVP.id))
                .filter(SessionRSVP.session_id.in_(session_ids))
                .group_by(SessionRSVP.session_id, SessionRSVP.status))
        for session_id, status, count in rows:
            counts.setdefault(session_id, {})[status] = count
    return counts


def team_events(team_id, start, end, player=None, types=TYPES, squad_id=None, mine=False, coach=False):
    """Events between start and end (inclusive) as dicts for FullCalendar."""
    events = []

    if 'session' in types:
        sessions = (SessionPlan.query.filter(SessionPlan.team_organization_id == team_id,
                                             SessionPlan.date >= start, SessionPlan.date <= end)
                    .order_by(SessionPlan.date).all())
        mine_by_session = {}
        if player:
            mine_by_session = {r.session_id: r for r in SessionRSVP.query.filter(
                SessionRSVP.player_id == player.id, SessionRSVP.session_id.in_([s.id for s in sessions] or [-1]))}
        counts = _session_counts([s.id for s in sessions]) if coach else {}
        for s in sessions:
            answer = mine_by_session.get(s.id)
            if mine and answer and answer.status == 'not_attending':
                continue
            event = {
                'id': f'session-{s.id}', 'event_id': s.id, 'type': 'session', 'title': s.title,
                'start': _iso(s.date, s.start_time), 'allDay': not s.start_time,
                'formatted_date': s.formatted_date, 'formatted_time': s.formatted_time,
                'location': s.location, 'focus_area': s.focus_area, 'notes': s.notes,
                'rsvp_status': answer.status if answer else None,
                'rsvp_notes': answer.notes if answer else None,
                'details_url': url_for('session.detail', session_id=s.id),
                'can_rsvp': True,
            }
            if s.start_time and s.end_time:
                event['end'] = _iso(s.date, s.end_time)
            if coach:
                c = counts.get(s.id, {})
                event['counts'] = {'attending': c.get('attending', 0), 'maybe': c.get('maybe', 0),
                                   'not_attending': c.get('not_attending', 0)}
                event['edit_url'] = url_for('session.edit_session', session_id=s.id)
                event['manage_url'] = url_for('session.rsvps', session_id=s.id)
            events.append(event)

    if 'tournament' in types:
        query = Tournament.query.filter(
            Tournament.team_organization_id == team_id, Tournament.start_date.isnot(None),
            Tournament.start_date <= end,
            db.func.coalesce(Tournament.end_date, Tournament.start_date) >= start)
        if squad_id:
            query = query.filter(Tournament.squad_id == squad_id)
        for t in query.order_by(Tournament.start_date).all():
            answer = (TournamentRSVP.query.filter_by(tournament_id=t.id, player_id=player.id).first()
                      if player else None)
            selection = rsvps.player_selection(t, answer)
            if mine and ((answer and answer.status == 'not_attending') or selection in ('not_picked',)):
                continue
            summary = rsvps.squad_summary(t)
            event = {
                'id': f'tournament-{t.id}', 'event_id': t.id, 'type': 'tournament', 'title': t.name,
                'start': t.start_date.isoformat(), 'allDay': True,
                # FullCalendar's end is exclusive: the day after the last day
                'end': ((t.end_date or t.start_date) + timedelta(days=1)).isoformat(),
                'formatted_date': t.formatted_date_range, 'location': t.location, 'notes': t.notes or '',
                'rsvp_status': answer.status if answer else None,
                'rsvp_notes': answer.notes if answer else None,
                'selection': selection,
                'deadline': t.rsvp_deadline.strftime('%a %d %b') if t.rsvp_deadline else None,
                'counts': {k: summary[k] for k in ('attending', 'maybe', 'not_attending', 'no_reply', 'picked')},
                'details_url': url_for('tournament.detail', tournament_id=t.id),
                'can_rsvp': True,
            }
            if coach:
                event['edit_url'] = url_for('tournament.edit', tournament_id=t.id)
                event['manage_url'] = url_for('tournament.detail', tournament_id=t.id, tab='squad')
            events.append(event)

    if 'game' in types:
        query = Game.query.filter(Game.team_organization_id == team_id, Game.date.isnot(None),
                                  Game.date >= start, Game.date <= end)
        if squad_id:
            query = query.filter(Game.squad_id == squad_id)
        games = query.order_by(Game.date, Game.start_time).all()
        playing = set()
        if player and games:
            playing = {gid for (gid,) in db.session.query(GamePlayer.game_id).filter(
                GamePlayer.player_id == player.id, GamePlayer.game_id.in_([g.id for g in games]))}
        for g in games:
            if mine and g.id not in playing:
                continue
            # A tournament's untimed games are already covered by the tournament
            if g.tournament_id and not g.start_time and g.id not in playing:
                continue
            played = bool(g.our_score or g.their_score)
            event = {
                'id': f'game-{g.id}', 'event_id': g.id, 'type': 'game',
                'title': f'vs {g.opponent}' + (f' ({g.result_string})' if played else ''),
                'start': _iso(g.date, g.start_time), 'allDay': not g.start_time,
                'formatted_date': g.date.strftime('%A %d %B %Y') + (f', {g.start_time.strftime("%H:%M")}' if g.start_time else ''),
                'location': ', '.join(filter(None, [g.tournament.name if g.tournament else None, g.field])),
                'notes': '', 'playing': g.id in playing,
                'details_url': url_for('game.detail', game_id=g.id),
                'can_rsvp': False,
            }
            if g.start_time:
                event['end'] = (datetime.combine(g.date, g.start_time) + timedelta(minutes=90)).isoformat()
            if coach:
                event['edit_url'] = url_for('game.edit', game_id=g.id)
            events.append(event)

    return events


@calendar_bp.route('/calendar')
@login_required
def index():
    team_id = get_current_team_id()
    feed_url = None
    if current_user.calendar_token:
        feed_url = url_for('calendar.feed', token=current_user.calendar_token, _external=True)
    return render_template('calendar/index.html', squads=team_squads(team_id), feed_url=feed_url)


@calendar_bp.route('/calendar/events')
@login_required
def events():
    """Events for the dates on screen: ?start=&end= (as FullCalendar sends
    them), ?types=session,game, ?squad=<id>, ?mine=1."""
    team_id = get_current_team_id()
    today = date.today()
    start = _day(request.args.get('start'), today.replace(day=1) - timedelta(days=7))
    end = _day(request.args.get('end'), start + timedelta(days=42))
    if end < start or (end - start).days > 400:
        end = start + timedelta(days=400)
    types = tuple(t for t in (request.args.get('types') or ','.join(TYPES)).split(',') if t in TYPES)
    squad_id = request.args.get('squad', type=int)
    if squad_id and squad_id not in {s.id for s in team_squads(team_id)}:
        squad_id = None
    return jsonify(team_events(team_id, start, end, player=current_user.player, types=types, squad_id=squad_id,
                               mine=request.args.get('mine') == '1', coach=current_user.is_coach))


@calendar_bp.route('/api/rsvp', methods=['POST'])
@login_required
def api_rsvp():
    if not request.is_json:
        return jsonify({'success': False, 'message': 'Invalid request format'}), 400

    data = request.get_json(silent=True) or {}
    event_id, event_type, status = data.get('id'), data.get('type'), data.get('status')
    if not all([event_id, event_type, status]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    if not current_user.player:
        return jsonify({'success': False, 'message': 'You need to link your account to a player first'}), 400

    try:
        answer = rsvps.set_rsvp(event_type, event_id, get_current_team_id(), current_user.player,
                                status, data.get('notes'))
    except rsvps.RSVPError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    if answer is None:
        return jsonify({'success': False, 'message': 'Event not found'}), 404
    db.session.commit()
    return jsonify({'success': True, 'message': 'RSVP updated successfully'})


# ── Calendar subscription ──────────────────────────────────────────────────

@calendar_bp.route('/calendar/feed-link', methods=['POST'])
@login_required
def feed_link():
    """Make (or, with reset=1, replace) the user's private feed address."""
    if not current_user.calendar_token or request.form.get('reset'):
        current_user.calendar_token = secrets.token_urlsafe(24)
        db.session.commit()
        if request.form.get('reset'):
            flash('New calendar link made: the old one no longer works.', 'info')
    return redirect(url_for('calendar.index', _anchor='subscribe'))


def _ics_escape(value):
    return (str(value or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
            .replace('\r\n', '\\n').replace('\n', '\\n'))


def _fold(line):
    """iCalendar lines are at most 75 octets; longer ones continue with a space."""
    out, raw = [], line.encode('utf-8')
    while len(raw) > 75:
        cut = 75 if not out else 74
        while cut and (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode('utf-8'))
        raw = raw[cut:]
    out.append(raw.decode('utf-8'))
    return '\r\n '.join(out)


def _ics_event(uid, summary, start, end=None, all_day=True, location=None, description=None, url=None):
    lines = ['BEGIN:VEVENT', f'UID:{uid}', f'DTSTAMP:{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}']
    if all_day:
        lines.append(f'DTSTART;VALUE=DATE:{start.strftime("%Y%m%d")}')
        lines.append(f'DTEND;VALUE=DATE:{(end or start + timedelta(days=1)).strftime("%Y%m%d")}')
    else:
        # Floating local time: shown at the same clock time wherever you are
        lines.append(f'DTSTART:{start.strftime("%Y%m%dT%H%M%S")}')
        lines.append(f'DTEND:{(end or start + timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")}')
    lines.append(f'SUMMARY:{_ics_escape(summary)}')
    if location:
        lines.append(f'LOCATION:{_ics_escape(location)}')
    if description:
        lines.append(f'DESCRIPTION:{_ics_escape(description)}')
    if url:
        lines.append(f'URL:{url}')
    lines.append('END:VEVENT')
    return [_fold(line) for line in lines]


def user_feed(user, today=None):
    """The user's calendar across their teams: sessions, tournaments (not
    ones they've said no to or weren't picked for) and the games they play,
    or every game for someone with no player profile."""
    today = today or date.today()
    start, end = today - timedelta(days=FEED_PAST_DAYS), today + timedelta(days=FEED_FUTURE_DAYS)
    base = request.host_url.rstrip('/')
    host = request.host.split(':')[0]
    lines = []
    for team_id in user.team_ids or [user.team_organization_id]:
        team = db.session.get(TeamOrganization, team_id)
        if team is None:
            continue
        player = Player.query.filter_by(user_id=user.id, team_organization_id=team_id).first()
        for e in team_events(team_id, start, end, player=player, mine=bool(player)):
            kind, event_id = e['type'], e['event_id']
            title = e['title'] if kind != 'game' else f'{team.name} {e["title"]}'
            if kind == 'tournament':
                first = date.fromisoformat(e['start'])
                lines += _ics_event(f'tournament-{event_id}@{host}', title, first, date.fromisoformat(e['end']),
                                    location=e['location'], description=e['notes'], url=base + e['details_url'])
            elif e['allDay']:
                lines += _ics_event(f'{kind}-{event_id}@{host}', title, date.fromisoformat(e['start'][:10]),
                                    location=e['location'], url=base + e['details_url'])
            else:
                lines += _ics_event(f'{kind}-{event_id}@{host}', title, datetime.fromisoformat(e['start']),
                                    datetime.fromisoformat(e['end']) if e.get('end') else None, all_day=False,
                                    location=e['location'], url=base + e['details_url'])
    head = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Ultimate Coach//Team calendar//EN',
            'CALSCALE:GREGORIAN', 'METHOD:PUBLISH', 'X-WR-CALNAME:Ultimate Coach', 'REFRESH-INTERVAL;VALUE=DURATION:PT6H']
    return '\r\n'.join(head + lines + ['END:VCALENDAR']) + '\r\n'


@calendar_bp.route('/calendar/feed/<token>.ics')
def feed(token):
    """No login: the long random token in the address is the key."""
    user = User.query.filter_by(calendar_token=token).first() if token else None
    if user is None:
        abort(404)
    return Response(user_feed(user), mimetype='text/calendar',
                    headers={'Content-Disposition': 'inline; filename="ultimate-coach.ics"',
                             'Cache-Control': 'private, max-age=900'})
