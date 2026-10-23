"""Training: regular schedules, players' availability, the coach's grid,
session settings and the session builder.

Every answer is saved through app.utils.rsvp.set_rsvp; schedule dates are
made by app.utils.schedules.
"""
import csv
import io
import re
from datetime import date, time, timedelta

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models.drill import SavedDrill
from app.models.player import Player
from app.models.schedule import WEEKDAYS, SessionTemplate, TrainingSchedule
from app.models.session import SessionComponent, SessionPlan
from app.models.team_settings import TeamSettings
from app.utils import rsvp, schedules
from app.utils.season import team_squads
from app.utils.team_filter import get_current_team_id
from app.utils.utils import coach_required

bp = Blueprint('training', __name__, url_prefix='/sessions')

GRID_WEEKS = 6
MAX_WEEKS = 26


def _wants_json():
    return request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest' \
        or request.accept_mimetypes.best == 'application/json'


def _session_or_404(session_id):
    return SessionPlan.query.filter_by(id=session_id, team_organization_id=get_current_team_id()).first_or_404()


def _settings(team_id):
    settings = TeamSettings.query.filter_by(team_id=team_id).first()
    if settings is None:
        settings = TeamSettings(team_id=team_id)
        db.session.add(settings)
        db.session.flush()
    return settings


def _date_arg(name, default=None):
    try:
        return date.fromisoformat(request.args.get(name, ''))
    except ValueError:
        return default


def _safe_next(target, fallback):
    """Only ever redirect back to a page on this site."""
    if target and target.startswith(request.host_url):
        target = '/' + target[len(request.host_url):]
    if target and target.startswith('/') and not target.startswith(('//', '/\\')):
        return target
    return fallback


def _int_arg(name, default, low, high):
    value = request.args.get(name, '')
    return max(low, min(high, int(value))) if value.isdigit() else default


# ── Schedules ──────────────────────────────────────────────────────────────

def _read_schedule_form(form, team_id):
    """(values, squads, skip dates, error) from the schedule form."""
    values = {'name': (form.get('name') or '').strip()[:100],
              'location': (form.get('location') or '').strip()[:100] or None,
              'session_type': form.get('session_type') or 'invited_training',
              'others_welcome': bool(form.get('others_welcome'))}
    if not values['name']:
        return None, None, None, 'Give the schedule a name, e.g. "Saturday training".'
    weekday = form.get('weekday', '')
    if not (weekday.isdigit() and int(weekday) < 7):
        return None, None, None, 'Pick the day it runs on.'
    values['weekday'] = int(weekday)
    if values['session_type'] not in dict(SessionPlan.SESSION_TYPE_CHOICES):
        values['session_type'] = 'invited_training'
    try:
        for key in ('start_time', 'end_time'):
            raw = (form.get(key) or '').strip()
            values[key] = time.fromisoformat(raw) if raw else None
    except ValueError:
        return None, None, None, 'Times look like 19:00.'
    try:
        values['start_date'] = date.fromisoformat(form.get('start_date') or '')
    except ValueError:
        return None, None, None, 'Pick the date it starts.'
    raw_end = (form.get('end_date') or '').strip()
    try:
        values['end_date'] = date.fromisoformat(raw_end) if raw_end else None
    except ValueError:
        return None, None, None, 'The end date isn\'t a date.'
    if values['end_date'] and values['end_date'] < values['start_date']:
        return None, None, None, 'It has to end after it starts.'
    if values['start_time'] and values['end_time'] and values['end_time'] <= values['start_time']:
        return None, None, None, 'It has to finish after it starts.'
    wanted = {int(v) for v in form.getlist('squads') if v.isdigit()}
    squads = [s for s in team_squads(team_id) if s.id in wanted]
    skips, bad = schedules.parse_skip_dates(form.get('skip_dates'))
    if bad:
        return None, None, None, f"These skip dates aren't dates: {', '.join(bad)} (write them like 2026-12-26)."
    return values, squads, skips, None


