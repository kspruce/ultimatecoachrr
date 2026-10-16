"""Season plan: phases, week-by-week themes, session notes and the plan's
long-form pages. Only for teams with the Season plan feature switched on;
for everyone else every page here is a 404.

Captains, coaches and admins see everything. Players see only the parts a
coach has opened to them (Season plan > Player access).

Classroom sessions (C1, C2, ...) have their own pages: prep and a join link
beforehand; the recording, slides, summary and commitments afterwards.
Videos and slides are links (embedded where the host allows it), never
uploads.
"""
from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db, login
from app.models.season_plan import (
    SeasonPlan, SeasonPhase, SeasonWeek, SeasonPage, ClassroomSession, ClassroomResource,
)
from app.models.session import SessionPlan
from app.models.team_settings import TeamSettings
from app.utils.media_embed import embed_url, is_web_url
from app.utils.season_sessions import WEEKDAYS, build_sessions, sync_week, week_sessions
from app.utils.team_filter import get_current_team_id
from app.utils.utils import coach_required

bp = Blueprint('season_plan', __name__, url_prefix='/season-plan')

SECTIONS = [
    ('overview', 'Overview', 'The phase timeline, this week and what is coming up'),
    ('weeks', 'Weeks', 'The week-by-week table and each week\'s themes'),
    ('session_notes', 'Session notes', 'The full session plan for each week'),
    ('phases', 'Phases', 'Each phase\'s aim, focus and strategic anchor'),
    ('classroom', 'Classroom sessions', 'Prep, join links, recordings, slides and published summaries'),
]
WEEK_TEXT_FIELDS = ['block', 'joint_theme', 'firsts_theme', 'seconds_theme', 'classroom',
                    'off_pitch', 'session_title', 'session_detail_md', 'notes']


def feature_enabled(team_id):
    if not team_id:
        return False
    settings = TeamSettings.query.filter_by(team_id=team_id).first()
    return bool(settings and settings.season_plan_enabled)


def sees_everything(user=None):
    """Coaches, captains and admins (captains are team admins, so is_coach
    covers all three)."""
    user = user or current_user
    return user.is_authenticated and user.is_coach


def active_plan(team_id):
    return (SeasonPlan.query.filter_by(team_organization_id=team_id, is_active=True)
            .order_by(SeasonPlan.start_date.desc()).first())


def can_see(plan, section):
    if sees_everything():
        return True
    if plan is None:
        return False
    if isinstance(section, SeasonPage):
        return section.players_can_view
    return bool(getattr(plan, f'players_see_{section}', False))


def visible_pages(plan):
    return [p for p in plan.pages if can_see(plan, p)] if plan else []


@bp.before_request
def check_feature():
    if not current_user.is_authenticated:
        return login.unauthorized()
    if not feature_enabled(get_current_team_id()):
        abort(404)


@bp.app_context_processor
def season_plan_nav():
    """season_plan_nav() is true when the nav should show Season plan: the
    feature is on and the user can see at least part of it."""
    def show():
        if not current_user.is_authenticated:
            return False
        team_id = get_current_team_id()
        if not feature_enabled(team_id):
            return False
        if sees_everything():
            return True
        plan = active_plan(team_id)
        return bool(plan and (any(can_see(plan, s) for s, _, _ in SECTIONS) or visible_pages(plan)))
    return {'season_plan_nav': show, 'season_plan_sees_all': sees_everything,
            'embed_url': embed_url}


def _plan_or_404():
    plan = active_plan(get_current_team_id())
    if plan is None:
        abort(404)
    return plan


def _require(plan, section):
    if not can_see(plan, section):
        abort(404)


def _today():
    """Today, or ?on=YYYY-MM-DD for coaches previewing another date."""
    on = request.args.get('on')
    if on and current_user.is_coach:
        try:
            return date.fromisoformat(on)
        except ValueError:
            flash('Preview dates look like 2027-10-04.', 'warning')
    return date.today()


def _week_status(plan, today):
    """(current week or None, the week to feature, a label for it)."""
    current = plan.week_for(today)
    if current:
        return current, current, 'This week'
    upcoming = next((w for w in plan.weeks if w.week_commencing and w.week_commencing > today), None)
    if upcoming:
        return None, upcoming, 'Next week' if (upcoming.week_commencing - today).days <= 7 else 'First up'
    return None, None, None


