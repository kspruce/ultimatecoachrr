"""Building sessions from the season plan: the week-notes parser, the build
(run on the real 2027/28 export), keeping sessions in step when a week is
edited or the plan re-imported, and the Season plan > Sessions page."""
from datetime import date, time

from app import db
from app.models.drill import SavedDrill
from app.models.season_plan import SeasonPlan, SeasonWeek
from app.models.session import Attendance, SessionComponent, SessionPlan
from app.models.team_organization import TeamOrganization
from app.utils.season_sessions import (
    build_sessions, component_type, length_from_label, parse_week_notes, split_name,
)
from tests import stats_data
from tests.test_season_plan import client, do_import, enable, herd, needs_export  # noqa: F401

WEEK_MD = """**Learning points:** (1) Balance. (2) Use your pivot. (3) Two hands.

**What to tell players**

- Step, flick, point.

**Joint session**

| Time | Activity | How it runs | Source |
| --- | --- | --- | --- |
| 0:00 | Warm-up | Three-part warm-up | HB App. A.3 |
| 0:20 | Star throws | Pivot foot on a centre cone | BFD ch. 1 |
| 1:00 | Water |  |  |
| 1:10 | Free game | Mixed 7v7 | Plan |
| 1:40 | Recap | Say back the three points |  |

**Split sessions**

| Time | 1s group | 2s group (suggested) | Source |
| --- | --- | --- | --- |
| 0:00 | Warm-up | Same | HB App. A.3 |
| 0:30 | Shared vocabulary: dump, mac, zip. Walk through, then 2v2 | Five Frisbee Habits | DK 6.11 |
| 1:30 | Scrimmage | Scrimmage |  |

**Coaching notes**

- Keep it positive.
"""


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def test_parse_week_notes():
    parsed = parse_week_notes(WEEK_MD)
    assert parsed['learning_points'] == ['Balance.', 'Use your pivot.', 'Two hands.']
    joint, ones, twos = parsed['sessions']
    assert [s['squad'] for s in parsed['sessions']] == ['joint', '1s', '2s']
    assert joint['label'] == 'Joint session'
    assert [(a['title'], a['duration_minutes'], a['component_type']) for a in joint['activities']] == [
        ('Warm-up', 20, 'warmup'), ('Star throws', 40, 'drill'), ('Water', 10, 'water'),
        ('Free game', 30, 'scrimmage'), ('Recap', None, 'discussion')]
    assert joint['activities'][1]['description'] == 'Pivot foot on a centre cone'
    assert joint['activities'][1]['notes'] == 'Source: BFD ch. 1'
    # "Same" in the 2s column copies the 1s activity
    assert twos['activities'][0]['title'] == 'Warm-up'
    assert [a['title'] for a in ones['activities']] == ['Warm-up', 'Shared vocabulary: dump, mac, zip. Walk through, then 2v2', 'Scrimmage']
    # The tables, their labels and the learning points leave the notes
    notes = parsed['notes']
    assert '**What to tell players**' in notes and 'Keep it positive.' in notes
    assert '| Time' not in notes and '**Joint session**' not in notes and 'Learning points' not in notes


def test_parse_lengths_and_labels():
    md = ('**Light joint session (about 2 hours)**\n\n| Time | Activity | How it runs |\n| --- | --- | --- |\n'
          '| 0:00 | Warm-up | x |\n| 1:30 | Briefing | y |\n')
    (s,) = parse_week_notes(md)['sessions']
    assert s['label'] == 'Light joint session (about 2 hours)'
    assert [a['duration_minutes'] for a in s['activities']] == [90, 30]
    assert length_from_label('Joint session (about 2.5 hours)') == 150
    assert length_from_label('Light joint session (about 90 minutes):') == 90
    assert length_from_label('Joint session') is None
    # Tables that aren't timed sessions are left alone
    assert parse_week_notes('| When | What |\n| --- | --- |\n| Fri | Travel |\n')['sessions'] == []
    assert parse_week_notes(None) == {'sessions': [], 'learning_points': [], 'notes': None}


def test_split_name_and_types():
    assert split_name('Golden Arm') == ('Golden Arm', None)
    long_cell = ('Bull zone refresh: roles, counting attackers, the movement on swings, sideline talk '
                 'and a lot more after that')
    assert split_name(long_cell) == ('Bull zone refresh', 'roles, counting attackers, the movement on swings, '
                                                          'sideline talk and a lot more after that')
    name, desc = split_name('word ' * 40)
    assert len(name) <= 81 and name.endswith('…') and desc == ('word ' * 40).strip()
    assert component_type('Conditioned 7v7') == 'scrimmage'
    assert component_type('Welcome and the pitch') == 'discussion'
    assert component_type('Game-day warm-up rehearsal') == 'warmup'
    assert component_type('Asymmetric offence') == 'drill'