def _form_values(form=None, schedule=None):
    """The schedule form's fields as strings, from a posted form or a schedule."""
    if form is not None:
        values = {k: form.get(k, '') for k in ('name', 'weekday', 'start_time', 'end_time', 'location',
                                                 'session_type', 'start_date', 'end_date', 'skip_dates')}
        values['others_welcome'] = bool(form.get('others_welcome'))
        values['squads'] = form.getlist('squads')
        return values
    if schedule is not None:
        return {'name': schedule.name, 'weekday': str(schedule.weekday),
                'start_time': schedule.start_time.strftime('%H:%M') if schedule.start_time else '',
                'end_time': schedule.end_time.strftime('%H:%M') if schedule.end_time else '',
                'location': schedule.location or '', 'session_type': schedule.session_type or '',
                'start_date': schedule.start_date.isoformat(),
                'end_date': schedule.end_date.isoformat() if schedule.end_date else '',
                'skip_dates': '', 'others_welcome': schedule.others_welcome,
                'squads': [str(q.id) for q in schedule.squads]}
    return {'start_date': date.today().isoformat(), 'session_type': 'invited_training', 'squads': []}


def _apply_skips(schedule, skips):
    count = 0
    for day in skips:
        session = schedule.sessions.filter(SessionPlan.date == day).first()
        if session and not session.is_cancelled:
            schedules.cancel(session, 'No training this week')
            count += 1
    return count


@bp.route('/schedules', methods=['GET', 'POST'])
@login_required
@coach_required
def schedules_page():
    team_id = get_current_team_id()
    if request.method == 'POST':
        values, squads, skips, error = _read_schedule_form(request.form, team_id)
        if error:
            flash(error, 'danger')
            return _render_schedules(team_id, _form_values(request.form)), 400
        schedule = TrainingSchedule(team_organization_id=team_id, **values)
        schedule.squads = squads
        db.session.add(schedule)
        db.session.flush()
        report = schedules.sync_schedule(schedule)
        skipped = _apply_skips(schedule, skips)
        db.session.commit()
        flash(f'"{schedule.name}" added: {len(report.created)} dates are ready for players to answer'
              + (f', {skipped} skipped' if skipped else '') + '.', 'success')
        return redirect(url_for('training.schedules_page'))
    return _render_schedules(team_id)


def _render_schedules(team_id, form=None):
    items = TrainingSchedule.query.filter_by(team_organization_id=team_id).order_by(
        TrainingSchedule.weekday, TrainingSchedule.start_time).all()
    today = date.today()
    upcoming = {s.id: s.sessions.filter(SessionPlan.date >= today).order_by(SessionPlan.date).limit(12).all()
                for s in items}
    planned = {sess.id for dates in upcoming.values() for sess in dates if sess.components.count()}
    return render_template('training/schedules.html', schedules=items, upcoming=upcoming, planned=planned,
                           squads=team_squads(team_id), weekdays=WEEKDAYS, values=form or _form_values(),
                           clashes=schedules.clashes(team_id), today=today,
                           session_types=SessionPlan.SESSION_TYPE_CHOICES)


@bp.route('/schedules/<int:schedule_id>/edit', methods=['GET', 'POST'])
@login_required
@coach_required
def edit_schedule(schedule_id):
    team_id = get_current_team_id()
    schedule = TrainingSchedule.query.filter_by(id=schedule_id, team_organization_id=team_id).first_or_404()
    if request.method == 'POST':
        values, squads, skips, error = _read_schedule_form(request.form, team_id)
        if error:
            flash(error, 'danger')
        else:
            for key, value in values.items():
                setattr(schedule, key, value)
            schedule.squads = squads
            report = schedules.sync_schedule(schedule)
            skipped = _apply_skips(schedule, skips)
            db.session.commit()
            flash(f'"{schedule.name}" saved: {report.summary()}' + (f', {skipped} skipped' if skipped else '')
                  + '. Dates already planned keep their own time and place.', 'success')
            return redirect(url_for('training.schedules_page'))
    values = _form_values(request.form) if request.method == 'POST' else _form_values(schedule=schedule)
    return render_template('training/schedule_form.html', schedule=schedule, squads=team_squads(team_id),
                           weekdays=WEEKDAYS, session_types=SessionPlan.SESSION_TYPE_CHOICES, values=values)


