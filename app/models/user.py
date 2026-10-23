# app/models/user.py
from app import db, login
from flask import has_request_context
from flask_login import UserMixin
from sqlalchemy import event
from sqlalchemy.orm import Session
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

    # Role on the home team. A login can belong to several teams, each with
    # its own role (TeamMembership); use `role`, which answers for the team
    # being viewed, rather than this column.
    home_role = db.Column("role", db.String(20), default="player", nullable=False)

    # IMPORTANT:
    # Your DB already has a column called "is_admin". You previously also had a @property called is_admin,
    # which broke the column. We keep the DB column but map it to a different attribute name.
    # We'll stop using it and use is_superadmin instead.
    is_admin_flag = db.Column("is_admin", db.Boolean, default=False, nullable=False)

    # Global superadmin (you = username 'admin')
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Set by "Connect Discord" (signing in with Discord), never typed in
    discord_id = db.Column(db.String(64), nullable=True, unique=True)
    discord_username = db.Column(db.String(100), nullable=True)

    # Two-step sign-in (app/utils/two_factor.py): the authenticator app's
    # secret, hashed one-time recovery codes (JSON list), and the last code
    # used (so a code can't be used twice)
    totp_secret = db.Column(db.String(64), nullable=True)
    totp_recovery_codes = db.Column(db.Text, nullable=True)
    totp_last_step = db.Column(db.Integer, nullable=True)

    # Secret for their personal calendar feed (/calendar/feed/<token>.ics)
    calendar_token = db.Column(db.String(64), nullable=True, unique=True)
    # Emails about tournaments: reply reminders, selection, game schedules
    email_event_updates = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())

    # Home team: where they land after logging in. Every team they belong
    # to, this one included, has a TeamMembership row.
    team_organization_id = db.Column(db.Integer, db.ForeignKey("team_organization.id"))

    # Relationships
    memberships = db.relationship("TeamMembership", back_populates="user",
                                  cascade="all, delete-orphan")
    # One player profile per team they're on
    player_profiles = db.relationship("Player", back_populates="user_account")
    # team_organization backref is defined on TeamOrganization.users — available as user.team_organization (the home team)

    # ── Teams ────────────────────────────────────────────────

    def _context_team_id(self):
        """The team `role` and `player` answer for: the team being viewed in
        this request (so a coach's users page shows each person's role on
        that team), else the home team."""
        if has_request_context():
            from flask_login import current_user
            from app.utils.team_filter import get_current_team_id
            if current_user and current_user.is_authenticated:
                team_id = get_current_team_id()
                if team_id:
                    return team_id
        return self.team_organization_id

    def membership_for(self, team_id):
        return next((m for m in self.memberships if m.team_organization_id == team_id), None)

    @property
    def team_ids(self):
        return [m.team_organization_id for m in self.memberships]

    def is_member_of(self, team_id):
        return self.membership_for(team_id) is not None

    def role_in(self, team_id):
        """Role on one team. Not on it: guest (superadmins: their home role)."""
        membership = self.membership_for(team_id)
        if membership:
            return membership.role
        if self.is_superadmin or not self.memberships or team_id in (None, self.team_organization_id):
            return self.home_role
        return "guest"

    def set_role_in(self, team_id, role):
        """Give them `role` on a team, adding them to it if they aren't on it."""
        membership = self.membership_for(team_id)
        if team_id is None or team_id == self.team_organization_id:
            self.home_role = role
        if membership:
            membership.role = role
        elif team_id is not None and team_id != self.team_organization_id:
            self.memberships.append(TeamMembership(team_organization_id=team_id, role=role))

    def join_team(self, team_id, role="player"):
        """Add them to a team (keeping their role if they're already on it)."""
        membership = self.membership_for(team_id)
        if membership is None:
            if not self.team_organization_id:
                self.team_organization_id = team_id
                self.home_role = role
            self.set_role_in(team_id, role)
            membership = self.membership_for(team_id)
        return membership

    def leave_team(self, team_id):
        """Take them off a team (their player profile there is unlinked).
        Their home moves to another team they're on."""
        with db.session.no_autoflush:  # half-done, it would look like a lost home membership
            membership = self.membership_for(team_id)
            if self.team_organization_id == team_id:
                other = next((m for m in self.memberships if m.team_organization_id != team_id), None)
                self.team_organization_id = other.team_organization_id if other else None
                if other:
                    self.home_role = other.role
            if membership:
                self.memberships.remove(membership)
            for player in list(self.player_profiles):
                if player.team_organization_id == team_id:
                    self.player_profiles.remove(player)

    @property
    def role(self):
        return self.role_in(self._context_team_id())

    @role.setter
    def role(self, value):
        self.set_role_in(self._context_team_id() if self.memberships else self.team_organization_id, value)

    def player_for(self, team_id):
        """Their player profile on one team."""
        return next((p for p in self.player_profiles if p.team_organization_id == team_id), None)

    @property
    def player_profile(self):
        team_id = self._context_team_id()
        if team_id is None:
            return self.player_profiles[0] if self.player_profiles else None
        return self.player_for(team_id)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def password_fingerprint(self):
        """Changes whenever the password does (and never reveals it)."""
        return hashlib.sha256((self.password_hash or 'no-password').encode()).hexdigest()[:16]

    def session_fingerprint(self):
        """Changes with the password or the authenticator app."""
        secret = (self.password_hash or 'no-password') + (self.totp_secret or '')
        return hashlib.sha256(secret.encode()).hexdigest()[:16]

    @property
    def two_factor_enabled(self):
        return bool(self.totp_secret)

    def get_id(self):
        # Logins and remember-me cookies carry this fingerprint, so changing
        # or resetting a password, or setting up two-step sign-in again,
        # signs out every other device
        return f"{self.id}:{self.session_fingerprint()}"

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

@event.listens_for(Session, "before_flush")
def _add_home_membership(session, flush_context, instances):
    """Every login is a member of its home team, however it was made."""
    if session.info.get('restoring_backup'):
        return
    for obj in list(session.new) + list(session.dirty):
        if isinstance(obj, User) and obj.team_organization_id and not obj.is_member_of(obj.team_organization_id):
            obj.memberships.append(TeamMembership(team_organization_id=obj.team_organization_id,
                                                  role=obj.home_role or "player"))


@login.user_loader
def load_user(id):
    user_id, _, fingerprint = str(id).partition(':')
    if not user_id.isdigit():
        return None
    user = db.session.get(User, int(user_id))
    if user is None or fingerprint != user.session_fingerprint():
        return None
    return user


from app.models.team_membership import TeamMembership  # noqa: E402,F401  (register the model)
