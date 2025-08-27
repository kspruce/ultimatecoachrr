from app import db
from datetime import datetime


class PlayerPointStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    o_line_plus_minus = db.Column(db.Float, default=0.0)
    d_line_plus_minus = db.Column(db.Float, default=0.0)
    calculated_per = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
 
    # Use back_populates for bidirectional relationships
    player = db.relationship('Player', back_populates='point_stats')
    point = db.relationship('Point', back_populates='point_stats')

    def __repr__(self):
        return f'<PlayerPointStats {self.player_id}-{self.point_id}>'

class PlayerStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=True)
    season = db.Column(db.String(50), nullable=True)
    
    # Core Stats
    points_played = db.Column(db.Integer, default=0)
    o_line_points_played = db.Column(db.Integer, default=0)
    d_line_points_played = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    hockey_assists = db.Column(db.Integer, default=0)
    blocks = db.Column(db.Integer, default=0)
    throws = db.Column(db.Integer, default=0)
    completions = db.Column(db.Integer, default=0)
    throwaways = db.Column(db.Integer, default=0)
    drops = db.Column(db.Integer, default=0)
    stalls = db.Column(db.Integer, default=0)
    
    # Calculated Stats
    completion_rate = db.Column(db.Float, default=0.0)
    catch_rate = db.Column(db.Float, default=0.0)
    plus_minus = db.Column(db.Float, default=0.0)
    per = db.Column(db.Float, default=0.0)
    
    # Metadata
    last_calculated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_dirty = db.Column(db.Boolean, default=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    
    # Relationships
    player = db.relationship('Player', back_populates='stats')
    game = db.relationship('Game', back_populates='player_stats')
    tournament = db.relationship('Tournament', back_populates='player_stats')
    
    __table_args__ = (
        db.UniqueConstraint('player_id', 'game_id', 'tournament_id', 'season', name='_player_stats_scope_uc'),
    )

class TeamStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=True)
    season = db.Column(db.String(50), nullable=True)
    
    # Core Stats
    games_played = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    losses = db.Column(db.Integer, default=0)
    ties = db.Column(db.Integer, default=0)
    total_points = db.Column(db.Integer, default=0)
    o_line_points = db.Column(db.Integer, default=0)
    o_line_conversions = db.Column(db.Integer, default=0)
    d_line_points = db.Column(db.Integer, default=0)
    d_line_conversions = db.Column(db.Integer, default=0)
    
    # Calculated Rates
    win_percentage = db.Column(db.Float, default=0.0)
    o_line_conversion_rate = db.Column(db.Float, default=0.0)
    d_line_conversion_rate = db.Column(db.Float, default=0.0)
    
    # Metadata
    last_calculated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_dirty = db.Column(db.Boolean, default=False, index=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    
    # Relationships
    game = db.relationship('Game', back_populates='team_stats')
    tournament = db.relationship('Tournament', back_populates='team_stats')

    __table_args__ = (
        db.UniqueConstraint('game_id', 'tournament_id', 'season', name='_team_stats_scope_uc'),
    )
