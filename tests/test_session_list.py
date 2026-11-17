"""The sessions list (/sessions/) with a season's worth of sessions: coming
up / past / all dates, weeks, search, and what each session still needs."""
from datetime import date, timedelta

from flask import template_rendered

from app import db
from app.models.session import Attendance, SessionComponent, SessionPlan
from app.utils import session_list as sl
from tests.test_training import TODAY, club, login, make_user  # noqa: F401

MONDAY = TODAY - timedelta(days=TODAY.weekday())


def make(club, title, day, components=0, published=True, attended=(), **kw):
    s = SessionPlan(title=title, date=day, team_organization_id=club['team'].id, is_published=published, **kw)
    db.session.add(s)
    db.session.flush()
    for i in range(components):
        db.session.add(SessionComponent(session_id=s.id, title=f'Part {i + 1}', order=i + 1, component_type='drill',
                                        team_organization_id=club['team'].id))
    for player, status in attended:
        db.session.add(Attendance(session_id=s.id, player_id=player.id, status=status,
                                  team_organization_id=club['team'].id))
    db.session.commit()
    return s


def context(c, url):
    seen = []

    def record(sender, template, context, **extra):
        if template.name == 'session/index.html':
            seen.append(context)
    template_rendered.connect(record)
    try:
        r = c.get(url)
        assert r.status_code == 200
    finally:
        template_rendered.disconnect(record)
    return seen[-1], r.get_data(as_text=True)


def titles(ctx):
    return [s.title for s in ctx['sessions']]


def test_monday_and_week_grouping():
    assert sl.monday(date(2028, 2, 10)) == date(2028, 2, 7)  # a Thursday
    today = date(2028, 2, 9)
    plans = [SessionPlan(id=i, title=str(i), date=date(2028, 2, 7) + timedelta(days=3 * i)) for i in range(12)]
    weeks = sl.group_by_week(plans, today, 'upcoming')
    assert [len(w.sessions) for w in weeks] == [3, 2, 2, 3, 2]
    assert [w.open for w in weeks] == [True] * 4 + [False]
    assert weeks[0].anchor == 'week-2028-02-07'

    # All dates opens this week and the three after, wherever they fall in the list
    earlier = [SessionPlan(id=100 + i, title='old', date=date(2028, 1, 3) + timedelta(weeks=i)) for i in range(4)]
    weeks = sl.group_by_week(earlier + plans, today, 'all')
    assert [w.open for w in weeks] == [False] * 4 + [True] * 4 + [False]

    # Undated sessions go in their own group, folded when there are dated ones
    weeks = sl.group_by_week(plans[:1] + [SessionPlan(id=99, title='?')], today, 'upcoming')
    assert weeks[-1].start is None and not weeks[-1].open


def test_needs():
    today = date(2028, 2, 9)
    past, future = date(2028, 2, 1), date(2028, 2, 20)
    assert sl.needs(SessionPlan(date=future, is_published=True), 0, 0, today) == ['plan']
    assert sl.needs(SessionPlan(date=future, is_published=False), 3, 0, today) == ['draft']
    assert sl.needs(SessionPlan(date=future, is_published=True), 3, 0, today) == []
    assert sl.needs(SessionPlan(date=past, is_published=True), 3, 0, today) == ['register']
    assert sl.needs(SessionPlan(date=past, is_published=True), 3, 5, today) == []
    assert sl.needs(SessionPlan(date=past, status='cancelled'), 0, 0, today) == []


def test_opens_on_whats_coming_up_in_date_order(app, club):
    make(club, 'Last month', TODAY - timedelta(days=30))
    make(club, 'In three weeks', TODAY + timedelta(weeks=3))
    make(club, 'Tomorrow', TODAY + timedelta(days=1))
    make(club, 'End of season', TODAY + timedelta(weeks=30))
    c = login(app, club, 'coach')

    ctx, html = context(c, '/sessions/')
    # Not the far end of the season first, as a newest-first list did
    assert titles(ctx) == ['Tomorrow', 'In three weeks', 'End of season']
    assert ctx['when_counts'] == {'upcoming': 3, 'past': 1, 'all': 4}
    assert 'Coming up <span>3</span>' in html

    ctx, _ = context(c, '/sessions/?show=past')
    assert titles(ctx) == ['Last month']
    ctx, _ = context(c, '/sessions/?show=all')
    assert titles(ctx) == ['Last month', 'Tomorrow', 'In three weeks', 'End of season']


