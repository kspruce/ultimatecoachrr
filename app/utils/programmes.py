"""Training programmes: versions, copies, scheduling, validation and the
numbers on the coach dashboard. Nothing here knows about any particular
club's programme; a programme is whatever its tracks, weeks, sessions and
tests say it is.

Versions: coaches edit a draft. Publishing freezes the draft and (by
default) moves players on the programme to it. Logs and test results keep
pointing at the rows they were recorded against, which are never edited
again, so a new version can't rewrite anyone's history. Progress on the
new version counts a log when its session `key` is still in the version.

Scheduling: a week starts at the programme's start date (calendar
programmes) or the player's own start date (relative programmes), plus the
track's offset, plus the week's place in the track, pushed back by any
pauses that began on or before it.
"""
from datetime import date, datetime, timedelta

from app import db
from app.models.programme import (
    LOG_FIELDS, PerformanceTest, Programme, ProgrammeEnrolment, ProgrammeExercise,
    ProgrammeMilestone, ProgrammeSession, ProgrammeTrack, ProgrammeVersion, ProgrammeWeek,
    new_key,
)
from app.utils.media_embed import is_web_url

# Columns copied from one version's rows to the next draft's
TRACK_FIELDS = ['position', 'name', 'description', 'colour', 'first_week_number', 'start_offset_weeks']
WEEK_FIELDS = ['position', 'title', 'kind', 'objective', 'supporting_skills', 'notes']
SESSION_FIELDS = ['position', 'title', 'session_type', 'custom_type', 'requirement', 'alternative_group',
                  'duration_minutes', 'focus', 'warmup', 'cooldown', 'coaching_cues', 'video_url',
                  'attachment_url', 'log_fields', 'custom_fields']
EXERCISE_FIELDS = ['position', 'block', 'name', 'sets', 'reps', 'distance_m', 'duration_seconds', 'rest',
                   'intensity', 'tempo', 'instructions', 'video_url']
TEST_FIELDS = ['position', 'name', 'description', 'measurement', 'unit', 'attempts', 'aggregation',
               'higher_is_better', 'min_value', 'max_value', 'instructions']
MILESTONE_FIELDS = ['position', 'name', 'kind', 'notes']

DEFAULT_LOG_FIELDS = ['duration_minutes', 'rpe']


# --------------------------------------------------------------------------
# Versions and copies
# --------------------------------------------------------------------------

def _clone(model, src, fields, keep_key, **extra):
    row = model(**{f: getattr(src, f) for f in fields}, **extra)
    row.key = src.key if keep_key else new_key()
    return row


def copy_content(src, dst, keep_keys):
    """Copy every track, week, session, exercise, test and milestone of
    version `src` into the empty version `dst` (which may belong to another
    club). keep_keys: True for a programme's next draft, False for a copy
    that should stand on its own."""
    team_id = dst.team_organization_id
    week_map = {}
    test_keys = {}
    for track in src.tracks:
        new_track = _clone(ProgrammeTrack, track, TRACK_FIELDS, keep_keys, team_organization_id=team_id)
        dst.tracks.append(new_track)
        for week in track.weeks:
            new_week = _clone(ProgrammeWeek, week, WEEK_FIELDS, keep_keys, team_organization_id=team_id)
            new_track.weeks.append(new_week)
            week_map[week.id] = new_week
            for session in week.sessions:
                new_session = _clone(ProgrammeSession, session, SESSION_FIELDS, keep_keys,
                                     team_organization_id=team_id)
                new_week.sessions.append(new_session)
                for ex in session.exercises:
                    new_session.exercises.append(
                        _clone(ProgrammeExercise, ex, EXERCISE_FIELDS, keep_keys, team_organization_id=team_id))
    for test in src.tests:
        new_test = _clone(PerformanceTest, test, TEST_FIELDS, keep_keys, team_organization_id=team_id)
        dst.tests.append(new_test)
        test_keys[test.key] = new_test.key
    for ms in src.milestones:
        new_ms = _clone(ProgrammeMilestone, ms, MILESTONE_FIELDS, keep_keys, team_organization_id=team_id)
        new_ms.test_keys = [test_keys[k] for k in (ms.test_keys or []) if k in test_keys] or None
        new_ms.week = week_map.get(ms.week_id)
        dst.milestones.append(new_ms)
    return dst


