"""The Stats menu: one Game Day entry for those who can open it (each
tournament's numbers are on its page), and cutting skills are recorded
through the stats blueprint by stat takers only."""
import pytest

from app import db
from app.models.cutting_skill import CuttingSkill
from app.models.game import Game
from app.models.point import Point
from app.models.tournament import Tournament
from tests import stats_data
from tests.test_feedback import make_user


@pytest.fixture
def club(app, team):
    coach = make_user(team, 'coach1', 'coach')
    player_user = make_user(team, 'player1', 'player')
    player = stats_data.build_players(team, 1)[0]
    tournament = Tournament(name='Tour of Herd', team_organization_id=team.id)
    db.session.add(tournament)
    db.session.flush()
    game = Game(opponent='Ka-Pow', tournament_id=tournament.id, team_organization_id=team.id)
    db.session.add(game)
    db.session.flush()
    point = Point(game_id=game.id, point_number=1, our_line_type='O-line', starting_position='offense',
                  team_organization_id=team.id)
    db.session.add(point)
    db.session.commit()
    return {'coach': stats_data.Client(app, coach.id, team.id),
            'player': stats_data.Client(app, player_user.id, team.id),
            'tournament': tournament.id, 'point': point.id, 'player_id': player.id}


def test_menu_and_tournament_page(app, club):
    coach_home = club['coach'].get('/').get_data(as_text=True)
    assert 'Game Day summary' in coach_home and 'Tour of Herd' not in coach_home
    assert 'Game Day summary' not in club['player'].get('/').get_data(as_text=True)

    hub = club['coach'].get(f"/tournaments/{club['tournament']}").get_data(as_text=True)
    assert f"/gameday/tournament/{club['tournament']}/stats" in hub
    hub = club['player'].get(f"/tournaments/{club['tournament']}").get_data(as_text=True)
    assert f"/gameday/tournament/{club['tournament']}/stats" not in hub


def test_cutting_skills_go_through_the_stats_blueprint(app, club):
    body = {'player_id': club['player_id'], 'cutting_type': 'open_deep', 'outcome': 'open_thrown_to',
            'field_position_x': 50, 'field_position_y': 20}
    r = club['coach'].post(f"/stats/record_cutting_skill/{club['point']}", json=body)
    assert r.status_code == 201
    data = r.get_json()
    assert data['id'] == data['cutting_skill_id'] and data['player_name'] and data['cutting_type'] == 'open_deep'

    assert club['player'].post(f"/stats/record_cutting_skill/{club['point']}", json=body).status_code == 302
    assert club['coach'].post(f"/cutting-skills/record/{club['point']}", json=body).status_code == 404
    assert club['coach'].post('/stats/record_cutting_skill/99999', json=body).status_code == 404
    bad = club['coach'].post(f"/stats/record_cutting_skill/{club['point']}", json={**body, 'outcome': 'caught'})
    assert bad.status_code == 400 and 'Invalid outcome' in bad.get_json()['error']
    assert CuttingSkill.query.count() == 1
