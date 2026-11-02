"""Ask the leaders: what a question in the Leadership hub can be about.

Each subject is found the way its own page finds it, so a question can only
be about something the asker can see (a player can't ask about a draft play,
a hidden clip or an unpublished theory topic, or anything of another team).
"""
from flask import url_for
from werkzeug.exceptions import HTTPException

from app import db
from app.utils.team_filter import get_current_team_id


def _clip(subject_id):
    from app.routes.clip.helpers import get_clip_or_404
    return get_clip_or_404(subject_id)


def _play(subject_id):
    from app.routes.playbook import play_or_404
    return play_or_404(subject_id)


def _topic(subject_id):
    from app.routes.theory import topic_or_404
    return topic_or_404(subject_id)


def _drill(subject_id):
    from app.models.drill import SavedDrill
    return SavedDrill.query.filter_by(id=subject_id, team_organization_id=get_current_team_id()).first()


def _session(subject_id):
    from app.models.session import SessionPlan
    session = db.session.get(SessionPlan, subject_id)
    return session if session and session.team_organization_id == get_current_team_id() else None


# key -> (label, icon, find(id), title(row), endpoint and its id argument)
SUBJECTS = {
    'clip': ('Clip', 'bi-film', _clip, lambda r: r.title or 'Clip', 'clip.view_clip', 'clip_id'),
    'play': ('Play', 'bi-diagram-3', _play, lambda r: r.name, 'playbook.view_play', 'play_id'),
    'topic': ('Theory', 'bi-book', _topic, lambda r: r.name, 'theory.topic', 'topic_id'),
    'drill': ('Drill', 'bi-clipboard2-check', _drill, lambda r: r.title, 'session.drill_detail', 'drill_id'),
    'session': ('Session', 'bi-calendar-check', _session, lambda r: r.title, 'session.detail', 'session_id'),
}


def parse(about):
    """'play:12' -> ('play', 12), or (None, None)."""
    kind, _, raw = (about or '').partition(':')
    if kind in SUBJECTS and raw.isdigit():
        return kind, int(raw)
    return None, None


def find(kind, subject_id):
    """The row, if the signed-in user can see it; else None."""
    if kind not in SUBJECTS or not subject_id:
        return None
    try:
        return SUBJECTS[kind][2](subject_id)
    except HTTPException:
        return None


def describe(kind, subject_id, row=None):
    """{'label', 'icon', 'title', 'url'} for showing what a post is about,
    or None when it's gone (or can't be seen)."""
    row = row if row is not None else find(kind, subject_id)
    if row is None:
        return None
    label, icon, _, title, endpoint, arg = SUBJECTS[kind]
    return {'label': label, 'icon': icon, 'title': title(row), 'url': url_for(endpoint, **{arg: row.id})}
