"""Season plan: creating and editing a plan on the website (coaches,
captains and admins only).

- Create a plan: dates, phases, squads and training days, from scratch or
  from a starter template.
- Plan settings: title, season, dates, number of weeks, squads; switch
  between the team's plans.
- Phases, milestones and pages.
- Import a spreadsheet (preview first) and export the plan as one.

The routes are on the season plan blueprint, so the feature switch and the
login check in season_plan.check_feature apply.
"""
from datetime import date, time

from flask import Response, abort, flash, redirect, render_template, request, url_for
from slugify import slugify

from app import db
from app.models.programme import Programme
from app.models.season import Squad
from app.models.season_plan import SeasonPlan, SeasonPhase, SeasonPage, SeasonMilestone
from app.models.team_organization import TeamOrganization
from app.routes.season_plan import bp, _plan_or_404, active_plan, visible_pages
from app.utils import season_plan_build as build
from app.utils import season_plan_sheet as sheet
from app.utils.programme_import import rows_from_csv, rows_from_xlsx, rows_to_csv
from app.utils.season_plan_import import SeasonPlanImportError, write_plan
from app.utils.season_plan_templates import BY_KEY as TEMPLATES_BY_KEY, TEMPLATES, template_weeks
from app.utils.season_sessions import WEEKDAYS, sync_week
from app.utils.team_filter import get_current_team_id
from app.utils.utils import coach_required

MAX_UPLOAD = 5 * 1024 * 1024


def _team_id():
    team_id = get_current_team_id()
    if not team_id:
        abort(404)
    return team_id


def _team_squads(team_id):
    return [q.name for q in Squad.query.filter_by(team_organization_id=team_id).order_by(Squad.sort_order, Squad.name)]


def _date(name):
    raw = (request.form.get(name) or '').strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise build.PlanError('Dates look like 2027-10-04.')


def _int(name):
    raw = (request.form.get(name) or '').strip()
    return int(raw) if raw.isdigit() else None


def _time(name):
    raw = (request.form.get(name) or '').strip()
    if not raw:
        return None
    try:
        return time.fromisoformat(raw)
    except ValueError:
        raise build.PlanError('Times look like 18:30.')


def _text(name, limit=None):
    value = (request.form.get(name) or '').strip()
    if limit and len(value) > limit:
        raise build.PlanError(f'{name.replace("_", " ").capitalize()} can be at most {limit} characters.')
    return value or None


def _default_season(today=None):
    today = today or date.today()
    # Most club seasons start in the autumn and run into the next year
    return f'{today.year}/{str(today.year + 1)[2:]}' if today.month >= 8 else str(today.year)


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------

@bp.route('/new', methods=['GET', 'POST'])
@coach_required
def new_plan():
    team_id = _team_id()
    team = db.session.get(TeamOrganization, team_id)
    team_squads = _team_squads(team_id)
    form = request.form if request.method == 'POST' else {
        'title': f'{team.name} season plan' if team else 'Season plan',
        'season': _default_season(), 'template': request.args.get('template', ''),
        'players_see': 'on',
    }
    default_phases = [('Foundations', 4), ('Building', 4), ('Competing', 6), ('Peak and review', 2)]

    if request.method == 'POST':
        try:
            template = TEMPLATES_BY_KEY.get(request.form.get('template') or '')
            names = request.form.getlist('phase_name')
            lengths = request.form.getlist('phase_weeks')
            phases = []
            for name, weeks in zip(names, lengths):
                weeks = (weeks or '').strip()
                if (name or '').strip() and not weeks.isdigit():
                    raise build.PlanError(f'Say how many weeks phase "{name.strip()}" lasts.')
                phases.append((name, int(weeks) if weeks.isdigit() else 0))
            squads = request.form.getlist('squad') + (request.form.get('other_squads') or '').split(',')
            sessions = {
                'joint_weekday': _int('joint_weekday'), 'joint_start': _time('joint_start'),
                'joint_end': _time('joint_end'), 'split_weekday': _int('split_weekday'),
                'split_start': _time('split_start'), 'split_end': _time('split_end'),
                'session_location': _text('session_location', 100),
            }
            for key in ('joint_weekday', 'split_weekday'):
                if sessions[key] is not None and sessions[key] > 6:
                    sessions[key] = None
            plan = build.create_plan(
                team_id, request.form.get('title'), request.form.get('season'), _date('start_date'),
                phases, squads=squads, template=template, players_see=bool(request.form.get('players_see')),
                sessions=sessions)
        except build.PlanError as e:
            db.session.rollback()
            flash(str(e), 'danger')
        else:
            db.session.commit()
            flash(f'{plan.title} created: {len(plan.weeks)} weeks in {len(plan.phases)} phases. '
                  'Open a week to fill in its theme and session notes.', 'success')
            return redirect(url_for('season_plan.index'))
        status = 400
    else:
        status = 200
    if request.method == 'POST':
        phase_rows = list(zip(request.form.getlist('phase_name'), request.form.getlist('phase_weeks'))) \
            or default_phases
        picked = request.form.getlist('squad')
    else:
        phase_rows, picked = default_phases, []
    return render_template('season_plan/new.html', form=form, templates=TEMPLATES, template_weeks=template_weeks,
                           team_squads=team_squads, weekdays=WEEKDAYS, phase_rows=phase_rows,
                           picked_squads=picked, plan=None), status


