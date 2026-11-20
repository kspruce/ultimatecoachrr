"""The season board (Season plan > Season board): every week's themes and
how far each of its sessions has been planned."""
from datetime import date, timedelta

from app import db
from app.models.season_plan import SeasonPlan, SeasonWeek
from app.models.session import SessionComponent, SessionPlan
from app.utils import session_outline as so
from app.utils.season_board import build_board
from app.utils.season_drafts import create_drafts
from app.utils.season_sessions import build_sessions, sync_week
from tests.test_season_drafts import MONDAY, make_plan, plan_sessions
from tests.test_training import club, login, make_user  # noqa: F401


def statuses(plan, key='joint', today=None):
    db.session.expire_all()
    board = build_board(db.session.get(SeasonPlan, plan.id), today or date.today())
    i = [k for k, _ in board['columns']].index(key)
    return {r.week.week_number: r.cells[i].status for r in board['rows']}, board


def week(plan, number):
    return SeasonWeek.query.filter_by(plan_id=plan.id, week_number=number).one()


def test_from_nothing_to_planned(app, club):
    plan = make_plan(club)
    joint, board = statuses(plan)
    # The 16-week template: every week has a theme, two are events
    assert [k for k, _ in board['columns']] == ['joint', '1s', '2s']  # the club's squads
    assert joint[1] == 'needed' and joint[12] == 'none' and joint[16] == 'none'
    assert board['totals']['needed'] == 14
    first_squad, _ = statuses(plan, '1s')
    assert set(first_squad.values()) == {'none'}  # no squad themes, so no squad sessions expected

    create_drafts(plan)
    db.session.commit()
    joint, board = statuses(plan)
    assert joint[1] == 'draft' and joint[12] == 'draft'  # event weeks can have a (light) session too
    assert board['totals']['draft'] == 16 and not board['totals']['needed']

    s = SessionPlan.query.filter_by(week_number=2, team_organization_id=club['team'].id).one()
    s.is_published = True
    s3 = SessionPlan.query.filter_by(week_number=3, team_organization_id=club['team'].id).one()
    SessionComponent.query.filter_by(session_id=s3.id).delete()
    s4 = SessionPlan.query.filter_by(week_number=4, team_organization_id=club['team'].id).one()
    s4.status = SessionPlan.STATUS_CANCELLED
    db.session.commit()
    joint, board = statuses(plan)
    assert (joint[2], joint[3], joint[4]) == ('planned', 'empty', 'cancelled')
    row = next(r for r in board['rows'] if r.week.week_number == 2)
    assert row.cells[0].activities == 5 and row.cells[0].minutes == 105


def test_notes_not_built_and_changed_in_both(app, club):
    plan = make_plan(club)
    create_drafts(plan, weeks=[week(plan, 5)])
    db.session.commit()
    # Week 6 gets notes but isn't built
    wk6 = week(plan, 6)
    wk6.session_detail_md = '| Time | Activity |\n| --- | --- |\n| 0:00 | Warm-up |'
    db.session.commit()
    joint, _ = statuses(plan)
    assert joint[6] == 'not_built'

    # Changed in the session and in the plan
    s = SessionPlan.query.filter_by(week_number=5, team_organization_id=club['team'].id).one()
    s.components.order_by(SessionComponent.order).first().title = 'Our own warm-up'
    db.session.commit()
    wk5 = week(plan, 5)
    outline = so.parse(wk5.session_detail_md)
    outline.joint.rows[1]['activity'] = 'Gate drill'
    wk5.session_detail_md = so.render(outline)
    db.session.commit()
    sync_week(db.session.get(SeasonPlan, plan.id), wk5)
    db.session.commit()
    joint, board = statuses(plan)
    assert joint[5] == 'conflict'
    row = next(r for r in board['rows'] if r.week.week_number == 5)
    assert row.cells[0].conflict_parts == ['activities'] and row.needs_work


def test_squad_sessions_have_their_own_columns(app, club):
    plan = make_plan(club)
    wk = week(plan, 2)
    wk.set_theme('1s', 'Breaks')
    wk.session_detail_md = ('| Time | 1s group | Source |\n| --- | --- | --- |\n| 0:00 | Break drill | X |')
    db.session.commit()
    build_sessions(db.session.get(SeasonPlan, plan.id))
    db.session.commit()
    firsts, _ = statuses(plan, '1s')
    assert firsts[2] == 'planned'
    joint, _ = statuses(plan)
    assert joint[2] == 'needed'  # the week still has a joint theme and no joint session
    wk3 = week(plan, 3)
    wk3.set_theme('2s', 'Hucks')
    db.session.commit()
    seconds, _ = statuses(plan, '2s')
    assert seconds[3] == 'needed'


def test_current_and_past_weeks(app, club):
    plan = make_plan(club)
    _, board = statuses(plan, today=MONDAY + timedelta(weeks=3, days=2))
    current = [r.week.week_number for r in board['rows'] if r.is_current]
    past = [r.week.week_number for r in board['rows'] if r.is_past]
    assert current == [4] and past == [1, 2, 3]


def test_the_page(app, club):
    plan = make_plan(club)
    create_drafts(plan, weeks=[week(plan, 1), week(plan, 2)])
    db.session.commit()
    coach = login(app, club, 'coach')
    html = coach.get('/season-plan/board').get_data(as_text=True)
    assert 'Season board' in html and 'Foundations' in html
    assert html.count('sb-chip sb-draft') == 2 and 'Start a draft' in html
    s = plan_sessions(club)[0]
    assert f'/sessions/s{s.number}/plan' in html  # drafts open in the planner

    # Filters
    html = coach.get('/season-plan/board?show=drafts').get_data(as_text=True)
    assert 'Week 1</a>' in html and 'Week 3</a>' not in html
    html = coach.get('/season-plan/board?show=attention').get_data(as_text=True)
    assert 'Week 3</a>' in html and 'Week 1</a>' not in html

    # Starting a draft from the board comes back to the board
    r = coach.post('/season-plan/sessions/drafts', data={'week': '3', 'next': 'board'})
    assert r.status_code == 302 and '/season-plan/board#board-week-3' in r.headers['Location']
    assert len(plan_sessions(club)) == 3

    # Coaches only
    assert login(app, club, 'ann').get('/season-plan/board').status_code in (302, 403, 404)
