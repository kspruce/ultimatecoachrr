# app/models/user.py
from app import db, login
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Role hierarchy (team-scoped)
ROLE_ORDER = {
    "player": 1,
    "stat_taker": 2,
    "captain": 3,
    "coach": 4,
    "admin": 5,
}

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255))

    # Team-scoped role (since user belongs to exactly one team)
    role = db.Column(db.String(20), default="player", nullable=False)

    # IMPORTANT:
    # Your DB already has a column called "is_admin". You previously also had a @property called is_admin,
    # which broke the column. We keep the DB column but map it to a different attribute name.
    # We'll stop using it and use is_superadmin instead.
    #is_admin_flag = db.Column("is_admin", db.Boolean, default=False, nullable=False)

    # Global superadmin (you = username 'admin')
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    discord_id = db.Column(db.String(64), nullable=True, unique=True)

    # Single-team membership
    team_organization_id = db.Column(db.Integer, db.ForeignKey("team_organization.id"))

    # Relationships
    player_profile = db.relationship("Player", back_populates="user_account", uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def player(self):
        return self.player_profile

    @property
    def is_admin(self):
        """
        Backwards compatibility property.
        True if user is global superadmin or team admin.
        """
        return self.is_superadmin or self.role == "admin"

    @property
    def is_coach(self):
        return self.role == "coach"

    # Convenience helpers (do NOT reintroduce an is_admin property)
    def role_level(self) -> int:
        return ROLE_ORDER.get(self.role or "player", 1)

    def __repr__(self):
        return f"<User {self.username}>"

@login.user_loader
def load_user(id):
    return User.query.get(int(id))
