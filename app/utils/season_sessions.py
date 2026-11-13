"""Build SessionPlans from the season plan's week-by-week session notes, so
the plan is the one place sessions are written.

Each "## Week N" section of the plan can hold timed tables:

  | Time | Activity | How it runs | Source |          -> one joint session
  | Time | 1s group | 2s group (suggested) | Source | -> a session for each of
                                                         the plan's squads named
                                                         in the header

The bold line just above a table ("**Joint session**", "**Light joint session
(about 2 hours)**") names it; a length in that line ("about 2 hours", "90
minutes") sets how long the last activity runs. Each row becomes a session
component, timed from the gap to the next row. "**Learning points:** (1) ...
(2) ..." become the learning points, and the rest of the week's notes become
the session notes.

Sessions are matched on external_id "plan-<season>-w<NN>-<squad slug>", so
building again updates them in place: the plan owns the title, date, times,
location, aim, notes and components. Attendance and RSVPs are never touched.
A session the plan no longer has is deleted if nobody has RSVPed or been
marked present, and otherwise left alone with a warning.

When the team has a training schedule, a week's session fills in the
schedule's date that week for the same squads (joint: a session for the
whole club; a squad: that squad's own session) instead of making a new one,
so players' answers for that date stay with it. The schedule keeps the date,
time and place; the plan's training days and times are only used for weeks
no schedule covers.
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app import db
from app.models.drill import SavedDrill
from app.models.session import SessionPlan
from app.utils.season_import import _apply, _sync_components
from app.utils.season_plan_import import clean_cell, parse_tables, squad_name

WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
NAME_LIMIT = 100  # SessionComponent.title and SessionPlan.title
SHORT_NAME = 80   # longer cells are split into a name and a description

LABEL_RE = re.compile(r'^\s*\*\*(.+?)\*\*\s*(.*)$')
LEARNING_RE = re.compile(r'^\s*\*\*learning points:?\*\*:?\s*(.*)$', re.I)
NUMBERED_RE = re.compile(r'\(\d+\)\s*')
CLOCK_RE = re.compile(r'^\s*(\d{1,2})[:.](\d{2})')
HOURS_RE = re.compile(r'(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b', re.I)
MINUTES_RE = re.compile(r'(\d+)\s*(?:minutes?|mins?)\b', re.I)
# "Ho game with 3 lives: each team has three turnovers before the point ends"
SAME_RE = re.compile(r'^(?:the\s+)?same(?![\w-])(?:\s+drill\b)?(.*)$', re.I)
EXPLAINED_RE = re.compile(r'^([^:]{3,50}):\s+(.{25,})$')

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
    """(name, extra description) for a table cell. Short cells are the name,
    unless they read "Name: how it runs"; longer ones are split at the first
    ':', ';' or '. ', or cut at a word."""
    text = (text or '').strip()
    if len(text) <= SHORT_NAME:
        m = EXPLAINED_RE.match(text)
        if m:
            return m.group(1).strip(), m.group(2).strip()
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


def _squad_columns(table, squads):
    """{column index: plan squad} for a split table's squad columns."""
    by_lower = {q.lower(): q for q in squads}
    out = {}
    for i, raw in enumerate(table.get('raw_header') or table['header']):
        if i == 0:
            continue
        squad = by_lower.get(squad_name(raw).lower())
        if squad and squad not in out.values():
            out[i] = squad
    return out


def parse_week_notes(markdown, squads=('1s', '2s')):
    """Read one week's session notes. `squads` are the plan's squads, which a
    split table's columns are matched to. Returns
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
        squad_cols = _squad_columns(table, squads) if activity is None else {}
        if activity is None and not squad_cols:
            continue
        label, label_line = _label_above(lines, table['start'])
        length = length_from_label(label)
        cells = [[clean_cell(c) for c in row] + [None] * len(header) for row in table['rows']]

        def cell(row, i):
            return row[i] if i is not None else None

        if activity is not None:
            rows = [(_clock(r[0]), cell(r, activity), cell(r, how), cell(r, source))
                    for r in cells if cell(r, activity)]
            if any(s['squad'] == 'joint' for s in sessions):
                continue  # a second joint table in one week: keep it in the notes
            sessions.append({'squad': 'joint', 'label': label or 'Joint session',
                             'length': length, 'activities': _rows_to_activities(rows, length)})
        else:
            if any(s['squad'] != 'joint' for s in sessions):
                continue
            columns = sorted(squad_cols.items())
            per_squad = {squad: [] for _, squad in columns}
            for r in cells:
                start, src = _clock(r[0]), cell(r, source)
                first = cell(r, columns[0][0])
                for n, (i, squad) in enumerate(columns):
                    text, extra = cell(r, i), None
                    same = SAME_RE.match(text or '') if n else None
                    if same and first:
                        # "Same", "The same", "Same drill at stall 7": the
                        # first squad's activity, with what changes in its
                        # description
                        text = first
                        rest = same.group(1).strip(' .,;:')
                        extra = f'{squad}: {rest}' if rest else None
                    if text:
                        per_squad[squad].append((start, text, extra, src))
            for squad, rows in per_squad.items():
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


def squad_slug(squad):
    return re.sub(r'[^a-z0-9]+', '-', (squad or '').lower()).strip('-') or 'squad'


def external_id(plan, week_number, squad):
    return f'plan-{plan.season}-w{week_number:02d}-{squad_slug(squad)}'


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
    return week.theme_for(squad)


def squad_label(squad):
    """SessionPlan.squad for a plan squad: 'joint', '1s' or '2s' (the
    labels the sessions pages filter on), else None; the session's ticked
    squads say who it's for."""
    value = 'joint' if squad == 'joint' else (squad or '').strip().lower()
    return value if value in {v for v, _ in SessionPlan.SQUAD_CHOICES} else None


