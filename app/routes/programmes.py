"""Training programmes (Training > Programmes): any club builds, publishes
and runs its own programmes here, with no code changes.

Who can do what (checked on the server for every request):
- Coaches, captains and admins of a club build its programmes, add its
  players, see its dashboard and record logs and test results for its
  players.
- Players see the published programmes they are on, and log their own
  sessions and test results. Nothing else.
- Another club can see a programme only when its owner shares it as a
  template, and then only the published content: never its players, logs,
  results or coach notes. Copying it makes an independent programme.

Every lookup goes through _programme() or _row(), which only find rows of
the current club; anything else is a 404. Content can only be edited in a
draft; published versions are frozen (see app/utils/programmes.py).
"""
import csv
import io
from datetime import date, timedelta

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.player import Player
from app.models.programme import (
    AGGREGATIONS, LOG_FIELDS, MEASUREMENTS, REQUIREMENTS, SESSION_TYPES, WEEK_KINDS,
    PerformanceTest, Programme, ProgrammeEnrolment, ProgrammeExercise, ProgrammeMilestone, ProgrammeSession,
    ProgrammeTrack, ProgrammeWeek, SessionLog, TestResult,
)
from app.utils import programme_import as pimport
from app.utils import programmes as svc
from app.utils.media_embed import is_web_url
from app.utils.team_filter import get_current_team_id
from app.utils.utils import coach_required

bp = Blueprint('programmes', __name__, url_prefix='/programmes')

TEXT_LIMIT = 20000


@bp.before_request
@login_required
def _signed_in():
    return None


@bp.app_context_processor
def programme_nav():
    def has_programmes():
        if not current_user.is_authenticated:
            return False
        if current_user.is_coach:
            return True
        return bool(_my_enrolments())
    return {'programmes_nav': has_programmes, 'today_date': date.today()}


# --------------------------------------------------------------------------
# Lookups: only ever the current club's rows
# --------------------------------------------------------------------------

def _team():
    team_id = get_current_team_id()
    if not team_id:
        abort(404)
    return team_id


def _programme(programme_id):
    return Programme.query.filter_by(id=programme_id, team_organization_id=_team()).first_or_404()


def _version_of(row):
    if isinstance(row, ProgrammeTrack):
        return row.version
    if isinstance(row, ProgrammeWeek):
        return row.track.version
    if isinstance(row, ProgrammeSession):
        return row.week.track.version
    if isinstance(row, (PerformanceTest, ProgrammeMilestone)):
        return row.version
    raise TypeError(row)


def _row(model, row_id, programme, draft_only=True):
    """A content row of this programme (its draft, unless draft_only is off)."""
    row = model.query.filter_by(id=row_id, team_organization_id=programme.team_organization_id).first_or_404()
    version = _version_of(row)
    if version.programme_id != programme.id or (draft_only and not version.is_draft):
        abort(404)
    return row


def _player():
    return getattr(current_user, 'player', None)


def _my_enrolments():
    player = _player()
    if player is None or player.team_organization_id != get_current_team_id():
        return []
    return (ProgrammeEnrolment.query.join(Programme)
            .filter(ProgrammeEnrolment.player_id == player.id,
                    ProgrammeEnrolment.team_organization_id == player.team_organization_id,
                    ProgrammeEnrolment.status != 'withdrawn', Programme.archived.is_(False))
            .all())


def _coach_enrolment(programme, enrolment_id):
    if enrolment_id is None:
        abort(400)
    return _enrolment(programme, enrolment_id)


def _enrolment(programme, enrolment_id=None):
    """The enrolment a request is about: a coach may name any of the club's;
    a player only ever gets their own."""
    if enrolment_id is not None:
        if not current_user.is_coach:
            abort(404)
        return ProgrammeEnrolment.query.filter_by(id=enrolment_id, programme_id=programme.id,
                                                  team_organization_id=programme.team_organization_id).first_or_404()
    player = _player()
    if player is None:
        abort(404)
    return ProgrammeEnrolment.query.filter_by(programme_id=programme.id, player_id=player.id,
                                              team_organization_id=programme.team_organization_id).first_or_404()


# --------------------------------------------------------------------------
# Form helpers
# --------------------------------------------------------------------------

def _text(name, limit=TEXT_LIMIT):
    value = (request.form.get(name) or '').strip()
    return value[:limit] or None


def _int(name, default=None, minimum=None, maximum=None):
    raw = (request.form.get(name) or '').strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f'"{raw}" isn\'t a whole number.')
    if minimum is not None and value < minimum:
        raise ValueError(f'{value} is below {minimum}.')
    if maximum is not None and value > maximum:
        raise ValueError(f'{value} is above {maximum}.')
    return value


def _float(name, raw=None, minimum=None):
    raw = (raw if raw is not None else request.form.get(name) or '').strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f'"{raw}" isn\'t a number.')
    if value != value or (minimum is not None and value < minimum):
        raise ValueError(f'{raw} is out of range.')
    return value


def _date(name):
    raw = (request.form.get(name) or '').strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValueError(f'"{raw}" isn\'t a date.')


def _url(name):
    value = _text(name, 500)
    if value and not is_web_url(value):
        raise ValueError(f'"{value}" isn\'t a web link (http:// or https://).')
    return value


def _choice(name, choices, default):
    value = request.form.get(name) or default
    return value if value in {k for k, _ in choices} else default


def _back(programme, anchor=None):
    return redirect(url_for('programmes.build', programme_id=programme.id) + (f'#{anchor}' if anchor else ''))


def _draft_or_redirect(programme):
    draft = programme.draft
    if draft is None:
        flash('Start a new draft to make changes; the published version stays as it is.', 'info')
    return draft


# --------------------------------------------------------------------------
# Lists, creating, settings
# --------------------------------------------------------------------------

