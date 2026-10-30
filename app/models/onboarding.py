# app/models/onboarding.py
from datetime import datetime

from app import db


class UserOnboarding(db.Model):
    """What we can't work out from a user's data about their getting-started
    guide: which role they were last welcomed as, whether they hid the
    checklist, the "go and look at this" steps they've opened, and when
    they were sent their reminder."""

    __tablename__ = 'user_onboarding'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'),
                        unique=True, nullable=False)
    # Role the welcome page was last shown for; a promotion shows it again
    welcomed_role = db.Column(db.String(20))
    dismissed_at = db.Column(db.DateTime)
    # The one email reminding them of the steps they haven't done
    nudged_at = db.Column(db.DateTime)
    completed_steps = db.Column(db.JSON, nullable=False, default=list)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def has_completed(self, key):
        return key in (self.completed_steps or [])

    def complete(self, key):
        if not self.has_completed(key):
            # Reassign so SQLAlchemy notices the change to the JSON column
            self.completed_steps = [*(self.completed_steps or []), key]

    def __repr__(self):
        return f'<UserOnboarding user_id={self.user_id} welcomed_role={self.welcomed_role}>'
