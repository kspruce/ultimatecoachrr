"""Session planner -> season plan: when a coach saves a session built from
the plan, its activities are written back into its week's session notes, so
the week, the export and the spreadsheet show what will actually happen.

- The joint session rewrites the week's joint table.
- A squad's session rewrites only that squad's column of the split table.
  Rows line up by start time, so squads can run to different timings (each
  squad's activity runs until its own next one). "Same" cells that would
  change meaning are written out first.
- The rest of the notes stay exactly as written (app/utils/session_outline.py).

Afterwards the week's sessions are brought in step with the session's
version kept (season_sessions.reconcile with choose='session'), so the plan
doesn't then report the coach's own change back as a conflict.

Deleting a built session can also take it out of its week
(remove_from_week), so building again doesn't bring it back.
"""
from app import db
from app.models.season_plan import SeasonPlan, SeasonWeek
from app.models.session import SessionComponent
from app.utils import session_outline as so
from app.utils.season_sessions import (
    SAME_RE, _clock, _fingerprint, _session_blocks, build_sessions, is_built_session, split_squads, squad_slug,
)

SOURCE_PREFIX = 'Source: '
JOINT_COLUMNS = [('time', 'Time'), ('activity', 'Activity'), ('how', 'How it runs'), ('source', 'Source')]


def _plan_week(session):
    if not is_built_session(session) or not session.season or not session.week_number:
        return None, None
    plan = SeasonPlan.query.filter_by(team_organization_id=session.team_organization_id,
                                      season=session.season).first()
    if plan is None:
        return None, None
    week = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=session.week_number).first()
    return plan, week


def _squad_of(plan, session):
    """'joint' or the plan squad this session is for, from its external id
    ('plan-2027/28-w05-1s')."""
    slug = session.external_id.rsplit('-w', 1)[-1].split('-', 1)[-1]
    if slug == 'joint':
        return 'joint'
    return next((q for q in split_squads(plan) if squad_slug(q) == slug), None)


def _source(block):
    notes = block.notes or ''
    return notes[len(SOURCE_PREFIX):].strip() or None if notes.startswith(SOURCE_PREFIX) else None


def _minutes(text):
    return _clock(text or '')


def _time_texts(table):
    """{minute: time as written} for the table's rows, or None when a row's
    time can't be read (the table is then left alone)."""
    out = {}
    for row in table.rows:
        m = _minutes(row.get('time'))
        if m is None:
            return None
        out.setdefault(m, row['time'])
    return out


def _schedule(blocks, base):
    """[(start minute, block)] laid end to end from `base`."""
    t, out = base, []
    for b in blocks:
        out.append((t, b))
        t += b.duration_minutes or 0
    return out


def _joint_table(outline):
    table = outline.joint
    if table is None:
        table = so.Table(kind='joint', columns=list(JOINT_COLUMNS), label='**Joint session**')
        outline.parts.append('')
        outline.parts.append(table)
    return table


def _write_joint(outline, blocks):
    table = _joint_table(outline)
    times = _time_texts(table) if table.rows else {}
    if times is None:
        return False
    base = min(times) if times else 0
    keys = [k for k, _ in table.columns]
    rows = []
    for t, b in _schedule(blocks, base):
        row = {k: None for k in keys}
        row['time'] = times.get(t) or so.clock(t)
        row['activity'] = b.title
        if 'how' in keys:
            row['how'] = b.description
        elif b.description:
            row['activity'] = f'{b.title}: {b.description}'
        if 'source' in keys:
            row['source'] = _source(b)
        rows.append(row)
    table.rows = rows
    return True


def _split_table(outline, plan, squad):
    table = outline.split
    if table is None:
        squads = split_squads(plan)
        table = so.Table(kind='split', label='**Split sessions**',
                         columns=[('time', 'Time')] + [(q, f'{q} group') for q in squads] + [('source', 'Source')])
        outline.parts.append('')
        outline.parts.append(table)
    if squad not in table.squads:
        at = next((i for i, (k, _) in enumerate(table.columns) if k == 'source'), len(table.columns))
        table.columns.insert(at, (squad, f'{squad} group'))
        for row in table.rows:
            row[squad] = None
    return table