# --------------------------------------------------------------------------
# Plan settings
# --------------------------------------------------------------------------

def _edit(template, plan, **kw):
    return render_template(f'season_plan/{template}', plan=plan, pages=visible_pages(plan), **kw)


@bp.route('/settings', methods=['GET', 'POST'])
@coach_required
def settings():
    plan = _plan_or_404()
    team_id = plan.team_organization_id
    status = 200
    if request.method == 'POST':
        try:
            title = _text('title', 200)
            season = _text('season', 20)
            if not title or not season:
                raise build.PlanError('A plan needs a title and a season.')
            clash = SeasonPlan.query.filter(SeasonPlan.team_organization_id == team_id,
                                            SeasonPlan.season == season, SeasonPlan.id != plan.id).first()
            if clash:
                raise build.PlanError(f'Another plan is already for {season}.')
            start = _date('start_date')
            weeks = _int('week_count')
            # Squads: existing ones by position (renamed or removed), then new ones
            names, renames = [], {}
            for i, old in enumerate(plan.squads):
                if request.form.get(f'remove_squad_{i}'):
                    continue
                new = (request.form.get(f'squad_{i}') or '').strip() or old
                names.append(new)
                if new != old:
                    renames[old] = new
            names += [n for n in request.form.getlist('new_squad') if n.strip()]

            if season != plan.season and plan.sessions_built_at:
                flash('Sessions built from the plan keep the old season in their links; '
                      'build them again from Sessions to bring them in line.', 'info')
            plan.title, plan.season, plan.summary = title, season, _text('summary')
            build.set_squads(plan, names, renames)
            blocked = []
            if weeks and weeks != len(plan.weeks):
                blocked = build.set_week_count(plan, weeks)
            if start and start != plan.start_date:
                build.redate_weeks(plan, start)
        except build.PlanError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            status = 400
        else:
            db.session.commit()
            if blocked:
                flash(f'Week {blocked[0]} has notes or themes, so it and the weeks before it were kept. '
                      'Clear it first to remove it.', 'warning')
            flash('Plan settings saved.', 'success')
            return redirect(url_for('season_plan.settings'))
    plans = (SeasonPlan.query.filter_by(team_organization_id=team_id)
             .order_by(SeasonPlan.start_date.desc().nullslast()).all())
    return _edit('settings.html', plan, plans=plans, team_squads=_team_squads(team_id)), status


def _team_plan_or_404(plan_id):
    plan = SeasonPlan.query.filter_by(id=plan_id, team_organization_id=_team_id()).first()
    if plan is None:
        abort(404)
    return plan


@bp.route('/plans/<int:plan_id>/current', methods=['POST'])
@coach_required
def make_current(plan_id):
    plan = _team_plan_or_404(plan_id)
    build.make_current(plan)
    db.session.commit()
    flash(f'{plan.title} is now the plan everyone sees.', 'success')
    return redirect(url_for('season_plan.index'))


@bp.route('/plans/<int:plan_id>/delete', methods=['POST'])
@coach_required
def delete_plan(plan_id):
    plan = _team_plan_or_404(plan_id)
    if (request.form.get('confirm') or '').strip() != plan.season:
        flash(f'Type the season ({plan.season}) to delete the plan.', 'danger')
        return redirect(url_for('season_plan.settings'))
    title, team_id = plan.title, plan.team_organization_id
    db.session.delete(plan)
    db.session.flush()
    remaining = active_plan(team_id) or SeasonPlan.query.filter_by(
        team_organization_id=team_id).order_by(SeasonPlan.start_date.desc()).first()
    if remaining:
        build.make_current(remaining)
    db.session.commit()
    flash(f'{title} deleted. Sessions built from it are kept.', 'success')
    return redirect(url_for('season_plan.index'))


