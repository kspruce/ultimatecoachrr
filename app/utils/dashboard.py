"""What the home page shows: the next things on, what needs the signed-in
person (an answer from a player, a decision from a coach), and the season.

Everything is worked out here so the page and its sentence at the top
("2 things need you") read from the same lists.
"""
from datetime import date, time, timedelta

from flask import url_for

from app import db
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.session import Attendance, SessionPlan
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP
from app.utils import rsvp as session_rsvp
from app.utils import tournament_rsvp as rsvps
from app.utils.season import viewing_season, viewing_squad

# How far ahead "Coming up" and the coach's checks look
SESSION_DAYS = 14
GAME_DAYS = 30
COMING_UP_ROWS = 6


def _unplayed(query):
    return query.filter(Game.our_score == 0, Game.their_score == 0)


def _enabled(settings, name):
    return settings is None or getattr(settings, name, True)


# ── Results and the season ─────────────────────────────────────────────────

def season_summary(team_id, today):
    played = (Game.query
              .filter(Game.team_organization_id == team_id,
                      Game.date.isnot(None), Game.date <= today)
              .order_by(Game.date.desc(), Game.id.desc())
              .all())
    # A game with no points scored yet hasn't really been played
    played = [g for g in played if (g.our_score or 0) + (g.their_score or 0) > 0]

    # The season being viewed (the current one unless another is picked)
    viewing = viewing_season(team_id)
    squad_view = viewing_squad(team_id)
    season_games = [g for g in played
                    if (viewing is None or g.season_id == viewing.id)
                    and (squad_view is None or g.squad_id == squad_view.id)]
    wins = sum(1 for g in season_games if g.is_win)
    losses = sum(1 for g in season_games if g.is_loss)
    season = {
        'year': viewing.name if viewing else 'all time',
        'obj': viewing,
        'game_ids': [g.id for g in season_games],
        'games': len(season_games),
        'wins': wins,
        'losses': losses,
        'win_rate': round(wins / len(season_games) * 100) if season_games else 0,
        'point_diff': sum((g.our_score or 0) - (g.their_score or 0) for g in season_games),
        # Oldest first, for the little bar chart
        'diffs': [(g.our_score or 0) - (g.their_score or 0) for g in reversed(season_games[:12])],
    }
    recent_results = [{
        'opponent': g.opponent,
        'score': f'{g.our_score}–{g.their_score}',
        'result': 'W' if g.is_win else ('L' if g.is_loss else 'T'),
        'date': g.date,
        'tournament': g.tournament.name if g.tournament else None,
        'link': url_for('game.detail', game_id=g.id),
    } for g in played[:5]]
    return season, recent_results


def next_games(team_id, today):
    """The next unplayed game and up to three more on the same day."""
    next_game = (_unplayed(Game.query.filter(Game.team_organization_id == team_id,
                                             Game.date.isnot(None), Game.date >= today))
                 .order_by(Game.date.asc(), Game.start_time.asc(), Game.id.asc())
                 .first())
    later = []
    if next_game:
        later = (_unplayed(Game.query.filter(Game.team_organization_id == team_id,
                                             Game.date == next_game.date, Game.id != next_game.id))
                 .order_by(Game.start_time.asc(), Game.id.asc()).limit(3).all())
    return next_game, later


def upcoming_tournaments(team_id, today, limit=3):
    """Tournaments that haven't finished yet, soonest first."""
    return (Tournament.query
            .filter(Tournament.team_organization_id == team_id, Tournament.start_date.isnot(None),
                    db.func.coalesce(Tournament.end_date, Tournament.start_date) >= today)
            .order_by(Tournament.start_date).limit(limit).all())


def squad_card(tournament):
    """Replies so far for the coach's tournament card."""
    if tournament is None:
        return None
    summary = rsvps.squad_summary(tournament)
    return {
        'tournament': tournament,
        'attending': summary['attending'],
        'maybe': summary['maybe'],
        'out': summary['not_attending'],
        'no_reply': summary['no_reply'],
        'active': summary['total'],
        'picked': summary['picked'],
    }


# ── Coming up, with the viewer's answer on each row ────────────────────────

