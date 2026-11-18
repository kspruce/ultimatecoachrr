"""The season plan and its sessions, both ways (docs/SESSION_SEASON_LINK_PLAN.md,
steps B and C): a week shows its sessions, the planner shows its week, and
saving a session in the planner writes its activities back into the week's
session notes."""
from app import db
from app.models.season_plan import SeasonWeek
from app.models.session import SessionComponent, SessionPlan
from app.utils import session_outline as so
from app.utils.season_sessions import build_sessions, parse_week_notes
from tests.test_season_plan import client, enable, herd, needs_export  # noqa: F401
from tests.test_season_sessions import _setup
from tests.urls import session_path

JOINT, FIRSTS, SECONDS = 'plan-2027/28-w05-joint', 'plan-2027/28-w05-1s', 'plan-2027/28-w05-2s'


def session(ext):
    db.session.expire_all()
    return SessionPlan.query.filter_by(external_id=ext).one()


def week(plan, number=5):
    db.session.expire_all()
    return SeasonWeek.query.filter_by(plan_id=plan.id, week_number=number).one()


def blocks_payload(s):
    return [{'id': c.id, 'title': c.title, 'component_type': c.component_type,
             'duration_minutes': c.duration_minutes, 'description': c.description or '',
             'coach_cue': c.coach_cue or '', 'notes': c.notes or '', 'focus_area': c.focus_area or '',
             'drill_id': c.drill_id} for c in s.components.order_by(SessionComponent.order)]


def save_in_planner(coach, s, blocks, **extra):
    r = coach.post(session_path(s.id, '/plan'), json={'blocks': blocks, 'title': s.title, **extra})
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_json()


def activities(md, squad):
    return [a['title'] for a in next(s for s in parse_week_notes(md)['sessions'] if s['squad'] == squad)['activities']]


