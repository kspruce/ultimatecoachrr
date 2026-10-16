"""Fitness goals: set, tracked against new records, team-limited."""
import pytest

from app import db
from app.models.fitness import FitnessGoal, FitnessMetric
from tests import stats_data
from tests.test_teams import make_user


@pytest.fixture
def setup(app, team):
    player = stats_data.build_players(team, 1)[0]
    sprint = FitnessMetric(name='40-Yard Sprint', unit='seconds', higher_is_better=False,
                           team_organization_id=team.id)
    jump = FitnessMetric(name='Vertical Jump', unit='inches', higher_is_better=True)  # shared
    db.session.add_all([sprint, jump])
    db.session.commit()
    coach = stats_data.Client(app, make_user(team, 'coachy', role='coach').id, team.id)
    return {'player': player.id, 'sprint': sprint.id, 'jump': jump.id, 'coach': coach,
            'team': team}


def test_goal_page_add_achieve_complete_delete(app, setup):
    coach, pid = setup['coach'], setup['player']
    page = coach.get(f'/fitness/player/{pid}/goals')
    assert page.status_code == 200 and b'Add a goal' in page.data

    r = coach.post(f'/fitness/add-goal/{pid}', data={'metric_id': setup['sprint'],
                                                    'target_value': '5.2', 'target_date': ''})
    assert r.status_code == 302
    goal = FitnessGoal.query.one()
    assert goal.target_value == 5.2 and goal.target_date is None and not goal.completed
    assert b'40-Yard Sprint' in coach.get(f'/fitness/player/{pid}').data

    # A slower time doesn't meet a lower-is-better goal; a faster one does
    coach.post(f'/fitness/record/{pid}', data={'metric': setup['sprint'], 'value': '5.6'})
    db.session.expire_all()
    assert not db.session.get(FitnessGoal, goal.id).completed
    coach.post(f'/fitness/record/{pid}', data={'metric': setup['sprint'], 'value': '5.1'})
    db.session.expire_all()
    assert db.session.get(FitnessGoal, goal.id).completed

    # Set from the history page (shared metric), then complete and delete
    r = coach.post(f"/fitness/set-goal/{pid}/{setup['jump']}",
                   data={'target_value': '30', 'target_date': '2027-06-01'})
    assert r.status_code == 302
    jump_goal = FitnessGoal.query.filter_by(metric_id=setup['jump']).one()
    coach.post(f'/fitness/goal/{jump_goal.id}/complete')
    db.session.expire_all()
    assert db.session.get(FitnessGoal, jump_goal.id).completed
    coach.post(f'/fitness/goal/{jump_goal.id}/delete')
    assert FitnessGoal.query.count() == 1


def test_bad_input_and_other_teams(app, setup):
    coach, pid = setup['coach'], setup['player']
    coach.post(f'/fitness/add-goal/{pid}', data={'metric_id': setup['sprint'], 'target_value': 'fast'})
    assert FitnessGoal.query.count() == 0

    other_team = stats_data.build_team('Herd 2028', 'herd-2028')
    other_metric = FitnessMetric(name='Theirs', unit='s', team_organization_id=other_team.id)
    db.session.add(other_metric)
    db.session.commit()
    assert coach.post(f'/fitness/add-goal/{pid}', data={'metric_id': other_metric.id,
                                                       'target_value': '1'}).status_code == 404

    coach.post(f'/fitness/add-goal/{pid}', data={'metric_id': setup['sprint'], 'target_value': '5'})
    goal_id = FitnessGoal.query.one().id
    other = stats_data.Client(app, make_user(other_team, 'othercoach', role='coach').id, other_team.id)
    assert other.get(f'/fitness/player/{pid}/goals').status_code == 404
    assert other.post(f'/fitness/goal/{goal_id}/delete').status_code == 404

    # A player can manage their own goals but not a teammate's
    teammate = stats_data.build_players(setup['team'], 2)[1]
    user = make_user(setup['team'], 'me', role='player')
    me = db.session.get(type(teammate), pid)
    me.user_id = user.id
    db.session.commit()
    player_client = stats_data.Client(app, user.id, setup['team'].id)
    assert player_client.get(f'/fitness/player/{pid}/goals').status_code == 200
    assert player_client.get(f'/fitness/player/{teammate.id}/goals').status_code == 403
