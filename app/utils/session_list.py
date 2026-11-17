"""The sessions list (/sessions/): sessions grouped into Monday-to-Sunday
weeks, and what each still needs from a coach.

A season built from the season plan can hold a hundred or more sessions, so
the list opens on what's coming up, groups by week (with the plan's week,
phase and block when the sessions have them) and keeps only the nearest
weeks open.
"""
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func

from app import db
from app.models.session import Attendance, SessionComponent, SessionPlan

SHOW_CHOICES = [('upcoming', 'Coming up'), ('past', 'Past'), ('all', 'All dates')]
NEEDS_CHOICES = [('', 'Any status'), ('any', 'Needs something'), ('plan', 'No plan yet'),
                 ('draft', 'Plan not published'), ('register', 'Register not taken')]
OPEN_WEEKS = 4  # weeks shown open; the rest start folded

ATTENDED = ('present', 'late')


def monday(day):
    return day - timedelta(days=day.weekday())


def session_day(session):
    """The date a session sorts and groups by: its date, else its week."""
    return session.date or session.week_commencing


def counts_for(sessions):
    """{session id: n} for components, players attended and register rows,
    in three queries rather than three per session."""
    ids = [s.id for s in sessions]
    if not ids:
        return {}, {}, {}

    def grouped(column, *where):
        query = db.session.query(column, func.count()).filter(column.in_(ids), *where).group_by(column)
        return dict(query.all())

    return (grouped(SessionComponent.session_id),
            grouped(Attendance.session_id, Attendance.status.in_(ATTENDED)),
            grouped(Attendance.session_id))


def needs(session, components, register_rows, today):
    """What a coach still has to do for a session: a list of
    'plan' / 'draft' / 'register'. Cancelled sessions need nothing."""
    if session.is_cancelled:
        return []
    out = []
    if not components:
        out.append('plan')
    elif not session.is_published:
        out.append('draft')
    if session.date and session.date <= today and not register_rows:
        out.append('register')
    return out


@dataclass
class Week:
    start: object  # the Monday, or None for sessions with no date
    sessions: list = field(default_factory=list)
    open: bool = False
    need_count: int = 0  # coaches: things still to do across its sessions

    @property
    def anchor(self):
        return f'week-{self.start.isoformat()}' if self.start else 'week-undated'

    def plan_info(self):
        """(week number, phase, block) from the first session that has
        them, for weeks built from the season plan."""
        number = next((s.week_number for s in self.sessions if s.week_number), None)
        phase = next((s.phase_name for s in self.sessions if s.phase_name), None)
        block = next((s.block for s in self.sessions if s.block), None)
        return number, phase, block


def group_by_week(sessions, today, show='upcoming'):
    """[Week] in the order the sessions came. The weeks nearest today are
    open: the first OPEN_WEEKS for upcoming or past, and for all dates this
    week and the three after it (or the last four, once the season's over)."""
    weeks, by_start = [], {}
    for s in sessions:
        day = session_day(s)
        start = monday(day) if day else None
        week = by_start.get(start)
        if week is None:
            week = by_start[start] = Week(start)
            weeks.append(week)
        week.sessions.append(s)

    dated = [w for w in weeks if w.start]
    if show == 'all':
        this_week = monday(today)
        current = [w for w in dated if w.start >= this_week]
        if current:
            current.sort(key=lambda w: w.start)
            open_weeks = current[:OPEN_WEEKS]
        else:
            open_weeks = sorted(dated, key=lambda w: w.start)[-OPEN_WEEKS:]
    else:
        open_weeks = dated[:OPEN_WEEKS]
    for w in open_weeks:
        w.open = True
    for w in weeks:
        if w.start is None:
            w.open = not dated
    return weeks


def order_for(query, show):
    """Upcoming and all dates read forwards; past reads back from today."""
    day = func.coalesce(SessionPlan.date, SessionPlan.week_commencing)
    if show == 'past':
        return query.order_by(day.desc(), SessionPlan.start_time.desc(), SessionPlan.id.desc())
    return query.order_by(day.is_(None), day.asc(), SessionPlan.start_time.asc(), SessionPlan.id.asc())


def filter_when(query, show, today):
    day = func.coalesce(SessionPlan.date, SessionPlan.week_commencing)
    if show == 'upcoming':
        return query.filter(db.or_(day >= today, day.is_(None)))
    if show == 'past':
        return query.filter(day < today)
    return query