# --------------------------------------------------------------------------
# Phases
# --------------------------------------------------------------------------

def _programmes(team_id):
    return (Programme.query.filter_by(team_organization_id=team_id, kind='programme', archived=False)
            .order_by(Programme.start_date.desc().nullslast(), Programme.name).all())


def _phase_or_404(plan, number):
    phase = SeasonPhase.query.filter_by(plan_id=plan.id, number=number,
                                        team_organization_id=plan.team_organization_id).first()
    if phase is None:
        abort(404)
    return phase


@bp.route('/phases')
@coach_required
def phases():
    plan = _plan_or_404()
    unassigned = [w.week_number for w in plan.weeks if w.phase is None]
    return _edit('phases.html', plan, unassigned=unassigned)


@bp.route('/phases/new', methods=['GET', 'POST'])
@bp.route('/phases/<int:number>/edit', methods=['GET', 'POST'])
@coach_required
def edit_phase(number=None):
    plan = _plan_or_404()
    phase = _phase_or_404(plan, number) if number is not None else None
    programmes = _programmes(plan.team_organization_id)
    if request.method == 'POST':
        try:
            name = _text('name', 100)
            if not name:
                raise build.PlanError('Give the phase a name.')
            start_week, end_week = _int('start_week'), _int('end_week')
            if start_week is None or end_week is None:
                raise build.PlanError('Pick the first and last week of the phase.')
            build.check_phase_range(plan, start_week, end_week, phase)
            colour = (request.form.get('colour') or '').strip()
            programme_id = _int('programme_id')
            if programme_id and not any(p.id == programme_id for p in programmes):
                programme_id = None
            if phase is None:
                phase = SeasonPhase(team_organization_id=plan.team_organization_id,
                                    number=max((p.number for p in plan.phases), default=0) + 1,
                                    colour=build.next_colour(plan))
                plan.phases.append(phase)
            phase.name, phase.start_week, phase.end_week = name, start_week, end_week
            for field in ('aim', 'training_focus', 'events', 'strategic_anchor'):
                setattr(phase, field, _text(field))
            if len(colour) == 7 and colour.startswith('#'):
                phase.colour = colour
            phase.programme_id = programme_id
            db.session.flush()
            build.renumber_phases(plan)
            build.assign_phases(plan)
        except build.PlanError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            return _edit('edit_phase.html', plan, phase=phase, form=request.form, programmes=programmes), 400
        db.session.commit()
        _sync_built_sessions(plan)
        flash(f'Phase {phase.number}, {phase.name}, saved.', 'success')
        return redirect(url_for('season_plan.phases'))
    if phase is None:
        # Suggest the first weeks not yet in a phase
        free = [w.week_number for w in plan.weeks if w.phase is None]
        form = {'start_week': free[0] if free else '', 'end_week': free[-1] if free else ''}
    else:
        form = {}
    return _edit('edit_phase.html', plan, phase=phase, form=form, programmes=programmes)


@bp.route('/phases/<int:number>/delete', methods=['POST'])
@coach_required
def delete_phase(number):
    plan = _plan_or_404()
    phase = _phase_or_404(plan, number)
    name = phase.name
    for week in list(phase.weeks):
        week.phase = None
    plan.phases.remove(phase)
    db.session.flush()
    build.renumber_phases(plan)
    build.assign_phases(plan)
    db.session.commit()
    _sync_built_sessions(plan)
    flash(f'Phase "{name}" removed. Its weeks are kept, outside any phase.', 'success')
    return redirect(url_for('season_plan.phases'))


def _sync_built_sessions(plan):
    """Sessions built from the plan carry their phase; keep them in step."""
    if plan.sessions_built_at:
        for week in plan.weeks:
            sync_week(plan, week)


# --------------------------------------------------------------------------
# Milestones
# --------------------------------------------------------------------------

