from app_factory import db
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, Float, String, JSON

class StatsCache(db.Model):
    """
    Model for caching calculated statistics to improve performance and ensure consistency.
    This model stores pre-calculated statistics that can be reused across different pages.
    """
    id = db.Column(db.Integer, primary_key=True)
    
    # Cache type (player, team, game)
    cache_type = db.Column(db.String(20), nullable=False)
    
    # Reference IDs
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    
    # Cache data stored as JSON
    stats_data = db.Column(db.JSON, nullable=False, default={})
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    player = db.relationship('Player', backref=db.backref('stats_cache', lazy='dynamic'))
    team_organization = db.relationship('TeamOrganization', backref=db.backref('stats_cache', lazy='dynamic'))
    game = db.relationship('Game', backref=db.backref('stats_cache', lazy='dynamic'))
    
    # Indexes for faster lookups
    __table_args__ = (
        db.Index('idx_stats_cache_player', 'player_id'),
        db.Index('idx_stats_cache_team', 'team_organization_id'),
        db.Index('idx_stats_cache_game', 'game_id'),
        db.Index('idx_stats_cache_type', 'cache_type'),
    )
    
    def __repr__(self):
        return f'<StatsCache {self.cache_type} for {"player" if self.player_id else "team" if self.team_organization_id else "game"}>'

class PlayerStatsCache(db.Model):
    """
    Specialized cache for player statistics.
    This model stores detailed player statistics for quick access.
    """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    
    # Basic stats
    points_played = db.Column(db.Integer, default=0)
    o_line_points_played = db.Column(db.Integer, default=0)
    d_line_points_played = db.Column(db.Integer, default=0)
    
    # Efficiency stats
    o_line_efficiency = db.Column(db.Float, default=0.0)
    d_line_efficiency = db.Column(db.Float, default=0.0)
    
    # PER and plus/minus
    per = db.Column(db.Float, default=0.0)
    o_line_plus_minus = db.Column(db.Float, default=0.0)
    d_line_plus_minus = db.Column(db.Float, default=0.0)
    
    # Throw stats
    completions = db.Column(db.Integer, default=0)
    throw_attempts = db.Column(db.Integer, default=0)
    completion_percentage = db.Column(db.Float, default=0.0)
    
    # Scoring stats
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    blocks = db.Column(db.Integer, default=0)
    
    # Time range
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Team organization
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    
    # Relationships
    player = db.relationship('Player', backref=db.backref('player_stats_cache', lazy='dynamic'))
    team_organization = db.relationship('TeamOrganization', backref=db.backref('player_stats_cache', lazy='dynamic'))
    
    # Indexes
    __table_args__ = (
        db.Index('idx_player_stats_cache_player', 'player_id'),
        db.Index('idx_player_stats_cache_team', 'team_organization_id'),
        db.Index('idx_player_stats_cache_date_range', 'start_date', 'end_date'),
    )
    
    def __repr__(self):
        return f'<PlayerStatsCache for {self.player_id}>'

class TeamStatsCache(db.Model):
    """
    Specialized cache for team statistics.
    This model stores detailed team statistics for quick access.
    """
    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    
    # Offensive stats
    o_line_conversion_rate = db.Column(db.Float, default=0.0)
    o_line_efficiency = db.Column(db.Float, default=0.0)
    
    # Defensive stats
    d_line_conversion_rate = db.Column(db.Float, default=0.0)
    d_line_efficiency = db.Column(db.Float, default=0.0)
    defensive_efficiency = db.Column(db.Float, default=0.0)
    
    # Break stats
    break_percentage = db.Column(db.Float, default=0.0)
    
    # Other team stats
    blocks_per_point = db.Column(db.Float, default=0.0)
    turnovers_forced_per_point = db.Column(db.Float, default=0.0)
    
    # Time range
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    team_organization = db.relationship('TeamOrganization', backref=db.backref('team_stats_cache', lazy='dynamic'))
    
    # Indexes
    __table_args__ = (
        db.Index('idx_team_stats_cache_team', 'team_organization_id'),
        db.Index('idx_team_stats_cache_date_range', 'start_date', 'end_date'),
    )
    
    def __repr__(self):
        return f'<TeamStatsCache for team {self.team_organization_id}>'

class GameStatsCache(db.Model):
    """
    Specialized cache for game statistics.
    This model stores detailed game statistics for quick access.
    """
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    
    # Game stats
    o_line_conversion_rate = db.Column(db.Float, default=0.0)
    d_line_conversion_rate = db.Column(db.Float, default=0.0)
    o_line_efficiency = db.Column(db.Float, default=0.0)
    d_line_efficiency = db.Column(db.Float, default=0.0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Team organization
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    
    # Relationships
    game = db.relationship('Game', backref=db.backref('game_stats_cache', uselist=False))
    team_organization = db.relationship('TeamOrganization', backref=db.backref('game_stats_cache', lazy='dynamic'))
    
    # Indexes
    __table_args__ = (
        db.Index('idx_game_stats_cache_game', 'game_id'),
        db.Index('idx_game_stats_cache_team', 'team_organization_id'),
    )
    
    def __repr__(self):
        return f'<GameStatsCache for game {self.game_id}>'