def start_draft(programme):
    """The programme's draft, creating one from the published version (or
    an empty one) if there isn't one yet."""
    draft = programme.draft
    if draft:
        return draft
    number = max((v.number for v in programme.versions), default=0) + 1
    draft = ProgrammeVersion(number=number, status='draft', team_organization_id=programme.team_organization_id)
    programme.versions.append(draft)
    if programme.published:
        copy_content(programme.published, draft, keep_keys=True)
    db.session.flush()
    return draft


def publish(programme, user, change_note=None, move_players=True):
    """Freeze the draft as the live version. Players on the programme move to
    it when move_players is set; otherwise they stay on the version they
    have until a coach moves them. Returns the published version."""
    draft = programme.draft
    if draft is None:
        raise ValueError('Nothing to publish: there is no draft.')
    previous = programme.published
    if previous:
        previous.status = 'superseded'
    draft.status = 'published'
    draft.published_at = datetime.utcnow()
    draft.published_by_id = user.id if user else None
    draft.change_note = change_note
    if move_players:
        for enrolment in programme.enrolments:
            if enrolment.status in ('active', 'paused'):
                enrolment.version = draft
    db.session.flush()
    return draft


def copy_programme(source, team_id, user, name=None, kind='programme', start_date=None, from_shared=False):
    """A new, independent programme in `team_id` with the content of
    `source` (its draft when copying your own programme, else its published
    version). Players, logs, results and coach notes are never copied."""
    if from_shared:
        content = source.published
    else:
        content = source.draft or source.published
    if content is None:
        raise ValueError('That programme has no content to copy yet.')
    copy = Programme(
        team_organization_id=team_id, name=name or f'{source.name} (copy)', description=source.description,
        kind=kind, schedule_mode=source.schedule_mode,
        start_date=start_date if start_date is not None else (None if from_shared else source.start_date),
        workload_enabled=source.workload_enabled, recovery_enabled=source.recovery_enabled,
        source_kind='template' if source.is_template or from_shared else 'copy',
        source_uid=source.uid, source_name=source.name, source_team=source.team.name if source.team else None,
        source_version=content.number,
        source_author=source.source_author or (source.team.name if source.team else None),
        created_by_id=user.id if user else None,
    )
    db.session.add(copy)
    draft = ProgrammeVersion(number=1, status='draft', team_organization_id=team_id)
    copy.versions.append(draft)
    copy_content(content, draft, keep_keys=False)
    db.session.flush()
    return copy


def renumber(rows):
    for i, row in enumerate(rows):
        row.position = i


def move(rows, row, delta):
    """Move `row` up (-1) or down (+1) within `rows` (sorted by position)."""
    rows = list(rows)
    i = rows.index(row)
    j = i + delta
    if 0 <= j < len(rows):
        rows[i], rows[j] = rows[j], rows[i]
    renumber(rows)


def duplicate_week(week):
    track = week.track
    copy = ProgrammeWeek(**{f: getattr(week, f) for f in WEEK_FIELDS}, team_organization_id=week.team_organization_id)
    copy.title = f'{week.title} (copy)' if week.title else None
    weeks = list(track.weeks)
    weeks.insert(weeks.index(week) + 1, copy)
    track.weeks = weeks
    for session in week.sessions:
        copy.sessions.append(duplicate_session_content(session))
    renumber(track.weeks)
    return copy


def duplicate_session_content(session):
    copy = ProgrammeSession(**{f: getattr(session, f) for f in SESSION_FIELDS},
                            team_organization_id=session.team_organization_id)
    for ex in session.exercises:
        copy.exercises.append(ProgrammeExercise(**{f: getattr(ex, f) for f in EXERCISE_FIELDS},
                                                team_organization_id=ex.team_organization_id))
    return copy


# --------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------

