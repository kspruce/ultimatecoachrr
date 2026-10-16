"""Build SessionPlans from the season plan's week-by-week session notes, so
the plan is the one place sessions are written.

Each "## Week N" section of the plan can hold timed tables:

  | Time | Activity | How it runs | Source |          -> one joint session
  | Time | 1s group | 2s group (suggested) | Source | -> a 1s and a 2s session

The bold line just above a table ("**Joint session**", "**Light joint session
(about 2 hours)**") names it; a length in that line ("about 2 hours", "90
minutes") sets how long the last activity runs. Each row becomes a session
component, timed from the gap to the next row. "**Learning points:** (1) ...
(2) ..." become the learning points, and the rest of the week's notes become
the session notes.

Sessions are matched on external_id "plan-<season>-w<NN>-<squad>", so
building again updates them in place: the plan owns the title, date, times,
location, aim, notes and components. Attendance and RSVPs are never touched.
A session the plan no longer has is deleted if nobody has RSVPed or been
marked present, and otherwise left alone with a warning.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app import db
from app.models.drill import SavedDrill
from app.models.session import SessionPlan
from app.utils.season_import import _apply, _sync_components
from app.utils.season_plan_import import clean_cell, parse_tables

SQUAD_LABELS = {'joint': 'Joint', '1s': '1s', '2s': '2s'}
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
NAME_LIMIT = 100  # SessionComponent.title and SessionPlan.title
SHORT_NAME = 80   # longer cells are split into a name and a description

LABEL_RE = re.compile(r'^\s*\*\*(.+?)\*\*\s*(.*)$')
LEARNING_RE = re.compile(r'^\s*\*\*learning points:?\*\*:?\s*(.*)$', re.I)
NUMBERED_RE = re.compile(r'\(\d+\)\s*')
CLOCK_RE = re.compile(r'^\s*(\d{1,2})[:.](\d{2})')
HOURS_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b', re.I)
MINUTES_RE = re.compile(r'(\d+)\s*(?:minutes?|mins?)\b', re.I)

# First match wins; anything else is a drill.
COMPONENT_TYPES = [
    ('water', re.compile(r'\bwater\b', re.I)),
    ('warmup', re.compile(r'\bwarm[- ]?up\b', re.I)),
    ('cooldown', re.compile(r'\bcool[- ]?down\b', re.I)),
    ('scrimmage', re.compile(r'\b(scrimmage|free game|7v7|game[- ]plan scrimmage)\b', re.I)),
    ('discussion', re.compile(r'^(welcome|recap|close|briefing|debrief|review|talk|huddle|'
                              r'shout-outs|captains|q&a)\b', re.I)),
]


# --------------------------------------------------------------------------
# Parsing one week's notes
# --------------------------------------------------------------------------

def _clock(text):
    m = CLOCK_RE.match(text or '')
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def length_from_label(label):
    """Minutes from "(about 2.5 hours)" / "(90 minutes)", or None."""
    m = HOURS_RE.search(label or '')
    if m:
        return round(float(m.group(1)) * 60)
    m = MINUTES_RE.search(label or '')
    return int(m.group(1)) if m else None


def component_type(name):
    for ctype, pattern in COMPONENT_TYPES:
        if pattern.search(name or ''):
            return ctype
    return 'drill'


def split_name(text):
    """(name, extra description) for a table cell. Short cells are the name;
    longer ones are split at the first ':', ';' or '. ', or cut at a word."""
    text = (text or '').strip()
    if len(text) <= SHORT_NAME:
        return text, None
    m = re.search(r'(:\s|;\s|\.\s)', text)
    if m and 3 <= m.start() <= SHORT_NAME:
        return text[:m.start()].strip(), text[m.end():].strip() or None
    cut = text.rfind(' ', 0, SHORT_NAME)
    return text[:cut if cut > 20 else SHORT_NAME].rstrip(' ,;:') + '…', text


def _label_above(lines, start):
    """(label text, line index) of the bold line just above a table."""
    for j in range(start - 1, -1, -1):
        if lines[j].strip():
            m = LABEL_RE.match(lines[j])
            if m and len(m.group(1)) <= 120:
                label = (m.group(1).rstrip(':') + (' ' + m.group(2) if m.group(2) else '')).strip()
                return clean_cell(label), j
            return None, None
    return None, None


def _rows_to_activities(rows, length):
    """[(start minute or None, name, how, source)] -> component dicts. Each
    row runs until the next row starts; the last runs to `length`."""
    out = []
    for i, (start, name, how, source) in enumerate(rows):
        nxt = next((r[0] for r in rows[i + 1:] if r[0] is not None), None)
        end = nxt if nxt is not None else (length if i == len(rows) - 1 else None)
        mins = end - start if start is not None and end is not None and end > start else None
        title, extra = split_name(name)
        description = '\n\n'.join(p for p in (extra, how) if p) or None
        out.append({
            'title': title[:NAME_LIMIT],
            'description': description,
            'coach_cue': None,
            'duration_minutes': mins,
            'component_type': component_type(title),
            'focus_area': None,
            'notes': f'Source: {source}' if source else None,
            'order': i + 1,
        })
    return out


def _col(header, *prefixes):
    return next((i for i, h in enumerate(header) if any(h.startswith(p) for p in prefixes)), None)


def parse_week_notes(markdown):
    """Read one week's session notes. Returns
    {'sessions': [{'squad', 'label', 'activities'}], 'learning_points': [...],
     'notes': the rest of the markdown}."""
    lines = (markdown or '').splitlines()
    drop = set()
    sessions = []

    for table in parse_tables(markdown or ''):
        header = table['header']
        if not header or header[0] != 'time':
            continue
        activity, how, source = _col(header, 'activity'), _col(header, 'how'), _col(header, 'source')
        firsts, seconds = _col(header, '1s'), _col(header, '2s')
        if activity is None and (firsts is None or seconds is None):
            continue
        label, label_line = _label_above(lines, table['start'])
        length = length_from_label(label)
        cells = [[clean_cell(c) for c in row] + [None] * len(header) for row in table['rows']]

        def cell(row, i):
            return row[i] if i is not None else None

        if activity is not None:
            rows = [(_clock(r[0]), cell(r, activity), cell(r, how), cell(r, source))
                    for r in cells if cell(r, activity)]
            squad = 'joint' if not sessions or all(s['squad'] != 'joint' for s in sessions) else None
            if squad is None:
                continue  # a second joint table in one week: keep it in the notes
            sessions.append({'squad': 'joint', 'label': label or 'Joint session',
                             'length': length, 'activities': _rows_to_activities(rows, length)})
        else:
            if any(s['squad'] in ('1s', '2s') for s in sessions):
                continue
            ones, twos = [], []
            for r in cells:
                one, two = cell(r, firsts), cell(r, seconds)
                if two and two.lower().rstrip('.') == 'same':
                    two = one
                start, src = _clock(r[0]), cell(r, source)
                if one:
                    ones.append((start, one, None, src))
                if two:
                    twos.append((start, two, None, src))
            for squad, rows in (('1s', ones), ('2s', twos)):
                if rows:
                    sessions.append({'squad': squad, 'label': label or 'Split session',
                                     'length': length, 'activities': _rows_to_activities(rows, length)})
        drop.update(range(table['start'], table['end']))
        if label_line is not None:
            drop.add(label_line)

    points = []
    for i, line in enumerate(lines):
        m = LEARNING_RE.match(line)
        if m:
            parts = [p.strip() for p in NUMBERED_RE.split(m.group(1)) if p.strip()]
            points = [clean_cell(p) for p in parts] or ([m.group(1).strip()] if m.group(1).strip() else [])
            drop.add(i)
            break

    notes = '\n'.join(line for i, line in enumerate(lines) if i not in drop)
    notes = re.sub(r'\n{3,}', '\n\n', notes).strip() or None
    return {'sessions': sessions, 'learning_points': points, 'notes': notes}


# --------------------------------------------------------------------------
# Building sessions
# --------------------------------------------------------------------------

@dataclass
class BuildReport:
    dry_run: bool = False
    rows: list = field(default_factory=list)  # one per session: week, squad, title, status, ...
    skipped: list = field(default_factory=list)  # (week number, why)
    removed: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def count(self, status):
        return sum(1 for r in self.rows if r['status'] == status)

    def summary(self):
        parts = [f'{self.count(s)} {s}' for s in ('created', 'updated', 'unchanged') if self.count(s)]
        if self.removed:
            parts.append(f'{len(self.removed)} removed')
        return ', '.join(parts) or 'nothing to build'

    def text(self):
        out = [f'sessions: {self.summary()}']
        out += [f'  {r["status"]:>9}  {r["title"]}' for r in self.rows if r['status'] != 'unchanged']
        out += [f'  removed  {line}' for line in self.removed]
        out += [f'  warning: {line}' for line in self.warnings]
        return '\n'.join(out)


def external_id(plan, week_number, squad):
    return f'plan-{plan.season}-w{week_number:02d}-{squad}'


def _external_prefix(plan):
    return f'plan-{plan.season}-w'


def is_built_session(session):
    return bool(session.external_id and session.external_id.startswith('plan-'))


def _session_when(plan, week, squad):
    """(date, start, end) from the plan's training days and times."""
    if squad == 'joint':
        weekday, start, end = plan.joint_weekday, plan.joint_start, plan.joint_end
    else:
        weekday, start, end = plan.split_weekday, plan.split_start, plan.split_end
    day = (week.week_commencing + timedelta(days=weekday)
           if week.week_commencing and weekday is not None else None)
    return day, start, end


