# app/utils/tournament_rsvp.py
"""Replies to tournaments and the coach's picks (sessions are app/utils/rsvp.py).

Every place a player answers a tournament (its page, the calendar, the home
page) and every place a coach picks a squad goes through here, so the rules
are the same everywhere: only real answers are stored, a coach's pick never
stands in for the player's answer, and replies after the reply-by date are
kept but flagged.
"""
from datetime import datetime

from app import db
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.player import Player
from app.models.season import SeasonRoster
from app.models.session import SessionPlan
from app.models.tournament import Tournament
from app.models.tournament_rsvp import TournamentRSVP

STATUSES = tuple(value for value, _ in TournamentRSVP.STATUSES)
SELECTIONS = tuple(value for value, _ in TournamentRSVP.SELECTIONS)


class RSVPError(ValueError):
    """An answer that can't be stored; the message is fit to show."""


def _clean_notes(notes):
    notes = (notes or '').strip()
    return notes[:1000] or None


# ── Players answering ──────────────────────────────────────────────────────

def set_tournament_rsvp(tournament, player, status, notes=None):
    """Store the player's answer for a tournament and return the row."""
    if status not in STATUSES:
        raise RSVPError('Pick attending, maybe or can\'t make it.')
    if player.team_organization_id != tournament.team_organization_id:
        raise RSVPError('That player isn\'t on this team.')
    rsvp = TournamentRSVP.query.filter_by(tournament_id=tournament.id, player_id=player.id).first()
    if rsvp is None:
        rsvp = TournamentRSVP(tournament_id=tournament.id, player_id=player.id,
                              team_organization_id=tournament.team_organization_id)
        db.session.add(rsvp)
    rsvp.status = status
    rsvp.notes = _clean_notes(notes)
    rsvp.responded_at = datetime.utcnow()
    return rsvp


def set_rsvp(kind, event_id, team_id, player, status, notes=None):
    """Answer a session or tournament by id; None if it isn't this team's."""
    from app.utils import rsvp as session_rsvp

    model = {'session': SessionPlan, 'tournament': Tournament}.get(kind)
    if model is None:
        raise RSVPError('Unknown event type.')
    event = model.query.filter_by(id=event_id, team_organization_id=team_id).first()
    if event is None:
        return None
    if kind == 'tournament':
        return set_tournament_rsvp(event, player, status, notes)
    if status not in STATUSES:
        raise RSVPError('Pick attending, maybe or can\'t make it.')
    try:
        return session_rsvp.set_rsvp(event, player, status, notes)
    except ValueError as e:
        raise RSVPError(str(e))


# ── Who can go ─────────────────────────────────────────────────────────────

def eligible_players(tournament):
    """Players the tournament is for: its season's roster (just its squad,
    if it has one), without those who've left. A season with no roster yet
    falls back to the club's active players."""
    team_id = tournament.team_organization_id
    if tournament.season_id:
        query = (Player.query.join(SeasonRoster, SeasonRoster.player_id == Player.id)
                 .filter(SeasonRoster.season_id == tournament.season_id,
                         SeasonRoster.status != 'left',
                         Player.team_organization_id == team_id))
        if tournament.squad_id:
            query = query.filter(SeasonRoster.squad_id == tournament.squad_id)
        players = query.order_by(Player.name).all()
        if players or tournament.squad_id:
            return players
    return (Player.query.filter_by(team_organization_id=team_id, active=True)
            .order_by(Player.name).all())


def squad_rows(tournament):
    """One row per player for the coach's squad table: everyone eligible
    plus anyone else who has replied or been picked."""
    rsvps = {r.player_id: r for r in tournament.rsvps}
    players = {p.id: p for p in eligible_players(tournament)}
    missing = [pid for pid in rsvps if pid not in players]
    if missing:
        for p in Player.query.filter(Player.id.in_(missing)).all():
            players[p.id] = p
    rows = [{'player': p, 'rsvp': rsvps.get(p.id)} for p in players.values()]
    order = {'attending': 0, 'maybe': 1, None: 2, 'not_attending': 3}
    rows.sort(key=lambda r: (order.get(r['rsvp'].status if r['rsvp'] else None, 2), r['player'].name.lower()))
    return rows