@bp.route('/')
def index():
    team_id = _team()
    enrolments = _my_enrolments()
    if not current_user.is_coach:
        if len(enrolments) == 1:
            return redirect(url_for('programmes.me', programme_id=enrolments[0].programme_id))
        return render_template('programmes/index.html', programmes=[], templates=[], shared=[],
                               enrolments=enrolments, archived=[])
    rows = Programme.query.filter_by(team_organization_id=team_id).order_by(Programme.created_at.desc()).all()
    shared = (Programme.query.filter(Programme.is_shared.is_(True), Programme.team_organization_id != team_id)
              .order_by(Programme.name).all())
    return render_template(
        'programmes/index.html',
        programmes=[p for p in rows if not p.is_template and not p.archived],
        templates=[p for p in rows if p.is_template and not p.archived],
        archived=[p for p in rows if p.archived],
        shared=[p for p in shared if p.published], enrolments=enrolments)


@bp.route('/new', methods=['GET', 'POST'])
@coach_required
def new():
    team_id = _team()
    if request.method == 'POST':
        try:
            name = _text('name', 200)
            if not name:
                raise ValueError('Give the programme a name.')
            programme = Programme(
                team_organization_id=team_id, name=name, description=_text('description'),
                kind=_choice('kind', [('programme', ''), ('template', '')], 'programme'),
                schedule_mode=_choice('schedule_mode', [('calendar', ''), ('relative', '')], 'calendar'),
                start_date=_date('start_date'), created_by_id=current_user.id)
        except ValueError as e:
            flash(str(e), 'danger')
            return render_template('programmes/new.html', form=request.form), 400
        db.session.add(programme)
        draft = svc.start_draft(programme)
        weeks = min(max(_safe_int(request.form.get('weeks'), 0), 0), 104)
        track_name = _text('track_name', 100)
        if track_name:
            track = ProgrammeTrack(name=track_name, team_organization_id=team_id)
            draft.tracks.append(track)
            for i in range(weeks):
                track.weeks.append(ProgrammeWeek(position=i, team_organization_id=team_id))
        db.session.commit()
        flash('Programme created. Add tracks, weeks and sessions, then publish it.', 'success')
        return redirect(url_for('programmes.build', programme_id=programme.id))
    return render_template('programmes/new.html', form={})


def _safe_int(raw, default):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


@bp.route('/<int:programme_id>')
def show(programme_id):
    programme = _programme(programme_id)
    if not current_user.is_coach:
        return redirect(url_for('programmes.me', programme_id=programme.id))
    version = programme.published or programme.draft
    return render_template('programmes/show.html', programme=programme, version=version,
                           end=svc.end_date(programme, version) if version else None,
                           total_weeks=svc.total_weeks(version) if version else 0)


@bp.route('/<int:programme_id>/settings', methods=['GET', 'POST'])
@coach_required
def settings(programme_id):
    programme = _programme(programme_id)
    if request.method == 'POST':
        try:
            name = _text('name', 200)
            if not name:
                raise ValueError('The programme needs a name.')
            pauses = []
            for start, weeks, note in zip(request.form.getlist('pause_from'), request.form.getlist('pause_weeks'),
                                          request.form.getlist('pause_note')):
                if not start.strip() and not weeks.strip():
                    continue
                try:
                    start_day = date.fromisoformat(start.strip())
                    weeks = int(weeks)
                except ValueError:
                    raise ValueError('Each pause needs a start date and a whole number of weeks.')
                if not 1 <= weeks <= 52:
                    raise ValueError('A pause is between 1 and 52 weeks.')
                pauses.append({'from': start_day.isoformat(), 'weeks': weeks, 'note': note.strip()[:200]})
            programme.name = name
            programme.description = _text('description')
            programme.coach_notes = _text('coach_notes')
            programme.schedule_mode = _choice('schedule_mode', [('calendar', ''), ('relative', '')], 'calendar')
            programme.start_date = _date('start_date')
            programme.pauses = pauses or None
            programme.workload_enabled = bool(request.form.get('workload_enabled'))
            programme.recovery_enabled = bool(request.form.get('recovery_enabled'))
            share = bool(request.form.get('is_shared'))
            if share and not programme.published:
                raise ValueError('Publish the programme before sharing it as a template.')
            programme.is_shared = share
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return render_template('programmes/settings.html', programme=programme), 400
        db.session.commit()
        flash('Settings saved.', 'success')
        return redirect(url_for('programmes.show', programme_id=programme.id))
    return render_template('programmes/settings.html', programme=programme)


@bp.route('/<int:programme_id>/duplicate', methods=['POST'])
@coach_required
def duplicate(programme_id):
    programme = _programme(programme_id)
    kind = _choice('kind', [('programme', ''), ('template', '')], programme.kind)
    try:
        copy = svc.copy_programme(programme, programme.team_organization_id, current_user,
                                  name=_text('name', 200) or f'{programme.name} (copy)', kind=kind,
                                  start_date=_date('start_date'))
    except ValueError as e:
        flash(str(e), 'danger')
        return redirect(url_for('programmes.show', programme_id=programme.id))
    db.session.commit()
    flash('Copied. The copy is a draft of its own: changing it leaves the original alone.', 'success')
    return redirect(url_for('programmes.build', programme_id=copy.id))


@bp.route('/<int:programme_id>/archive', methods=['POST'])
@coach_required
def archive(programme_id):
    programme = _programme(programme_id)
    programme.archived = not programme.archived
    if programme.archived:
        programme.is_shared = False
    db.session.commit()
    flash('Archived.' if programme.archived else 'Restored.', 'success')
    return redirect(url_for('programmes.show', programme_id=programme.id))


@bp.route('/<int:programme_id>/delete', methods=['POST'])
@coach_required
def delete(programme_id):
    programme = _programme(programme_id)
    if any(e.logs or e.results for e in programme.enrolments):
        flash('Players have logged sessions or results on this programme, so it can only be archived.', 'warning')
        return redirect(url_for('programmes.show', programme_id=programme.id))
    db.session.delete(programme)
    db.session.commit()
    flash('Programme deleted.', 'success')
    return redirect(url_for('programmes.index'))


