"""Session numbers in URLs.

Every team's sessions share one `session_plan.id` counter, so the first
session a new team makes could be id 173. URLs use the team's own count
instead (`/sessions/s12/plan`), and these two pieces keep that out of the
rest of the code:

* `SessionRefConverter` turns `s12` into the real id before a view runs, so
  views and `url_for(..., session_id=session.id)` calls are unchanged.
* `number_for_legacy_id` finds the new URL for an old `/sessions/173/...`
  link, so bookmarks, Discord messages and emails sent before the change
  keep working.

The `s` prefix is what lets an old id link and a new number link tell
themselves apart: `/sessions/173/plan` can only be the old form.
"""
from flask_login import current_user
from werkzeug.routing import BaseConverter, ValidationError

from app import db


class SessionRefConverter(BaseConverter):
    regex = r's\d+'

    def to_python(self, value):
        from app.models.session import SessionPlan
        from app.utils.team_filter import get_current_team_id
        if not current_user.is_authenticated:
            # Nothing to look up yet; the view's login_required sends them to
            # sign in and brings them back here.
            return 0
        session_id = db.session.query(SessionPlan.id).filter_by(
            team_organization_id=get_current_team_id(), number=int(value[1:])).scalar()
        if session_id is None:
            raise ValidationError()
        return session_id

    def to_url(self, value):
        from app.models.session import SessionPlan
        value = int(value)
        if value == 0:
            return 's0'  # placeholder that page scripts swap for a real number
        # Served from the session's identity map when the page already loaded it
        session = db.session.get(SessionPlan, value)
        if session is None:
            raise ValidationError()
        return f's{session.number}'


def number_for_legacy_id(session_id):
    """The current team's number for an old-style session id, or None if
    the team has no such session."""
    from app.models.session import SessionPlan
    from app.utils.team_filter import get_current_team_id
    return db.session.query(SessionPlan.number).filter_by(
        id=session_id, team_organization_id=get_current_team_id()).scalar()