def squad_summary(tournament, rows=None):
    rows = rows if rows is not None else squad_rows(tournament)
    summary = {'attending': 0, 'maybe': 0, 'not_attending': 0, 'no_reply': 0,
               'picked': 0, 'reserve': 0, 'picked_female': 0, 'picked_male': 0, 'picked_handlers': 0,
               'total': len(rows)}
    for row in rows:
        rsvp, player = row['rsvp'], row['player']
        summary[rsvp.status if rsvp and rsvp.status else 'no_reply'] += 1
        if rsvp and rsvp.selection == 'picked':
            summary['picked'] += 1
            gender = (player.gender_match or player.gender or '').lower()
            if gender in ('female', 'male'):
                summary[f'picked_{gender}'] += 1
            if player.position == 'handler':
                summary['picked_handlers'] += 1
        elif rsvp and rsvp.selection == 'reserve':
            summary['reserve'] += 1
    return summary


def no_reply_players(tournament):
    return [row['player'] for row in squad_rows(tournament)
            if not (row['rsvp'] and row['rsvp'].status)]


# ── The coach's picks ──────────────────────────────────────────────────────

def set_selection(tournament, player, selection):
    """Pick / reserve / not pick a player (None clears it). A player who
    hasn't replied gets a row with no answer, not a made-up one."""
    if selection is not None and selection not in SELECTIONS:
        raise RSVPError('Unknown selection.')
    if player.team_organization_id != tournament.team_organization_id:
        raise RSVPError('That player isn\'t on this team.')
    rsvp = TournamentRSVP.query.filter_by(tournament_id=tournament.id, player_id=player.id).first()
    if rsvp is None:
        if selection is None:
            return None
        rsvp = TournamentRSVP(tournament_id=tournament.id, player_id=player.id, status=None,
                              team_organization_id=tournament.team_organization_id)
        db.session.add(rsvp)
    rsvp.selection = selection
    rsvp.selected_by_admin = selection == 'picked'
    if selection != 'picked':
        # Not going: take them out of the tournament's games
        game_ids = [g.id for g in tournament.games]
        if game_ids:
            GamePlayer.query.filter(GamePlayer.game_id.in_(game_ids),
                                    GamePlayer.player_id == player.id).delete(synchronize_session=False)
    return rsvp


def picked_players(tournament):
    return (Player.query.join(TournamentRSVP, TournamentRSVP.player_id == Player.id)
            .filter(TournamentRSVP.tournament_id == tournament.id,
                    TournamentRSVP.selection == 'picked',
                    Player.team_organization_id == tournament.team_organization_id)
            .order_by(Player.name).all())


def player_selection(tournament, rsvp):
    """What the player may see of the coach's call: None until published."""
    if rsvp is None or not tournament.selection_published:
        return None
    return rsvp.selection or 'not_picked'


# ── Game line-ups ──────────────────────────────────────────────────────────

def default_game_players(game):
    """Who a new game starts with: a tournament's picked players (or, if
    nobody is picked yet, those attending); otherwise the squad's roster for
    the season, or the club's active players."""
    team_id = game.team_organization_id
    if game.tournament_id:
        tournament = db.session.get(Tournament, game.tournament_id)
        if tournament is not None:
            picked = [p.id for p in picked_players(tournament)]
            if picked:
                return picked
            attending = [r.player_id for r in tournament.rsvps.filter_by(status='attending')]
            if attending:
                return attending
            return [p.id for p in eligible_players(tournament)]
    if game.season_id:
        query = (db.session.query(SeasonRoster.player_id)
                 .filter(SeasonRoster.season_id == game.season_id, SeasonRoster.status != 'left'))
        if game.squad_id:
            query = query.filter(SeasonRoster.squad_id == game.squad_id)
        ids = [pid for (pid,) in query]
        if ids or game.squad_id:
            return ids
    return [p.id for p in Player.query.filter_by(team_organization_id=team_id, active=True)]


def assign_default_players(game):
    for player_id in default_game_players(game):
        db.session.add(GamePlayer(game_id=game.id, player_id=player_id,
                                  team_organization_id=game.team_organization_id))


def set_game_player(game, player_id, playing):
    existing = GamePlayer.query.filter_by(game_id=game.id, player_id=player_id).first()
    if playing and existing is None:
        db.session.add(GamePlayer(game_id=game.id, player_id=player_id,
                                  team_organization_id=game.team_organization_id))
    elif not playing and existing is not None:
        db.session.delete(existing)


def player_games(tournament, player):
    """The tournament's games the player is down to play, in order."""
    return (Game.query.join(GamePlayer, GamePlayer.game_id == Game.id)
            .filter(Game.tournament_id == tournament.id, GamePlayer.player_id == player.id)
            .order_by(Game.date, Game.start_time, Game.id).all())