# --------------------------------------------------------------------------
# Shared templates (other clubs' published content only)
# --------------------------------------------------------------------------

def _shared(programme_id):
    programme = Programme.query.filter_by(id=programme_id, is_shared=True, archived=False).first_or_404()
    if programme.published is None:
        abort(404)
    return programme


@bp.route('/shared/<int:programme_id>')
@coach_required
def shared(programme_id):
    programme = _shared(programme_id)
    return render_template('programmes/player_view.html', programme=programme, version=programme.published,
                           enrolment=None, progress=None, shared_view=True, preview=False,
                           weeks=_player_weeks(programme, programme.published, None, None))


@bp.route('/shared/<int:programme_id>/copy', methods=['POST'])
@coach_required
def copy_shared(programme_id):
    source = _shared(programme_id)
    copy = svc.copy_programme(source, _team(), current_user, name=_text('name', 200) or source.name,
                              kind=_choice('kind', [('programme', ''), ('template', '')], 'programme'),
                              start_date=_date_or_none('start_date'), from_shared=True)
    db.session.commit()
    flash(f'Copied "{source.name}" into your club. Edit it as you like; the original is unaffected.', 'success')
    return redirect(url_for('programmes.build', programme_id=copy.id))


def _date_or_none(name):
    try:
        return _date(name)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Builder: drafts, tracks, weeks, sessions, exercises
# --------------------------------------------------------------------------

@bp.route('/<int:programme_id>/build')
@coach_required
def build(programme_id):
    programme = _programme(programme_id)
    version = programme.draft or programme.published
    errors, warnings = svc.validate(programme, version) if version else ([], [])
    return render_template('programmes/build.html', programme=programme, version=version,
                           errors=errors, warnings=warnings, week_kinds=WEEK_KINDS)


@bp.route('/<int:programme_id>/draft', methods=['POST'])
@coach_required
def start_draft(programme_id):
    programme = _programme(programme_id)
    svc.start_draft(programme)
    db.session.commit()
    return _back(programme)


@bp.route('/<int:programme_id>/draft/discard', methods=['POST'])
@coach_required
def discard_draft(programme_id):
    programme = _programme(programme_id)
    draft = programme.draft
    if draft is None:
        abort(404)
    if programme.published is None:
        flash('This is the only version; delete the programme instead.', 'warning')
        return _back(programme)
    db.session.delete(draft)
    db.session.commit()
    flash('Draft discarded.', 'success')
    return redirect(url_for('programmes.show', programme_id=programme.id))


@bp.route('/<int:programme_id>/tracks/add', methods=['POST'])
@coach_required
def add_track(programme_id):
    programme = _programme(programme_id)
    draft = _draft_or_redirect(programme)
    if draft is None:
        return _back(programme)
    try:
        weeks = _int('weeks', 0, 0, 104)
        first = _int('first_week_number', 1, 0, 100)
        offset = _int('start_offset_weeks', 0, 0, 104)
    except ValueError as e:
        flash(str(e), 'danger')
        return _back(programme)
    track = ProgrammeTrack(name=_text('name', 100) or f'Track {len(draft.tracks) + 1}', position=len(draft.tracks),
                           first_week_number=first, start_offset_weeks=offset,
                           team_organization_id=programme.team_organization_id)
    draft.tracks.append(track)
    for i in range(weeks):
        track.weeks.append(ProgrammeWeek(position=i, team_organization_id=programme.team_organization_id))
    db.session.commit()
    return _back(programme, f'track-{track.id}')


@bp.route('/<int:programme_id>/tracks/<int:track_id>', methods=['GET', 'POST'])
@coach_required
def edit_track(programme_id, track_id):
    programme = _programme(programme_id)
    track = _row(ProgrammeTrack, track_id, programme)
    if request.method == 'POST':
        try:
            track.name = _text('name', 100) or track.name
            track.description = _text('description')
            colour = _text('colour', 7)
            track.colour = colour if colour and len(colour) == 7 and colour.startswith('#') else None
            track.first_week_number = _int('first_week_number', 1, 0, 100)
            track.start_offset_weeks = _int('start_offset_weeks', 0, 0, 104)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return render_template('programmes/edit_track.html', programme=programme, track=track), 400
        db.session.commit()
        flash('Track saved.', 'success')
        return _back(programme, f'track-{track.id}')
    return render_template('programmes/edit_track.html', programme=programme, track=track)


@bp.route('/<int:programme_id>/tracks/<int:track_id>/<action>', methods=['POST'])
@coach_required
def track_action(programme_id, track_id, action):
    programme = _programme(programme_id)
    track = _row(ProgrammeTrack, track_id, programme)
    version = track.version
    if action == 'delete':
        week_ids = {w.id for w in track.weeks}
        for ms in version.milestones:
            if ms.week_id in week_ids:
                ms.week = None
        version.tracks.remove(track)
        svc.renumber(version.tracks)
    elif action in ('up', 'down'):
        svc.move(version.tracks, track, -1 if action == 'up' else 1)
    elif action == 'add-week':
        track.weeks.append(ProgrammeWeek(position=len(track.weeks), team_organization_id=track.team_organization_id))
    else:
        abort(404)
    db.session.commit()
    return _back(programme, f'track-{track.id}' if action != 'delete' else None)


@bp.route('/<int:programme_id>/weeks/<int:week_id>', methods=['GET', 'POST'])
@coach_required
def edit_week(programme_id, week_id):
    programme = _programme(programme_id)
    week = _row(ProgrammeWeek, week_id, programme)
    if request.method == 'POST':
        week.title = _text('title', 200)
        week.kind = _choice('kind', WEEK_KINDS, 'training')
        week.objective = _text('objective')
        week.supporting_skills = _text('supporting_skills')
        week.notes = _text('notes')
        db.session.commit()
        flash('Week saved.', 'success')
        return redirect(url_for('programmes.edit_week', programme_id=programme.id, week_id=week.id))
    return render_template('programmes/edit_week.html', programme=programme, week=week, week_kinds=WEEK_KINDS,
                           session_types=SESSION_TYPES)


