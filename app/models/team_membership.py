# app/models/team_membership.py
from datetime import datetime

from app import db


class TeamMembership(db.Model):
    """One person's place on one team: a login can belong to several teams
    (someone who plays for two clubs keeps one account and one email), with
    its own role on each."""
    __tablename__ = "team_membership"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    team_organization_id = db.Column(db.Integer, db.ForeignKey("team_organization.id"), nullable=False)
    role = db.Column(db.String(20), default="player", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="memberships")
    team_organization = db.relationship("TeamOrganization")

    __table_args__ = (
        db.UniqueConstraint("user_id", "team_organization_id", name="uq_team_membership_user_team"),
        db.Index("idx_team_membership_team", "team_organization_id"),
    )

    def __repr__(self):
        return f"<TeamMembership user={self.user_id} team={self.team_organization_id} {self.role}>"


def add_missing_home_memberships():
    """Give every user with a home team a membership of it, where it's
    missing (e.g. after restoring a backup from before memberships)."""
    from app.models.user import User
    missing = User.query.filter(
        User.team_organization_id.isnot(None),
        ~User.memberships.any(TeamMembership.team_organization_id == User.team_organization_id)).all()
    for user in missing:
        db.session.add(TeamMembership(user_id=user.id, team_organization_id=user.team_organization_id,
                                      role=user.home_role or "player"))
    db.session.commit()
    return len(missing)