def coming_up(team_id, today, player=None, is_coach=False, settings=None):
    """Sessions, tournaments and games (those not part of a tournament) in
    date order. Each row says whether the player still needs to answer,
    or, for a coach, how many are coming."""
    rows = []
    squad_id = session_rsvp.player_squads(team_id).get(player.id) if player else None

    if _enabled(settings, 'sessions_enabled'):
        sessions = session_rsvp.upcoming_sessions(team_id, today, today + timedelta(days=SESSION_DAYS))
        if player is not None:
            sessions = [s for s in sessions if session_rsvp.can_join(s, squad_id)]
        answer_map = session_rsvp.answers(sessions, None if is_coach else ([player.id] if player else []))
        players = session_rsvp.team_players(team_id) if is_coach else None
        squads = session_rsvp.player_squads(team_id) if is_coach else None
        for s in sessions:
            answer = answer_map.get((s.id, player.id)) if player else None
            row = {
                'type': 'session', 'id': s.id, 'title': s.title, 'day': s.date,
                'time': s.start_time, 'url': url_for('session.detail', session_id=s.id),
                'meta': ' · '.join(x for x in ['Session', s.location] if x),
                'status': answer.status if answer else None,
                'usual': bool(answer and answer.usual),
                'can_reply': player is not None,
                # Another squad's session they're welcome at: answer if they like, not asked to
                'asked': player is not None and session_rsvp.is_for(s, squad_id),
            }
            if is_coach:
                row['counts'] = session_rsvp.counts(s, answer_map, players, squads)
            rows.append(row)

    tournaments = upcoming_tournaments(team_id, today)
    mine = {}
    if player is not None and tournaments:
        mine = {r.tournament_id: r for r in TournamentRSVP.query.filter(
            TournamentRSVP.player_id == player.id,
            TournamentRSVP.tournament_id.in_([t.id for t in tournaments]))}
    for t in tournaments:
        r = mine.get(t.id)
        eligible = player is not None and (r is not None or player.id in {p.id for p in rsvps.eligible_players(t)})
        if player is not None and not eligible and not is_coach:
            continue
        selection = rsvps.player_selection(t, r) if eligible else None
        days = ((t.end_date or t.start_date) - t.start_date).days + 1
        meta = ['Tournament', f'{days} days' if days > 1 else None, t.location]
        if selection == 'picked':
            meta.append('Picked')
        elif selection == 'reserve':
            meta.append('Reserve')
        elif eligible and not (r and r.status) and t.rsvp_deadline:
            meta.append(f'reply by {t.rsvp_deadline.day} {t.rsvp_deadline.strftime("%b")}')
        row = {
            'type': 'tournament', 'id': t.id, 'title': t.name, 'day': t.start_date, 'time': None,
            'url': url_for('tournament.detail', tournament_id=t.id),
            'meta': ' · '.join(x for x in meta if x),
            'status': r.status if r else None, 'usual': False, 'can_reply': eligible,
            'selection': selection,
        }
        if is_coach:
            row['summary'] = rsvps.squad_summary(t)
        rows.append(row)

    games = (_unplayed(Game.query.filter(Game.team_organization_id == team_id,
                                         Game.tournament_id.is_(None), Game.date.isnot(None),
                                         Game.date >= today, Game.date <= today + timedelta(days=GAME_DAYS)))
             .order_by(Game.date, Game.start_time).limit(3).all())
    for g in games:
        rows.append({
            'type': 'game', 'id': g.id, 'title': f'vs {g.opponent}', 'day': g.date, 'time': g.start_time,
            'url': url_for('game.detail', game_id=g.id),
            'meta': ' · '.join(x for x in ['Game', g.field, g.location] if x),
            'status': None, 'usual': False, 'can_reply': False,
        })

    for row in rows:
        row.setdefault('selection', None)
        # Once the squad is out there's nothing left to answer
        row['needs_reply'] = (row['can_reply'] and row.get('asked', True)
                              and not row['status'] and not row['selection'])
    rows.sort(key=lambda r: (r['day'], r['time'] is None, r['time'] or time.min, r['type']))
    # Keep anything still waiting on the player, even if it's further out
    shown = rows[:COMING_UP_ROWS] + [r for r in rows[COMING_UP_ROWS:] if r['needs_reply']]
    return shown, [r for r in rows if r['needs_reply']]


# ── Player cards ───────────────────────────────────────────────────────────

def my_tournaments(team_id, today, player):
    """The upcoming tournaments the player is going to or being asked
    about, with their answer, the coach's (published) call and their games."""
    if player is None:
        return []
    out = []
    for t in upcoming_tournaments(team_id, today):
        r = TournamentRSVP.query.filter_by(tournament_id=t.id, player_id=player.id).first()
        if r is None and player.id not in {p.id for p in rsvps.eligible_players(t)}:
            continue
        selection = rsvps.player_selection(t, r)
        games = rsvps.player_games(t, player) if selection == 'picked' else []
        out.append({'tournament': t, 'status': r.status if r else None, 'selection': selection,
                    'games': [g for g in games if g.date is None or g.date >= today]})
    return out


def my_session(team_id, today, player, coming):
    """The player's next session (the first in Coming up)."""
    for row in coming:
        if row['type'] == 'session':
            return {'session': db.session.get(SessionPlan, row['id']), 'status': row['status'],
                    'usual': row['usual'], 'can_reply': row['can_reply']}
    return None