@bp.route('/<int:programme_id>/weeks/<int:week_id>/<action>', methods=['POST'])
@coach_required
def week_action(programme_id, week_id, action):
    programme = _programme(programme_id)
    week = _row(ProgrammeWeek, week_id, programme)
    track = week.track
    if action == 'delete':
        for ms in track.version.milestones:
            if ms.week_id == week.id:
                ms.week = None
        track.weeks.remove(week)
        svc.renumber(track.weeks)
    elif action in ('up', 'down'):
        svc.move(track.weeks, week, -1 if action == 'up' else 1)
    elif action == 'duplicate':
        svc.duplicate_week(week)
    elif action == 'add-session':
        title = _text('title', 200) or 'New session'
        session = ProgrammeSession(title=title, position=len(week.sessions),
                                   session_type=_choice('session_type', SESSION_TYPES, 'custom'),
                                   log_fields=list(svc.DEFAULT_LOG_FIELDS),
                                   team_organization_id=week.team_organization_id)
        week.sessions.append(session)
        db.session.commit()
        return redirect(url_for('programmes.edit_session', programme_id=programme.id, session_id=session.id))
    else:
        abort(404)
    db.session.commit()
    if request.form.get('next') == 'week' and action != 'delete':
        return redirect(url_for('programmes.edit_week', programme_id=programme.id, week_id=week.id))
    return _back(programme, f'track-{track.id}')


EXERCISE_TEXT = [('block', 20), ('sets', 30), ('reps', 50), ('rest', 100), ('intensity', 100), ('tempo', 30)]


def _save_exercises(session):
    """The exercise table on the session page: every row at once, plus the
    blank row for a new exercise. Rows ticked for removal are dropped."""
    ids = request.form.getlist('ex_id')
    forms = {k: request.form.getlist(f'ex_{k}') for k in
             ('name', 'block', 'sets', 'reps', 'distance_m', 'duration_seconds', 'rest', 'intensity', 'tempo',
              'instructions', 'video_url', 'order')}
    remove = set(request.form.getlist('ex_remove'))
    existing = {str(ex.id): ex for ex in session.exercises}
    keep = []
    for i, ex_id in enumerate(ids):
        def cell(key, limit=None):
            values = forms[key]
            value = (values[i] if i < len(values) else '').strip()
            return (value[:limit] if limit else value) or None
        name = cell('name', 200)
        ex = existing.get(ex_id)
        if ex_id in remove or (ex is None and not name):
            continue
        if not name:
            raise ValueError('Every exercise needs a name (tick "remove" to delete one).')
        if ex is None:
            ex = ProgrammeExercise(team_organization_id=session.team_organization_id)
            session.exercises.append(ex)
        ex.name = name
        for key, limit in EXERCISE_TEXT:
            setattr(ex, key, cell(key, limit))
        ex.instructions = cell('instructions', TEXT_LIMIT)
        ex.distance_m = _float(None, cell('distance_m') or '', minimum=0)
        seconds = cell('duration_seconds')
        try:
            ex.duration_seconds = int(seconds) if seconds else None
        except ValueError:
            raise ValueError(f'Duration "{seconds}" must be a whole number of seconds.')
        video = cell('video_url', 500)
        if video and not is_web_url(video):
            raise ValueError(f'"{video}" isn\'t a web link.')
        ex.video_url = video
        keep.append((_safe_int(cell('order'), 10_000 + i), i, ex))
    for ex in list(session.exercises):
        if ex not in [k[2] for k in keep]:
            session.exercises.remove(ex)
    ordered = [k[2] for k in sorted(keep, key=lambda k: (k[0], k[1]))]
    session.exercises = ordered
    svc.renumber(session.exercises)


def _custom_fields(raw):
    """'Throws on target, Max distance (m)' -> [{key, label, unit}]"""
    fields = []
    for part in (raw or '').split(','):
        part = part.strip()[:60]
        if not part:
            continue
        unit = ''
        if part.endswith(')') and '(' in part:
            part, unit = part[:-1].split('(', 1)
            part, unit = part.strip(), unit.strip()
        key = ''.join(ch if ch.isalnum() else '_' for ch in part.lower()).strip('_')[:40] or f'field_{len(fields)}'
        if key in {f['key'] for f in fields}:
            continue
        fields.append({'key': key, 'label': part, 'unit': unit})
    return fields or None


@bp.route('/<int:programme_id>/sessions/<int:session_id>', methods=['GET', 'POST'])
@coach_required
def edit_session(programme_id, session_id):
    programme = _programme(programme_id)
    session = _row(ProgrammeSession, session_id, programme)
    if request.method == 'POST':
        try:
            session.title = _text('title', 200) or session.title
            session.session_type = _choice('session_type', SESSION_TYPES, 'custom')
            session.custom_type = _text('custom_type', 50) if session.session_type == 'custom' else None
            session.requirement = _choice('requirement', REQUIREMENTS, 'required')
            session.alternative_group = _text('alternative_group', 50) if session.requirement == 'alternative' else None
            if session.requirement == 'alternative' and not session.alternative_group:
                raise ValueError('Name the group of alternatives (sessions with the same group: do any one).')
            session.duration_minutes = _int('duration_minutes', None, 0, 1440)
            for field in ('focus', 'warmup', 'cooldown', 'coaching_cues'):
                setattr(session, field, _text(field))
            session.video_url = _url('video_url')
            session.attachment_url = _url('attachment_url')
            known = {k for k, _ in LOG_FIELDS}
            session.log_fields = [f for f in request.form.getlist('log_fields') if f in known]
            session.custom_fields = _custom_fields(request.form.get('custom_fields'))
            _save_exercises(session)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            session = _row(ProgrammeSession, session_id, programme)
            return render_template('programmes/edit_session.html', programme=programme, session=session,
                                   **_session_choices()), 400
        db.session.commit()
        flash('Session saved.', 'success')
        if request.form.get('then') == 'week':
            return redirect(url_for('programmes.edit_week', programme_id=programme.id, week_id=session.week_id))
        return redirect(url_for('programmes.edit_session', programme_id=programme.id, session_id=session.id))
    return render_template('programmes/edit_session.html', programme=programme, session=session,
                           **_session_choices())