def _pause_list(pauses):
    out = []
    for p in pauses or []:
        try:
            start = date.fromisoformat(p['from'])
            weeks = int(p.get('weeks') or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if weeks > 0:
            out.append((start, weeks))
    return sorted(out)


def apply_pauses(day, *pause_lists):
    for start, weeks in sorted(p for pauses in pause_lists for p in _pause_list(pauses)):
        if day >= start:
            day += timedelta(weeks=weeks)
    return day


def anchor(programme, enrolment=None):
    if programme.schedule_mode == 'relative':
        if enrolment and enrolment.start_date:
            return enrolment.start_date
        return None
    return programme.start_date


def programme_week_index(track, week):
    """Weeks from the programme (or player) start to this week."""
    return track.start_offset_weeks + week.position


def week_start(programme, track, week, enrolment=None):
    start = anchor(programme, enrolment)
    if start is None:
        return None
    day = start + timedelta(weeks=programme_week_index(track, week))
    return apply_pauses(day, programme.pauses, enrolment.pauses if enrolment else None)


def current_week(programme, track, enrolment=None, today=None):
    """The track week that contains today, or None outside the track."""
    today = today or date.today()
    for week in track.weeks:
        start = week_start(programme, track, week, enrolment)
        if start and start <= today < start + timedelta(days=7):
            return week
    return None


def total_weeks(version):
    return max((t.start_offset_weeks + len(t.weeks) for t in version.tracks), default=0)


def end_date(programme, version, enrolment=None):
    last = None
    for track in version.tracks:
        if track.weeks:
            start = week_start(programme, track, track.weeks[-1], enrolment)
            if start and (last is None or start > last):
                last = start
    return last + timedelta(days=6) if last else None


def week_index_for(programme, version, day, enrolment=None):
    """The programme week (0-based, ignoring pauses) a date falls in; used as
    the default starting point for a player who joins late."""
    start = anchor(programme, enrolment)
    if start is None or day <= start:
        return 0
    return min((day - start).days // 7, max(total_weeks(version) - 1, 0))


# --------------------------------------------------------------------------
# Validation (before publishing)
# --------------------------------------------------------------------------

def validate(programme, version):
    """(errors, warnings). Errors block publishing; warnings don't."""
    errors, warnings = [], []
    if not (programme.name or '').strip():
        errors.append('The programme needs a name.')
    if not programme.is_template and programme.schedule_mode == 'calendar' and not programme.start_date:
        errors.append('Calendar programmes need a start date (or switch to "each player\'s own start").')
    if not version.tracks:
        errors.append('Add at least one track.')
    for track in version.tracks:
        label = f'Track "{track.name}"'
        if not track.weeks:
            errors.append(f'{label} has no weeks.')
        if track.start_offset_weeks < 0:
            errors.append(f'{label} can\'t start before the programme does.')
        for week in track.weeks:
            wl = f'{label}, week {week.number}'
            if not week.is_rest and not week.sessions:
                warnings.append(f'{wl} has no sessions (mark it as a rest week if that is intended).')
            groups = {}
            for s in week.sessions:
                sl = f'{wl}, "{s.title}"'
                if not (s.title or '').strip():
                    errors.append(f'{wl} has a session with no title.')
                if s.session_type == 'custom' and not (s.custom_type or '').strip():
                    warnings.append(f'{sl} is a custom session with no type name.')
                for url in (s.video_url, s.attachment_url):
                    if url and not is_web_url(url):
                        errors.append(f'{sl}: "{url}" isn\'t a web link (http:// or https://).')
                if s.requirement == 'alternative':
                    if not (s.alternative_group or '').strip():
                        errors.append(f'{sl} is an alternative but has no group.')
                    else:
                        groups.setdefault(s.alternative_group.strip().lower(), []).append(s)
                for ex in s.exercises:
                    if ex.video_url and not is_web_url(ex.video_url):
                        errors.append(f'{sl}, "{ex.name}": the video link isn\'t a web link.')
                    if ex.distance_m is not None and ex.distance_m < 0:
                        errors.append(f'{sl}, "{ex.name}": distance can\'t be negative.')
            for group, members in groups.items():
                if len(members) < 2:
                    warnings.append(f'{wl}: alternative group "{group}" has only one session.')
    names = set()
    for test in version.tests:
        tl = f'Test "{test.name}"'
        if test.name.lower() in names:
            errors.append(f'{tl} is listed twice.')
        names.add(test.name.lower())
        if not (test.unit or '').strip():
            errors.append(f'{tl} needs a unit.')
        if test.attempts < 1:
            errors.append(f'{tl} needs at least one attempt.')
        if test.min_value is not None and test.max_value is not None and test.min_value >= test.max_value:
            errors.append(f'{tl}: the lowest allowed value must be below the highest.')
    test_keys = {t.key for t in version.tests}
    week_ids = {w.id for t in version.tracks for w in t.weeks}
    for ms in version.milestones:
        if ms.is_test and not version.tests:
            errors.append(f'Milestone "{ms.name}" is a test milestone but the programme has no tests.')
        if ms.week_id is None:
            warnings.append(f'Milestone "{ms.name}" isn\'t in a week yet.')
        elif ms.week_id not in week_ids:
            errors.append(f'Milestone "{ms.name}" is in a week of another version.')
        if any(k not in test_keys for k in ms.test_keys or []):
            errors.append(f'Milestone "{ms.name}" lists a test that is no longer in the programme.')
    return errors, warnings


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

def parse_attempts(test, raw_values):
    """([floats], error). Blank attempts are left out; at least one needed."""
    values = []
    for raw in raw_values:
        raw = (raw or '').strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            return None, f'"{raw}" isn\'t a number.'
        if value != value or value in (float('inf'), float('-inf')):
            return None, f'"{raw}" isn\'t a number.'
        if test.min_value is not None and value < test.min_value:
            return None, f'{value:g} is below the lowest allowed ({test.min_value:g} {test.unit}).'
        if test.max_value is not None and value > test.max_value:
            return None, f'{value:g} is above the highest allowed ({test.max_value:g} {test.unit}).'
        if value < 0 and test.measurement in ('time', 'distance', 'count'):
            return None, f'{value:g} can\'t be negative.'
        values.append(value)
    if not values:
        return None, 'Enter at least one attempt.'
    if len(values) > test.attempts:
        return None, f'This test allows {test.attempts} attempt(s).'
    return values, None


def aggregate(test, values):
    if test.aggregation == 'mean':
        return sum(values) / len(values)
    if test.aggregation == 'last':
        return values[-1]
    return max(values) if test.higher_is_better else min(values)


def improvement(test_higher_is_better, before, after):
    """Positive when `after` is better than `before`."""
    if before is None or after is None:
        return None
    return (after - before) if test_higher_is_better else (before - after)


# --------------------------------------------------------------------------
# Progress and the dashboard
# --------------------------------------------------------------------------

def session_units(version):
    """[(track, week, unit, [sessions], requirement)] for every non-rest week,
    in order. A unit is one session, or one alternative group."""
    out = []
    for track in version.tracks:
        for week in track.weeks:
            if week.is_rest:
                continue
            seen = {}
            for s in week.sessions:
                unit = s.completion_unit
                if unit in seen:
                    seen[unit][3].append(s)
                    continue
                req = 'optional' if s.requirement == 'optional' else 'required'
                seen[unit] = [track, week, unit, [s], req]
                out.append(seen[unit])
    return [tuple(u) for u in out]


def enrolment_progress(enrolment, today=None):
    """Where one player stands. Missing (nothing logged after the week
    ended) and skipped (a player said so) are counted apart, and a number
    that can't be worked out yet is None rather than 0."""
    today = today or date.today()
    programme, version = enrolment.programme, enrolment.version
    logs = {log.session_key: log for log in enrolment.logs}
    p = {'due': 0, 'done': 0, 'skipped': 0, 'missing': [], 'optional_done': 0, 'units': {}, 'tracks': []}
    for track, week, unit, sessions, req in session_units(version):
        start = week_start(programme, track, week, enrolment)
        expected = programme_week_index(track, week) >= enrolment.start_offset_weeks
        unit_logs = [logs[s.key] for s in sessions if s.key in logs]
        done = any(lg.status in ('completed', 'partial') for lg in unit_logs)
        skipped = not done and any(lg.status == 'skipped' for lg in unit_logs)
        due = expected and start is not None and start + timedelta(days=7) <= today
        if not expected:
            status = 'not_expected'
        elif done:
            status = 'done'
        elif skipped:
            status = 'skipped'
        elif due:
            status = 'missing' if req == 'required' else 'optional'
        elif start is not None and start <= today:
            status = 'this_week'
        else:
            status = 'upcoming'
        p['units'][unit] = status
        if req == 'optional':
            p['optional_done'] += done
            continue
        if due:
            p['due'] += 1
            p['done'] += done
            p['skipped'] += skipped
            if status == 'missing':
                p['missing'].append((track, week, sessions))
    p['completion'] = round(100 * p['done'] / p['due']) if p['due'] else None
    for track in version.tracks:
        week = current_week(programme, track, enrolment, today)
        p['tracks'].append({'track': track, 'week': week, 'of': len(track.weeks)})
    dated = [lg for lg in enrolment.logs if lg.completed_on]
    p['last_logged'] = max((lg.completed_on for lg in dated), default=None)
    p['workload_7'] = _sum_or_none(lg.workload for lg in dated if today - timedelta(days=7) < lg.completed_on <= today)
    p['workload_28'] = _sum_or_none(lg.workload for lg in dated if today - timedelta(days=28) < lg.completed_on <= today)
    recent = [lg for lg in dated if today - timedelta(days=14) < lg.completed_on <= today]
    p['soreness'] = _mean_or_none(lg.soreness for lg in recent)
    p['sleep'] = _mean_or_none(lg.sleep_hours for lg in recent)
    p['rpe'] = _mean_or_none(lg.rpe for lg in recent)
    p['tests'] = test_summary(enrolment)
    p['missing_tests'] = missing_tests(enrolment, today)
    current_keys = {s.key for t in version.tracks for w in t.weeks for s in w.sessions}
    p['old_version_logs'] = [lg for lg in enrolment.logs if lg.session_key not in current_keys]
    return p


def this_week(programme, version, enrolment=None, progress=None, today=None):
    """What's on now, for the top of the player page: each track's week that
    contains today and the session to do next.

    When no week contains today (before the start, or a pause) it is the next
    weeks to start, with `starts` set; after the end `finished` is set and
    there are no weeks. A relative programme with no start date yet shows each
    track's first week."""
    today = today or date.today()
    out = {'weeks': [], 'next': None, 'starts': None, 'finished': False, 'required': 0, 'done': 0}
    if anchor(programme, enrolment) is None:
        out['weeks'] = [(t, t.weeks[0], None) for t in version.tracks if t.weeks]
    else:
        dated = [(t, w, week_start(programme, t, w, enrolment)) for t in version.tracks for w in t.weeks]
        out['weeks'] = [(t, w, s) for t, w, s in dated if s <= today < s + timedelta(days=7)]
        if not out['weeks']:
            future = [s for _, _, s in dated if s > today]
            if future:
                out['starts'] = min(future)
                out['weeks'] = [(t, w, s) for t, w, s in dated if s == out['starts']]
            else:
                out['finished'] = bool(dated)
    units = progress['units'] if progress else {}
    seen = set()
    candidates = []
    for _, week, _ in out['weeks']:
        if week.is_rest:
            continue
        for s in week.sessions:
            status = units.get(s.completion_unit)
            if s.completion_unit not in seen and s.requirement != 'optional':
                seen.add(s.completion_unit)
                out['required'] += 1
                out['done'] += status in ('done', 'skipped')
            if status not in ('done', 'skipped', 'not_expected'):
                candidates.append(s)
    out['next'] = next((s for s in candidates if s.requirement != 'optional'), None) or \
        next(iter(candidates), None)
    first = out['weeks'][0][2] if out['weeks'] else None
    out['week_of'] = (first, first + timedelta(days=6)) if first else None
    return out


def players_week(player, today=None):
    """[(enrolment, this_week)] for a player's live programmes, for the
    homepage card."""
    if player is None:
        return []
    enrolments = (ProgrammeEnrolment.query.join(Programme)
                  .filter(ProgrammeEnrolment.player_id == player.id,
                          ProgrammeEnrolment.team_organization_id == player.team_organization_id,
                          ProgrammeEnrolment.status == 'active', Programme.archived.is_(False))
                  .all())
    out = []
    for e in enrolments:
        now = this_week(e.programme, e.version, e, enrolment_progress(e, today), today)
        if not now['finished']:
            out.append((e, now))
    return out


def _sum_or_none(values):
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def _mean_or_none(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def test_summary(enrolment):
    """{test key: {test, first, latest, change}} for the tests on the
    player's version. `first` is the baseline result when there is one."""
    out = {}
    by_key = {}
    for r in sorted(enrolment.results, key=lambda r: (r.recorded_on, r.id)):
        by_key.setdefault(r.test_key, []).append(r)
    for test in enrolment.version.tests:
        results = by_key.get(test.key, [])
        baseline = next((r for r in results if r.milestone and r.milestone.kind == 'baseline'), None)
        first = baseline or (results[0] if results else None)
        latest = results[-1] if results else None
        if latest is first:
            latest = None
        out[test.key] = {
            'test': test, 'results': results, 'first': first, 'latest': latest,
            'change': improvement(test.higher_is_better, first.value if first else None,
                                  latest.value if latest else None),
        }
    return out


def missing_tests(enrolment, today=None):
    """[(milestone, test)] test milestones whose week has ended with no result."""
    today = today or date.today()
    programme = enrolment.programme
    have = {(r.milestone_key, r.test_key) for r in enrolment.results}
    out = []
    for ms in enrolment.version.milestones:
        if not ms.is_test or ms.week is None:
            continue
        track = ms.week.track
        if programme_week_index(track, ms.week) < enrolment.start_offset_weeks:
            continue
        start = week_start(programme, track, ms.week, enrolment)
        if start is None or start + timedelta(days=7) > today:
            continue
        for test in enrolment.version.tests:
            if ms.covers(test) and (ms.key, test.key) not in have:
                out.append((ms, test))
    return out


def follow_up_reasons(progress, today=None):
    today = today or date.today()
    reasons = []
    if len(progress['missing']) >= 2:
        reasons.append(f"{len(progress['missing'])} required sessions not logged")
    if progress['completion'] is not None and progress['completion'] < 50:
        reasons.append(f"completion {progress['completion']}%")
    if progress['due'] and (progress['last_logged'] is None or (today - progress['last_logged']).days > 14):
        reasons.append('nothing logged in two weeks')
    if progress['missing_tests']:
        reasons.append(f"{len(progress['missing_tests'])} test result(s) missing")
    return reasons


def dashboard(programme, today=None):
    """Everything the coach dashboard shows, worked out from the programme's
    own sessions and tests."""
    today = today or date.today()
    version = programme.published
    rows = []
    for enrolment in sorted(programme.enrolments, key=lambda e: e.player.name.lower()):
        if enrolment.status == 'withdrawn':
            continue
        progress = enrolment_progress(enrolment, today)
        rows.append({'enrolment': enrolment, 'p': progress, 'follow_up': follow_up_reasons(progress, today)})
    due = sum(r['p']['due'] for r in rows)
    done = sum(r['p']['done'] for r in rows)
    has_rpe = any(r['p']['workload_28'] is not None for r in rows)
    tests = []
    if version:
        for test in version.tests:
            changes = [r['p']['tests'].get(test.key, {}).get('change') for r in rows]
            changes = [c for c in changes if c is not None]
            tested = sum(1 for r in rows if r['p']['tests'].get(test.key, {}).get('results'))
            tests.append({
                'test': test, 'tested': tested, 'compared': len(changes),
                'improved': sum(1 for c in changes if c > 0),
                'mean_change': round(sum(changes) / len(changes), 3) if changes else None,
            })
    tracks = []
    if version:
        for track in version.tracks:
            week = current_week(programme, track, today=today) if programme.schedule_mode == 'calendar' else None
            tracks.append({'track': track, 'week': week})
    return {
        'version': version, 'rows': rows, 'tracks': tracks, 'tests': tests,
        'enrolled': len(rows), 'active': sum(1 for r in rows if r['enrolment'].status == 'active'),
        'due': due, 'done': done, 'completion': round(100 * done / due) if due else None,
        'missing': sum(len(r['p']['missing']) for r in rows),
        'skipped': sum(r['p']['skipped'] for r in rows),
        'missing_tests': sum(len(r['p']['missing_tests']) for r in rows),
        'follow_up': [r for r in rows if r['follow_up']],
        'show_workload': programme.workload_enabled and has_rpe,
        'show_recovery': programme.recovery_enabled,
        'end_date': end_date(programme, version) if version else None,
    }


def log_field_choices():
    return LOG_FIELDS


def enrol(programme, player, start_date=None, start_offset_weeks=None, today=None):
    """Put a player on the programme's published version. A player joining a
    calendar programme after it started begins at the current week unless
    the coach says otherwise."""
    version = programme.published
    if version is None:
        raise ValueError('Publish the programme before adding players.')
    existing = ProgrammeEnrolment.query.filter_by(programme_id=programme.id, player_id=player.id).first()
    if existing:
        if existing.status == 'withdrawn':
            existing.status = 'active'
        return existing, False
    today = today or date.today()
    enrolment = ProgrammeEnrolment(programme=programme, version=version, player_id=player.id,
                                   team_organization_id=programme.team_organization_id,
                                   start_date=start_date or (today if programme.schedule_mode == 'relative' else None))
    if start_offset_weeks is None:
        start_offset_weeks = (week_index_for(programme, version, today)
                              if programme.schedule_mode == 'calendar' else 0)
    enrolment.start_offset_weeks = max(0, start_offset_weeks)
    db.session.add(enrolment)
    return enrolment, True