@bp.route('/schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
@coach_required
def delete_schedule(schedule_id):
    schedule = TrainingSchedule.query.filter_by(
        id=schedule_id, team_organization_id=get_current_team_id()).first_or_404()
    name = schedule.name
    schedules.remove_schedule(schedule)
    db.session.commit()
    flash(f'"{name}" removed. Future dates nobody had answered for are gone; the rest are cancelled.', 'success')
    return redirect(url_for('training.schedules_page'))


@bp.route('/<int:session_id>/cancel', methods=['POST'])
@login_required
@coach_required
def cancel(session_id):
    from app.utils.reminders import tell_cancelled

    session = _session_or_404(session_id)
    schedules.cancel(session, request.form.get('reason'))
    db.session.commit()
    told = tell_cancelled(session) if session.date and session.date >= date.today() else 0
    flash(f'{session.title} on {session.formatted_date} is cancelled'
          + (f'; {told} player{"s" if told != 1 else ""} who were coming have been told.' if told else '.'),
          'success')
    return redirect(_safe_next(request.form.get('next'), url_for('session.detail', session_id=session.id)))


@bp.route('/<int:session_id>/restore', methods=['POST'])
@login_required
@coach_required
def restore(session_id):
    session = _session_or_404(session_id)
    schedules.restore(session)
    db.session.commit()
    flash(f'{session.title} on {session.formatted_date} is back on.', 'success')
    return redirect(_safe_next(request.form.get('next'), url_for('session.detail', session_id=session.id)))


# ── Players' availability ──────────────────────────────────────────────────

@bp.route('/availability')
@login_required
def availability():
    """A player's upcoming sessions, one tap each, plus their usual answers."""
    player = current_user.player
    if player is None:
        if current_user.is_coach:
            return redirect(url_for('training.grid'))
        flash('Link your account to your player profile to say when you can train.', 'warning')
        return redirect(url_for('auth.link_player'))
    team_id = get_current_team_id()
    weeks = _int_arg('weeks', 12, 1, 60)
    today = date.today()
    squad_id = rsvp.player_squads(team_id).get(player.id)
    sessions = rsvp.upcoming_sessions(team_id, today, today + timedelta(weeks=weeks), include_cancelled=True)
    answers = rsvp.answers(sessions, [player.id])
    mine = [s for s in sessions if rsvp.is_for(s, squad_id) or (s.id, player.id) in answers]
    extra = [s for s in sessions if s not in mine and rsvp.can_join(s, squad_id) and not s.is_cancelled]

    months = []
    for s in mine:
        label = s.date.strftime('%B %Y')
        if not months or months[-1][0] != label:
            months.append((label, []))
        months[-1][1].append(s)

    all_schedules = TrainingSchedule.query.filter_by(team_organization_id=team_id).order_by(
        TrainingSchedule.weekday).all()
    my_schedules = [s for s in all_schedules
                    if not s.squads or squad_id in {q.id for q in s.squads} or s.others_welcome]
    unanswered = sum(1 for s in mine if not s.is_cancelled and
                     ((a := answers.get((s.id, player.id))) is None or a.status == rsvp.MAYBE))
    return render_template('training/availability.html', player=player, months=months, extra=extra,
                           answers=answers, schedules=my_schedules, usual=rsvp.usual_answers(player),
                           weeks=weeks, unanswered=unanswered)


@bp.route('/availability/usual', methods=['POST'])
@login_required
def save_usual():
    player = current_user.player
    if player is None:
        abort(403)
    team_id = get_current_team_id()
    for schedule in TrainingSchedule.query.filter_by(team_organization_id=team_id):
        key = f'usual_{schedule.id}'
        if key in request.form:
            rsvp.set_usual(schedule, player, request.form.get(key) or None)
    db.session.commit()
    flash('Usual answers saved. They fill in every date you haven\'t answered yourself.', 'success')
    return redirect(url_for('training.availability'))


@bp.route('/<int:session_id>/answer', methods=['POST'])
@bp.route('/<int:session_id>/answer/<int:player_id>', methods=['POST'])
@login_required
def answer(session_id, player_id=None):
    """Save one answer: a player's own, or (coaches) a player's."""
    session = _session_or_404(session_id)
    if player_id is None:
        player = current_user.player
        if player is None:
            abort(403)
    else:
        if not current_user.is_coach:
            abort(403)
        player = Player.query.filter_by(id=player_id, team_organization_id=session.team_organization_id).first_or_404()
    data = request.get_json(silent=True) or request.form
    raw = data.get('status')
    status = rsvp.normalise(raw) if raw not in (None, '', 'none') else None
    if raw not in (None, '', 'none') and status is None:
        return _answer_error('Answer yes, maybe or no.', session)
    if session.is_cancelled:
        return _answer_error('This session is cancelled.', session)
    if player_id is None and status is None:
        return _answer_error('Answer yes, maybe or no.', session)
    rsvp.set_rsvp(session, player, status, data.get('notes'))
    db.session.commit()

    if _wants_json():
        counts = rsvp.counts(session)
        return jsonify({'ok': True, 'status': status, 'session_id': session.id, 'player_id': player.id,
                        'counts': counts, 'label': rsvp.LABELS.get(status, '')})
    flash(f'Saved: {rsvp.LABELS[status]} for {session.title}, {session.formatted_date}.' if status
          else 'Answer cleared.', 'success')
    return redirect(_safe_next(request.form.get('next') or request.referrer,
                               url_for('session.detail', session_id=session.id)))


def _answer_error(message, session):
    if _wants_json():
        return jsonify({'ok': False, 'message': message}), 400
    flash(message, 'warning')
    return redirect(url_for('session.detail', session_id=session.id))


# ── The coach's grid ───────────────────────────────────────────────────────

def _grid_data(team_id):
    """Everything the grid (and its CSV) shows, from the query string."""
    start = _date_arg('start', date.today())
    weeks = _int_arg('weeks', GRID_WEEKS, 1, MAX_WEEKS)
    squads = team_squads(team_id)
    squad_arg = request.args.get('squad', '')
    squad = next((s for s in squads if str(s.id) == squad_arg), None)
    sessions = rsvp.upcoming_sessions(team_id, start, start + timedelta(weeks=weeks) - timedelta(days=1),
                                      include_cancelled=True)
    player_squads = rsvp.player_squads(team_id)
    players = rsvp.team_players(team_id)
    if squad is not None:
        sessions = [s for s in sessions if rsvp.is_for(s, squad.id)]
        players = [p for p in players if player_squads.get(p.id) == squad.id]
    answers = rsvp.answers(sessions)
    squad_names = {s.id: s.name for s in squads}
    columns = []
    for s in sessions:
        answered = {pid for (sid, pid) in answers if sid == s.id}
        columns.append({'session': s, 'counts': rsvp.counts(s, answers, players, player_squads),
                        'expected': {p.id for p in rsvp.expected_players(s, players, player_squads, answered)}})
    return {'start': start, 'weeks': weeks, 'squads': squads, 'squad': squad, 'columns': columns,
            'players': players, 'answers': answers, 'player_squads': player_squads, 'squad_names': squad_names}


@bp.route('/availability/grid')
@login_required
@coach_required
def grid():
    data = _grid_data(get_current_team_id())
    return render_template('training/grid.html', **data,
                           prev_start=data['start'] - timedelta(weeks=data['weeks']),
                           next_start=data['start'] + timedelta(weeks=data['weeks']))


@bp.route('/availability/grid.csv')
@login_required
@coach_required
def grid_csv():
    data = _grid_data(get_current_team_id())
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['Player', 'Squad'] + [_column_header(c['session']) for c in data['columns']])
    for player in data['players']:
        row = [player.name, data['squad_names'].get(data['player_squads'].get(player.id), '')]
        for c in data['columns']:
            a = data['answers'].get((c['session'].id, player.id))
            row.append((a.label + (' (usual)' if a.usual else '')) if a else '')
        writer.writerow(row)
    name = f"availability-{data['start'].isoformat()}.csv"
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{name}"'})


