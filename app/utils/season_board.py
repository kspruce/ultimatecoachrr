"""The season board (Season plan > Season board, coaches): every week of
the plan in one grid, with its phase, block and themes, and a cell for each
session the week has or should have (the joint session, then one per squad),
saying how far its planning has got.

Statuses, worst first:
    conflict    changed in the session and in the plan (choose under Sessions)
    needed      the week has a theme for it but no session yet
    not_built   the week's notes have it, but it hasn't been built
    empty       the session exists but has no activities
    draft       planned, but players can't see it yet
    planned     published, with activities
    cancelled   called off
    none        nothing expected (a break, an event, or a squad with no theme)
"""
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import func

from app import db
from app.models.session import SessionComponent, SessionPlan
from app.utils.season_sessions import _external_prefix, _like_prefix, build_sessions, split_squads, squad_slug
from app.utils.session_list import counts_for

STATUS_LABELS = {
    'conflict': 'Changed in both', 'needed': 'Needs planning', 'not_built': 'Not built yet',
    'empty': 'No activities', 'draft': 'Draft', 'planned': 'Planned', 'cancelled': 'Cancelled', 'none': '',
}
NEEDS_WORK = ('conflict', 'needed', 'not_built', 'empty')


@dataclass
class Cell:
    key: str  # 'joint' or a squad name
    status: str
    session: object = None
    activities: int = 0
    minutes: int = 0
    conflict_parts: list = field(default_factory=list)

    @property
    def label(self):
        return STATUS_LABELS[self.status]


@dataclass
class Row:
    week: object
    cells: list
    is_current: bool = False
    is_past: bool = False

    @property
    def needs_work(self):
        return any(c.status in NEEDS_WORK for c in self.cells)

    @property
    def has_drafts(self):
        return any(c.status == 'draft' for c in self.cells)


def columns(plan):
    """[(key, label)]: the joint session, then a column per squad."""
    return [('joint', 'Joint')] + [(q, q) for q in split_squads(plan)]


def _expected(week, key):
    """Should this week have a session in this column?"""
    if week.is_break or week.is_event:
        return False
    if key == 'joint':
        return bool(week.joint_theme or week.block or week.session_title)
    return bool(week.theme_for(key))


def build_board(plan, today):
    cols = columns(plan)
    by_slug = {('joint' if k == 'joint' else squad_slug(k)): k for k, _ in cols}
    prefix = _external_prefix(plan)
    sessions = SessionPlan.query.filter(SessionPlan.team_organization_id == plan.team_organization_id,
                                        _like_prefix(prefix)).all()
    found = {}
    for s in sessions:
        rest = s.external_id[len(prefix):]  # '05-joint'
        number, _, slug = rest.partition('-')
        if number.isdigit() and slug in by_slug:
            found[(int(number), by_slug[slug])] = s
    components, _, _ = counts_for(sessions)
    minutes = dict(db.session.query(SessionComponent.session_id, func.sum(SessionComponent.duration_minutes))
                   .filter(SessionComponent.session_id.in_([s.id for s in sessions]))
                   .group_by(SessionComponent.session_id).all()) if sessions else {}

    # What building would do: sessions the notes have but that aren't built,
    # and sessions changed both in the session and in the plan
    preview = build_sessions(plan, dry_run=True)
    to_build = {(r['week'], r['squad']) for r in preview.rows if r['status'] == 'created'}
    conflicts = {c['session_id']: c['parts'] for c in preview.conflicts}

    current = plan.week_for(today)
    rows = []
    for week in plan.weeks:
        cells = []
        for key, _ in cols:
            s = found.get((week.week_number, key))
            if s is not None:
                if s.is_cancelled:
                    status = 'cancelled'
                elif s.id in conflicts:
                    status = 'conflict'
                elif not components.get(s.id):
                    status = 'empty'
                else:
                    status = 'planned' if s.is_published else 'draft'
                cells.append(Cell(key, status, s, components.get(s.id, 0), minutes.get(s.id) or 0,
                                  conflicts.get(s.id, [])))
            elif (week.week_number, key) in to_build:
                cells.append(Cell(key, 'not_built'))
            else:
                cells.append(Cell(key, 'needed' if _expected(week, key) else 'none'))
        rows.append(Row(week, cells, is_current=current is not None and current.id == week.id,
                        is_past=bool(week.week_ending and week.week_ending < today)))

    totals = Counter(c.status for r in rows for c in r.cells)
    return {'columns': cols, 'rows': rows, 'totals': totals, 'current': current}
