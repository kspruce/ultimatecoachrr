"""Cached stats calculations, cleared whenever stats data changes.

Any commit that adds, changes or deletes a row the stats are built from
(see STATS_MODELS) clears the cache, so pages never show stale numbers after
a point is recorded or undone. The cache is per process (SimpleCache); the
app runs a single gunicorn worker, so that covers every request.
"""
from itertools import chain

from flask import current_app
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import cache
from app.models.cutting_skill import CuttingSkill
from app.models.event import Event, Pull
from app.models.game import Game
from app.models.player import Player
from app.models.point import Point, LineUp
from app.models.throws import Throw
from app.models.tournament import Tournament
from app.utils.team_filter import get_current_team_id

from app.stats.formulas import games_to_tuple
from app.stats.team import calculate_team_averages

STATS_MODELS = (Game, Point, LineUp, Event, Pull, Throw, CuttingSkill, Player, Tournament)
_DIRTY = 'stats_cache_dirty'


def get_cached_team_averages(games=None):
    """Team averages used to scale PER, cached per team and set of games."""
    team_id = get_current_team_id()
    game_ids = games_to_tuple(games) if games else None
    return _cached_team_averages(team_id, game_ids)


@cache.memoize(timeout=3600)
def _cached_team_averages(team_id, game_ids_tuple):
    """Internal cached worker — keyed by team_id + sorted game IDs."""
    if game_ids_tuple:
        games = Game.query.filter(Game.id.in_(game_ids_tuple)).all()
    else:
        games = None
    return calculate_team_averages(games)


def invalidate_stats_cache():
    """Drop every cached stats result."""
    cache.delete_memoized(_cached_team_averages)


@event.listens_for(Session, 'before_flush')
def _note_stats_changes(session, flush_context, instances):
    if any(isinstance(obj, STATS_MODELS)
           for obj in chain(session.new, session.dirty, session.deleted)):
        session.info[_DIRTY] = True


@event.listens_for(Session, 'do_orm_execute')
def _note_bulk_stats_changes(orm_execute_state):
    # Query.update()/delete() and update()/delete() statements skip before_flush.
    if orm_execute_state.is_update or orm_execute_state.is_delete:
        mapper = orm_execute_state.bind_mapper
        if mapper is not None and issubclass(mapper.class_, STATS_MODELS):
            orm_execute_state.session.info[_DIRTY] = True


@event.listens_for(Session, 'after_commit')
def _clear_after_commit(session):
    if session.info.pop(_DIRTY, False):
        try:
            invalidate_stats_cache()
        except RuntimeError:
            pass  # no app context (e.g. a standalone script): nothing cached
        else:
            current_app.logger.debug('Stats cache cleared after a data change')