def _column_header(session):
    text = session.date.isoformat() + ' ' + session.title
    return text + (' (cancelled)' if session.is_cancelled else '')


DATE_PATTERNS = [
    (re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})'), lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{4})'), lambda m: date(int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{2})\b'), lambda m: date(2000 + int(m[3]), int(m[2]), int(m[1]))),
]


def parse_header(text):
    """(date, the rest of the header) from '2026-11-07 Saturday', '07/11/2026', ..."""
    text = (text or '').strip()
    for pattern, build in DATE_PATTERNS:
        m = pattern.match(text)
        if m:
            try:
                return build(m), text[m.end():].strip(' -–·')
            except ValueError:
                return None, text
    return None, text


def import_availability(team_id, text):
    """Read a spreadsheet of answers: player names down the first column,
    one column per session headed by its date (and name, when there are two
    on one day). Cells say Yes, Maybe or No; empty cells and usual answers
    are left alone. Returns a report dict; the caller commits."""
    rows = list(csv.reader(io.StringIO(text.lstrip('﻿'))))
    report = {'saved': 0, 'unknown_players': [], 'unmatched_columns': [], 'bad_cells': 0}
    if not rows:
        return report
    header = rows[0]
    players = {p.name.strip().lower(): p for p in Player.query.filter_by(team_organization_id=team_id)}
    columns = {}
    for i, cell in enumerate(header[1:], start=1):
        day, rest = parse_header(cell)
        if day is None:
            if cell.strip().lower() not in ('squad', ''):
                report['unmatched_columns'].append(cell)
            continue
        same_day = SessionPlan.query.filter_by(team_organization_id=team_id, date=day).all()
        rest_key = re.sub(r'\s*\(cancelled\)$', '', rest).strip().lower()
        match = [s for s in same_day if s.title.strip().lower() == rest_key] if rest_key else []
        if not match:
            match = same_day if len(same_day) == 1 else []
        if len(match) == 1:
            columns[i] = match[0]
        else:
            report['unmatched_columns'].append(cell)
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        player = players.get(row[0].strip().lower())
        if player is None:
            report['unknown_players'].append(row[0].strip())
            continue
        for i, session in columns.items():
            cell = row[i].strip() if i < len(row) else ''
            if not cell or cell.lower().endswith('(usual)') or session.is_cancelled:
                continue
            status = rsvp.normalise(cell)
            if status is None:
                report['bad_cells'] += 1
                continue
            rsvp.set_rsvp(session, player, status)
            report['saved'] += 1
    return report


