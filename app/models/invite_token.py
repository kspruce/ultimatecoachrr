import secrets
from datetime import datetime, timedelta
from app import db


class InviteToken(db.Model):
    """A single-use token that lets a player claim their own account.

    Created by a coach/admin; the player follows the link, picks a
    username + password, and their User record is automatically linked
    to the correct Player row.
    """

    __tablename__ = 'invite_token'

    id                  = db.Column(db.Integer, primary_key=True)
    token               = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Which player this invite is for (nullable → general team invite)
    player_id           = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    team_organization_id = db.Column(db.Integer, db.ForeignKey('team_organization.id'), nullable=False)

    created_by_id       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at          = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at          = db.Column(db.DateTime, nullable=False)

    # Populated when the invite is accepted
    used_at             = db.Column(db.DateTime, nullable=True)
    used_by_user_id     = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # Relationships
    player      = db.relationship('Player',           foreign_keys=[player_id])
    team        = db.relationship('TeamOrganization', foreign_keys=[team_organization_id])
    created_by  = db.relationship('User',             foreign_keys=[created_by_id])
    used_by     = db.relationship('User',             foreign_keys=[used_by_user_id])

    # ── Convenience properties ────────────────────────────────

    @property
    def is_expired(self):
        return datetime.utcnow() > self.expires_at

    @property
    def is_used(self):
        return self.used_at is not None

    @property
    def is_valid(self):
        return not self.is_expired and not self.is_used

    # ── Factory ───────────────────────────────────────────────

    @classmethod
    def create(cls, player_id, team_id, created_by_id, expires_days=7):
        """Generate a new token and return the (unsaved) InviteToken instance."""
        return cls(
            token=secrets.token_urlsafe(32),
            player_id=player_id,
            team_organization_id=team_id,
            created_by_id=created_by_id,
            expires_at=datetime.utcnow() + timedelta(days=expires_days),
        )

    def __repr__(self):
        return f'<InviteToken player_id={self.player_id} used={self.is_used}>'