def _timeline(plan, today):
    start, end = plan.start_date, plan.end_date
    if not start or not end or end <= start:
        return None
    total = (end - start).days + 1

    def pct(d):
        return max(0.0, min(100.0, (d - start).days / total * 100))

    bands = []
    for phase in plan.phases:
        if phase.start_date and phase.end_date:
            left = pct(phase.start_date)
            bands.append({'phase': phase, 'left': left,
                          'width': max(pct(phase.end_date + timedelta(days=1)) - left, 1.5)})
    marker = pct(today) if start <= today <= end else None
    return {'bands': bands, 'marker': marker, 'start': start, 'end': end}


def _upcoming(plan, today):
    """The next event week and the next milestone (with its first week) that
    haven't finished by today."""
    next_event = next((w for w in plan.weeks if w.is_event and w.week_ending
                       and w.week_ending >= today), None)
    by_number = {w.week_number: w for w in plan.weeks}
    next_milestone = None
    for m in plan.milestones:
        first, last = by_number.get(m.start_week), by_number.get(m.end_week or m.start_week)
        if first and last and last.week_ending and last.week_ending >= today:
            next_milestone = (m, first)
            break
    return next_event, next_milestone


@bp.route('/')
def index():
    team_id = get_current_team_id()
    plan = active_plan(team_id)
    if plan is None:
        if not sees_everything():
            abort(404)
        return render_template('season_plan/empty.html')
    if not can_see(plan, 'overview'):
        # Send players to the first part they can see
        if can_see(plan, 'weeks'):
            return redirect(url_for('season_plan.weeks'))
        if can_see(plan, 'phases') and plan.phases:
            return redirect(url_for('season_plan.phase', number=plan.phases[0].number))
        if can_see(plan, 'classroom'):
            return redirect(url_for('season_plan.classroom_list'))
        pages = visible_pages(plan)
        if pages:
            return redirect(url_for('season_plan.page', slug=pages[0].slug))
        abort(404)

    today = _today()
    current, featured, featured_label = _week_status(plan, today)
    next_event, next_milestone = _upcoming(plan, today)
    featured_classroom = (classroom_cards(plan, featured.classroom_sessions, _now())
                          if featured and can_see(plan, 'classroom') else [])
    return render_template(
        'season_plan/overview.html', plan=plan, today=today, current=current,
        featured_classroom=featured_classroom,
        featured=featured, featured_label=featured_label, timeline=_timeline(plan, today),
        next_event=next_event, next_milestone=next_milestone, pages=visible_pages(plan),
        days_to_start=(plan.start_date - today).days if plan.start_date and today < plan.start_date else None)


@bp.route('/weeks')
def weeks():
    plan = _plan_or_404()
    _require(plan, 'weeks')
    today = _today()
    phase_no = request.args.get('phase', type=int)
    squad = request.args.get('squad', 'all')
    if squad not in ('all', '1s', '2s'):
        squad = 'all'
    rows = [w for w in plan.weeks if not phase_no or (w.phase and w.phase.number == phase_no)]
    current = plan.week_for(today)
    return render_template('season_plan/weeks.html', plan=plan, weeks=rows, phase_no=phase_no,
                           squad=squad, current=current, today=today, pages=visible_pages(plan),
                           link_classroom=can_see(plan, 'classroom'))


def _week_or_404(plan, number):
    week = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=number,
                                      team_organization_id=plan.team_organization_id).first()
    if week is None:
        abort(404)
    return week


@bp.route('/week/<int:number>')
def week(number):
    plan = _plan_or_404()
    _require(plan, 'weeks')
    wk = _week_or_404(plan, number)
    numbers = [w.week_number for w in plan.weeks]
    i = numbers.index(wk.week_number)
    prev_wk = plan.weeks[i - 1] if i > 0 else None
    next_wk = plan.weeks[i + 1] if i + 1 < len(plan.weeks) else None
    classroom_page = next((p for p in visible_pages(plan) if 'classroom' in p.slug), None)
    cards = classroom_cards(plan, wk.classroom_sessions, _now()) if can_see(plan, 'classroom') else []
    return render_template('season_plan/week.html', plan=plan, week=wk, prev_wk=prev_wk,
                           next_wk=next_wk, show_notes=can_see(plan, 'session_notes'),
                           classroom=cards,
                           show_phase=can_see(plan, 'phases'), classroom_page=classroom_page,
                           current=plan.week_for(date.today()), pages=visible_pages(plan),
                           built_sessions=week_sessions(plan, wk))