def _title(week, squad):
    name = week.session_title or week.block
    title = f'Week {week.week_number} {"Joint" if squad == "joint" else squad}' + (f': {name}' if name else '')
    return title if len(title) <= NAME_LIMIT else title[:NAME_LIMIT - 1].rstrip() + '…'


def split_squads(plan):
    """The squads a split table's columns can name: the plan's squads, or,
    for a plan without any, the club's squads."""
    if plan.squads:
        return plan.squads
    from app.models.season import Squad
    return [q.name for q in Squad.query.filter_by(team_organization_id=plan.team_organization_id)
            .order_by(Squad.sort_order, Squad.name)]


def plan_week(plan, week):
    """The sessions one week should have: [{'external_id', 'values', 'components'}]."""
    if week.is_break or not week.session_detail_md:
        return []
    parsed = parse_week_notes(week.session_detail_md, split_squads(plan))
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
            'squad': squad_label(squad),
            'aim': _theme(week, squad) or week.session_title,
            'learning_points': parsed['learning_points'] or None,
            'notes': parsed['notes'],
            'focus_area': (week.session_title or '')[:100] or None,
            'date': day,
            'start_time': start,
            'end_time': end,
            'location': plan.session_location,
        }
        out.append({'external_id': external_id(plan, week.week_number, squad), 'squad': squad,
                    'values': values, 'components': activities})
    return out


def _like_prefix(prefix):
    return SessionPlan.external_id.like(prefix.replace('_', r'\_') + '%', escape='\\')


def week_sessions(plan, week):
    """The sessions built from one week, joint first, then in the plan's
    squad order."""
    prefix = f'{_external_prefix(plan)}{week.week_number:02d}-'
    order = {'joint': 0, **{squad_slug(q): i + 1 for i, q in enumerate(split_squads(plan))}}
    rows = SessionPlan.query.filter(
        SessionPlan.team_organization_id == plan.team_organization_id, _like_prefix(prefix)).all()
    return sorted(rows, key=lambda s: order.get(s.external_id[len(prefix):], len(order)))


QUALIFIER_RE = re.compile(r'\b(stall \d+|then|with|against|as in|from week|in ho|in vert)\b.*$')


def drill_key(text):
    """A drill or activity name reduced for matching: lower case, no
    bracketed parts ("(GRUT)"), punctuation as spaces, no "a", "an" or
    "the"."""
    text = re.sub(r'\([^)]*\)', ' ', (text or '').lower())
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return ' '.join(w for w in text.split() if w not in ('a', 'an', 'the'))


def _prefix_ok(key):
    """Library names short enough to be mistaken for a word in another name
    ("Marking", "Zone") only ever match exactly."""
    return ' ' in key or any(ch.isdigit() for ch in key)


def match_drill(title, keys, prefixable=None):
    """The library key (from `keys`, a set of drill_key()s) that an activity
    title refers to, or None. Only keys in `prefixable` (default: all) match
    by prefix. Tries, in order: the whole title; each side of
    a "Label: name" title; the title without qualifiers such as ", stall 5"
    or "then ..."; then the longest library name that starts the title
    ("Keeping margins, then box of death" -> "keeping margins"), or that the
    title starts if only one does ("4v4, stall 7" -> "4v4 continuous")."""
    candidates = [title or '']
    if ':' in candidates[0]:
        left, right = candidates[0].split(':', 1)
        candidates += [left, right]
    tried = []
    for cand in candidates:
        key = drill_key(cand)
        for k in (key, QUALIFIER_RE.sub('', key).strip()):
            if k and k not in tried:
                tried.append(k)
    for k in tried:
        if k in keys:
            return k
    keys = [k for k in keys if prefixable is None or k in prefixable]
    for k in tried:
        starts = [lib for lib in keys if _prefix_ok(lib) and (k + ' ').startswith(lib + ' ')]
        if starts:
            return max(starts, key=len)
    for k in tried:
        if not _prefix_ok(k):
            continue
        started = [lib for lib in keys if lib.startswith(k + ' ')]
        if len(started) == 1:
            return started[0]
    return None