# --------------------------------------------------------------------------
# Building from the real export
# --------------------------------------------------------------------------

def _plan(team_id):
    return SeasonPlan.query.filter_by(team_organization_id=team_id).one()


def _setup(team_id):
    do_import(team_id)
    plan = _plan(team_id)
    plan.joint_weekday, plan.joint_start, plan.joint_end = 6, time(10), time(13)
    plan.split_weekday, plan.split_start, plan.split_end = 2, time(19), time(21)
    plan.session_location = 'Regent\'s Park'
    db.session.commit()
    return plan


def built(team_id):
    return SessionPlan.query.filter(SessionPlan.team_organization_id == team_id,
                                    SessionPlan.external_id.like('plan-%')).all()


@needs_export
def test_build_from_the_real_plan(app, herd):
    plan = _setup(herd['team'])
    report = build_sessions(plan)
    sessions = {s.external_id: s for s in built(herd['team'])}
    assert report.count('created') == len(sessions) > 60
    # Week 1: a joint session and both splits
    joint = sessions['plan-2027/28-w01-joint']
    ones, twos = sessions['plan-2027/28-w01-1s'], sessions['plan-2027/28-w01-2s']
    assert joint.title == 'Week 1 Joint: Welcome, baseline tests, grip and pivot'
    assert (joint.date, joint.start_time, joint.location) == (date(2027, 10, 10), time(10), 'Regent\'s Park')
    assert ones.date == date(2027, 10, 6) and ones.squad == '1s' and twos.squad == '2s'
    assert joint.week_number == 1 and joint.phase_number == 1 and joint.season == '2027/28'
    assert len(joint.learning_points) == 3 and 'What to tell players' in joint.notes
    comps = joint.components.order_by(SessionComponent.order).all()
    assert [c.title for c in comps][:3] == ['Welcome and the pitch', 'Warm-up', 'Baseline tests']
    assert comps[-1].title == 'Recap' and comps[-1].duration_minutes == 10  # runs to 13:00
    # Event weeks without a table get nothing; the week links to its joint session
    assert 'plan-2027/28-w37-joint' not in sessions
    assert (37, 'no session table') in report.skipped
    week1 = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=1).one()
    assert week1.session_plan_id == joint.id
    assert _plan(herd['team']).sessions_built_at is not None

    # Building again changes nothing
    again = build_sessions(_plan(herd['team']))
    assert again.count('unchanged') == len(sessions) and not again.removed


@needs_export
def test_activities_link_to_drills_by_name(app, herd):
    db.session.add(SavedDrill(title='Star throws', team_organization_id=herd['team']))
    db.session.commit()
    plan = _setup(herd['team'])
    build_sessions(plan)
    joint = SessionPlan.query.filter_by(external_id='plan-2027/28-w01-joint').one()
    star = joint.components.filter_by(title='Star throws').one()
    assert star.saved_drill.title == 'Star throws'


@needs_export
def test_dry_run_writes_nothing(app, herd):
    plan = _setup(herd['team'])
    report = build_sessions(plan, dry_run=True)
    assert report.count('created') > 60
    assert built(herd['team']) == [] and _plan(herd['team']).sessions_built_at is None


@needs_export
def test_editing_a_week_updates_its_sessions(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    enable(herd['team'])
    week = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=2).one()
    joint_id = week.session_plan_id
    md = week.session_detail_md.replace('| Gauntlet |', '| Gauntlet 2.0 |')
    split_start = md.index('**Split sessions**')
    md = md[:split_start] + md[md.index('**Coaching notes**'):]  # drop the split table
    c = client(app, herd, 'coach')
    r = c.post('/season-plan/week/2/edit', data={
        'block': week.block or '', 'session_title': 'Pivots, fakes and more',
        'session_detail_md': md, 'session_plan_id': str(joint_id)})
    assert r.status_code == 302
    joint = db.session.get(SessionPlan, joint_id)
    assert joint.title == 'Week 2 Joint: Pivots, fakes and more'
    assert joint.components.filter_by(title='Gauntlet 2.0').count() == 1
    # The split sessions left the notes, so they're gone
    assert SessionPlan.query.filter_by(external_id='plan-2027/28-w02-1s').first() is None
    # Other weeks are untouched
    assert SessionPlan.query.filter_by(external_id='plan-2027/28-w03-1s').count() == 1


