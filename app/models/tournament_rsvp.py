from app import db
from datetime import datetime


class TournamentRSVP(db.Model):
    """A player's availability for a tournament and the coach's pick.

    `status` is the player's own answer (attending / maybe / not_attending),
    or NULL if the coach picked them before they replied. `selection` is the
    coach's call: picked / reserve / not_picked, or NULL while undecided.
    """
    STATUSES = [('attending', 'Attending'), ('maybe', 'Maybe'), ('not_attending', "Can't make it")]
    SELECTIONS = [('picked', 'Picked'), ('reserve', 'Reserve'), ('not_picked', 'Not picked')]

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournament.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    status = db.Column(db.String(20), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    selection = db.Column(db.String(20), nullable=True)
    # Kept in step with selection == 'picked' for older code and backups
    selected_by_admin = db.Column(db.Boolean, default=False)
    # When the player last answered (NULL if they never have)
    responded_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'))

    # Relationships
    player = db.relationship('Player', back_populates='tournament_rsvps')
    tournament = db.relationship('Tournament', back_populates='rsvps')

    @property
    def status_label(self):
        return dict(self.STATUSES).get(self.status, 'No reply')

    @property
    def is_late(self):
        """Answered after the tournament's reply-by date."""
        deadline = self.tournament.rsvp_deadline if self.tournament else None
        return bool(deadline and self.responded_at and self.responded_at.date() > deadline)

    def __repr__(self):
        return f'<TournamentRSVP {self.player_id} for {self.tournament_id}: {self.status}>'
