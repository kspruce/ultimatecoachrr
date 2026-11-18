"""Sessions built from the season plan keep coaches' edits: building again
writes the plan's changes only to parts nobody has changed in the session,
and lists the ones changed on both sides so a coach can choose
(docs/SESSION_SEASON_LINK_PLAN.md, step A)."""
from app import db
from app.models.season_plan import SeasonWeek
from app.models.session import SessionComponent, SessionPlan
from app.utils import session_outline as so
from app.utils.season_sessions import build_sessions, sync_week
from tests.test_season_plan import client, enable, herd, needs_export  # noqa: F401
from tests.test_season_sessions import _setup

JOINT = 'plan-2027/28-w05-joint'


def session(ext=JOINT):
    db.session.expire_all()
    return SessionPlan.query.filter_by(external_id=ext).one()


def blocks(s):
    return [c.title for c in s.components.order_by(SessionComponent.order)]


def week(plan, number=5):
    return SeasonWeek.query.filter_by(plan_id=plan.id, week_number=number).one()


def edit_week_notes(plan, change, number=5):
    """Change a week's joint table the way an editor would, then save the
    week (which keeps its sessions in step)."""
    wk = week(plan, number)
    outline = so.parse(wk.session_detail_md)
    change(outline.joint)
    wk.session_detail_md = so.render(outline)
    db.session.commit()
    report = sync_week(plan, wk)
    db.session.commit()
    return report


def coach_renames_block(index, title, ext=JOINT):
    s = session(ext)
    c = s.components.order_by(SessionComponent.order).all()[index]
    c.title = title
    db.session.commit()
    return c.id


@needs_export
def test_plan_changes_reach_untouched_sessions(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    ids = [c.id for c in session().components.order_by(SessionComponent.order)]

    report = edit_week_notes(plan, lambda t: t.rows[1].update(activity='Gate drill'))
    assert blocks(session())[1] == 'Gate drill'
    assert report.count('updated') == 1 and not report.conflicts
    # Updated in place: the same blocks, so links from the playbook survive
    assert [c.id for c in session().components.order_by(SessionComponent.order)] == ids


@needs_export
def test_a_coachs_edit_is_kept_and_other_changes_still_arrive(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    coach_renames_block(0, 'Our own warm-up')

    # The plan changes something else in the same session: the title
    wk = week(plan)
    wk.session_title = 'A new name for the week'
    db.session.commit()
    report = sync_week(plan, wk)
    db.session.commit()
    s = session()
    assert blocks(s)[0] == 'Our own warm-up'
    assert s.title.endswith('A new name for the week')
    assert not report.conflicts

    # Building again with nothing new changes nothing and asks nothing
    report = build_sessions(plan, weeks=[week(plan)])
    assert blocks(session())[0] == 'Our own warm-up' and not report.conflicts


@needs_export
def test_changed_on_both_sides_keeps_the_sessions_and_asks(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    coach_renames_block(0, 'Our own warm-up')
    report = edit_week_notes(plan, lambda t: t.rows[1].update(activity='Gate drill'))

    assert blocks(session())[0] == 'Our own warm-up'  # the session's version
    assert blocks(session())[1] != 'Gate drill'
    [conflict] = report.conflicts
    assert conflict['parts'] == ['activities'] and conflict['week'] == 5
    assert [r['status'] for r in report.rows if r['session_id'] == session().id] == ['conflict']

    # Still listed until someone chooses
    assert build_sessions(plan, weeks=[week(plan)]).conflicts

    # Use the plan's version
    build_sessions(plan, weeks=[week(plan)], choose={JOINT: 'plan'})
    assert blocks(session())[1] == 'Gate drill' and blocks(session())[0] != 'Our own warm-up'
    assert not build_sessions(plan, weeks=[week(plan)]).conflicts


@needs_export
def test_keeping_the_sessions_version_stops_asking(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    coach_renames_block(0, 'Our own warm-up')
    edit_week_notes(plan, lambda t: t.rows[1].update(activity='Gate drill'))

    build_sessions(plan, weeks=[week(plan)], choose={JOINT: 'session'})
    assert blocks(session())[0] == 'Our own warm-up'
    report = build_sessions(plan, weeks=[week(plan)])
    assert not report.conflicts and blocks(session())[0] == 'Our own warm-up'
    # ...until the plan changes it again
    report = edit_week_notes(plan, lambda t: t.rows[1].update(activity='Box drill'))
    assert report.conflicts


@needs_export
def test_sessions_built_before_the_plan_kept_track_are_never_overwritten(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    s = session()
    s.plan_snapshot = None  # as built before this change
    db.session.commit()
    coach_renames_block(0, 'Edited before the upgrade')

    report = build_sessions(plan, weeks=[week(plan)])
    assert blocks(session())[0] == 'Edited before the upgrade'
    assert [c['parts'] for c in report.conflicts] == [['activities']]
    # Sessions nobody edited just start being tracked
    other = session('plan-2027/28-w05-1s')
    assert other.plan_snapshot and 'blocks' in other.plan_snapshot


@needs_export
def test_week_and_phase_always_follow_the_plan(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    s = session()
    s.block = 'Something else'
    db.session.commit()
    build_sessions(plan, weeks=[week(plan)])
    assert session().block == week(plan).block


@needs_export
def test_settling_from_the_sessions_page(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    coach_renames_block(0, 'Our own warm-up')
    edit_week_notes(plan, lambda t: t.rows[1].update(activity='Gate drill'))
    coach = client(app, herd, 'coach')

    page = coach.get('/season-plan/sessions').get_data(as_text=True)
    assert 'Changed in the session and in the plan' in page and "Use the plan's" in page
    r = coach.post(f'/season-plan/sessions/{session().id}/settle', data={'choice': 'plan'})
    assert r.status_code == 302
    assert blocks(session())[1] == 'Gate drill'
    page = coach.get('/season-plan/sessions').get_data(as_text=True)
    assert 'Changed in the session and in the plan' not in page

    assert coach.post(f'/season-plan/sessions/{session().id}/settle', data={'choice': 'nope'}).status_code == 404


@needs_export
def test_saving_a_week_says_when_both_changed(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    coach_renames_block(0, 'Our own warm-up')
    wk = week(plan)
    outline = so.parse(wk.session_detail_md)
    outline.joint.rows[1]['activity'] = 'Gate drill'
    coach = client(app, herd, 'coach')
    form = {'session_detail_md': so.render(outline), 'session_title': wk.session_title or '',
            'block': wk.block or '', 'theme_0': wk.joint_theme or ''}
    for i, (key, _) in enumerate(plan.theme_columns[1:], start=1):
        form[f'theme_{i}'] = wk.theme_for(key) or ''
    r = coach.post('/season-plan/week/5/edit', data=form, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert 'were changed in the session too' in html
    assert blocks(session())[0] == 'Our own warm-up'