@bp.route('/week/<int:number>/edit', methods=['GET', 'POST'])
@coach_required
def edit_week(number):
    plan = _plan_or_404()
    wk = _week_or_404(plan, number)
    session_plans = (SessionPlan.query.filter_by(team_organization_id=plan.team_organization_id)
                     .order_by(SessionPlan.date.desc()).limit(200).all())

    if request.method == 'POST':
        for name in WEEK_TEXT_FIELDS:
            value = (request.form.get(name) or '').strip()
            limit = getattr(SeasonWeek, name).type.length
            if limit and len(value) > limit:
                flash(f'{name.replace("_", " ").capitalize()} must be at most {limit} characters.', 'danger')
                return render_template('season_plan/edit_week.html', plan=plan, week=wk,
                                       session_plans=session_plans, pages=visible_pages(plan)), 400
            setattr(wk, name, value or None)
        wk.is_event = bool(request.form.get('is_event'))
        wk.is_break = bool(request.form.get('is_break'))
        sp_id = request.form.get('session_plan_id', type=int)
        wk.session_plan_id = sp_id if sp_id and any(s.id == sp_id for s in session_plans) else None
        db.session.commit()
        flash(f'Week {wk.week_number} saved.', 'success')
        report = sync_week(plan, wk)
        if report and (report.rows or report.removed):
            flash(f'Sessions for week {wk.week_number}: {report.summary()}.', 'info')
        for warning in report.warnings if report else []:
            flash(warning, 'warning')
        return redirect(url_for('season_plan.week', number=wk.week_number))

    return render_template('season_plan/edit_week.html', plan=plan, week=wk,
                           session_plans=session_plans, pages=visible_pages(plan))


@bp.route('/phase/<int:number>')
def phase(number):
    plan = _plan_or_404()
    _require(plan, 'phases')
    ph = SeasonPhase.query.filter_by(plan_id=plan.id, number=number,
                                     team_organization_id=plan.team_organization_id).first_or_404()
    pages = visible_pages(plan)
    phase_page = next((p for p in pages if f'phase-{number}-' in p.slug or p.slug.endswith(f'phase-{number}')), None)
    return render_template('season_plan/phase.html', plan=plan, phase=ph, phase_page=phase_page,
                           show_weeks=can_see(plan, 'weeks'), current=plan.week_for(date.today()),
                           pages=pages)


@bp.route('/page/<slug>')
def page(slug):
    plan = _plan_or_404()
    pg = SeasonPage.query.filter_by(plan_id=plan.id, slug=slug,
                                    team_organization_id=plan.team_organization_id).first_or_404()
    _require(plan, pg)
    return render_template('season_plan/page.html', plan=plan, page=pg, pages=visible_pages(plan))


@bp.route('/access', methods=['GET', 'POST'])
@coach_required
def access():
    """Which parts of the plan players can see."""
    plan = _plan_or_404()
    if request.method == 'POST':
        for section, _, _ in SECTIONS:
            setattr(plan, f'players_see_{section}', bool(request.form.get(section)))
        for pg in plan.pages:
            pg.players_can_view = bool(request.form.get(f'page_{pg.id}'))
        db.session.commit()
        flash('Player access saved.', 'success')
        return redirect(url_for('season_plan.access'))
    return render_template('season_plan/access.html', plan=plan, sections=SECTIONS, pages=plan.pages)


SESSION_SETTINGS = ['joint_weekday', 'joint_start', 'joint_end',
                    'split_weekday', 'split_start', 'split_end', 'session_location']


def _read_session_settings(form):
    """Session settings from the form, or (None, error)."""
    values = {}
    for name in SESSION_SETTINGS:
        raw = (form.get(name) or '').strip()
        if name.endswith('weekday'):
            values[name] = int(raw) if raw.isdigit() and int(raw) < 7 else None
        elif name == 'session_location':
            if len(raw) > 100:
                return None, 'Location must be at most 100 characters.'
            values[name] = raw or None
        else:
            try:
                values[name] = time.fromisoformat(raw) if raw else None
            except ValueError:
                return None, 'Times look like 18:30.'
    return values, None


