"""Training schedules -> session dates.

sync_schedule() makes a SessionPlan for every date a schedule runs on, from
today to its end date (or the end of the current season), so players can
answer before the plan is written. It's safe to run again: dates that
already exist are kept, and the ones nobody has planned yet follow the
schedule's time, place and squads. A date the schedule no longer covers is
deleted if nobody has answered for it, and cancelled otherwise. A cancelled
date stays cancelled (and is never made again) until a coach restores it.

The app's daily job runs extend_all() so open-ended schedules keep going.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

from app import db
from app.models.schedule import TrainingSchedule
from app.models.season import Season
from app.models.session import SessionPlan

# How far ahead dates are made when neither the schedule nor a season ends
DEFAULT_HORIZON = timedelta(weeks=26)
MAX_HORIZON = timedelta(days=400)


@dataclass
class SyncReport:
    created: list = field(default_factory=list)
    updated: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    cancelled: list = field(default_factory=list)

    def summary(self):
        parts = [f'{len(v)} {k}' for k, v in (('added', self.created), ('updated', self.updated),
                                                ('removed', self.removed), ('cancelled', self.cancelled)) if v]
        return ', '.join(parts) or 'no changes'


def last_date(schedule, today=None):
    """The last date a schedule makes sessions for."""
    today = today or date.today()
    end = schedule.end_date
    if end is None:
        season = Season.query.filter_by(team_organization_id=schedule.team_organization_id,
                                        is_current=True).first()
        end = season.end_date if season and season.end_date >= today else today + DEFAULT_HORIZON
    return min(end, today + MAX_HORIZON)


def schedule_dates(schedule, start, end):
    """Every date from start to end (inclusive) on the schedule's weekday."""
    start = max(start, schedule.start_date)
    if schedule.end_date:
        end = min(end, schedule.end_date)
    day = start + timedelta(days=(schedule.weekday - start.weekday()) % 7)
    out = []
    while day <= end:
        out.append(day)
        day += timedelta(days=7)
    return out


def is_planned(session):
    """Has a coach (or the season plan) put anything into this date?"""
    return bool(session.external_id) or session.components.count() > 0


def has_people(session):
    return session.rsvps.count() > 0 or session.attendances.count() > 0


def _follow(session, schedule):
    """Make an unplanned date match its schedule; True if anything changed."""
    values = {'title': schedule.name, 'start_time': schedule.start_time, 'end_time': schedule.end_time,
              'location': schedule.location, 'session_type': schedule.session_type or 'invited_training'}
    changed = False
    for key, value in values.items():
        if getattr(session, key) != value:
            setattr(session, key, value)
            changed = True
    if [s.id for s in session.squads] != [s.id for s in schedule.squads]:
        session.squads = list(schedule.squads)
        changed = True
    return changed


def new_session(schedule, day):
    session = SessionPlan(team_organization_id=schedule.team_organization_id, schedule_id=schedule.id,
                          date=day, is_published=False)
    _follow(session, schedule)
    return session


def sync_schedule(schedule, today=None):
    """Bring a schedule's dates up to date. The caller commits."""
    today = today or date.today()
    report = SyncReport()
    wanted = set(schedule_dates(schedule, today, last_date(schedule, today)))
    existing = {}
    for s in schedule.sessions.filter(SessionPlan.date >= today):
        existing.setdefault(s.date, s)

    for day in sorted(wanted - set(existing)):
        session = new_session(schedule, day)
        db.session.add(session)
        report.created.append(session)

    for day, session in existing.items():
        if day in wanted:
            if not session.is_cancelled and not is_planned(session) and _follow(session, schedule):
                report.updated.append(session)
        elif session.is_cancelled:
            continue
        elif has_people(session) or is_planned(session):
            session.status = SessionPlan.STATUS_CANCELLED
            session.cancel_reason = 'No longer on the training schedule'
            report.cancelled.append(session)
        else:
            report.removed.append(session)
            db.session.delete(session)
    db.session.flush()
    return report


def remove_schedule(schedule, today=None):
    """Delete a schedule: its future dates nobody has answered for or
    planned go, the others are cancelled, and past dates stay as they were.
    The caller commits."""
    today = today or date.today()
    for session in schedule.sessions.filter(SessionPlan.date >= today).all():
        if session.is_cancelled or has_people(session) or is_planned(session):
            if not session.is_cancelled:
                session.status = SessionPlan.STATUS_CANCELLED
                session.cancel_reason = 'Training schedule removed'
        else:
            db.session.delete(session)
    db.session.delete(schedule)


def extend_all(team_id=None, today=None):
    """Sync every schedule (used by the daily job). Commits."""
    query = TrainingSchedule.query
    if team_id is not None:
        query = query.filter_by(team_organization_id=team_id)
    total = 0
    for schedule in query.all():
        total += len(sync_schedule(schedule, today).created)
    db.session.commit()
    return total


def cancel(session, reason=None):
    session.status = SessionPlan.STATUS_CANCELLED
    session.cancel_reason = (reason or '').strip()[:200] or None


def restore(session):
    session.status = SessionPlan.STATUS_SCHEDULED
    session.cancel_reason = None


def clashes(team_id, today=None):
    """[(session, tournament)] for upcoming training dates that fall during
    one of the team's tournaments."""
    from app.models.tournament import Tournament

    today = today or date.today()
    tournaments = Tournament.query.filter(Tournament.team_organization_id == team_id,
                                          Tournament.start_date.isnot(None),
                                          Tournament.start_date >= today - timedelta(days=7)).all()
    if not tournaments:
        return []
    sessions = SessionPlan.query.filter(SessionPlan.team_organization_id == team_id,
                                        SessionPlan.schedule_id.isnot(None),
                                        SessionPlan.status != SessionPlan.STATUS_CANCELLED,
                                        SessionPlan.date >= today).order_by(SessionPlan.date).all()
    out = []
    for session in sessions:
        for t in tournaments:
            if t.start_date <= session.date <= (t.end_date or t.start_date):
                out.append((session, t))
                break
    return out


def parse_skip_dates(text, today=None):
    """Dates typed as '2026-12-26, 2027-01-02' (or one per line)."""
    out, bad = [], []
    for part in (text or '').replace(',', '\n').split():
        try:
            out.append(date.fromisoformat(part.strip()))
        except ValueError:
            bad.append(part.strip())
    return out, bad