def my_numbers(team_id, today, player, season):
    """Training attended (of sessions where attendance was taken) and games
    played, both in the season being viewed."""
    if player is None:
        return None
    taken = (db.session.query(Attendance.session_id)
             .join(SessionPlan, SessionPlan.id == Attendance.session_id)
             .filter(SessionPlan.team_organization_id == team_id, SessionPlan.date <= today))
    viewing = season.get('obj')
    if viewing is not None:
        taken = taken.filter(SessionPlan.date >= viewing.start_date, SessionPlan.date <= viewing.end_date)
    taken_ids = {sid for (sid,) in taken.distinct()}
    attended = 0
    if taken_ids:
        attended = (Attendance.query
                    .filter(Attendance.player_id == player.id, Attendance.session_id.in_(taken_ids),
                            Attendance.status.in_(['present', 'late']))
                    .count())
    played = 0
    if season['game_ids']:
        played = (GamePlayer.query
                  .filter(GamePlayer.player_id == player.id, GamePlayer.game_id.in_(season['game_ids']))
                  .count())
    return {
        'attendance': round(attended / len(taken_ids) * 100) if taken_ids else None,
        'sessions': len(taken_ids),
        'games_played': played,
    }


def to_read_and_watch(team_id, settings, sees_hidden=False, user=None):
    """Theory the coaches have asked this person to read and hasn't yet,
    then the newest theory topics and clip playlists from the coaches."""
    from app.models.clip_playlist import ClipPlaylist
    from app.models.theory import TheorySection, TheoryTopic

    items, assigned = [], []
    if _enabled(settings, 'theory_enabled'):
        if user is not None:
            from app.utils.theory import assigned_unread
            for a in assigned_unread(user.id, team_id):
                due = f' · read by {a.due_date.strftime("%a %-d %b")}' if a.due_date else ''
                assigned.append({'kind': 'theory', 'title': a.topic.name, 'meta': f'Assigned reading{due}',
                                 'when': None, 'pill': 'To read',
                                 'url': url_for('theory.topic', topic_id=a.topic_id)})
        topics = (TheoryTopic.query.join(TheorySection, TheorySection.id == TheoryTopic.section_id)
                  .filter(TheoryTopic.team_organization_id == team_id, TheoryTopic.published.is_(True))
                  .order_by(db.func.coalesce(TheoryTopic.updated_at, TheoryTopic.created_at).desc())
                  .limit(3).all())
        assigned_urls = {a['url'] for a in assigned}
        for t in topics:
            if url_for('theory.topic', topic_id=t.id) in assigned_urls:
                continue
            items.append({'kind': 'theory', 'title': t.name, 'meta': t.section.name if t.section else 'Theory',
                          'when': t.updated_at or t.created_at,
                          'url': url_for('theory.topic', topic_id=t.id)})
    if _enabled(settings, 'clip_enabled'):
        playlists = (ClipPlaylist.query.filter_by(team_organization_id=team_id)
                     .order_by(db.func.coalesce(ClipPlaylist.updated_at, ClipPlaylist.created_at).desc())
                     .limit(2).all())
        for p in playlists:
            n = len(p.visible_items(sees_hidden))
            if not n:
                continue
            items.append({'kind': 'playlist', 'title': p.title,
                          'meta': f'Playlist · {n} clip{"s" if n != 1 else ""}',
                          'when': p.updated_at or p.created_at,
                          'url': url_for('clip.view_playlist', playlist_id=p.id)})
    items.sort(key=lambda i: i['when'] or date.min, reverse=True)
    return (assigned + items)[:max(4, len(assigned))]


# ── What a coach needs to deal with ────────────────────────────────────────