def _drill_lookup(team_id):
    """(drill_key(title) -> SavedDrill id, the keys that may also match by
    prefix), for linking components to the team's drill library. Standard
    cards only match their exact title. Where two share a name the newest
    wins."""
    rows = db.session.query(SavedDrill.id, SavedDrill.title, SavedDrill.is_standard_card).filter(
        SavedDrill.team_organization_id == team_id).order_by(SavedDrill.id).all()
    lookup, prefixable = {}, set()
    for drill_id, title, is_card in rows:
        key = drill_key(title)
        if key:
            lookup[key] = drill_id
            if not is_card:
                prefixable.add(key)
            else:
                prefixable.discard(key)
    return lookup, prefixable


# Water breaks and warm-ups are never linked to a drill.
UNLINKED_TYPES = ('water', 'warmup')

WHEN_KEYS = ('date', 'start_time', 'end_time', 'location')
PLAN_KEYS = ('season', 'phase_number', 'phase_name', 'block', 'week_number', 'week_commencing', 'squad',
             'aim', 'learning_points', 'notes', 'focus_area')


def _scheduled_date(team_id, week, squad):
    """An unplanned training-schedule date in this week for this squad
    ('joint' or a plan squad name)."""
    if not week.week_commencing:
        return None
    candidates = SessionPlan.query.filter(
        SessionPlan.team_organization_id == team_id, SessionPlan.schedule_id.isnot(None),
        SessionPlan.external_id.is_(None), SessionPlan.status != SessionPlan.STATUS_CANCELLED,
        SessionPlan.date >= week.week_commencing,
        SessionPlan.date <= week.week_commencing + timedelta(days=6)).order_by(SessionPlan.date).all()
    for session in candidates:
        if session.components.count():
            continue
        names = {q.name.strip().lower() for q in session.squads}
        if (squad == 'joint' and len(names) != 1) or (squad != 'joint' and names == {squad.strip().lower()}):
            return session
    return None


def _squads_for(team_id, squad):
    """The team's Squad rows for a plan squad ('joint' is everyone)."""
    if squad == 'joint':
        return []
    from app.models.season import Squad
    return [q for q in Squad.query.filter_by(team_organization_id=team_id)
            if q.name.strip().lower() == squad.strip().lower()]


def _has_people(session):
    return session.attendances.count() > 0 or session.rsvps.count() > 0


def build_sessions(plan, weeks=None, dry_run=False, commit=True):
    """Create or update the sessions for `weeks` (default: every week).
    With every week, sessions the plan no longer has are removed too."""
    team_id = plan.team_organization_id
    report = BuildReport(dry_run=dry_run)
    drills, prefixable = _drill_lookup(team_id)
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
                values = item['values']
                if session is None:
                    session = _scheduled_date(team_id, week, item['squad'])
                    if session is not None:
                        # Fill in the schedule's date; it keeps its own when and where
                        session.external_id = ext
                        session.is_published = True
                        _apply(session, {k: v for k, v in values.items() if k not in WHEN_KEYS})
                        status = 'created'
                    else:
                        session = SessionPlan(team_organization_id=team_id, external_id=ext)
                        _apply(session, values)
                        session.squads = _squads_for(team_id, item['squad'])
                        db.session.add(session)
                        status = 'created'
                    db.session.flush()
                else:
                    if session.schedule_id:
                        values = {k: v for k, v in values.items() if k not in WHEN_KEYS}
                    status = 'updated' if _apply(session, values) else 'unchanged'
                for c in item['components']:
                    c['drill_external_id'] = (match_drill(c['title'], set(drills), prefixable)
                                              if c['component_type'] not in UNLINKED_TYPES else None)
                if _sync_components(session, item['components'], drills, team_id) and status == 'unchanged':
                    status = 'updated'
                if item['squad'] == 'joint':
                    joint_by_week[week.week_number] = session
                report.rows.append({'week': week.week_number, 'squad': item['squad'],
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
    if session.schedule_id:
        _unplan(session, report)
        return
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


def _unplan(session, report):
    """A schedule date the plan no longer uses goes back to being an
    unplanned date of its schedule (answers kept)."""
    from app.models.playbook import Play
    from app.models.season_plan import SeasonWeek
    SeasonWeek.query.filter_by(session_plan_id=session.id).update({'session_plan_id': None})
    assoc = Play.play_session_component
    ids = [c.id for c in session.components]
    if ids:
        db.session.execute(assoc.delete().where(assoc.c.component_id.in_(ids)))
        for c in session.components:
            db.session.delete(c)
    report.removed.append(f'{session.title} (back to an unplanned {session.schedule.name} date)')
    session.external_id = None
    for key in PLAN_KEYS:
        setattr(session, key, None)
    session.title = session.schedule.name


def sync_week(plan, week):
    """Keep one week's sessions in step after the week is edited, once the
    plan's sessions have been built. Returns the report or None."""
    if not plan.sessions_built_at:
        return None
    return build_sessions(plan, weeks=[week])