@bp.route('/availability/import', methods=['GET', 'POST'])
@login_required
@coach_required
def import_page():
    report = None
    if request.method == 'POST':
        upload = request.files.get('file')
        text = upload.read().decode('utf-8-sig', errors='replace') if upload and upload.filename else \
            request.form.get('text', '')
        if not text.strip():
            flash('Choose a CSV file or paste the sheet in.', 'warning')
        else:
            report = import_availability(get_current_team_id(), text)
            db.session.commit()
            flash(f"{report['saved']} answers saved.", 'success' if report['saved'] else 'warning')
    return render_template('training/import.html', report=report)


@bp.route('/<int:session_id>/nudge', methods=['POST'])
@login_required
@coach_required
def nudge(session_id):
    from app.utils.reminders import nudge as send_nudge

    session = _session_or_404(session_id)
    reached, missed = send_nudge(session)
    message = f'Reminded {reached} player{"s" if reached != 1 else ""} on Maybe or with no answer.'
    if missed:
        message += f' {missed} have no Discord or email to reach them on.'
    if not reached and not missed:
        message = 'Everyone has answered Yes or No already.'
    flash(message, 'success' if reached or not missed else 'warning')
    return redirect(_safe_next(request.form.get('next'), url_for('training.grid')))


# ── Session settings ───────────────────────────────────────────────────────

@bp.route('/settings', methods=['GET', 'POST'])
@login_required
@coach_required
def settings():
    from app.models.team_organization import TeamOrganization

    team_id = get_current_team_id()
    team = TeamOrganization.query.get_or_404(team_id)
    settings = _settings(team_id)
    if request.method == 'POST':
        visibility = request.form.get('attendee_visibility')
        if visibility in dict(TeamSettings.ATTENDEE_VISIBILITY):
            settings.attendee_visibility = visibility
        days = (request.form.get('plan_visible_days') or '').strip()
        settings.plan_visible_days = min(int(days), 60) if request.form.get('plan_when') == 'days' and days.isdigit() \
            else None
        settings.reminders_enabled = bool(request.form.get('reminders_enabled'))
        reminder_days = (request.form.get('reminder_days') or '').strip()
        settings.reminder_days = max(1, min(int(reminder_days), 28)) if reminder_days.isdigit() else 7
        db.session.commit()
        flash('Session settings saved.', 'success')
        return redirect(url_for('training.settings'))
    db.session.commit()
    return render_template('training/settings.html', team=team, settings=settings,
                           visibility_choices=TeamSettings.ATTENDEE_VISIBILITY)


# ── The session builder ────────────────────────────────────────────────────

