"""Season plan: the year on one page (coaches), and a phase's training
programme on each of its weeks.

The year shows the current plan's phases and the club's training
programmes (e.g. the off-season fitness plan) on one timeline, so a coach
sees what players are asked to do at any point. Linking a programme to a
phase (Edit plan > Phases) puts that week's programme sessions on each
week of the phase.
"""
from datetime import date, timedelta

from flask import redirect, render_template, url_for

from app.models.programme import Programme
from app.routes.season_plan import bp, _today, active_plan, visible_pages
from app.utils.team_filter import get_current_team_id
from app.utils import programmes as svc
from app.utils.utils import coach_required

LOOK_BACK = timedelta(weeks=26)  # programmes that finished up to half a year before the plan


def programme_span(programme):
    """(start, end) of a calendar programme's live (or draft) version."""
    version = programme.published or programme.draft
    if programme.schedule_mode != 'calendar' or not programme.start_date or version is None:
        return None, None
    return programme.start_date, svc.end_date(programme, version) or programme.start_date + timedelta(days=6)


def programme_week(programme, week_commencing):
    """[(track, week)] of a programme's published version that fall in the
    plan week starting `week_commencing` (calendar programmes only)."""
    version = programme.published if programme else None
    if version is None or programme.schedule_mode != 'calendar' or not week_commencing:
        return []
    end = week_commencing + timedelta(days=6)
    out = []
    for track in version.tracks:
        for week in track.weeks:
            start = svc.week_start(programme, track, week)
            if start and week_commencing <= start <= end:
                out.append((track, week))
    return out


@bp.route('/year')
@coach_required
def year():
    plan = active_plan(get_current_team_id())
    if plan is None:
        return redirect(url_for('season_plan.index'))  # the ways to make one
    today = _today()
    team_id = plan.team_organization_id
    programmes = (Programme.query.filter_by(team_organization_id=team_id, kind='programme', archived=False)
                  .order_by(Programme.start_date).all())
    start, end = plan.start_date, plan.end_date
    rows, relative = [], []
    for p in programmes:
        p_start, p_end = programme_span(p)
        if p_start is None:
            if p.schedule_mode == 'relative' and (p.published or p.draft):
                relative.append(p)
            continue
        if start and end and (p_end < start - LOOK_BACK or p_start > end):
            continue
        rows.append({'programme': p, 'start': p_start, 'end': p_end,
                     'phases': [ph for ph in plan.phases if ph.programme_id == p.id]})
    window_start = min([d for d in [start] + [r['start'] for r in rows] if d], default=today)
    window_end = max([d for d in [end] + [r['end'] for r in rows] if d], default=today + timedelta(weeks=12))
    total = max((window_end - window_start).days + 1, 1)

    def pct(day):
        return max(0.0, min(100.0, (day - window_start).days / total * 100))

    def bar(a, b):
        left = pct(a)
        return {'left': left, 'width': max(pct(b + timedelta(days=1)) - left, 1.2)}

    phase_bars = [dict(bar(ph.start_date, ph.end_date), phase=ph) for ph in plan.phases
                  if ph.start_date and ph.end_date]
    for r in rows:
        r.update(bar(r['start'], r['end']))
    months, day = [], date(window_start.year, window_start.month, 1)
    while day <= window_end:
        if day >= window_start:
            months.append({'label': day.strftime('%b %Y' if day.month == 1 or not months else '%b'),
                           'left': pct(day)})
        day = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    linked = {ph.programme_id for ph in plan.phases if ph.programme_id}
    return render_template('season_plan/year.html', plan=plan, phase_bars=phase_bars, rows=rows,
                           relative=relative, months=months, linked=linked,
                           today_left=pct(today) if window_start <= today <= window_end else None,
                           pages=visible_pages(plan))
