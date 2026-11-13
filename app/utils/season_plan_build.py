"""Creating and reshaping a season plan on the website: the plan's weeks
follow from its start date and length, and each phase covers a run of weeks.

Everything here works on a plan that may also have been imported (markdown
or spreadsheet): imported weeks keep their own text, and changing the start
date or the number of weeks only re-dates or adds and trims weeks.
"""
import re
from datetime import date, datetime, timedelta

from slugify import slugify

from app import db
from app.models.season_plan import SeasonPlan, SeasonPhase, SeasonWeek, SeasonMilestone, SeasonPage
from app.utils.season_plan_import import PHASE_COLOURS, SQUAD_NAME_LIMIT

MAX_WEEKS = 60
MAX_SQUADS = 6


class PlanError(ValueError):
    """A problem with what a coach entered; the message is shown to them."""


def monday(day):
    return day - timedelta(days=day.weekday())


def week_label(start_week, end_week=None):
    if end_week and end_week != start_week:
        return f'Weeks {start_week}-{end_week}'
    return f'Week {start_week}'


def clean_squads(names):
    """Squad names, trimmed, without blanks or repeats (any case)."""
    out = []
    for name in names or []:
        name = re.sub(r'\s+', ' ', (name or '').strip())
        if not name:
            continue
        if len(name) > SQUAD_NAME_LIMIT:
            raise PlanError(f'Squad names can be at most {SQUAD_NAME_LIMIT} characters.')
        if name.lower() == 'joint':
            raise PlanError('"Joint" is the whole-club session; give the squad another name.')
        if name.lower() not in {n.lower() for n in out}:
            out.append(name)
    if len(out) > MAX_SQUADS:
        raise PlanError(f'A plan can have at most {MAX_SQUADS} squads with their own themes.')
    return out


# --------------------------------------------------------------------------
# Weeks and phases
# --------------------------------------------------------------------------

def set_dates(plan):
    """The plan's start and end from its weeks (or its phases)."""
    dated = [w.week_commencing for w in plan.weeks if w.week_commencing]
    if dated:
        plan.start_date = min(dated)
        plan.end_date = max(dated) + timedelta(days=6)


def redate_weeks(plan, start):
    """Week 1 (the first week) starts the Monday of `start`; each later week
    a week after the one before, in week-number order."""
    first = monday(start)
    for i, week in enumerate(sorted(plan.weeks, key=lambda w: w.week_number)):
        week.week_commencing = first + timedelta(weeks=i)
    set_dates(plan)
    assign_phases(plan)


def set_week_count(plan, count):
    """Add weeks to the end, or remove the last ones. Weeks with anything
    written in them aren't removed: returns the week numbers that were kept
    (and the count isn't reached)."""
    if not 1 <= count <= MAX_WEEKS:
        raise PlanError(f'A plan has between 1 and {MAX_WEEKS} weeks.')
    weeks = sorted(plan.weeks, key=lambda w: w.week_number)
    blocked = []
    while len(weeks) > count:
        week = weeks[-1]
        if week_has_content(week):
            blocked.append(week.week_number)
            break
        weeks.pop()
        plan.weeks.remove(week)
    if not weeks:
        start = monday(plan.start_date or date.today())
    else:
        start = None
    while len(weeks) < count:
        last = weeks[-1] if weeks else None
        week = SeasonWeek(team_organization_id=plan.team_organization_id,
                          week_number=(last.week_number + 1) if last else 1,
                          week_commencing=(last.week_commencing + timedelta(weeks=1)
                                           if last and last.week_commencing else start))
        plan.weeks.append(week)
        weeks.append(week)
    db.session.flush()
    set_dates(plan)
    assign_phases(plan)
    return blocked


def week_has_content(week):
    return bool(week.block or week.joint_theme or week.squad_themes or week.classroom or week.off_pitch
                or week.notes or week.session_detail_md or week.session_plan_id or week.classroom_sessions)


def assign_phases(plan):
    """Put each week in the phase whose week range holds it, and date each
    phase from its weeks."""
    by_number = {w.week_number: w for w in plan.weeks}
    for week in plan.weeks:
        week.phase = next((p for p in plan.phases if p.start_week and p.end_week
                           and p.start_week <= week.week_number <= p.end_week), None)
    for phase in plan.phases:
        first, last = by_number.get(phase.start_week), by_number.get(phase.end_week)
        if first and first.week_commencing:
            phase.start_date = first.week_commencing
        if last and last.week_commencing:
            phase.end_date = last.week_commencing + timedelta(days=6)


def renumber_phases(plan):
    """Number phases 1, 2, 3... in the order they start."""
    phases = sorted(plan.phases, key=lambda p: (p.start_week or 0, p.number))
    # Out of the way first: (plan, number) is unique
    for i, phase in enumerate(phases, start=1):
        phase.number = -i
    db.session.flush()
    for i, phase in enumerate(phases, start=1):
        phase.number = i
    db.session.flush()


def check_phase_range(plan, start_week, end_week, phase=None):
    numbers = {w.week_number for w in plan.weeks}
    if start_week not in numbers or end_week not in numbers:
        raise PlanError('Pick weeks that are in the plan.')
    if end_week < start_week:
        raise PlanError('A phase has to end on or after the week it starts.')
    for other in plan.phases:
        if other is phase or not (other.start_week and other.end_week):
            continue
        if start_week <= other.end_week and other.start_week <= end_week:
            raise PlanError(f'Those weeks overlap phase {other.number}, {other.name} '
                            f'(weeks {other.start_week}-{other.end_week}).')


def next_colour(plan):
    used = {p.colour for p in plan.phases}
    return next((c for c in PHASE_COLOURS if c not in used), PHASE_COLOURS[len(plan.phases) % len(PHASE_COLOURS)])


