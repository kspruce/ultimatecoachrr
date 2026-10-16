# app/models/team_signup_invite.py
import secrets
from datetime import datetime, timedelta

from app import db


class TeamSignupInvite(db.Model):
    """A single-use link a superadmin sends to let a new club register a team
    while team sign-up is closed to the public."""

    __tablename__ = 'team_signup_invite'

    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Who it's for, so the superadmin can tell links apart
    note = db.Column(db.String(200))
    email = db.Column(db.String(120))

    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)

    # Filled in when a team signs up with the link
    used_at = db.Column(db.DateTime, nullable=True)
    used_by_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=True)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    used_by = db.relationship('User', foreign_keys=[used_by_user_id])
    team = db.relationship('TeamOrganization', foreign_keys=[team_organization_id])

    @property
    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    @property
    def is_used(self):
        return self.used_at is not None

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_valid(self):
        return not (self.is_expired or self.is_used or self.is_revoked)

    @property
    def status(self):
        if self.is_used:
            return 'used'
        if self.is_revoked:
            return 'revoked'
        if self.is_expired:
            return 'expired'
        return 'active'

    @classmethod
    def create(cls, created_by_id, note=None, email=None, expires_days=14):
        return cls(
            token=secrets.token_urlsafe(32),
            note=note or None,
            email=email or None,
            created_by_id=created_by_id,
            expires_at=datetime.utcnow() + timedelta(days=expires_days),
        )

    @classmethod
    def find_valid(cls, token):
        if not token:
            return None
        invite = cls.query.filter_by(token=token).first()
        return invite if invite and invite.is_valid else None

    def __repr__(self):
        return f'<TeamSignupInvite {self.id} {self.status}>'