def _spell_out_same(table, changing):
    """Write out "Same" cells that refer to the first squad's column, when
    that column is about to change."""
    first = table.squads[0] if table.squads else None
    if changing != first:
        return
    for row in table.rows:
        for q in table.squads[1:]:
            m = SAME_RE.match(row.get(q) or '')
            if m and row.get(first):
                rest = m.group(1).strip(' .,;:')
                row[q] = row[first] + (f', {rest}' if rest else '')


def _write_split(outline, plan, squad, blocks):
    table = _split_table(outline, plan, squad)
    times = _time_texts(table) if table.rows else {}
    if times is None:
        return False
    _spell_out_same(table, squad)
    base = min(times) if times else 0
    by_time = {}
    for row in table.rows:
        m = _minutes(row['time'])
        merged = by_time.setdefault(m, dict(row))
        for k, v in row.items():
            merged[k] = merged.get(k) or v
        merged[squad] = None
    for t, b in _schedule(blocks, base):
        row = by_time.setdefault(t, {k: None for k, _ in table.columns})
        row['time'] = times.get(t) or so.clock(t)
        row[squad] = f'{b.title}: {b.description}' if b.description else b.title
        if 'source' in row and not row.get('source'):
            row['source'] = _source(b)
    table.rows = [by_time[t] for t in sorted(by_time) if any(by_time[t].get(q) for q in table.squads)]
    return True


def write_back(session):
    """Write a built session's activities into its week's session notes.
    Returns a short message for the coach, or None when the session isn't
    from the plan or its activities haven't changed since the plan wrote
    them. The caller commits."""
    plan, week = _plan_week(session)
    if week is None:
        return None
    if (session.plan_snapshot or {}).get('blocks') == _fingerprint(_session_blocks(session)):
        return None  # the activities are as the plan wrote them
    squad = _squad_of(plan, session)
    if squad is None:
        return None
    outline = so.parse(week.session_detail_md or '', split_squads(plan))
    if outline.unsupported:
        return (f"Week {week.week_number}'s session notes have a table the planner can't update, "
                f'so they were left as they are. Edit them on the week.')
    blocks = session.components.order_by(SessionComponent.order, SessionComponent.id).all()
    ok = _write_joint(outline, blocks) if squad == 'joint' else _write_split(outline, plan, squad, blocks)
    if not ok:
        return (f"Week {week.week_number}'s session table has a time the planner can't read, "
                f'so the notes were left as they are. Edit them on the week.')
    week.session_detail_md = so.render(outline).strip('\n') or None
    db.session.flush()
    # Bring the week's sessions in step, keeping this session as it is
    build_sessions(plan, weeks=[week], commit=False, choose={session.external_id: 'session'})
    return f'week {week.week_number} of the season plan updated to match'


def remove_from_week(session):
    """Take a built session out of its week's notes: the joint table, or the
    squad's column of the split table. Returns a message, or None."""
    plan, week = _plan_week(session)
    if week is None or not week.session_detail_md:
        return None
    squad = _squad_of(plan, session)
    outline = so.parse(week.session_detail_md, split_squads(plan))
    if squad == 'joint' and outline.joint is not None:
        outline.parts.remove(outline.joint)
    elif squad and outline.split is not None and squad in outline.split.squads:
        table = outline.split
        _spell_out_same(table, squad)
        table.columns = [(k, h) for k, h in table.columns if k != squad]
        for row in table.rows:
            row.pop(squad, None)
        table.rows = [r for r in table.rows if any(r.get(q) for q in table.squads)]
        if not table.squads:
            outline.parts.remove(table)
    else:
        return None
    week.session_detail_md = so.render(outline).strip('\n') or None
    return f'Removed from week {week.week_number} of the season plan.'