BLOCK_FIELDS = {'title': 100, 'component_type': 20, 'focus_area': 100, 'description': None,
                'coach_cue': None, 'notes': None}


def _block(component):
    return {'id': component.id, 'title': component.title, 'component_type': component.component_type,
            'duration_minutes': component.duration_minutes, 'description': component.description or '',
            'coach_cue': component.coach_cue or '', 'notes': component.notes or '',
            'focus_area': component.focus_area or '', 'drill_id': component.drill_id,
            'drill_title': component.saved_drill.title if component.saved_drill else None}


def _clean_blocks(raw, team_id):
    """Validated blocks from the builder, or raises ValueError."""
    if not isinstance(raw, list) or len(raw) > 60:
        raise ValueError('A session can have up to 60 blocks.')
    drill_ids = {d for (d,) in db.session.query(SavedDrill.id).filter(SavedDrill.team_organization_id == team_id)}
    out = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('Each block needs a title.')
        block = {}
        for key, limit in BLOCK_FIELDS.items():
            value = item.get(key)
            value = str(value).strip() if value is not None else ''
            block[key] = (value[:limit] if limit else value) or None
        if not block['title']:
            raise ValueError('Each block needs a title.')
        if block['component_type'] not in SessionComponent.COMPONENT_TYPES:
            block['component_type'] = 'drill'
        minutes = item.get('duration_minutes')
        try:
            minutes = int(minutes) if minutes not in (None, '') else None
        except (TypeError, ValueError):
            raise ValueError(f'"{block["title"]}": minutes should be a number.')
        block['duration_minutes'] = minutes if minutes and 0 < minutes <= 600 else None
        drill_id = item.get('drill_id')
        block['drill_id'] = drill_id if isinstance(drill_id, int) and drill_id in drill_ids else None
        block['id'] = item.get('id') if isinstance(item.get('id'), int) else None
        out.append(block)
    return out


def save_blocks(session, blocks):
    """Make the session's components match the blocks: existing ones (by id)
    are updated in place, so their playbook links stay; the rest are added
    or removed."""
    from app.models.playbook import Play

    existing = {c.id: c for c in session.components}
    keep = set()
    for order, block in enumerate(blocks, start=1):
        component = existing.get(block['id'])
        if component is None:
            component = SessionComponent(session_id=session.id, team_organization_id=session.team_organization_id)
            db.session.add(component)
        else:
            keep.add(component.id)
        for key in BLOCK_FIELDS:
            setattr(component, key, block[key])
        component.duration_minutes = block['duration_minutes']
        component.drill_id = block['drill_id']
        component.order = order
    gone = [c for cid, c in existing.items() if cid not in keep]
    if gone:
        assoc = Play.play_session_component
        db.session.execute(assoc.delete().where(assoc.c.component_id.in_([c.id for c in gone])))
        for c in gone:
            db.session.delete(c)


def _season_week(session):
    """The season plan's week this session falls in, if the team has one."""
    from app.models.season_plan import SeasonPlan, SeasonWeek
    if not session.date:
        return None
    plan = SeasonPlan.query.filter_by(team_organization_id=session.team_organization_id, is_active=True).first()
    if plan is None:
        return None
    return SeasonWeek.query.filter(SeasonWeek.plan_id == plan.id,
                                   SeasonWeek.week_commencing <= session.date,
                                   SeasonWeek.week_commencing > session.date - timedelta(days=7)).first()


def _previous(session):
    """The last earlier session of the same schedule (or weekday) that was planned."""
    query = SessionPlan.query.filter(SessionPlan.team_organization_id == session.team_organization_id,
                                     SessionPlan.id != session.id,
                                     SessionPlan.components.any())
    if session.date:
        query = query.filter(SessionPlan.date < session.date)
    if session.schedule_id:
        same = query.filter(SessionPlan.schedule_id == session.schedule_id)
        found = same.order_by(SessionPlan.date.desc()).first()
        if found:
            return found
    return query.order_by(SessionPlan.date.desc().nullslast(), SessionPlan.id.desc()).first()


