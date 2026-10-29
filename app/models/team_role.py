"""Who plays which team role, season by season.

A role is a PlayerPosition (app/models/playbook.py). Coaches and captains
give players roles on the Roles page or their profile ('assigned', in depth
order: depth 1 is first choice for the role); players say which roles they'd
like ('preferred'). Rows hang off the season roster, so last season's roles
stay as they were when someone moves on to a new role.
"""
from datetime import datetime

from app import db


class PlayerRole(db.Model):
    __tablename__ = 'player_role'
    ASSIGNED, PREFERRED = 'assigned', 'preferred'

    id = db.Column(db.Integer, primary_key=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False, index=True)
    season_roster_id = db.Column(db.Integer, db.ForeignKey('season_roster.id', ondelete='CASCADE'),
                                 nullable=False, index=True)
    role_id = db.Column(db.Integer, db.ForeignKey('player_position.id', ondelete='CASCADE'), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False, default=ASSIGNED)
    depth = db.Column(db.Integer, nullable=False, default=1)      # 1 = first choice for the role
    is_main = db.Column(db.Boolean, nullable=False, default=False)  # the player's main role
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    roster = db.relationship('SeasonRoster', backref=db.backref('roles', cascade='all, delete-orphan',
                                                                 passive_deletes=True))
    role = db.relationship('PlayerPosition', backref=db.backref('player_roles', cascade='all, delete-orphan',
                                                                passive_deletes=True))

    __table_args__ = (
        db.UniqueConstraint('season_roster_id', 'role_id', 'kind', name='uq_player_role_roster_role_kind'),
    )

    def __repr__(self):
        return f'<PlayerRole roster={self.season_roster_id} role={self.role_id} {self.kind}>'