@bp.route('/milestones', methods=['GET', 'POST'])
@coach_required
def milestones():
    plan = _plan_or_404()
    numbers = {w.week_number for w in plan.weeks}
    if request.method == 'POST':
        rows = []
        whats = request.form.getlist('what')
        whens = request.form.getlist('when')
        starts = request.form.getlist('start_week')
        ends = request.form.getlist('end_week')
        removes = set(request.form.getlist('remove'))
        try:
            for i, what in enumerate(whats):
                what = (what or '').strip()
                if not what or str(i) in removes:
                    continue
                start = int(starts[i]) if i < len(starts) and starts[i].isdigit() else None
                end = int(ends[i]) if i < len(ends) and ends[i].isdigit() else None
                if start and start not in numbers or end and end not in numbers:
                    raise build.PlanError(f'"{what[:40]}": pick weeks that are in the plan.')
                if start and end and end < start:
                    start, end = end, start
                if end and not start:
                    start, end = end, None
                when = (whens[i] if i < len(whens) else '').strip()
                if not when and not start:
                    raise build.PlanError(f'"{what[:40]}": pick a week, or say when in words.')
                rows.append({'what': what, 'when_label': (when or build.week_label(start, end))[:100],
                             'start_week': start, 'end_week': end or start})
        except build.PlanError as e:
            flash(str(e), 'danger')
            return _edit('milestones.html', plan), 400
        rows.sort(key=lambda r: (r['start_week'] is None, r['start_week'] or 0))
        plan.milestones.clear()
        db.session.flush()
        for i, row in enumerate(rows, start=1):
            plan.milestones.append(SeasonMilestone(team_organization_id=plan.team_organization_id, order=i, **row))
        db.session.commit()
        flash('Milestones saved.', 'success')
        return redirect(url_for('season_plan.milestones'))
    return _edit('milestones.html', plan)


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def _page_or_404(plan, slug):
    page = SeasonPage.query.filter_by(plan_id=plan.id, slug=slug,
                                      team_organization_id=plan.team_organization_id).first()
    if page is None:
        abort(404)
    return page


@bp.route('/pages')
@coach_required
def page_list():
    plan = _plan_or_404()
    return _edit('page_list.html', plan, all_pages=plan.pages)


@bp.route('/pages/new', methods=['GET', 'POST'])
@bp.route('/page/<slug>/edit', methods=['GET', 'POST'])
@coach_required
def edit_page(slug=None):
    plan = _plan_or_404()
    page = _page_or_404(plan, slug) if slug else None
    if request.method == 'POST':
        try:
            title = _text('title', 200)
            if not title:
                raise build.PlanError('Give the page a title.')
        except build.PlanError as e:
            flash(str(e), 'danger')
            return _edit('edit_page.html', plan, page=page, form=request.form), 400
        if page is None:
            page = SeasonPage(team_organization_id=plan.team_organization_id,
                              order=max((p.order for p in plan.pages), default=0) + 1)
            page.slug = build.unique_slug(plan, title)
            plan.pages.append(page)
        page.title = title
        page.body_markdown = (request.form.get('body_markdown') or '').strip() or None
        page.players_can_view = bool(request.form.get('players_can_view'))
        db.session.commit()
        flash(f'"{page.title}" saved.', 'success')
        return redirect(url_for('season_plan.page', slug=page.slug))
    return _edit('edit_page.html', plan, page=page, form={})


@bp.route('/page/<slug>/delete', methods=['POST'])
@coach_required
def delete_page(slug):
    plan = _plan_or_404()
    page = _page_or_404(plan, slug)
    plan.pages.remove(page)
    db.session.commit()
    flash(f'"{page.title}" deleted.', 'success')
    return redirect(url_for('season_plan.page_list'))


@bp.route('/page/<slug>/move', methods=['POST'])
@coach_required
def move_page(slug):
    plan = _plan_or_404()
    pages = list(plan.pages)
    page = _page_or_404(plan, slug)
    i = pages.index(page)
    j = i - 1 if request.form.get('direction') == 'up' else i + 1
    if 0 <= j < len(pages):
        pages[i], pages[j] = pages[j], pages[i]
        for n, p in enumerate(pages, start=1):
            p.order = n
        db.session.commit()
    return redirect(url_for('season_plan.page_list'))


# --------------------------------------------------------------------------
# Spreadsheet import and export
# --------------------------------------------------------------------------

XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def _csv_response(rows, filename):
    return Response(rows_to_csv([[_safe(c) for c in r] for r in rows]), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def _safe(value):
    """Stop spreadsheet apps running a cell as a formula."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@') and not text.lstrip('-').replace('.', '').isdigit() \
        else text


@bp.route('/import/template.xlsx')
@coach_required
def import_template_xlsx():
    return Response(sheet.workbook_bytes(), mimetype=XLSX,
                    headers={'Content-Disposition': 'attachment; filename="season-plan-template.xlsx"'})


@bp.route('/import/template-weeks.csv')
@coach_required
def import_template_csv():
    return _csv_response(sheet.weeks_csv_rows(), 'season-plan-weeks.csv')


@bp.route('/export.xlsx')
@coach_required
def export_xlsx():
    plan = _plan_or_404()
    name = slugify(f'{plan.title} {plan.season}', max_length=80) or 'season-plan'
    return Response(sheet.workbook_bytes(plan), mimetype=XLSX,
                    headers={'Content-Disposition': f'attachment; filename="{name}.xlsx"'})


def _uploaded_sheets():
    """(weeks rows, phase rows, milestone rows, file name, problem)."""
    upload = request.files.get('file')
    if upload and upload.filename:
        filename = upload.filename[:200]
        data = upload.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            return None, None, None, filename, 'That file is over 5 MB.'
        if filename.lower().endswith('.xlsx'):
            try:
                sheets = rows_from_xlsx(data)
            except Exception:
                return None, None, None, filename, 'That file couldn\'t be read as an .xlsx spreadsheet.'
            names = [n for n in sheets if n not in ('instructions', 'phases', 'milestones')]
            weeks = sheets.get('weeks') or (sheets[names[0]] if names else [])
            return weeks, sheets.get('phases') or [], sheets.get('milestones') or [], filename, None
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            return None, None, None, filename, 'Save the spreadsheet as CSV (UTF-8) or .xlsx and try again.'
        return rows_from_csv(text), [], [], filename, None
    return (rows_from_csv(request.form.get('weeks_csv', '')), rows_from_csv(request.form.get('phases_csv', '')),
            rows_from_csv(request.form.get('milestones_csv', '')), request.form.get('filename') or None, None)


@bp.route('/import', methods=['GET', 'POST'])
@coach_required
def import_sheet():
    team_id = _team_id()
    current = active_plan(team_id)
    if request.method == 'GET':
        form = {'season': current.season if current else _default_season(),
                'title': current.title if current else '',
                'start_date': current.start_date.isoformat() if current and current.start_date else ''}
        return render_template('season_plan/import.html', parsed=None, form=form, plan=current,
                               pages=visible_pages(current) if current else [])

    weeks, phase_rows, milestone_rows, filename, problem = _uploaded_sheets()
    form = dict(request.form)
    if problem:
        flash(problem, 'danger')
        return render_template('season_plan/import.html', parsed=None, form=form, plan=current,
                               pages=visible_pages(current) if current else []), 400
    season = (request.form.get('season') or '').strip()[:20]
    try:
        start = _date('start_date')
    except build.PlanError as e:
        flash(str(e), 'danger')
        start = None
    existing = SeasonPlan.query.filter_by(team_organization_id=team_id, season=season).first() if season else None
    title = (request.form.get('title') or '').strip()[:200] or (existing.title if existing else None) \
        or f'Season plan {season}'
    parsed = sheet.parse_sheets(weeks, phase_rows, milestone_rows, start=start, season=season, title=title,
                                summary=existing.summary if existing else None)
    if not season:
        parsed['errors'].insert(0, 'Say which season the plan is for, e.g. 2027 or 2027/28.')
    form.update(weeks_csv=rows_to_csv(weeks), phases_csv=rows_to_csv(phase_rows) if phase_rows else '',
                milestones_csv=rows_to_csv(milestone_rows) if milestone_rows else '', filename=filename or '',
                season=season, title=title)

    if request.form.get('confirm') and not parsed['errors']:
        team = db.session.get(TeamOrganization, team_id)
        try:
            report = write_plan(parsed, team)
        except SeasonPlanImportError as e:
            parsed['errors'] += e.errors
        else:
            plan = db.session.get(SeasonPlan, report.plan_id)
            build.make_current(plan)
            if report.plan_created:
                plan.players_see_overview = plan.players_see_weeks = plan.players_see_phases = \
                    bool(request.form.get('players_see'))
            db.session.commit()
            done = 'Created' if report.plan_created else 'Updated'
            flash(f'{done} {plan.title}: {len(parsed["weeks"])} weeks, {len(parsed["phases"])} phases, '
                  f'{len(parsed["milestones"])} milestones.', 'success')
            for line in report.removed:
                flash(f'Removed {line}.', 'info')
            if report.sessions:
                flash(f'Sessions from the plan: {report.sessions.summary()}.', 'info')
            return redirect(url_for('season_plan.index'))
    return render_template('season_plan/import.html', parsed=parsed, form=form, plan=current, existing=existing,
                           pages=visible_pages(current) if current else [])
