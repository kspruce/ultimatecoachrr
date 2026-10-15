"""Load each game's points once per request.

Game.points is a dynamic relationship, so every `game.points.all()` is a new
query; the stats code used to repeat it in several functions per game. These
helpers load the points (and their events) once and remember them on the
Game instance, which only lives for the current request's DB session.
"""
from sqlalchemy.orm import selectinload

from app.models.point import Point

_ATTR = '_stats_points'


def preload_game_points(games):
    """Load the points (with events) for many games in two queries."""
    games = [g for g in games or [] if g is not None and _ATTR not in g.__dict__]
    if not games:
        return
    by_game = {g.id: [] for g in games}
    points = (Point.query
              .filter(Point.game_id.in_(list(by_game)))
              .options(selectinload(Point.events))
              .order_by(Point.game_id, Point.point_number, Point.id)
              .all())
    for point in points:
        by_game[point.game_id].append(point)
    for game in games:
        game.__dict__[_ATTR] = by_game[game.id]


def game_points(game):
    """The game's points in point order (loaded once per request)."""
    if _ATTR not in game.__dict__:
        preload_game_points([game])
    return game.__dict__[_ATTR]


def game_line_points(game, line_type):
    """The game's points where we started on 'O-line' or 'D-line'."""
    return [p for p in game_points(game) if p.our_line_type == line_type]
