from app import db
from sqlalchemy import event
from app.models.point import Point
from app.models.game import Game
from app.models.player import Player
from app.models.throws import Throw
from app.models.event import Event
from app.models.stats import PlayerPointStats
from app.utils.stats_service import StatsService

# Define event listeners to automatically update the cache when data changes

# Point events
@event.listens_for(Point, 'after_insert')
def point_after_insert(mapper, connection, target):
    """Update cache after a new point is inserted"""
    StatsService.update_cache_after_event('point', target.id)

@event.listens_for(Point, 'after_update')
def point_after_update(mapper, connection, target):
    """Update cache after a point is updated"""
    StatsService.update_cache_after_event('point', target.id)

@event.listens_for(Point, 'after_delete')
def point_after_delete(mapper, connection, target):
    """Update cache after a point is deleted"""
    StatsService.update_cache_after_event('point', target.id)

# Game events
@event.listens_for(Game, 'after_insert')
def game_after_insert(mapper, connection, target):
    """Update cache after a new game is inserted"""
    StatsService.update_cache_after_event('game', target.id)

@event.listens_for(Game, 'after_update')
def game_after_update(mapper, connection, target):
    """Update cache after a game is updated"""
    StatsService.update_cache_after_event('game', target.id)

@event.listens_for(Game, 'after_delete')
def game_after_delete(mapper, connection, target):
    """Update cache after a game is deleted"""
    StatsService.update_cache_after_event('game', target.id)

# Player events
@event.listens_for(Player, 'after_update')
def player_after_update(mapper, connection, target):
    """Update cache after a player is updated"""
    StatsService.update_cache_after_event('player', target.id)

# Throw events
@event.listens_for(Throw, 'after_insert')
def throw_after_insert(mapper, connection, target):
    """Update cache after a new throw is inserted"""
    StatsService.update_cache_after_event('throw', target.id)

@event.listens_for(Throw, 'after_update')
def throw_after_update(mapper, connection, target):
    """Update cache after a throw is updated"""
    StatsService.update_cache_after_event('throw', target.id)

@event.listens_for(Throw, 'after_delete')
def throw_after_delete(mapper, connection, target):
    """Update cache after a throw is deleted"""
    StatsService.update_cache_after_event('throw', target.id)

# Event events
@event.listens_for(Event, 'after_insert')
def event_after_insert(mapper, connection, target):
    """Update cache after a new event is inserted"""
    # Get the point associated with this event
    if target.point_id:
        StatsService.update_cache_after_event('point', target.point_id)
    
    # Update player stats if applicable
    if target.player_id:
        StatsService.update_cache_after_event('player', target.player_id)
    if target.receiver_id:
        StatsService.update_cache_after_event('player', target.receiver_id)

@event.listens_for(Event, 'after_update')
def event_after_update(mapper, connection, target):
    """Update cache after an event is updated"""
    # Get the point associated with this event
    if target.point_id:
        StatsService.update_cache_after_event('point', target.point_id)
    
    # Update player stats if applicable
    if target.player_id:
        StatsService.update_cache_after_event('player', target.player_id)
    if target.receiver_id:
        StatsService.update_cache_after_event('player', target.receiver_id)

@event.listens_for(Event, 'after_delete')
def event_after_delete(mapper, connection, target):
    """Update cache after an event is deleted"""
    # Get the point associated with this event
    if target.point_id:
        StatsService.update_cache_after_event('point', target.point_id)
    
    # Update player stats if applicable
    if target.player_id:
        StatsService.update_cache_after_event('player', target.player_id)
    if target.receiver_id:
        StatsService.update_cache_after_event('player', target.receiver_id)

# PlayerPointStats events
@event.listens_for(PlayerPointStats, 'after_insert')
def player_point_stats_after_insert(mapper, connection, target):
    """Update cache after new player point stats are inserted"""
    StatsService.update_cache_after_event('player', target.player_id)

@event.listens_for(PlayerPointStats, 'after_update')
def player_point_stats_after_update(mapper, connection, target):
    """Update cache after player point stats are updated"""
    StatsService.update_cache_after_event('player', target.player_id)

@event.listens_for(PlayerPointStats, 'after_delete')
def player_point_stats_after_delete(mapper, connection, target):
    """Update cache after player point stats are deleted"""
    StatsService.update_cache_after_event('player', target.player_id)