def _minutes_between(start, end):
    if not start or not end:
        return None
    mins = (datetime.combine(date.min, end) - datetime.combine(date.min, start)).seconds // 60
    return mins or None


def _theme(week, squad):
    return {'joint': week.joint_theme, '1s': week.firsts_theme, '2s': week.seconds_theme}[squad]


def _title(week, squad):
    name = week.session_title or week.block
    title = f'Week {week.week_number} {SQUAD_LABELS[squad]}' + (f': {name}' if name else '')
    return title if len(title) <= NAME_LIMIT else title[:NAME_LIMIT - 1].rstrip() + '…'


def plan_week(plan, week):
    """The sessions one week should have: [{'external_id', 'values', 'components'}]."""
    if week.is_break or not week.session_detail_md:
        return []
    parsed = parse_week_notes(week.session_detail_md)
    out = []
    for s in parsed['sessions']:
        squad = s['squad']
        day, start, end = _session_when(plan, week, squad)
        activities = s['activities']
        # Without a length in the label, the last activity runs to the end time
        if activities and activities[-1]['duration_minutes'] is None and not s['length']:
            total = _minutes_between(start, end)
            if total:
                elapsed = sum(a['duration_minutes'] or 0 for a in activities[:-1])
                if total > elapsed:
                    activities[-1]['duration_minutes'] = total - elapsed
        if s['length'] and start and not end:
            end = (datetime.combine(date.min, start) + timedelta(minutes=s['length'])).time()
        values = {
            'title': _title(week, squad),
            'season': plan.season,
            'phase_number': week.phase.number if week.phase else None,
            'phase_name': (week.phase.name[:100] if week.phase else None),
            'block': week.block,
            'week_number': week.week_number,
            'week_commencing': week.week_commencing,
            'squad': squad,
            'aim': _theme(week, squad) or week.session_title,
            'learning_points': parsed['learning_points'] or None,
            'notes': parsed['notes'],
            'focus_area': (week.session_title or '')[:100] or None,
            'date': day,
            'start_time': start,
            'end_time': end,
            'location': plan.session_location,
        }
        out.append({'external_id': external_id(plan, week.week_number, squad),
                    'values': values, 'components': activities})
    return out


