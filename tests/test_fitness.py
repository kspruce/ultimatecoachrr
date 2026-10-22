"""Fitness: the four standard tests, PBs, targets, the opt-in leaderboard
and test day, all limited to your own team."""
import pytest

from app import db
from app.models.fitness import STANDARD_TEST_KEYS, FitnessGoal, FitnessMetric, FitnessRecord
from app.models.player import Player
from tests import stats_data
from tests.test_teams import make_user


@pytest.fixture
def setup(app, team):
    players = stats_data.build_players(team, 3)
    coach = stats_data.Client(app, make_user(team, 'coachy', role='coach').id, team.id)
    user = make_user(team, 'me', role='player')
    players[0].user_id = user.id
    db.session.commit()
    me = stats_data.Client(app, user.id, team.id)
    coach.get('/fitness/')  # creates the standard tests
    tests = {m.key: m.id for m in FitnessMetric.standard()}
    return {'me': players[0].id, 'mate': players[1].id, 'other': players[2].id,
            'coach': coach, 'me_client': me, 'tests': tests, 'team': team}


def records(player_id):
    return FitnessRecord.query.filter_by(player_id=player_id).count()


def test_standard_tests_are_created_once(app, setup):
    setup['coach'].get('/fitness/')
    assert [m.key for m in FitnessMetric.standard()] == STANDARD_TEST_KEYS
    assert FitnessMetric.query.count() == len(STANDARD_TEST_KEYS)
    guide = setup['me_client'].get('/fitness/tests').data.decode()
    assert '10 m Sprint' in guide and 'How to improve' in guide


def test_log_results_pbs_and_targets(app, setup):
    me, pid, sprint = setup['me_client'], setup['me'], setup['tests']['sprint_10m']

    r = me.post(f'/fitness/player/{pid}/target/{sprint}', data={'target_value': '1.80'})
    assert r.status_code == 302
    assert FitnessGoal.query.one().target_value == 1.8

    me.post(f'/fitness/record/{pid}', data={'metric_id': sprint, 'value': '1.95',
                                           'date': '2026-09-01'})
    assert b'New PB' in me.get(f'/fitness/player/{pid}').data
    me.post(f'/fitness/record/{pid}', data={'metric_id': sprint, 'value': '2.05'})
    assert b'New PB' not in me.get(f'/fitness/player/{pid}').data
    assert not FitnessGoal.query.one().completed

    # Lower is better on a sprint: 1.78 hits the target
    me.post(f'/fitness/record/{pid}', data={'metric_id': sprint, 'value': '1.78'})
    db.session.expire_all()
    assert FitnessGoal.query.one().completed

    page = me.get(f'/fitness/player/{pid}').data.decode()
    assert '1.78' in page and 'All results (3)' in page
    hub = me.get('/fitness/').data.decode()
    assert 'Your PBs' in hub and '1.78' in hub

    # Bad input is refused
    me.post(f'/fitness/record/{pid}', data={'metric_id': sprint, 'value': '-1'})
    me.post(f'/fitness/record/{pid}', data={'metric_id': sprint, 'value': 'fast'})
    assert records(pid) == 3

    # A target the PB already beats isn't set; clearing removes the open one
    me.post(f'/fitness/player/{pid}/target/{sprint}', data={'target_value': '1.9'})
    assert FitnessGoal.query.filter_by(completed=False).count() == 0
    me.post(f'/fitness/player/{pid}/target/{sprint}', data={'target_value': '1.7'})
    assert FitnessGoal.query.filter_by(completed=False).count() == 1
    me.post(f'/fitness/player/{pid}/target/{sprint}', data={'clear': '1'})
    assert FitnessGoal.query.filter_by(completed=False).count() == 0

    record = FitnessRecord.query.first()
    me.post(f'/fitness/record/delete/{record.id}')
    assert records(pid) == 2