def _session_choices():
    return {'session_types': SESSION_TYPES, 'requirements': REQUIREMENTS, 'log_fields': LOG_FIELDS}


@bp.route('/<int:programme_id>/sessions/<int:session_id>/<action>', methods=['POST'])
@coach_required
def session_action(programme_id, session_id, action):
    programme = _programme(programme_id)
    session = _row(ProgrammeSession, session_id, programme)
    week = session.week
    if action == 'delete':
        week.sessions.remove(session)
        svc.renumber(week.sessions)
    elif action in ('up', 'down'):
        svc.move(week.sessions, session, -1 if action == 'up' else 1)
    elif action == 'duplicate':
        copy = svc.duplicate_session_content(session)
        copy.title = f'{session.title} (copy)'
        sessions = list(week.sessions)
        sessions.insert(sessions.index(session) + 1, copy)
        week.sessions = sessions
        svc.renumber(week.sessions)
    else:
        abort(404)
    db.session.commit()
    return redirect(url_for('programmes.edit_week', programme_id=programme.id, week_id=week.id))


# --------------------------------------------------------------------------
# Tests and milestones
# --------------------------------------------------------------------------

@bp.route('/<int:programme_id>/tests', methods=['GET', 'POST'])
@coach_required
def tests(programme_id):
    programme = _programme(programme_id)
    version = programme.draft or programme.published
    if request.method == 'POST':
        draft = _draft_or_redirect(programme)
        if draft is None:
            return redirect(url_for('programmes.tests', programme_id=programme.id))
        action = request.form.get('action')
        try:
            if action == 'save-test':
                test_id = request.form.get('test_id')
                test = _row(PerformanceTest, int(test_id), programme) if test_id else PerformanceTest(
                    team_organization_id=programme.team_organization_id, position=len(draft.tests))
                _fill_test(test)
                if test not in draft.tests:
                    draft.tests.append(test)
            elif action == 'delete-test':
                test = _row(PerformanceTest, _int('test_id'), programme)
                for ms in draft.milestones:
                    if ms.test_keys and test.key in ms.test_keys:
                        ms.test_keys = [k for k in ms.test_keys if k != test.key] or None
                draft.tests.remove(test)
                svc.renumber(draft.tests)
            elif action == 'save-milestone':
                ms_id = request.form.get('milestone_id')
                ms = _row(ProgrammeMilestone, int(ms_id), programme) if ms_id else ProgrammeMilestone(
                    team_organization_id=programme.team_organization_id, position=len(draft.milestones))
                ms.name = _text('name', 100)
                if not ms.name:
                    raise ValueError('Give the milestone a name.')
                ms.kind = _choice('kind', [('baseline', ''), ('retest', ''), ('milestone', '')], 'milestone')
                week_id = _int('week_id')
                ms.week = _row(ProgrammeWeek, week_id, programme) if week_id else None
                keys = {t.key for t in draft.tests}
                chosen = [k for k in request.form.getlist('test_keys') if k in keys]
                ms.test_keys = chosen if chosen and len(chosen) < len(keys) else None
                ms.notes = _text('notes')
                if ms not in draft.milestones:
                    draft.milestones.append(ms)
            elif action == 'delete-milestone':
                ms = _row(ProgrammeMilestone, _int('milestone_id'), programme)
                draft.milestones.remove(ms)
                svc.renumber(draft.milestones)
            else:
                abort(400)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return redirect(url_for('programmes.tests', programme_id=programme.id))
        db.session.commit()
        flash('Saved.', 'success')
        return redirect(url_for('programmes.tests', programme_id=programme.id))
    return render_template('programmes/tests.html', programme=programme, version=version,
                           measurements=MEASUREMENTS, aggregations=AGGREGATIONS)


def _fill_test(test):
    test.name = _text('name', 100)
    if not test.name:
        raise ValueError('Give the test a name.')
    test.unit = _text('unit', 20)
    if not test.unit:
        raise ValueError('Give the test a unit (s, m, reps, level...).')
    test.description = _text('description')
    test.instructions = _text('instructions')
    test.measurement = _choice('measurement', MEASUREMENTS, 'other')
    test.attempts = _int('attempts', 1, 1, 20)
    test.aggregation = _choice('aggregation', AGGREGATIONS, 'best')
    test.higher_is_better = request.form.get('better') == 'higher'
    test.min_value = _float('min_value')
    test.max_value = _float('max_value')
    if test.min_value is not None and test.max_value is not None and test.min_value >= test.max_value:
        raise ValueError('The lowest allowed value must be below the highest.')


# --------------------------------------------------------------------------
# Preview, validation and publishing
# --------------------------------------------------------------------------

def _player_weeks(programme, version, enrolment, progress, today=None):
    """[(track, [(week, start date, is current)])] for the player view."""
    today = today or date.today()
    out = []
    for track in version.tracks:
        weeks = []
        for week in track.weeks:
            start = svc.week_start(programme, track, week, enrolment)
            current = bool(start and start <= today < start + timedelta(days=7))
            weeks.append((week, start, current))
        out.append((track, weeks))
    return out


@bp.route('/<int:programme_id>/preview')
@coach_required
def preview(programme_id):
    programme = _programme(programme_id)
    version = programme.draft or programme.published
    if version is None:
        abort(404)
    return render_template('programmes/player_view.html', programme=programme, version=version, enrolment=None,
                           progress=None, preview=True, shared_view=False,
                           weeks=_player_weeks(programme, version, None, None))


