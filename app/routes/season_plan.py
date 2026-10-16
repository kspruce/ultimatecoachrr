"""Season plan: phases, week-by-week themes, session notes and the plan's
long-form pages. Only for teams with the Season plan feature switched on;
for everyone else every page here is a 404.

Captains, coaches and admins see everything. Players see only the parts a
coach has opened to them (Season plan > Player access).
"""
from datetime import date, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db, login
from app.models.season_plan import SeasonPlan, SeasonPhase, SeasonWeek, SeasonPage
from app.models.session import SessionPlan
from app.models.team_settings import TeamSettings
from app.models.user import ROLE_ORDER
from app.utils.team_filter import get_current_team_id
from app.utils.utils import coach_required

bp = Blueprint('season_plan', __name__, url_prefix='/season-plan')

SECTIONS = [
    ('overview', 'Overview', 'The phase timeline, this week and what is coming up'),
    ('weeks', 'Weeks', 'The week-by-week table and each week\'s themes'),
    ('session_notes', 'Session notes', 'The full session plan for each week'),
    ('phases', 'Phases', 'Each phase\'s aim, focus and strategic anchor'),
]
WEEK_TEXT_FIELDS = ['block', 'joint_theme', 'firsts_theme', 'seconds_theme', 'classroom',
                    'off_pitch', 'session_title', 'session_detail_md', 'notes']


def feature_enabled(team_id):
    if not team_id:
        return False
    settings = TeamSettings.query.filter_by(team_id=team_id).first()
    return bool(settings and settings.season_plan_enabled)


def sees_everything(user=None):
    user = user or current_user
    return user.is_authenticated and (user.is_coach or user.role_level() >= ROLE_ORDER['captain'])


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
    return {'season_plan_nav': show, 'season_plan_sees_all': sees_everything}


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
        pages = visible_pages(plan)
        if pages:
            return redirect(url_for('season_plan.page', slug=pages[0].slug))
        abort(404)

    today = _today()
    current, featured, featured_label = _week_status(plan, today)
    next_event, next_milestone = _upcoming(plan, today)
    return render_template(
        'season_plan/overview.html', plan=plan, today=today, current=current,
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
                           squad=squad, current=current, today=today, pages=visible_pages(plan))


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
    return render_template('season_plan/week.html', plan=plan, week=wk, prev_wk=prev_wk,
                           next_wk=next_wk, show_notes=can_see(plan, 'session_notes'),
                           show_phase=can_see(plan, 'phases'), classroom_page=classroom_page,
                           current=plan.week_for(date.today()), pages=visible_pages(plan))


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
