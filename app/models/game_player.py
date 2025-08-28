from app.models.base import db
from datetime import datetime

class GamePlayer(db.Model):
    """Association table for players assigned to games."""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True) # Nullable for migration
   
    # Relationships
    game = db.relationship('Game', back_populates='assigned_players')

    player = db.relationship('Player', backref=db.backref('game_assignments', lazy='dynamic'))
    
    def __repr__(self):
        return f'<GamePlayer {self.player_id} for game {self.game_id}>'