# --------------------------------------------------------------------------
# Squads
# --------------------------------------------------------------------------

def set_squads(plan, names, renames=None):
    """Set the plan's squads. `renames` maps an old name to its new one, so
    the squad's themes go with it; themes of squads that are removed are
    dropped."""
    names = clean_squads(names)
    renames = renames or {}
    for week in plan.weeks:
        old = week.squad_themes or {}
        new = {}
        for key, text in old.items():
            key = renames.get(key, key)
            if key in names and text:
                new[key] = text
        week.squad_themes = new or None
    plan.squad_names = names or None


# --------------------------------------------------------------------------
# Creating a plan
# --------------------------------------------------------------------------

def unique_slug(plan, title, current=None):
    base = slugify(title or 'page', max_length=80) or 'page'
    taken = {p.slug for p in plan.pages if p is not current}
    slug, n = base, 2
    while slug in taken:
        slug, n = f'{base}-{n}', n + 1
    return slug


def create_plan(team_id, title, season, start, phases, squads=(), template=None,
                players_see=True, sessions=None):
    """A new plan for `team_id` starting the week of `start`.

    phases: [(name, number of weeks)], one after another from week 1; the
    plan has as many weeks as the phases add up to. A template (see
    season_plan_templates) brings its own phases, weekly themes, milestones
    and pages instead. Becomes the team's current plan."""
    title = (title or '').strip()
    season = (season or '').strip()
    if not title:
        raise PlanError('Give the plan a title.')
    if len(title) > 200:
        raise PlanError('The title can be at most 200 characters.')
    if not season:
        raise PlanError('Say which season the plan is for, e.g. 2027 or 2027/28.')
    if len(season) > 20:
        raise PlanError('The season can be at most 20 characters.')
    if SeasonPlan.query.filter_by(team_organization_id=team_id, season=season).first():
        raise PlanError(f'There is already a plan for {season}. Open it from Plan settings, '
                        f'or pick another season.')
    if start is None:
        raise PlanError('Pick the date of the first week.')
    squads = clean_squads(squads)

    if template:
        phases = [(p['name'], p['weeks']) for p in template['phases']]
    phases = [(name.strip(), weeks) for name, weeks in phases if (name or '').strip()]
    if not phases:
        raise PlanError('Add at least one phase, with a name and its number of weeks.')
    for name, weeks in phases:
        if not isinstance(weeks, int) or weeks < 1:
            raise PlanError(f'Phase "{name}" needs at least one week.')
        if len(name) > 100:
            raise PlanError('Phase names can be at most 100 characters.')
    total = sum(weeks for _, weeks in phases)
    if total > MAX_WEEKS:
        raise PlanError(f'That adds up to {total} weeks; a plan can have at most {MAX_WEEKS}.')

    for other in SeasonPlan.query.filter_by(team_organization_id=team_id, is_active=True):
        other.is_active = False
    first = monday(start)
    plan = SeasonPlan(team_organization_id=team_id, title=title, season=season, is_active=True,
                      source='Created on the website' if not template else f'Template: {template["name"]}',
                      squad_names=squads or None,
                      summary=(template or {}).get('summary'),
                      players_see_overview=players_see, players_see_weeks=players_see,
                      players_see_phases=players_see)
    for key, value in (sessions or {}).items():
        setattr(plan, key, value)
    db.session.add(plan)
    for n in range(1, total + 1):
        plan.weeks.append(SeasonWeek(team_organization_id=team_id, week_number=n,
                                     week_commencing=first + timedelta(weeks=n - 1)))
    week = 1
    for i, (name, weeks) in enumerate(phases):
        details = template['phases'][i] if template else {}
        plan.phases.append(SeasonPhase(
            team_organization_id=team_id, number=i + 1, name=name, start_week=week, end_week=week + weeks - 1,
            colour=PHASE_COLOURS[i % len(PHASE_COLOURS)], aim=details.get('aim'),
            training_focus=details.get('focus'), events=details.get('events')))
        week += weeks
    db.session.flush()
    if template:
        apply_template_content(plan, template, squads)
    set_dates(plan)
    assign_phases(plan)
    db.session.flush()
    return plan


def apply_template_content(plan, template, squads):
    """A template's weekly themes, milestones and pages. Squad themes are
    given for "the first squad", "the second squad"...; they go to the
    plan's squads in order (or are left out with no squads)."""
    by_number = {w.week_number: w for w in plan.weeks}
    for n, row in template.get('weeks', {}).items():
        week = by_number.get(n)
        if week is None:
            continue
        week.block = row.get('block')
        week.joint_theme = row.get('theme')
        week.off_pitch = row.get('off_pitch')
        week.is_event = bool(row.get('event'))
        week.is_break = bool(row.get('break'))
        if squads and row.get('squads'):
            week.squad_themes = {squads[i]: text for i, text in enumerate(row['squads'])
                                 if i < len(squads) and text} or None
    for i, (start_week, end_week, what) in enumerate(template.get('milestones', []), start=1):
        plan.milestones.append(SeasonMilestone(
            team_organization_id=plan.team_organization_id, order=i,
            when_label=week_label(start_week, end_week), what=what,
            start_week=start_week, end_week=end_week))
    for i, (title, body) in enumerate(template.get('pages', []), start=1):
        page = SeasonPage(team_organization_id=plan.team_organization_id, title=title, order=i,
                          body_markdown=body, players_can_view=True)
        page.slug = unique_slug(plan, title)
        plan.pages.append(page)


def make_current(plan):
    for other in SeasonPlan.query.filter_by(team_organization_id=plan.team_organization_id, is_active=True):
        other.is_active = other.id == plan.id
    plan.is_active = True
    plan.updated_at = datetime.utcnow()
