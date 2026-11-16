from datetime import datetime

from app import db


class PlayerLinkRequest(db.Model):
    """A player asking for their account to be linked to a player profile on
    the team. A coach approves it (the link is made) or declines it; either
    way the row goes. One open request per account per team.

    Linking used to happen straight away, which let anyone on the team take
    over an unlinked profile and read its feedback, goals and fitness."""

    __tablename__ = 'player_link_request'
    __table_args__ = (db.UniqueConstraint('team_organization_id', 'user_id', name='uq_link_request_team_user'),)

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User')
    player = db.relationship('Player')