@bp.route('/<int:programme_id>/publish', methods=['GET', 'POST'])
@coach_required
def publish(programme_id):
    programme = _programme(programme_id)
    draft = programme.draft
    if draft is None:
        flash('There is no draft to publish.', 'info')
        return redirect(url_for('programmes.show', programme_id=programme.id))
    errors, warnings = svc.validate(programme, draft)
    if request.method == 'POST':
        if errors:
            flash('Fix the problems listed before publishing.', 'danger')
        else:
            move_players = request.form.get('players') != 'stay'
            svc.publish(programme, current_user, _text('change_note', 2000), move_players=move_players)
            db.session.commit()
            flash(f'Version {draft.number} published.', 'success')
            return redirect(url_for('programmes.show', programme_id=programme.id))
    active = [e for e in programme.enrolments if e.status in ('active', 'paused')]
    return render_template('programmes/publish.html', programme=programme, draft=draft, errors=errors,
                           warnings=warnings, active=active)


# --------------------------------------------------------------------------
# Players on a programme
# --------------------------------------------------------------------------

@bp.route('/<int:programme_id>/players', methods=['GET', 'POST'])
@coach_required
def players(programme_id):
    programme = _programme(programme_id)
    team_id = programme.team_organization_id
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'enrol':
                if programme.is_template:
                    raise ValueError('Templates don\'t have players: copy it into a programme first.')
                ids = [_safe_int(i, None) for i in request.form.getlist('player_ids')]
                chosen = Player.query.filter(Player.id.in_([i for i in ids if i]),
                                             Player.team_organization_id == team_id).all()
                if not chosen:
                    raise ValueError('Pick at least one player.')
                offset = _int('start_offset_weeks', None, 0, 104)
                start = _date('start_date')
                added = 0
                for player in chosen:
                    _, created = svc.enrol(programme, player, start_date=start, start_offset_weeks=offset)
                    added += created
                flash(f'Added {added} player(s).', 'success')
            elif action == 'update':
                enrolment = _coach_enrolment(programme, _int('enrolment_id'))
                enrolment.status = _choice('status', [('active', ''), ('paused', ''), ('finished', ''),
                                                      ('withdrawn', '')], enrolment.status)
                enrolment.start_offset_weeks = _int('start_offset_weeks', 0, 0, 104)
                enrolment.start_date = _date('start_date')
                if request.form.get('move_to_current') and programme.published:
                    enrolment.version = programme.published
                flash(f'{enrolment.player.name} updated.', 'success')
            elif action == 'remove':
                enrolment = _coach_enrolment(programme, _int('enrolment_id'))
                if enrolment.logs or enrolment.results:
                    enrolment.status = 'withdrawn'
                    flash(f'{enrolment.player.name} has logs, so they were withdrawn (their history is kept).', 'info')
                else:
                    db.session.delete(enrolment)
                    flash('Removed.', 'success')
            else:
                abort(400)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
        db.session.commit()
        return redirect(url_for('programmes.players', programme_id=programme.id))
    enrolled = {e.player_id for e in programme.enrolments}
    available = (Player.query.filter_by(team_organization_id=team_id, active=True).order_by(Player.name).all())
    version = programme.published
    return render_template('programmes/players.html', programme=programme,
                           enrolments=sorted(programme.enrolments, key=lambda e: e.player.name.lower()),
                           available=[p for p in available if p.id not in enrolled],
                           default_offset=svc.week_index_for(programme, version, date.today()) if version else 0,
                           total_weeks=svc.total_weeks(version) if version else 0)


# --------------------------------------------------------------------------
# A player's programme: viewing, logging sessions, recording tests
# --------------------------------------------------------------------------

@bp.route('/<int:programme_id>/me')
def me(programme_id):
    programme = _programme(programme_id)
    player = _player()
    enrolment = None
    if player is not None:
        enrolment = ProgrammeEnrolment.query.filter_by(programme_id=programme.id, player_id=player.id,
                                                       team_organization_id=programme.team_organization_id).first()
    if enrolment is None or enrolment.status == 'withdrawn':
        if current_user.is_coach:
            return redirect(url_for('programmes.preview', programme_id=programme.id))
        abort(404)
    return _player_page(programme, enrolment)


@bp.route('/<int:programme_id>/players/<int:enrolment_id>')
@coach_required
def player_detail(programme_id, enrolment_id):
    programme = _programme(programme_id)
    return _player_page(programme, _enrolment(programme, enrolment_id), coach_view=True)


def _player_page(programme, enrolment, coach_view=False):
    progress = svc.enrolment_progress(enrolment)
    logs = {lg.session_key: lg for lg in enrolment.logs}
    return render_template('programmes/player_view.html', programme=programme, version=enrolment.version,
                           enrolment=enrolment, progress=progress, logs=logs, preview=False, shared_view=False,
                           coach_view=coach_view, weeks=_player_weeks(programme, enrolment.version, enrolment, progress))


def _log_redirect(programme, enrolment, coach_view):
    if coach_view:
        return redirect(url_for('programmes.player_detail', programme_id=programme.id, enrolment_id=enrolment.id))
    return redirect(url_for('programmes.me', programme_id=programme.id))


