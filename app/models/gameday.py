from app import db
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship

class LineTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    line_type = db.Column(db.String(20), nullable=False)  # O-line or D-line
    gender_ratio = db.Column(db.String(4), nullable=False)  # e.g., "4-3"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    # Relationships
    players = db.relationship('LineTemplatePlayer', back_populates='template', 
                             cascade='all, delete-orphan')

class LineTemplatePlayer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('line_template.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    # Relationships
    template = db.relationship('LineTemplate', back_populates='players')
    player = db.relationship('Player')

class GameDayEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # Nullable for possession changes
    event_type = db.Column(db.String(20), nullable=False)  # catch, drop, score, throwaway, stall, block, pickup, callahan, assist, pull
    event_result = db.Column(db.String(20), nullable=True)  # For pulls: in/out
    hang_time = db.Column(db.Float, nullable=True)  # Pull hang time in seconds
    sequence = db.Column(db.Integer, nullable=False)  # Order of events within a point
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    # Relationships
    point = db.relationship('Point', back_populates='gameday_events')
    player = db.relationship('Player', back_populates='gameday_events')
    
    def __repr__(self):
        return f'<GameDayEvent {self.event_type} by Player {self.player_id} in Point {self.point_id}>'

class GameDayPlayerStats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    points_played = db.Column(db.Integer, default=0)
    o_points = db.Column(db.Integer, default=0)
    d_points = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    blocks = db.Column(db.Integer, default=0)
    turns = db.Column(db.Integer, default=0)  # Combined throwaways, drops, stalls
    pulls = db.Column(db.Integer, default=0)
    pulls_ob = db.Column(db.Integer, default=0)
    total_hang_time = db.Column(db.Float, default=0.0)  # Total pull hang time in seconds
    callahans = db.Column(db.Integer, default=0)
    plus_minus = db.Column(db.Integer, default=0)
    team_organization_id = db.Column(Integer, ForeignKey('team_organization.id'))
    
    # Relationships
    player = db.relationship('Player', back_populates='gameday_stats')
    game = db.relationship('Game', back_populates='gameday_stats')
    
    def __repr__(self):
        return f'<GameDayPlayerStats for Player {self.player_id} in Game {self.game_id}>'
