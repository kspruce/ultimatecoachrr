"""The game call sheet: coaches pick a game's plays, Game Day records the
play called each point, and the playbook shows how each play went."""
from datetime import date

from app import db
from app.models.game import Game
from app.models.playbook import GameCallPlay, Play
from app.models.point import Point
from app.models.scouting import ScoutingReport
from tests.test_playbook_overhaul import client, club  # noqa: F401
from tests.test_theory import text


def make_game(club, opponent='Ka-Pow'):
    game = Game(opponent=opponent, date=date.today(), team_organization_id=club['team'])
    db.session.add(game)
    db.session.commit()
    return game.id


def record(c, game_id, number, line, outcome, play_id):
    r = c.post('/gameday/api/record-point', json={'game_id': game_id, 'point_number': number, 'line_type': line,
                                                  'gender_ratio': '4-3', 'players': [], 'events': [],
                                                  'outcome': outcome, 'play_id': play_id})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_coach_builds_the_sheet(app, club):
    game_id = make_game(club)
    c = client(app, club, 'coach')
    c.post(f'/playbook/games/{game_id}/sheet', data={'action': 'save', 'play_id': [club['Hammer'], club['Cup'], club['their_play'], club['Hammer']],
                                                     f'note_{club["Hammer"]}': 'After a timeout'})
    rows = GameCallPlay.query.order_by(GameCallPlay.order).all()
    assert [(r.play_id, r.order) for r in rows] == [(club['Hammer'], 1), (club['Cup'], 2)]  # not the other team's, no repeats
    assert rows[0].note == 'After a timeout'
    page = text(client(app, club, 'player').get(f'/playbook/games/{game_id}/sheet'))
    assert 'Hammer' in page and 'After a timeout' in page and 'not called' in page and 'Choose the plays' not in page
    # Reorder; players can't change it
    c.post(f'/playbook/games/{game_id}/sheet', data={'action': 'save', 'play_id': [club['Cup'], club['Hammer']]})
    db.session.expire_all()
    assert [r.play_id for r in GameCallPlay.query.order_by(GameCallPlay.order)] == [club['Cup'], club['Hammer']]
    assert client(app, club, 'player').post(f'/playbook/games/{game_id}/sheet', data={'action': 'save'}).status_code == 403
    assert client(app, club, 'other_coach', team='other').get(f'/playbook/games/{game_id}/sheet').status_code == 404


def test_sheet_from_the_game_plan(app, club):
    game_id = make_game(club)
    report = ScoutingReport(team_name='Ka-Pow', game_id=game_id, team_organization_id=club['team'])
    report.plays = [db.session.get(Play, club['Side stack']), db.session.get(Play, club['Cup'])]
    db.session.add(report)
    db.session.commit()
    c = client(app, club, 'coach')
    assert 'from the game plan' in text(c.get(f'/playbook/games/{game_id}/sheet'))
    c.post(f'/playbook/games/{game_id}/sheet', data={'action': 'from_plan'})
    assert {r.play_id for r in GameCallPlay.query} == {club['Side stack'], club['Cup']}


def test_game_day_records_the_called_play_and_results_add_up(app, club):
    game_id = make_game(club)
    db.session.add(GameCallPlay(game_id=game_id, play_id=club['Hammer'], order=1, team_organization_id=club['team']))
    db.session.commit()
    c = client(app, club, 'coach')
    dash = text(c.get(f'/gameday/game/{game_id}'))
    assert 'id="play-called"' in dash and f'id="call-{club["Hammer"]}"' in dash and 'Cup' in dash  # Cup under "Other play…"
    assert 'Secret set' not in dash  # drafts aren't called

    record(c, game_id, 1, 'O-line', 'scored', club['Hammer'])
    record(c, game_id, 2, 'D-line', 'scored', club['Cup'])
    record(c, game_id, 3, 'O-line', 'conceded', club['Hammer'])
    record(c, game_id, 4, 'D-line', 'conceded', club['their_play'])  # not ours: no play recorded
    record(c, game_id, 5, 'D-line', 'conceded', None)
    assert [p.called_play_id for p in Point.query.order_by(Point.point_number)] == \
        [club['Hammer'], club['Cup'], club['Hammer'], None, None]

    sheet = text(client(app, club, 'player').get(f'/playbook/games/{game_id}/sheet'))
    assert '1/2' in sheet and 'Also called' in sheet and 'Cup' in sheet
    play = text(client(app, club, 'player').get(f'/playbook/plays/{club["Hammer"]}'))
    assert 'Scored 1 of 2 times called' in play and 'Holds 1/2' in play and 'vs Ka-Pow' in play
    results = text(client(app, club, 'player').get('/playbook/results?season=all'))
    assert results.index('Hammer') < results.index('Cup')  # called most first
    assert 'Breaks 1/1' in results and '50%' in results


def test_playbook_off_hides_the_calls(app, club):
    from app.models.team_settings import TeamSettings
    game_id = make_game(club)
    TeamSettings.query.filter_by(team_id=club['team']).one().playbook_enabled = False
    db.session.commit()
    c = client(app, club, 'coach')
    assert 'id="play-called"' not in text(c.get(f'/gameday/game/{game_id}'))
    assert c.get(f'/playbook/games/{game_id}/sheet').status_code == 404
