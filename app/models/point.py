from app.models.base import db
from datetime import datetime

class Point(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    point_number = db.Column(db.Integer, nullable=False)
    our_line_type = db.Column(db.String(20), nullable=False)
    our_score_before = db.Column(db.Integer, default=0)
    their_score_before = db.Column(db.Integer, default=0)
    our_score_after = db.Column(db.Integer, default=0)
    their_score_after = db.Column(db.Integer, default=0)
    starting_position = db.Column(db.String(20), nullable=False)
    point_outcome = db.Column(db.String(20), nullable=False)
    duration = db.Column(db.Integer, nullable=True)
    timestamp_in_video = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    gender_ratio = db.Column(db.String(4))
    force_direction = db.Column(db.String(10))
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    
    # Relationships
    game = db.relationship('Game', back_populates='points')
    lineups = db.relationship('LineUp', back_populates='point', cascade='all, delete-orphan')
    events = db.relationship('Event', back_populates='point', cascade='all, delete-orphan')
    pulls = db.relationship('Pull', back_populates='point', cascade='all, delete-orphan')
    clips = db.relationship('Clip', back_populates='point')
    point_stats = db.relationship('PlayerPointStats', back_populates='point')
    throws = db.relationship('Throw', back_populates='point')  # Add this line
    cutting_skills = db.relationship('CuttingSkill', back_populates='point', cascade='all, delete-orphan')
    # Add this relationship
    gameday_events = db.relationship('GameDayEvent', back_populates='point', cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('idx_point_game', 'game_id'),
        db.Index('idx_point_line_type', 'our_line_type'),
        db.Index('idx_point_outcome', 'point_outcome'),
    )

    def __repr__(self):
        return f'<Point {self.point_number} in Game {self.game_id}>'

    @property
    def players(self):
        """Return all players who participated in this point."""
        return [lineup.player for lineup in self.lineups]

    @property
    def player_ids(self):
        """Return all player IDs who participated in this point."""
        return [lineup.player_id for lineup in self.lineups]

    @property
    def we_scored(self):
        """Return True if we scored this point."""
        return self.point_outcome == 'scored'

    @property
    def they_scored(self):
        """Return True if the opponent scored this point."""
        return self.point_outcome == 'conceded'

    @property
    def is_break(self):
        """Return True if this was a break point."""
        return (self.our_line_type == 'D-line' and self.we_scored) or \
               (self.our_line_type == 'O-line' and self.they_scored)

    @property
    def is_hold(self):
        """Return True if this was a hold point."""
        return (self.our_line_type == 'O-line' and self.we_scored) or \
               (self.our_line_type == 'D-line' and self.they_scored)


class LineUp(db.Model):
    __tablename__ = 'line_up'
    
    id = db.Column(db.Integer, primary_key=True)
    point_id = db.Column(db.Integer, db.ForeignKey('point.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)
    
    # Relationships
    point = db.relationship('Point', back_populates='lineups')
    player = db.relationship('Player', back_populates='lineups')

    __table_args__ = (
        db.Index('idx_lineup_player_point', 'player_id', 'point_id'),
    )

    def __repr__(self):
        return f'<LineUp: Player {self.player_id} in Point {self.point_id}>'