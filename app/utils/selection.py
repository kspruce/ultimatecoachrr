"""Numbers beside each name when a coach picks a tournament squad:
training attendance, games played and rating, for the tournament's season.
Only for teams that have switched this on (TeamSettings.selection_stats_enabled):
some coaches would rather not have numbers in front of them when they pick."""
from app import db
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.session import Attendance, SessionPlan
from app.stats.profile import MIN_RATED_POINTS
from app.utils import rsvp


def _season_games(tournament):
    """The team's played games in the tournament's season, before it starts."""
    query = Game.query.filter(Game.team_organization_id == tournament.team_organization_id,
                              Game.date.isnot(None), Game.our_score + Game.their_score > 0)
    if tournament.season_id:
        query = query.filter(Game.season_id == tournament.season_id)
    if tournament.start_date:
        query = query.filter(Game.date < tournament.start_date)
    return query.all()


def _attendance(tournament, players):
    """{player id: (came, of)} over the season's sessions with a register
    taken that were for the player's squad (or that they were marked at)."""
    team_id = tournament.team_organization_id
    query = SessionPlan.query.filter(SessionPlan.team_organization_id == team_id, SessionPlan.date.isnot(None),
                                     SessionPlan.attendances.any())
    season = tournament.season_obj
    if season is not None:
        query = query.filter(SessionPlan.date >= season.start_date, SessionPlan.date <= season.end_date)
    if tournament.start_date:
        query = query.filter(SessionPlan.date < tournament.start_date)
    sessions = query.all()
    if not sessions:
        return {}
    marks = {}
    for a in Attendance.query.filter(Attendance.session_id.in_([s.id for s in sessions])):
        marks[(a.session_id, a.player_id)] = a.status
    squads = rsvp.player_squads(team_id)
    out = {}
    for p in players:
        came = of = 0
        for s in sessions:
            mark = marks.get((s.id, p.id))
            if mark is None and not rsvp.is_for(s, squads.get(p.id)):
                continue
            of += 1
            came += mark in ('present', 'late')
        if of:
            out[p.id] = (came, of)
    return out


def numbers(tournament, players, with_ratings=True):
    """{player id: {'attendance': % or None, 'sessions': n, 'games': n,
    'per': rating or None}} for the squad table."""
    games = _season_games(tournament)
    game_ids = [g.id for g in games]
    played = {}
    if game_ids:
        played = dict(db.session.query(GamePlayer.player_id, db.func.count(GamePlayer.id))
                      .filter(GamePlayer.game_id.in_(game_ids)).group_by(GamePlayer.player_id).all())
    attendance = _attendance(tournament, players)
    ratings = {}
    if with_ratings and games:
        from app.stats.cache import get_cached_team_averages
        from app.stats.formulas import apply_ratings
        from app.stats.loaders import preload_game_points
        from app.stats.players import get_players_base_stats
        preload_game_points(games)
        averages = get_cached_team_averages(games)
        for player_id, stats in get_players_base_stats(players, games).items():
            # Too few full-stat points and a rating is noise
            if stats.get('analysed_points', 0) >= MIN_RATED_POINTS:
                ratings[player_id] = apply_ratings(stats, averages).get('per')
            played[player_id] = max(played.get(player_id, 0), stats.get('games_played', 0))
    out = {}
    for p in players:
        came, of = attendance.get(p.id, (0, 0))
        out[p.id] = {'attendance': round(came / of * 100) if of else None, 'sessions': of,
                     'games': played.get(p.id, 0), 'per': ratings.get(p.id)}
    return out
