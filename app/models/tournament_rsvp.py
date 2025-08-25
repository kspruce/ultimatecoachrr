from app_factory import db
from datetime import datetime

class TournamentRSVP(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'attending', 'maybe', 'not_attending'
    notes = db.Column(db.Text, nullable=True)
    selected_by_admin = db.Column(db.Boolean, default=False)  # Indicates if admin selected this player for the tournament
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))
   
    # Relationships
    player = db.relationship('Player', back_populates='tournament_rsvps')
    tournament = db.relationship('Tournament', back_populates='rsvps')

    def __repr__(self):
        return f'<TournamentRSVP {self.player_id} for {self.tournament_id}: {self.status}>'