@needs_export
def test_the_week_shows_its_sessions(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    html = client(app, herd, 'coach').get('/season-plan/week/5').get_data(as_text=True)
    assert "This week's sessions" in html and 'Edit in planner' in html
    assert 'Joint session' in html and '1s session' in html
    first = session(JOINT).components.order_by(SessionComponent.order).first()
    assert first.title in html


@needs_export
def test_the_planner_shows_its_week(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    html = client(app, herd, 'coach').get(session_path(session(JOINT).id, '/plan')).get_data(as_text=True)
    assert 'Season plan · week 5' in html and 'Linked to week 5' in html
    assert 'href="/season-plan/week/5"' in html


@needs_export
def test_saving_the_joint_session_rewrites_the_joint_table(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    coach = client(app, herd, 'coach')
    before = week(plan).session_detail_md
    s = session(JOINT)
    blocks = blocks_payload(s)
    blocks[1]['title'] = 'Gate drill'
    blocks[1]['description'] = 'Cutters run through a gate of cones'
    del blocks[-1]
    blocks.append({'id': None, 'title': 'Box drill', 'component_type': 'drill', 'duration_minutes': 15,
                   'description': '', 'notes': '', 'coach_cue': '', 'focus_area': '', 'drill_id': None})
    result = save_in_planner(coach, s, blocks)
    assert result['plan_message'] == 'week 5 of the season plan updated to match'

    after = week(plan).session_detail_md
    titles = [b['title'] for b in blocks]
    assert activities(after, 'joint') == titles
    # Only the joint table changed: the split table and the prose are as they were
    old, new = so.parse(before), so.parse(after)
    assert new.split.rows == old.split.rows
    assert [p for p in new.parts if isinstance(p, str)] == [p for p in old.parts if isinstance(p, str)]
    assert '| 0:20 | Gate drill | Cutters run through a gate of cones |' in after
    # The session is as the coach left it, and the plan doesn't report it back
    assert [c.title for c in session(JOINT).components.order_by(SessionComponent.order)] == titles
    report = build_sessions(plan, weeks=[week(plan)])
    assert not report.conflicts
    assert [c.title for c in session(JOINT).components.order_by(SessionComponent.order)] == titles
    # The other sessions that week are untouched
    assert [c.title for c in session(FIRSTS).components] == activities(before, '1s')


@needs_export
def test_saving_a_squad_session_rewrites_only_its_column(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    coach = client(app, herd, 'coach')
    before = week(plan).session_detail_md
    s = session(SECONDS)
    # Different timings from the 1s: a longer first block, one fewer
    blocks = blocks_payload(s)[:-1]
    blocks[0]['duration_minutes'] = 30
    blocks[1]['title'] = 'Christmas tree, then 3v3'
    blocks[1]['description'] = ''
    save_in_planner(coach, s, blocks)

    after = week(plan).session_detail_md
    assert activities(after, '2s') == [b['title'] for b in blocks]
    assert activities(after, '1s') == activities(before, '1s')  # the 1s session is unchanged
    week_sessions = parse_week_notes(after)['sessions']
    seconds = next(x for x in week_sessions if x['squad'] == '2s')
    assert seconds['activities'][0]['duration_minutes'] == 30
    assert activities(after, 'joint') == activities(before, 'joint')
    assert not build_sessions(plan, weeks=[week(plan)]).conflicts


@needs_export
def test_editing_the_first_squad_spells_out_same(app, herd):
    plan = _setup(herd['team'])
    wk = week(plan)
    outline = so.parse(wk.session_detail_md)
    outline.split.rows[0]['2s'] = 'Same'  # "Same" as the 1s warm-up
    wk.session_detail_md = so.render(outline)
    db.session.commit()
    build_sessions(plan)
    enable(herd['team'])
    before = week(plan).session_detail_md
    s = session(FIRSTS)
    blocks = blocks_payload(s)
    blocks[0]['title'] = 'Dynamic warm-up'
    save_in_planner(client(app, herd, 'coach'), s, blocks)
    after = week(plan).session_detail_md
    assert activities(after, '1s')[0] == 'Dynamic warm-up'
    assert activities(after, '2s') == activities(before, '2s')  # still the old warm-up


@needs_export
def test_saving_without_changing_activities_leaves_the_notes(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    before = week(plan).session_detail_md
    s = session(JOINT)
    result = save_in_planner(client(app, herd, 'coach'), s, blocks_payload(s), notes='Bring cones')
    assert result['plan_message'] is None
    assert week(plan).session_detail_md == before


@needs_export
def test_a_table_the_planner_cant_update_is_left_alone(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    wk = week(plan)
    wk.session_detail_md += '\n\n| Time | Activity | Coach |\n| --- | --- | --- |\n| 0:00 | Extra | Sam |'
    db.session.commit()
    before = wk.session_detail_md
    s = session(JOINT)
    blocks = blocks_payload(s)
    blocks[0]['title'] = 'Changed'
    result = save_in_planner(client(app, herd, 'coach'), s, blocks)
    assert "can't update" in result['plan_message']
    assert week(plan).session_detail_md == before
    assert session(JOINT).components.order_by(SessionComponent.order).first().title == 'Changed'


@needs_export
def test_deleting_a_session_can_take_it_out_of_the_week(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    admin = client(app, herd, 'captain')  # captains run the team, so can delete
    s = session(SECONDS)
    r = admin.post(f'/sessions/delete/s{s.number}', data={'remove_from_plan': '1'})
    assert r.status_code == 302
    md = week(plan).session_detail_md
    assert '2s group' not in md and '1s group' in md
    build_sessions(plan, weeks=[week(plan)])
    assert SessionPlan.query.filter_by(external_id=SECONDS).first() is None

    # Without ticking it, the next build brings it back
    s = session(FIRSTS)
    admin.post(f'/sessions/delete/s{s.number}', data={})
    build_sessions(plan, weeks=[week(plan)])
    assert SessionPlan.query.filter_by(external_id=FIRSTS).first() is not None
