"""Draft sessions for the season plan's weeks, and training-schedule dates
taking them over (docs/SESSION_SEASON_LINK_PLAN.md, step D)."""
from datetime import time, timedelta

from app import db
from app.models.drill import SavedDrill
from app.models.schedule import SessionTemplate
from app.models.season_plan import SeasonPlan, SeasonWeek
from app.models.session import SessionComponent, SessionPlan
from app.models.team_settings import TeamSettings
from app.utils import season_plan_build as build
from app.utils.season_drafts import STANDARD_SHAPE, create_drafts, draftable
from app.utils.season_plan_templates import BY_KEY
from app.utils.season_sessions import parse_week_notes
from tests.test_training import TODAY, add_schedule, club, login, make_user  # noqa: F401
from tests.urls import session_path

MONDAY = TODAY - timedelta(days=TODAY.weekday())


def make_plan(club, **sessions):
    team_id = club['team'].id
    settings = TeamSettings.query.filter_by(team_id=team_id).first() or TeamSettings(team_id=team_id)
    settings.season_plan_enabled = True
    db.session.add(settings)
    plan = build.create_plan(team_id, 'Test plan', '2026/27', MONDAY, [], template=BY_KEY['season-16'],
                             sessions=sessions or None)
    db.session.commit()
    return plan


def plan_sessions(club):
    db.session.expire_all()
    return SessionPlan.query.filter(SessionPlan.team_organization_id == club['team'].id,
                                    SessionPlan.external_id.like('plan-%')).order_by(SessionPlan.week_number).all()


def test_drafts_fill_every_themed_week(app, club):
    plan = make_plan(club, joint_weekday=5, joint_start=time(10), joint_end=time(12))
    themed = [w for w in plan.weeks if draftable(w)]
    assert len(themed) == 16

    filled, report = create_drafts(plan)
    db.session.commit()
    assert len(filled) == 16 and report.count('created') == 16
    sessions = plan_sessions(club)
    assert len(sessions) == 16
    assert not any(s.is_published for s in sessions)  # drafts: players see nothing yet
    first = sessions[0]
    assert [c.title for c in first.components.order_by(SessionComponent.order)] == [b['title'] for b in STANDARD_SHAPE]
    assert [c.duration_minutes for c in first.components.order_by(SessionComponent.order)] == [15, 25, 30, 30, 5]
    skill = first.components.order_by(SessionComponent.order).all()[1]
    assert 'Grip, pivot, backhand and forehand' in skill.description  # week 1's theme
    assert first.aim == 'Grip, pivot, backhand and forehand'
    assert first.date == MONDAY + timedelta(days=5)
    assert db.session.get(SeasonPlan, plan.id).sessions_built_at is not None

    # Nothing left to fill
    filled, report = create_drafts(db.session.get(SeasonPlan, plan.id))
    assert filled == [] and report is None


def test_drafts_from_a_saved_template_link_its_drills(app, club):
    plan = make_plan(club)
    drill = SavedDrill(title='Box drill', team_organization_id=club['team'].id)
    db.session.add(drill)
    db.session.flush()
    template = SessionTemplate(team_organization_id=club['team'].id, name='Short night', blocks=[
        {'title': 'Warm-up', 'component_type': 'warmup', 'duration_minutes': 10},
        {'title': 'Our box', 'component_type': 'drill', 'duration_minutes': 20, 'drill_id': drill.id},
        {'title': 'Game', 'component_type': 'scrimmage', 'duration_minutes': 30}])
    db.session.add(template)
    db.session.commit()

    week = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=3).one()
    create_drafts(plan, weeks=[week], template_id=template.id)
    db.session.commit()
    [session] = plan_sessions(club)
    blocks = session.components.order_by(SessionComponent.order).all()
    assert [b.title for b in blocks] == ['Warm-up', 'Box drill', 'Game']
    assert blocks[1].drill_id == drill.id
    assert [b.duration_minutes for b in blocks] == [10, 20, 30]  # the last keeps its length


def test_weeks_with_notes_or_breaks_are_left_alone(app, club):
    plan = make_plan(club)
    week1, week2 = plan.weeks[0], plan.weeks[1]
    week1.session_detail_md = 'Our own notes.'
    week2.is_break = True
    db.session.commit()
    filled, _ = create_drafts(plan)
    assert week1 not in filled and week2 not in filled
    assert week1.session_detail_md == 'Our own notes.'