def test_weeks_show_the_season_plan(app, club):
    make(club, 'Joint', MONDAY + timedelta(days=7), week_number=12, phase_name='Building', block='Zones')
    make(club, '1s', MONDAY + timedelta(days=9), week_number=12, phase_name='Building', block='Zones')
    ctx, html = context(login(app, club, 'coach'), '/sessions/')
    assert len(ctx['weeks']) == 1
    assert 'Next week' in html and 'Week 12' in html and 'Building' in html and 'Zones' in html
    assert 'id="week-' + (MONDAY + timedelta(days=7)).isoformat() + '"' in html


def test_search(app, club):
    make(club, 'Zone offence', TODAY + timedelta(days=2))
    make(club, 'Hucks', TODAY + timedelta(days=3), focus_area='Deep throws')
    make(club, '50%_off', TODAY + timedelta(days=4))
    c = login(app, club, 'coach')
    assert titles(context(c, '/sessions/?q=zone')[0]) == ['Zone offence']
    assert titles(context(c, '/sessions/?q=deep')[0]) == ['Hucks']
    # % and _ are searched for, not wildcards
    assert titles(context(c, '/sessions/?q=%25_')[0]) == ['50%_off']


def test_coaches_see_what_needs_doing(app, club):
    ann = club['ann']
    make(club, 'No plan', TODAY + timedelta(days=2))
    make(club, 'Draft', TODAY + timedelta(days=3), components=2, published=False)
    make(club, 'Ready', TODAY + timedelta(days=4), components=2)
    make(club, 'Register missing', TODAY - timedelta(days=3), components=2)
    make(club, 'Register taken', TODAY - timedelta(days=4), components=2, attended=[(ann, 'present')])
    c = login(app, club, 'coach')

    ctx, html = context(c, '/sessions/?show=all')
    assert ctx['coach_todo'] == {'plan': 1, 'draft': 1, 'register': 1}
    assert 'No plan yet' in html and 'Not published' in html and 'Register not taken' in html
    assert ctx['attended'] == {s.id: 1 for s in ctx['sessions'] if s.title == 'Register taken'}

    assert titles(context(c, '/sessions/?show=all&needs=plan')[0]) == ['No plan']
    assert titles(context(c, '/sessions/?show=all&needs=register')[0]) == ['Register missing']
    assert set(titles(context(c, '/sessions/?show=all&needs=any')[0])) == {'No plan', 'Draft', 'Register missing'}


def test_players_dont_see_coach_to_dos(app, club):
    make(club, 'No plan', TODAY + timedelta(days=2))
    c = login(app, club, 'ann')
    ctx, html = context(c, '/sessions/?needs=plan')
    assert ctx['coach_todo'] is None and ctx['session_needs'] == {}
    assert titles(ctx) == ['No plan']  # the needs filter is ignored
    assert 'No plan yet' not in html and 'name="needs"' not in html


def test_counts_take_three_queries_however_many_sessions(app, club):
    from sqlalchemy import event
    for i in range(30):
        make(club, f'S{i}', TODAY + timedelta(days=i + 1), components=1)
    sessions = SessionPlan.query.all()
    statements = []

    def count(*args):
        statements.append(args[2])
    event.listen(db.engine, 'before_cursor_execute', count)
    try:
        components, attended, rows = sl.counts_for(sessions)
    finally:
        event.remove(db.engine, 'before_cursor_execute', count)
    assert len(statements) == 3
    assert all(components[s.id] == 1 for s in sessions)
