from app import db
from datetime import datetime

class Tournament(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    season = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    games = db.relationship('Game', back_populates='tournament')
    
    def __repr__(self):
        return f'<Tournament {self.name}>'
    
    @property
    def game_count(self):
        """Return the number of games in this tournament."""
        return self.games.count()
    
    @property
    def win_count(self):
        """Return the number of games won in this tournament."""
        from app.models.game import Game  # Import here to avoid circular imports
        return self.games.filter(Game.our_score > Game.their_score).count()
    
    @property
    def loss_count(self):
        """Return the number of games lost in this tournament."""
        from app.models.game import Game  # Import here to avoid circular imports
        return self.games.filter(Game.our_score < Game.their_score).count()