@bp.route('/<int:programme_id>/log/<int:session_id>', methods=['GET', 'POST'])
def log_session(programme_id, session_id):
    programme = _programme(programme_id)
    enrolment_id = request.values.get('enrolment', type=int)
    enrolment = _enrolment(programme, enrolment_id)
    if enrolment.status == 'withdrawn' or current_user.is_guest:
        abort(404)
    session = ProgrammeSession.query.filter_by(id=session_id,
                                               team_organization_id=programme.team_organization_id).first_or_404()
    # Only the sessions of the version the player is on
    if session.week.track.version_id != enrolment.version_id:
        abort(404)
    log = SessionLog.query.filter_by(enrolment_id=enrolment.id, session_key=session.key).first()
    coach_view = enrolment_id is not None
    if request.method == 'POST':
        if request.form.get('action') == 'delete':
            if log:
                db.session.delete(log)
                db.session.commit()
                flash('Log removed.', 'success')
            return _log_redirect(programme, enrolment, coach_view)
        try:
            if log is None:
                log = SessionLog(enrolment=enrolment, session_key=session.key,
                                 team_organization_id=programme.team_organization_id)
                db.session.add(log)
            log.session = session
            log.status = _choice('status', [('completed', ''), ('partial', ''), ('skipped', '')], 'completed')
            log.completed_on = _date('completed_on') or date.today()
            if log.completed_on > date.today():
                raise ValueError('The date can\'t be in the future.')
            log.duration_minutes = _int('duration_minutes', None, 0, 1440)
            log.rpe = _int('rpe', None, 1, 10)
            log.distance_m = _float('distance_m', minimum=0)
            log.soreness = _int('soreness', None, 1, 5)
            log.sleep_hours = _float('sleep_hours', minimum=0)
            if log.sleep_hours is not None and log.sleep_hours > 24:
                raise ValueError('Sleep is at most 24 hours.')
            values = {}
            for field in session.custom_fields or []:
                value = _float(f'custom_{field["key"]}')
                if value is not None:
                    values[field['key']] = value
            log.values = values or None
            log.notes = _text('notes', 2000)
            log.logged_by_id = current_user.id
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return render_template('programmes/log_session.html', programme=programme, session=session,
                                   enrolment=enrolment, log=log, coach_view=coach_view,
                                   field_labels=dict(LOG_FIELDS)), 400
        db.session.commit()
        flash('Logged. Nice work.' if log.status != 'skipped' else 'Noted as skipped.', 'success')
        return _log_redirect(programme, enrolment, coach_view)
    return render_template('programmes/log_session.html', programme=programme, session=session,
                           enrolment=enrolment, log=log, coach_view=coach_view, field_labels=dict(LOG_FIELDS))


@bp.route('/<int:programme_id>/results', methods=['GET', 'POST'])
def record_results(programme_id):
    programme = _programme(programme_id)
    enrolment_id = request.values.get('enrolment', type=int)
    enrolment = _enrolment(programme, enrolment_id)
    if enrolment.status == 'withdrawn' or current_user.is_guest:
        abort(404)
    version = enrolment.version
    coach_view = enrolment_id is not None
    if request.method == 'POST':
        milestone_id = _safe_int(request.form.get('milestone_id'), None)
        milestone = None
        if milestone_id:
            milestone = next((m for m in version.milestones if m.id == milestone_id and m.is_test), None)
            if milestone is None:
                abort(404)
        try:
            recorded_on = _date('recorded_on') or date.today()
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(request.url)
        saved, problems = 0, []
        for test in version.tests:
            if milestone and not milestone.covers(test):
                continue
            raw = request.form.getlist(f'attempt_{test.id}')
            if not any((r or '').strip() for r in raw):
                continue
            values, error = svc.parse_attempts(test, raw)
            if error:
                problems.append(f'{test.name}: {error}')
                continue
            result = None
            if milestone:
                result = TestResult.query.filter_by(enrolment_id=enrolment.id, test_key=test.key,
                                                    milestone_key=milestone.key).first()
            if result is None:
                result = TestResult(enrolment=enrolment, test_key=test.key,
                                    team_organization_id=programme.team_organization_id)
                db.session.add(result)
            result.test = test
            result.milestone = milestone
            result.milestone_key = milestone.key if milestone else None
            result.attempts = values
            result.value = svc.aggregate(test, values)
            result.recorded_on = recorded_on
            result.notes = _text(f'notes_{test.id}', 1000)
            result.recorded_by_id = current_user.id
            saved += 1
        if problems:
            db.session.rollback()
            for p in problems:
                flash(p, 'danger')
            return render_template('programmes/record_results.html', programme=programme, enrolment=enrolment,
                                   version=version, coach_view=coach_view, form=request.form), 400
        db.session.commit()
        flash(f'Saved {saved} result(s).' if saved else 'Nothing entered.', 'success' if saved else 'info')
        return _log_redirect(programme, enrolment, coach_view)
    return render_template('programmes/record_results.html', programme=programme, enrolment=enrolment,
                           version=version, coach_view=coach_view, form={})


# --------------------------------------------------------------------------
# Dashboard and exports
# --------------------------------------------------------------------------

@bp.route('/<int:programme_id>/dashboard')
@coach_required
def dashboard(programme_id):
    programme = _programme(programme_id)
    return render_template('programmes/dashboard.html', programme=programme, d=svc.dashboard(programme))


