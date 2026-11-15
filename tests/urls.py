"""URL helpers for tests."""
from app import db
from app.models.session import SessionPlan


def session_path(session_id, rest=''):
    """A session's page, e.g. session_path(3, '/plan'). Sessions are numbered
    per team in URLs (/sessions/s12/plan), not by their database id."""
    return f'/sessions/s{db.session.get(SessionPlan, session_id).number}{rest}'