@needs_export
def test_sessions_with_attendance_are_kept(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    ones = SessionPlan.query.filter_by(external_id='plan-2027/28-w03-1s').one()
    player = stats_data.build_players(db.session.get(TeamOrganization, herd['team']), 1)[0]
    db.session.add(Attendance(session_id=ones.id, player_id=player.id, team_organization_id=herd['team']))
    week = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=3).one()
    week.session_detail_md = 'No tables any more.'
    db.session.commit()
    report = build_sessions(_plan(herd['team']))
    assert any('kept because it has attendance' in w for w in report.warnings)
    assert SessionPlan.query.filter_by(external_id='plan-2027/28-w03-1s').count() == 1
    assert SessionPlan.query.filter_by(external_id='plan-2027/28-w03-joint').count() == 0


@needs_export
def test_reimport_keeps_built_sessions_in_step(app, herd):
    plan = _setup(herd['team'])
    build_sessions(plan)
    joint = SessionPlan.query.filter_by(external_id='plan-2027/28-w05-joint').one()
    joint.title = 'Edited on the site'
    db.session.commit()
    report = do_import(herd['team'])
    assert report.sessions is not None and report.sessions.count('updated') == 1
    assert db.session.get(SessionPlan, joint.id).title.startswith('Week 5 Joint:')
    assert 'sessions: 1 updated' in report.text()
    # --replace keeps the session settings and the links
    report = do_import(herd['team'], replace=True)
    plan = _plan(herd['team'])
    assert plan.joint_weekday == 6 and plan.sessions_built_at is not None
    assert report.sessions.count('unchanged') == len(built(herd['team']))
    week5 = SeasonWeek.query.filter_by(plan_id=plan.id, week_number=5).one()
    assert week5.session_plan_id == joint.id


@needs_export
def test_import_does_not_build_until_asked(app, herd):
    report = do_import(herd['team'])
    assert report.sessions is None and built(herd['team']) == []
    report = do_import(herd['team'], build_sessions=True)
    assert report.sessions.count('created') > 60


# --------------------------------------------------------------------------
# The Sessions page
# --------------------------------------------------------------------------

@needs_export
def test_sessions_page(app, herd):
    do_import(herd['team'])
    enable(herd['team'])
    coach = client(app, herd, 'coach')
    page = coach.get('/season-plan/sessions').get_data(as_text=True)
    assert 'Week 1 Joint: Welcome, baseline tests, grip and pivot' in page and 'Create' in page
    assert 'href="/season-plan/sessions"' in page
    assert built(herd['team']) == []

    # Preview doesn't save the settings
    r = coach.post('/season-plan/sessions', data={'action': 'preview', 'joint_weekday': '6',
                                                  'joint_start': '10:00', 'joint_end': '13:00'})
    assert r.status_code == 200 and 'Sun 10 Oct' in r.get_data(as_text=True)
    assert _plan(herd['team']).joint_weekday is None and built(herd['team']) == []

    assert coach.post('/season-plan/sessions', data={'joint_start': 'soon'}).status_code == 400

    r = coach.post('/season-plan/sessions', data={'action': 'build', 'joint_weekday': '6',
                                                  'joint_start': '10:00', 'joint_end': '13:00',
                                                  'split_weekday': '2', 'session_location': 'Pitch 3'})
    assert r.status_code == 302
    plan = _plan(herd['team'])
    assert (plan.joint_weekday, plan.joint_start, plan.split_weekday, plan.session_location) == \
        (6, time(10), 2, 'Pitch 3')
    joint = SessionPlan.query.filter_by(external_id='plan-2027/28-w01-joint').one()
    assert joint.date == date(2027, 10, 10)
    assert 'Up to date' in coach.get('/season-plan/sessions').get_data(as_text=True)

    # Built sessions say where to edit them, and the week lists them
    detail = coach.get(f'/sessions/{joint.id}/detail').get_data(as_text=True)
    assert 'Built from the season plan' in detail and '/season-plan/week/1/edit' in detail
    week = coach.get('/season-plan/week/1').get_data(as_text=True)
    assert '1s session' in week and '2s session' in week

    # Coaches only
    player = client(app, herd, 'player')
    assert player.get('/season-plan/sessions').status_code in (302, 403, 404)
    assert player.post('/season-plan/sessions', data={'action': 'build'}).status_code in (302, 403, 404)