def needs_attention(team_id, today, coming, settings=None, roster_signup=None):
    """[{icon, title, detail, url, action, action_label}] for the coach,
    most pressing first: chasing replies, publishing a squad, filling
    line-ups, and players who still need an account."""
    items = []

    for row in coming:
        if row['type'] == 'tournament':
            t = db.session.get(Tournament, row['id'])
            summary = row['summary']
            hub = url_for('tournament.detail', tournament_id=t.id, tab='squad')
            if summary['no_reply'] and not t.deadline_passed:
                deadline = f'reply by {t.rsvp_deadline.strftime("%a %-d %b")}' if t.rsvp_deadline else 'no reply-by date set'
                items.append({'icon': 'bi-envelope', 'url': hub,
                              'title': f'{summary["no_reply"]} haven\'t replied for {t.name}',
                              'detail': f'{summary["attending"]} in · {summary["maybe"]} maybe · {deadline}',
                              'action': url_for('tournament.nudge', tournament_id=t.id),
                              'action_label': 'Nudge'})
            if not t.selection_published and (t.deadline_passed or (t.start_date - today).days <= 14):
                picked = f'{summary["picked"]} picked' + (f' of {t.squad_size_target}' if t.squad_size_target else '')
                items.append({'icon': 'bi-people', 'url': hub,
                              'title': f'Squad for {t.name} not published',
                              'detail': f'{picked} · {summary["attending"]} available',
                              'action': None, 'action_label': None})

    # Upcoming games with nobody down to play
    empty = (_unplayed(Game.query.outerjoin(GamePlayer, GamePlayer.game_id == Game.id)
                       .filter(Game.team_organization_id == team_id, Game.date.isnot(None),
                               Game.date >= today, Game.date <= today + timedelta(days=GAME_DAYS)))
             .group_by(Game.id).having(db.func.count(GamePlayer.id) == 0)
             .order_by(Game.date).all())
    by_tournament = {}
    for g in empty:
        by_tournament.setdefault(g.tournament_id, []).append(g)
    for tournament_id, games in by_tournament.items():
        n = len(games)
        if tournament_id:
            t = games[0].tournament
            items.append({'icon': 'bi-grid-3x3', 'url': url_for('tournament.detail', tournament_id=t.id, tab='games'),
                          'title': f'{n} game{"s" if n != 1 else ""} at {t.name} {"have" if n != 1 else "has"} no players',
                          'detail': ', '.join(f'vs {g.opponent}' for g in games[:3]) + ('…' if n > 3 else ''),
                          'action': None, 'action_label': None})
        else:
            for g in games:
                items.append({'icon': 'bi-grid-3x3', 'url': url_for('game.detail', game_id=g.id),
                              'title': f'No players down for vs {g.opponent}',
                              'detail': f'{g.date.strftime("%a %-d %b")}',
                              'action': None, 'action_label': None})

    # The next session in the coming week that people haven't answered
    for row in coming:
        if row['type'] == 'session' and (row['day'] - today).days <= 7:
            c = row['counts']
            if c['none'] or c[session_rsvp.MAYBE]:
                items.append({'icon': 'bi-calendar-check', 'url': row['url'],
                              'title': f'{c["none"]} haven\'t answered for {row["title"]}',
                              'detail': f'{row["day"].strftime("%a %-d %b")} · {c[session_rsvp.ATTENDING]} yes · {c[session_rsvp.MAYBE]} maybe',
                              'action': url_for('training.nudge', session_id=row['id']),
                              'action_label': 'Nudge'})
            break

    if roster_signup and roster_signup.get('waiting'):
        waiting = roster_signup['waiting']
        names = ', '.join(p.name for p in waiting[:4]) + (f' and {len(waiting) - 4} more' if len(waiting) > 4 else '')
        verb = "hasn't" if len(waiting) == 1 else "haven't"
        items.append({'icon': 'bi-person-plus',
                      'url': url_for('auth.users', _anchor='signup'),
                      'title': f'{len(waiting)} of {roster_signup["active"]} players {verb} joined yet',
                      'detail': names, 'action': None, 'action_label': None})
    return items


# ── Everything for the page ────────────────────────────────────────────────

def build(user, team_id, settings=None, roster_signup=None, today=None):
    today = today or date.today()
    is_coach = bool(user.is_coach)
    player = user.player if getattr(user, 'player', None) is not None \
        and user.player.team_organization_id == team_id else None

    season, recent_results = season_summary(team_id, today)
    next_game, later_games = next_games(team_id, today)
    coming, waiting = coming_up(team_id, today, player, is_coach, settings)

    data = {
        'today': today,
        'is_coach_view': is_coach,
        'season': season,
        'recent_results': recent_results,
        'next_game': next_game,
        'later_games': later_games,
        'coming_up': coming,
        'needs_reply': waiting,
        'me': player,
        'my_numbers': my_numbers(team_id, today, player, season),
        'my_tournaments': my_tournaments(team_id, today, player),
        'my_session': my_session(team_id, today, player, coming) if player else None,
    }
    if is_coach:
        tournaments = upcoming_tournaments(team_id, today, limit=1)
        data['squad'] = squad_card(tournaments[0] if tournaments else None)
        data['next_session'] = next((db.session.get(SessionPlan, r['id']) for r in coming
                                     if r['type'] == 'session'), None)
        data['next_session_counts'] = next((r['counts'] for r in coming if r['type'] == 'session'), None)
        data['attention'] = needs_attention(team_id, today, coming, settings, roster_signup)
    else:
        data['learn'] = to_read_and_watch(team_id, settings, user=user)
    return data