@bp.route('/<int:session_id>/plan', methods=['GET', 'POST'])
@login_required
@coach_required
def plan(session_id):
    session = _session_or_404(session_id)
    team_id = session.team_organization_id
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        try:
            blocks = _clean_blocks(data.get('blocks', []), team_id)
        except ValueError as e:
            return jsonify({'ok': False, 'message': str(e)}), 400
        for key, limit in (('title', 100), ('focus_area', 100)):
            if key in data:
                value = (data.get(key) or '').strip()[:limit]
                if key == 'title' and not value:
                    return jsonify({'ok': False, 'message': 'The session needs a title.'}), 400
                setattr(session, key, value or None)
        if 'notes' in data:
            session.notes = (data.get('notes') or '').strip() or None
        newly_published = False
        if 'publish' in data:
            newly_published = bool(data['publish']) and not session.is_published
            session.is_published = bool(data['publish'])
        save_blocks(session, blocks)
        db.session.commit()
        if newly_published:
            _announce_plan(session)
        return jsonify({'ok': True, 'blocks': [_block(c) for c in session.components.order_by(SessionComponent.order)],
                        'published': session.is_published})

    blocks = [_block(c) for c in session.components.order_by(SessionComponent.order)]
    drills = [{'id': d.id, 'title': d.title, 'duration_minutes': d.recommended_duration,
               'focus_area': d.focus_area or '', 'description': (d.description or '')[:400]}
              for d in SavedDrill.query.filter_by(team_organization_id=team_id).order_by(SavedDrill.title)]
    templates = SessionTemplate.query.filter_by(team_organization_id=team_id).order_by(SessionTemplate.name).all()
    recent = (SessionPlan.query.filter(SessionPlan.team_organization_id == team_id, SessionPlan.id != session.id,
                                       SessionPlan.components.any())
              .order_by(SessionPlan.date.desc().nullslast(), SessionPlan.id.desc()).limit(25).all())
    answers = rsvp.answers([session])
    answered = {pid for (_, pid) in answers}
    coming = {status: [] for status in rsvp.STATUSES + ('none',)}
    for p in rsvp.expected_players(session, answered=answered):
        a = answers.get((session.id, p.id))
        coming[a.status if a else 'none'].append(p)
    positions = {}
    for p in coming[rsvp.ATTENDING]:
        key = (p.position or 'other').lower()
        positions[key] = positions.get(key, 0) + 1
    return render_template('training/plan.html', session=session, blocks=blocks, drills=drills,
                           templates=templates, recent=recent, previous=_previous(session), coming=coming,
                           positions=positions, week=_season_week(session),
                           component_types=SessionComponent.COMPONENT_TYPE_CHOICES)


def _announce_plan(session):
    from app.discord import messages, notify
    try:
        notify.post(session.team_organization_id, messages.session_post(
            session, intro=f'📋 The plan for {session.title} ({messages.when(session)}) is up.'))
    except Exception:
        pass


@bp.route('/<int:session_id>/blocks.json')
@login_required
@coach_required
def blocks_json(session_id):
    session = _session_or_404(session_id)
    blocks = [_block(c) for c in session.components.order_by(SessionComponent.order)]
    for b in blocks:
        b['id'] = None  # copies, not the same blocks
    return jsonify({'title': session.title, 'blocks': blocks})


@bp.route('/templates', methods=['POST'])
@login_required
@coach_required
def save_template():
    team_id = get_current_team_id()
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()[:100]
    if not name:
        return jsonify({'ok': False, 'message': 'Give the template a name.'}), 400
    try:
        blocks = _clean_blocks(data.get('blocks', []), team_id)
    except ValueError as e:
        return jsonify({'ok': False, 'message': str(e)}), 400
    if not blocks:
        return jsonify({'ok': False, 'message': 'Add some blocks first.'}), 400
    for b in blocks:
        b.pop('id', None)
    template = SessionTemplate.query.filter_by(team_organization_id=team_id, name=name).first()
    if template is None:
        template = SessionTemplate(team_organization_id=team_id, name=name, created_by=current_user.id)
        db.session.add(template)
    template.blocks = blocks
    db.session.commit()
    return jsonify({'ok': True, 'id': template.id, 'name': template.name, 'blocks': template.blocks})


@bp.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@coach_required
def delete_template(template_id):
    template = SessionTemplate.query.filter_by(id=template_id,
                                               team_organization_id=get_current_team_id()).first_or_404()
    db.session.delete(template)
    db.session.commit()
    if _wants_json():
        return jsonify({'ok': True})
    flash('Template deleted.', 'success')
    return redirect(request.referrer or url_for('session.index'))