def test_leaderboard_is_opt_in(app, setup):
    coach, me, tests = setup['coach'], setup['me_client'], setup['tests']
    jump = tests['broad_jump']
    for pid, value in ((setup['me'], '240'), (setup['mate'], '255')):
        coach.post(f'/fitness/record/{pid}', data={'metric_id': jump, 'value': value})
    mate_name = db.session.get(Player, setup['mate']).name
    my_name = db.session.get(Player, setup['me']).name

    hub = me.get('/fitness/').data.decode()
    assert 'on the leaderboard yet' in hub and mate_name not in hub

    me.post(f"/fitness/player/{setup['me']}/leaderboard", data={'opt_in': '1'})
    hub = me.get('/fitness/').data.decode()
    assert my_name in hub and mate_name not in hub

    # Only the player can opt themselves in, not a coach or teammate
    assert coach.post(f"/fitness/player/{setup['mate']}/leaderboard",
                      data={'opt_in': '1'}).status_code == 403
    assert me.post(f"/fitness/player/{setup['mate']}/leaderboard",
                   data={'opt_in': '1'}).status_code == 403
    db.session.expire_all()
    assert not db.session.get(Player, setup['mate']).fitness_leaderboard

    # Coaches see the whole squad's PBs
    assert mate_name in coach.get('/fitness/').data.decode()


def test_test_day(app, setup):
    coach, tests = setup['coach'], setup['tests']
    yoyo = tests['yoyo_ir1']
    page = coach.get(f'/fitness/test-day?metric_id={yoyo}')
    assert page.status_code == 200 and b'Yo-Yo' in page.data
    coach.post(f'/fitness/test-day?metric_id={yoyo}', data={
        'date': '2026-09-10', f"value_{setup['me']}": '1480', f"value_{setup['mate']}": '',
        f"value_{setup['other']}": 'lots'})
    page = coach.get(f'/fitness/test-day?metric_id={yoyo}').data
    assert b'Saved 1 ' in page and b'skipped' in page
    record = FitnessRecord.query.one()
    assert record.value == 1480 and record.date_recorded.date().isoformat() == '2026-09-10'

    assert setup['me_client'].get('/fitness/test-day').status_code == 403


def test_players_and_other_teams_are_kept_out(app, setup):
    me, pid, sprint = setup['me_client'], setup['me'], setup['tests']['sprint_10m']
    assert me.get(f'/fitness/player/{pid}').status_code == 200
    assert me.get(f"/fitness/player/{setup['mate']}").status_code == 403
    assert me.post(f"/fitness/record/{setup['mate']}",
                   data={'metric_id': sprint, 'value': '2'}).status_code == 403

    # Only the standard tests can be logged
    custom = FitnessMetric(name='Bench press', unit='kg', team_organization_id=setup['team'].id)
    db.session.add(custom)
    db.session.commit()
    assert me.post(f'/fitness/record/{pid}',
                   data={'metric_id': custom.id, 'value': '60'}).status_code == 404

    other_team = stats_data.build_team('Herd 2028', 'herd-2028')
    other = stats_data.Client(app, make_user(other_team, 'othercoach', role='coach').id, other_team.id)
    assert other.get(f'/fitness/player/{pid}').status_code == 404
    assert other.post(f'/fitness/record/{pid}', data={'metric_id': sprint, 'value': '2'}).status_code == 404
    setup['coach'].post(f'/fitness/record/{pid}', data={'metric_id': sprint, 'value': '2'})
    record_id = FitnessRecord.query.one().id
    assert other.post(f'/fitness/record/delete/{record_id}').status_code == 404
    assert records(pid) == 1


def test_results_on_old_tests_still_show(app, setup):
    pid = setup['me']
    old = FitnessMetric(name='Beep Test/Yo-Yo Test', unit='level', higher_is_better=True)
    db.session.add(old)
    db.session.flush()
    db.session.add(FitnessRecord(player_id=pid, metric_id=old.id, value=9.5,
                                 team_organization_id=setup['team'].id))
    db.session.commit()
    page = setup['me_client'].get(f'/fitness/player/{pid}').data.decode()
    assert 'Older tests' in page and 'Beep Test/Yo-Yo Test' in page and '9.50' in page