def test_one_week_from_its_page(app, club):
    make_plan(club)
    coach = login(app, club, 'coach')
    html = coach.get('/season-plan/week/4').get_data(as_text=True)
    assert 'Create a draft session' in html
    r = coach.post('/season-plan/sessions/drafts', data={'week': '4'})
    assert r.status_code == 302 and r.headers['Location'].endswith('/season-plan/week/4')
    [session] = plan_sessions(club)
    assert session.week_number == 4 and not session.is_published
    html = coach.get('/season-plan/week/4').get_data(as_text=True)
    assert 'Create a draft session' not in html and 'Edit in planner' in html


def test_all_weeks_from_the_sessions_page(app, club):
    make_plan(club)
    coach = login(app, club, 'coach')
    html = coach.get('/season-plan/sessions').get_data(as_text=True)
    assert '16 weeks with a theme have no session notes yet' in html
    r = coach.post('/season-plan/sessions/drafts', data={})
    assert r.status_code == 302
    assert len(plan_sessions(club)) == 16
    assert 'Plan ahead in the session planner' not in coach.get('/season-plan/sessions').get_data(as_text=True)
    # Players can't make drafts
    assert login(app, club, 'ann').post('/season-plan/sessions/drafts', data={}).status_code in (302, 403, 404)
    assert len(plan_sessions(club)) == 16


def test_planning_a_draft_writes_back_to_its_week(app, club):
    plan = make_plan(club)
    week = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=2).one()
    create_drafts(plan, weeks=[week])
    db.session.commit()
    [session] = plan_sessions(club)
    blocks = [{'id': c.id, 'title': c.title, 'component_type': c.component_type,
               'duration_minutes': c.duration_minutes, 'description': c.description or '', 'notes': '',
               'coach_cue': '', 'focus_area': '', 'drill_id': None}
              for c in session.components.order_by(SessionComponent.order)]
    blocks[1]['title'] = 'Dump-swing drill'
    r = login(app, club, 'coach').post(session_path(session.id, '/plan'), json={'blocks': blocks, 'title': session.title})
    assert r.get_json()['plan_message'] == 'week 2 of the season plan updated to match'
    db.session.expire_all()
    md = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=2).one().session_detail_md
    joint = parse_week_notes(md)['sessions'][0]
    assert [a['title'] for a in joint['activities']][1] == 'Dump-swing drill'


def test_a_schedule_date_takes_over_the_plans_session(app, club):
    plan = make_plan(club)  # no training days: drafts sit on their week, undated
    create_drafts(plan)
    db.session.commit()
    drafts = {s.week_number: s.id for s in plan_sessions(club)}

    schedule = add_schedule(club, 'Saturday', 5, weeks=3)  # everyone, from today
    db.session.expire_all()
    dates = sorted(s.date for s in schedule.sessions)
    assert dates
    for day in dates:
        week_number = (day - MONDAY).days // 7 + 1
        session = SessionPlan.query.filter_by(schedule_id=schedule.id, date=day).one()
        # The plan's draft for that week, not a second session
        assert session.id == drafts[week_number]
        assert session.title.startswith(f'Week {week_number} Joint')
        assert (session.start_time, session.location) == (time(19), 'Park')
        assert not session.is_published and session.components.count() == 5
    assert SessionPlan.query.filter_by(team_organization_id=club['team'].id).count() == len(drafts)

    # Building the plan again leaves the schedule's date and time alone
    from app.utils.season_sessions import build_sessions
    build_sessions(db.session.get(SeasonPlan, plan.id))
    db.session.commit()
    db.session.expire_all()
    for day in dates:
        assert SessionPlan.query.filter_by(schedule_id=schedule.id, date=day).one().start_time == time(19)


def test_a_squad_schedule_only_takes_that_squads_session(app, club):
    plan = make_plan(club)
    create_drafts(plan)
    db.session.commit()
    add_schedule(club, '2s midweek', 1, [club['seconds']], weeks=2)
    db.session.expire_all()
    # Only joint drafts exist, so the 2s schedule makes its own dates
    assert all(s.schedule_id is None for s in plan_sessions(club))