def _like_prefix(prefix):
    return SessionPlan.external_id.like(prefix.replace('_', r'\_') + '%', escape='\\')


def week_sessions(plan, week):
    """The sessions built from one week, joint first."""
    order = {'joint': 0, '1s': 1, '2s': 2}
    rows = SessionPlan.query.filter(
        SessionPlan.team_organization_id == plan.team_organization_id,
        _like_prefix(f'{_external_prefix(plan)}{week.week_number:02d}-')).all()
    return sorted(rows, key=lambda s: order.get(s.squad, 3))


def _drill_lookup(team_id):
    """Activity name (lower case) -> SavedDrill id, for linking components to
    the team's drill library."""
    rows = db.session.query(SavedDrill.id, SavedDrill.title).filter(
        SavedDrill.team_organization_id == team_id).all()
    return {title.strip().lower(): drill_id for drill_id, title in rows if title}


def _has_people(session):
    return session.attendances.count() > 0 or session.rsvps.count() > 0


def build_sessions(plan, weeks=None, dry_run=False, commit=True):
    """Create or update the sessions for `weeks` (default: every week).
    With every week, sessions the plan no longer has are removed too."""
    team_id = plan.team_organization_id
    report = BuildReport(dry_run=dry_run)
    drills = _drill_lookup(team_id)
    whole_plan = weeks is None
    weeks = plan.weeks if whole_plan else weeks
    wanted_ids = set()
    joint_by_week = {}

    try:
        for week in weeks:
            planned = plan_week(plan, week)
            if not planned:
                why = ('break' if week.is_break else 'no session notes' if not week.session_detail_md
                       else 'no session table')
                report.skipped.append((week.week_number, why))
            prefix = f'{_external_prefix(plan)}{week.week_number:02d}-'
            existing = {s.external_id: s for s in SessionPlan.query.filter(
                SessionPlan.team_organization_id == team_id,
                _like_prefix(prefix))}

            for item in planned:
                ext = item['external_id']
                wanted_ids.add(ext)
                session = existing.pop(ext, None)
                if session is None:
                    session = SessionPlan(team_organization_id=team_id, external_id=ext)
                    _apply(session, item['values'])
                    db.session.add(session)
                    db.session.flush()
                    status = 'created'
                else:
                    status = 'updated' if _apply(session, item['values']) else 'unchanged'
                for c in item['components']:
                    c['drill_external_id'] = c['title'].strip().lower()
                if _sync_components(session, item['components'], drills, team_id) and status == 'unchanged':
                    status = 'updated'
                if session.squad == 'joint':
                    joint_by_week[week.week_number] = session
                report.rows.append({'week': week.week_number, 'squad': session.squad,
                                    'session_id': session.id,
                                    'title': session.title, 'date': session.date,
                                    'activities': len(item['components']), 'status': status,
                                    'session': session})

            for session in existing.values():
                _remove(session, report)

            # Point the week at its joint session (or its first one), unless a
            # coach linked it to a session of their own.
            built = joint_by_week.get(week.week_number) or next(
                (r['session'] for r in report.rows if r['week'] == week.week_number), None)
            linked = week.session_plan
            if built and (linked is None or is_built_session(linked)):
                week.session_plan = built
            elif not built and linked is not None and is_built_session(linked) \
                    and linked.external_id not in wanted_ids:
                week.session_plan = None

        if whole_plan:
            # Weeks that are gone from the plan altogether
            leftovers = SessionPlan.query.filter(
                SessionPlan.team_organization_id == team_id,
                _like_prefix(_external_prefix(plan))).all()
            for session in leftovers:
                if session.external_id not in wanted_ids:
                    _remove(session, report)
            plan.sessions_built_at = datetime.utcnow()

        db.session.flush()
        if dry_run:
            db.session.rollback()
        elif commit:
            db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return report


def _remove(session, report):
    if _has_people(session):
        report.warnings.append(f'{session.title}: no longer in the plan, but kept because it '
                               f'has attendance or RSVPs')
        return
    from app.models.season_plan import SeasonWeek
    SeasonWeek.query.filter_by(session_plan_id=session.id).update({'session_plan_id': None})
    from app.models.playbook import Play
    assoc = Play.play_session_component
    ids = [c.id for c in session.components]
    if ids:
        db.session.execute(assoc.delete().where(assoc.c.component_id.in_(ids)))
    report.removed.append(session.title)
    db.session.delete(session)


def sync_week(plan, week):
    """Keep one week's sessions in step after the week is edited, once the
    plan's sessions have been built. Returns the report or None."""
    if not plan.sessions_built_at:
        return None
    return build_sessions(plan, weeks=[week])

