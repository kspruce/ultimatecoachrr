# app/models/user.py
from app import db, login
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import hashlib

# Role hierarchy (team-scoped). Captains and team admins share the top level:
# both run everything on their own team. Only superadmins (is_superadmin)
# reach other teams.
ROLE_ORDER = {
    "guest": 0,
    "player": 1,
    "stat_taker": 2,
    "coach": 3,
    "captain": 4,
    "admin": 4,
}

# Roles with full control of their own team
TEAM_ADMIN_ROLES = ("admin", "captain")

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255))

    # Team-scoped role (since user belongs to exactly one team)
    role = db.Column(db.String(20), default="player", nullable=False)

    # IMPORTANT:
    # Your DB already has a column called "is_admin". You previously also had a @property called is_admin,
    # which broke the column. We keep the DB column but map it to a different attribute name.
    # We'll stop using it and use is_superadmin instead.
    is_admin_flag = db.Column("is_admin", db.Boolean, default=False, nullable=False)

    # Global superadmin (you = username 'admin')
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    discord_id = db.Column(db.String(64), nullable=True, unique=True)

    # Single-team membership
    team_organization_id = db.Column(db.Integer, db.ForeignKey("team_organization.id"))

    # Relationships
    player_profile = db.relationship("Player", back_populates="user_account", uselist=False)
    # team_organization backref is defined on TeamOrganization.users — available as user.team_organization

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def password_fingerprint(self):
        """Changes whenever the password does (and never reveals it)."""
        return hashlib.sha256((self.password_hash or 'no-password').encode()).hexdigest()[:16]

    def get_id(self):
        # Logins and remember-me cookies carry the password fingerprint, so
        # changing or resetting a password signs out every other device
        return f"{self.id}:{self.password_fingerprint()}"

    @property
    def player(self):
        return self.player_profile

    @property
    def is_guest(self):
        """True if this is a read-only guest/demo account."""
        return self.role == "guest"

    @property
    def is_admin(self):
        """
        Backwards compatibility property.
        True if user is global superadmin or runs their team (team admin or
        captain).
        """
        return self.is_superadmin or self.role in TEAM_ADMIN_ROLES

    @property
    def is_captain(self):
        return self.role == "captain"

    @property
    def is_coach(self):
        return self.role == "coach" or self.is_admin

    @property
    def is_stat_taker(self):
        """True for stat_taker, coach, captain, and admin — anyone at or
        above the stat_taker level in the role hierarchy."""
        return self.role_level() >= ROLE_ORDER["stat_taker"]

    # Convenience helpers (do NOT reintroduce an is_admin property)
    def role_level(self) -> int:
        return ROLE_ORDER.get(self.role or "player", 1)

    def __repr__(self):
        return f"<User {self.username}>"

@login.user_loader
def load_user(id):
    user_id, _, fingerprint = str(id).partition(':')
    if not user_id.isdigit():
        return None
    user = db.session.get(User, int(user_id))
    if user is None or fingerprint != user.password_fingerprint():
        return None
    return user
