from app import db
from datetime import datetime
from sqlalchemy import Column, Integer, ForeignKey, Float, JSON, String, Boolean, DateTime
from sqlalchemy.orm import relationship

class IndexStats(db.Model):
    """Model to store overall stats shown on the index page."""
    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    
    # Stats data stored as JSON
    stats_data = db.Column(db.JSON, nullable=False)
    
    # Filter parameters used when generating these stats
    filter_params = db.Column(db.JSON, nullable=True)
    
    # Version number for tracking changes
    version = db.Column(db.Integer, default=1)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Optimization fields
    compressed = db.Column(db.Boolean, default=False)
    compression_ratio = db.Column(db.Float, nullable=True)
    
    # Relationships
    team_organization = db.relationship('TeamOrganization', backref='index_stats')
    
    def __repr__(self):
        return f'<IndexStats {self.id} for {self.team_organization_id} (v{self.version})>'


class TeamStats(db.Model):
    """Model to store team stats."""
    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    
    # Stats data stored as JSON
    stats_data = db.Column(db.JSON, nullable=False)
    
    # Filter parameters used when generating these stats
    filter_params = db.Column(db.JSON, nullable=True)
    
    # Version number for tracking changes
    version = db.Column(db.Integer, default=1)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Optimization fields
    compressed = db.Column(db.Boolean, default=False)
    compression_ratio = db.Column(db.Float, nullable=True)
    
    # Relationships
    team_organization = db.relationship('TeamOrganization', backref='team_stats')
    
    def __repr__(self):
        return f'<TeamStats {self.id} for {self.team_organization_id} (v{self.version})>'


class GameStats(db.Model):
    """Model to store game stats."""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    
    # Stats data stored as JSON
    stats_data = db.Column(db.JSON, nullable=False)
    
    # Filter parameters used when generating these stats
    filter_params = db.Column(db.JSON, nullable=True)
    
    # Version number for tracking changes
    version = db.Column(db.Integer, default=1)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Optimization fields
    compressed = db.Column(db.Boolean, default=False)
    compression_ratio = db.Column(db.Float, nullable=True)
    
    # Relationships
    game = db.relationship('Game', backref='saved_stats')
    team_organization = db.relationship('TeamOrganization', backref='game_stats')
    
    def __repr__(self):
        return f'<GameStats {self.id} for game {self.game_id} (v{self.version})>'


class PlayerStats(db.Model):
    """Model to store player stats."""
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)  # Optional, for game-specific player stats
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)
    
    # Stats data stored as JSON
    stats_data = db.Column(db.JSON, nullable=False)
    
    # Filter parameters used when generating these stats
    filter_params = db.Column(db.JSON, nullable=True)
    
    # Version number for tracking changes
    version = db.Column(db.Integer, default=1)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Optimization fields
    compressed = db.Column(db.Boolean, default=False)
    compression_ratio = db.Column(db.Float, nullable=True)
    
    # Relationships
    player = db.relationship('Player', backref='saved_stats')
    game = db.relationship('Game', backref='player_stats', foreign_keys=[game_id])
    team_organization = db.relationship('TeamOrganization', backref='player_stats')
    
    def __repr__(self):
        game_info = f' in game {self.game_id}' if self.game_id else ''
        return f'<PlayerStats {self.id} for player {self.player_id}{game_info} (v{self.version})>'