@bp.route('/sessions', methods=['GET', 'POST'])
@coach_required
def sessions():
    """Build the team's sessions from the plan's weekly session notes."""
    plan = _plan_or_404()
    form = {name: getattr(plan, name) for name in SESSION_SETTINGS}
    status = 200
    if request.method == 'POST':
        values, error = _read_session_settings(request.form)
        if error:
            flash(error, 'danger')
            status = 400
        else:
            form = values
            for name, value in values.items():
                setattr(plan, name, value)
            if request.form.get('action') == 'build':
                report = build_sessions(plan)
                flash(f'Sessions built from the plan: {report.summary()}.', 'success')
                for warning in report.warnings:
                    flash(warning, 'warning')
                return redirect(url_for('season_plan.sessions'))
    # A dry run shows what building would do (and undoes any unsaved settings)
    report = build_sessions(plan, dry_run=True)
    return render_template('season_plan/sessions.html', plan=plan, form=form, report=report,
                           weekdays=WEEKDAYS, pages=visible_pages(plan)), status


# --------------------------------------------------------------------------
# Classroom sessions
# --------------------------------------------------------------------------

CLASSROOM_TEXT_FIELDS = {  # form field -> max length (None = Text)
    'title': 200, 'format': 100, 'audience': 200, 'main_source': 200, 'goal': None,
    'prep_md': None, 'plan_md': None, 'summary_md': None, 'commitments_md': None,
}


def _now():
    """Now in the team's local time (naive, like starts_at). A coach's
    ?on=YYYY-MM-DD preview counts as midday on that date."""
    on = request.args.get('on')
    if on and current_user.is_coach:
        try:
            return datetime.combine(date.fromisoformat(on), time(12))
        except ValueError:
            pass
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(current_app.config.get('SEASON_PLAN_TIMEZONE', 'Europe/London'))
        return datetime.now(tz).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def visible_resources(cs):
    return [r for r in cs.resources if sees_everything() or not r.coaches_only]


def classroom_card(cs, now):
    """Everything a template needs to show one session to the current user."""
    resources = visible_resources(cs)
    show_summary = bool((cs.summary_md or cs.commitments_md)
                        and (cs.summary_published or sees_everything()))
    end = cs.ends_at()
    if cs.starts_at:
        start = cs.starts_at
    elif cs.week and cs.week.week_commencing:
        start = datetime.combine(cs.week.week_commencing, time.min)
    else:
        start = None

    if end and now > end:
        if any(r.kind == 'video' for r in resources):
            status = ('recording', 'Recording available')
        elif show_summary and cs.summary_published:
            status = ('summary', 'Summary available')
        else:
            status = ('done', 'Done')
    elif start and now >= start:
        status = ('now', 'Happening now' if cs.starts_at else 'This week')
    elif start and (start - now) <= timedelta(days=7):
        status = ('soon', 'Coming up')
    else:
        status = ('upcoming', 'Upcoming')

    return {
        's': cs, 'status': status[0], 'label': status[1], 'resources': resources,
        'video': next((r for r in resources if r.kind == 'video'), None),
        'show_summary': show_summary,
        'show_join': bool(cs.join_url and (end is None or now <= end)),
        'show_plan': sees_everything() and bool(cs.plan_md),
    }


def classroom_cards(plan, sessions, now):
    return [classroom_card(cs, now) for cs in sessions]


def _classroom_or_404(plan, code):
    cs = ClassroomSession.query.filter_by(plan_id=plan.id, code=code.upper(),
                                          team_organization_id=plan.team_organization_id).first()
    if cs is None:
        abort(404)
    return cs


@bp.route('/classroom')
def classroom_list():
    plan = _plan_or_404()
    _require(plan, 'classroom')
    now = _now()
    cards = classroom_cards(plan, plan.classroom_sessions, now)
    next_card = next((c for c in cards if c['status'] in ('now', 'soon', 'upcoming')), None)
    return render_template('season_plan/classroom_list.html', plan=plan, cards=cards,
                           next_card=next_card, now=now, pages=visible_pages(plan))


@bp.route('/classroom/<code>')
def classroom(code):
    plan = _plan_or_404()
    _require(plan, 'classroom')
    cs = _classroom_or_404(plan, code)
    sessions = plan.classroom_sessions
    i = sessions.index(cs)
    return render_template('season_plan/classroom.html', plan=plan, card=classroom_card(cs, _now()),
                           prev_cs=sessions[i - 1] if i > 0 else None,
                           next_cs=sessions[i + 1] if i + 1 < len(sessions) else None,
                           show_week=can_see(plan, 'weeks'), pages=visible_pages(plan))