def _csv_response(rows, filename):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator='\n')
    for row in rows:
        writer.writerow([_safe_cell(c) for c in row])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def _safe_cell(value):
    """Stop a spreadsheet treating a cell as a formula."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '@') or (text[:1] == '-' and not _is_number(text)) else text


def _is_number(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def _slug(text):
    return ''.join(ch if ch.isalnum() else '-' for ch in text.lower()).strip('-')[:60] or 'programme'


@bp.route('/<int:programme_id>/export/<kind>.csv')
@coach_required
def export(programme_id, kind):
    programme = _programme(programme_id)
    version = programme.published or programme.draft
    if version is None:
        abort(404)
    slug = _slug(programme.name)
    if kind == 'programme':
        return _csv_response(pimport.export_rows(version), f'{slug}-programme.csv')
    if kind == 'tests':
        return _csv_response(pimport.export_test_rows(version), f'{slug}-tests.csv')
    if kind == 'report':
        d = svc.dashboard(programme)
        tests = [t['test'] for t in d['tests']]
        rows = [['player', 'status', 'sessions_due', 'sessions_done', 'completion_pct', 'not_logged', 'skipped',
                 'optional_done', 'last_logged', 'workload_28d'] +
                [f'{t.name} first ({t.unit})' for t in tests] + [f'{t.name} latest ({t.unit})' for t in tests] +
                ['follow_up']]
        for r in d['rows']:
            p = r['p']
            firsts, latests = [], []
            for t in tests:
                s = p['tests'].get(t.key, {})
                firsts.append(s['first'].value if s.get('first') else '')
                latests.append(s['latest'].value if s.get('latest') else '')
            rows.append([r['enrolment'].player.name, r['enrolment'].status, p['due'], p['done'],
                         '' if p['completion'] is None else p['completion'], len(p['missing']), p['skipped'],
                         p['optional_done'], p['last_logged'] or '',
                         '' if p['workload_28'] is None else p['workload_28']] + firsts + latests +
                        ['; '.join(r['follow_up'])])
        return _csv_response(rows, f'{slug}-report-{date.today().isoformat()}.csv')
    abort(404)


# --------------------------------------------------------------------------
# Import
# --------------------------------------------------------------------------

@bp.route('/import/template/<kind>.csv')
@coach_required
def import_template(kind):
    if kind == 'programme':
        rows = [pimport.PROGRAMME_COLUMNS,
                ['Speed', '1', '0', '1', 'Acceleration', '', 'Learn the drive phase', 'Arm drive', 'Speed session 1',
                 'sprint', 'required', '', '45', '', '10 min dynamic warm-up', '', 'Lean, drive the arms',
                 '', 'duration_minutes, rpe', '10 m sprints', '', '1', '15', '10', '', 'Walk back', 'Max', '',
                 'Stay low', ''],
                ['Speed', '', '', '2', 'Rest week', 'rest'] + [''] * (len(pimport.PROGRAMME_COLUMNS) - 6),
                ['Conditioning', '0', '0', '0', 'Intervals', '', '', '', 'Intervals', 'conditioning', 'required', '',
                 '30', '', '', '', '', '', 'duration_minutes, rpe, distance_m', 'Intervals', '', '4', '',
                 '', '120', '2 min active recovery', 'Hard but steady', '', '', ''],
                ]
        return _csv_response(rows, 'programme-template.csv')
    if kind == 'tests':
        rows = [pimport.TEST_COLUMNS,
                ['10 m sprint', 's', 'time', '3', 'best', 'lower', '1', '4', 'Standing start', '', 'Speed', '1', '2']]
        return _csv_response(rows, 'tests-template.csv')
    abort(404)


def _uploaded_rows():
    """(programme rows, test rows, file name, problem) from the import form:
    an .xlsx (sheets "programme" and "tests"), CSV files, or pasted CSV."""
    filename = None
    upload = request.files.get('file')
    if upload and upload.filename:
        filename = upload.filename[:200]
        data = upload.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            return None, None, filename, 'That file is over 5 MB.'
        if filename.lower().endswith('.xlsx'):
            try:
                sheets = pimport.rows_from_xlsx(data)
            except Exception:
                return None, None, filename, 'That file couldn\'t be read as an .xlsx spreadsheet.'
            names = list(sheets)
            programme_rows = sheets.get('programme') or (sheets[names[0]] if names else [])
            test_rows = sheets.get('tests') or []
            return programme_rows, test_rows, filename, None
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            return None, None, filename, 'Save the spreadsheet as CSV (UTF-8) or .xlsx and try again.'
        programme_rows = pimport.rows_from_csv(text)
    else:
        programme_rows = pimport.rows_from_csv(request.form.get('programme_csv', ''))
        filename = (request.form.get('filename') or '').strip()[:200] or None
    tests_upload = request.files.get('tests_file')
    if tests_upload and tests_upload.filename:
        try:
            test_rows = pimport.rows_from_csv(tests_upload.read(2 * 1024 * 1024).decode('utf-8-sig'))
        except UnicodeDecodeError:
            return None, None, filename, 'Save the tests sheet as CSV (UTF-8).'
    else:
        test_rows = pimport.rows_from_csv(request.form.get('tests_csv', ''))
    return programme_rows, test_rows, filename, None


@bp.route('/import', methods=['GET', 'POST'])
@coach_required
def import_programme():
    team_id = _team()
    if request.method == 'GET':
        return render_template('programmes/import.html', parsed=None, form={})
    programme_rows, test_rows, filename, problem = _uploaded_rows()
    if problem:
        flash(problem, 'danger')
        return render_template('programmes/import.html', parsed=None, form=request.form), 400
    parsed = pimport.parse(programme_rows, test_rows)
    digest = pimport.content_hash(programme_rows, test_rows)
    duplicate = pimport.find_duplicate(team_id, digest)
    form = dict(request.form)
    form['programme_csv'] = pimport.rows_to_csv(programme_rows)
    form['tests_csv'] = pimport.rows_to_csv(test_rows) if test_rows else ''
    form['filename'] = filename or ''
    form.setdefault('name', (filename or '').rsplit('.', 1)[0])
    if request.form.get('confirm') and not parsed['errors'] and not duplicate:
        try:
            name = (request.form.get('name') or '').strip()[:200]
            if not name:
                raise ValueError('Give the programme a name.')
            if Programme.query.filter_by(team_organization_id=team_id, name=name, archived=False).first():
                raise ValueError(f'You already have a programme called "{name}". Pick another name.')
            programme = pimport.build(
                parsed, team_id, current_user, name=name, description=_text('description'),
                start_date=_date('start_date'),
                schedule_mode=_choice('schedule_mode', [('calendar', ''), ('relative', '')], 'calendar'),
                kind=_choice('kind', [('programme', ''), ('template', '')], 'programme'),
                filename=filename, digest=digest)
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
        else:
            db.session.commit()
            flash('Imported as a draft. Check it over, then publish.', 'success')
            return redirect(url_for('programmes.build', programme_id=programme.id))
    return render_template('programmes/import.html', parsed=parsed, form=form, duplicate=duplicate)
