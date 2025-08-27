from app import db
from datetime import datetime


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=True)
    opponent = db.Column(db.String(100), nullable=False)
    our_score = db.Column(db.Integer, default=0)
    their_score = db.Column(db.Integer, default=0)
    date = db.Column(db.Date, nullable=True)
    youtube_link = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Add team organization relationship
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
    
    # Existing relationships
    tournament = db.relationship('Tournament', back_populates='games')
    points = db.relationship('Point', back_populates='game', 
                           cascade='all, delete-orphan', lazy='dynamic')
    clips = db.relationship('Clip', back_populates='game', 
                          cascade='all, delete-orphan', lazy='dynamic')
    assigned_players = db.relationship('GamePlayer', back_populates='game', cascade='all, delete-orphan', lazy='dynamic')
    gameday_stats = db.relationship('GameDayPlayerStats', back_populates='game', cascade='all, delete-orphan')
    # In the Game model class
    player_stats = db.relationship('PlayerStats', back_populates='game', cascade='all, delete-orphan')
    team_stats = db.relationship('TeamStats', back_populates='game', cascade='all, delete-orphan', uselist=False) # One-to-one

    __table_args__ = (
        db.Index('idx_game_tournament', 'tournament_id'),
        db.Index('idx_game_date', 'date'),
    )    
    
    def __repr__(self):
        return f'<Game vs {self.opponent}>'
    
    @property
    def is_win(self):
        """Return True if we won this game."""
        return self.our_score > self.their_score
    
    @property
    def is_loss(self):
        """Return True if we lost this game."""
        return self.our_score < self.their_score
    
    @property
    def is_tie(self):
        """Return True if the game was a tie."""
        return self.our_score == self.their_score
    
    @property
    def result_string(self):
        """Return a string representation of the game result."""
        if self.is_win:
            return f'W {self.our_score}-{self.their_score}'
        elif self.is_loss:
            return f'L {self.our_score}-{self.their_score}'
        else:
            return f'T {self.our_score}-{self.their_score}'
    
    @property
    def point_count(self):
        """Return the number of points in this game."""
        return self.points.count()
    
    @property
    def o_line_points(self):
        """Return points where we started on offense."""
        return self.points.filter_by(our_line_type='O-line').all()
    
    @property
    def d_line_points(self):
        """Return points where we started on defense."""
        return self.points.filter_by(our_line_type='D-line').all()
    
    @property
    def o_line_conversion_rate(self):
        """Return the percentage of offensive points we scored."""
        o_points = self.points.filter_by(our_line_type='O-line').all()
        if not o_points:
            return 0
        
        scored = sum(1 for p in o_points if p.point_outcome == 'scored')
        return (scored / len(o_points)) * 100
    
    @property
    def d_line_conversion_rate(self):
        """Return the percentage of defensive points we scored."""
        d_points = self.points.filter_by(our_line_type='D-line').all()
        if not d_points:
            return 0
        
        scored = sum(1 for p in d_points if p.point_outcome == 'scored')
        return (scored / len(d_points)) * 100
    
    @property
    def player_count(self):
        """Return the number of players assigned to this game."""
        return self.assigned_players.count()