def _parse_start(form):
    """starts_at from the date and time inputs; (value, error)."""
    day, at = (form.get('start_date') or '').strip(), (form.get('start_time') or '').strip()
    if not day:
        return None, None
    try:
        start_day = date.fromisoformat(day)
        start_time = time.fromisoformat(at) if at else time(19, 0)
    except ValueError:
        return None, 'Dates look like 2027-10-20 and times like 19:30.'
    return datetime.combine(start_day, start_time), None


@bp.route('/classroom/<code>/edit', methods=['GET', 'POST'])
@coach_required
def edit_classroom(code):
    plan = _plan_or_404()
    cs = _classroom_or_404(plan, code)

    def form_again(error):
        flash(error, 'danger')
        return render_template('season_plan/edit_classroom.html', plan=plan, cs=cs,
                               kinds=ClassroomResource.KINDS, pages=visible_pages(plan)), 400

    if request.method == 'POST':
        values = {}
        for name, limit in CLASSROOM_TEXT_FIELDS.items():
            value = (request.form.get(name) or '').strip()
            if limit and len(value) > limit:
                return form_again(f'{name.replace("_", " ").capitalize()} must be at most {limit} characters.')
            values[name] = value or None
        if not values['title']:
            return form_again('A session needs a title.')
        join_url = (request.form.get('join_url') or '').strip()
        if join_url and (not is_web_url(join_url) or len(join_url) > 500):
            return form_again('The join link must be a web address starting with https://')
        starts_at, error = _parse_start(request.form)
        if error:
            return form_again(error)
        duration = request.form.get('duration_minutes', type=int)
        if duration is not None and not 5 <= duration <= 600:
            return form_again('Length must be between 5 and 600 minutes.')

        for name, value in values.items():
            setattr(cs, name, value)
        cs.join_url = join_url or None
        cs.starts_at = starts_at
        cs.duration_minutes = duration
        cs.summary_published = bool(request.form.get('summary_published'))
        db.session.commit()
        flash(f'{cs.code} saved.', 'success')
        return redirect(url_for('season_plan.classroom', code=cs.code))

    return render_template('season_plan/edit_classroom.html', plan=plan, cs=cs,
                           kinds=ClassroomResource.KINDS, pages=visible_pages(plan))


@bp.route('/classroom/<code>/resources', methods=['POST'])
@coach_required
def add_classroom_resource(code):
    plan = _plan_or_404()
    cs = _classroom_or_404(plan, code)
    kind = request.form.get('kind') or 'link'
    title = (request.form.get('title') or '').strip()
    url = (request.form.get('url') or '').strip()
    back = redirect(url_for('season_plan.edit_classroom', code=cs.code) + '#resources')
    if kind not in dict(ClassroomResource.KINDS):
        kind = 'link'
    if not is_web_url(url) or len(url) > 500:
        flash('Links must be web addresses starting with https://', 'danger')
        return back
    if len(title) > 200:
        flash('Titles must be at most 200 characters.', 'danger')
        return back
    cs.resources.append(ClassroomResource(
        team_organization_id=plan.team_organization_id, kind=kind,
        title=title or dict(ClassroomResource.KINDS)[kind], url=url,
        order=max((r.order for r in cs.resources), default=0) + 1,
        coaches_only=bool(request.form.get('coaches_only'))))
    db.session.commit()
    flash('Added.', 'success')
    return back


def _resource_or_404(cs, resource_id):
    resource = next((r for r in cs.resources if r.id == resource_id), None)
    if resource is None:
        abort(404)
    return resource


@bp.route('/classroom/<code>/resources/<int:resource_id>/delete', methods=['POST'])
@coach_required
def delete_classroom_resource(code, resource_id):
    plan = _plan_or_404()
    cs = _classroom_or_404(plan, code)
    cs.resources.remove(_resource_or_404(cs, resource_id))
    db.session.commit()
    flash('Removed.', 'success')
    return redirect(url_for('season_plan.edit_classroom', code=cs.code) + '#resources')


@bp.route('/classroom/<code>/resources/<int:resource_id>/move', methods=['POST'])
@coach_required
def move_classroom_resource(code, resource_id):
    plan = _plan_or_404()
    cs = _classroom_or_404(plan, code)
    items = list(cs.resources)
    resource = _resource_or_404(cs, resource_id)
    i = items.index(resource)
    j = i - 1 if request.form.get('direction') == 'up' else i + 1
    if 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
        for n, item in enumerate(items, start=1):
            item.order = n
        db.session.commit()
    return redirect(url_for('season_plan.edit_classroom', code=cs.code) + '#resources')
