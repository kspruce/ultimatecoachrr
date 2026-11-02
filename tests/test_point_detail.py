"""The point page: the play in the order it was recorded, split into
possessions, with the throws between events and each player's numbers."""
import json
import re

import pytest

from app import db
from app.models.event import Event, Pull
from app.models.game import Game
from app.models.player import Player
from app.models.point import LineUp, Point
from app.stats.point_replay import build_point_replay, location_label, outcome_label
from tests import stats_data


@pytest.fixture
def setup(app):
    team = stats_data.build_team()
    admin = stats_data.build_admin(team)
    players = stats_data.build_players(team)
    game = Game(opponent='Opponent A', team_organization_id=team.id)
    db.session.add(game)
    db.session.commit()
    client = stats_data.Client(app, admin.id, team.id)
    return {'client': client, 'team_id': team.id, 'game_id': game.id,
            'line': [p.id for p in players[:7]]}


def _point(setup, number=1, start='offense', outcome=None, ours=0, theirs=0):
    point = Point(game_id=setup['game_id'], point_number=number,
                  our_line_type='O-line' if start == 'offense' else 'D-line',
                  starting_position=start, point_outcome=outcome, gender_ratio='4-3',
                  force_direction='forehand', our_score_before=ours, their_score_before=theirs,
                  our_score_after=ours + (outcome == 'scored'),
                  their_score_after=theirs + (outcome == 'conceded'),
                  team_organization_id=setup['team_id'])
    db.session.add(point)
    db.session.flush()
    db.session.add_all([LineUp(point_id=point.id, player_id=pid,
                               team_organization_id=setup['team_id']) for pid in setup['line']])
    db.session.commit()
    return point.id


def _record(setup, point_id, event_type, player, x, y, offensive):
    data = {'event_type': event_type, 'field_position_x': x, 'field_position_y': y,
            'is_offensive': offensive}
    if player == 'opponent':
        data['is_opponent'] = True
    else:
        data['player_id'] = setup['line'][player]
    r = setup['client'].post(f'/stats/record/{point_id}', json=data)
    assert r.status_code == 201, r.get_data(as_text=True)


def _play_break_back(setup, point_id):
    """We turn it over, get a block, and work it up for the goal."""
    _record(setup, point_id, 'catch', 0, 20, 18, True)       # pickup
    _record(setup, point_id, 'catch', 1, 35, 10, True)
    _record(setup, point_id, 'throwaway', 1, 60, 30, True)
    _record(setup, point_id, 'block', 2, 40, 20, False)
    _record(setup, point_id, 'catch', 3, 42, 20, True)       # pickup after the D
    _record(setup, point_id, 'catch', 4, 60, 18, True)       # becomes the hockey assist
    _record(setup, point_id, 'catch', 0, 75, 15, True)       # becomes the assist
    _record(setup, point_id, 'goal', 5, 88, 18, True)


def _replay(point_id, team_id):
    point = db.session.get(Point, point_id)
    events = Event.query.filter_by(point_id=point_id, team_organization_id=team_id).all()
    return build_point_replay(point, events)


def test_possessions_throws_and_numbers(setup):
    point_id = _point(setup)
    _play_break_back(setup, point_id)
    replay = _replay(point_id, setup['team_id'])

    assert [s['event_type'] for s in replay['steps']] == [
        'catch', 'catch', 'throwaway', 'block', 'catch', 'hockey_assist', 'assist', 'goal']
    assert [(p['ours'], p['ended_by'], p['steps']) for p in replay['possessions']] == [
        (True, 'Throwaway', [0, 1, 2]), (False, 'Block', [3]), (True, 'Goal', [4, 5, 6, 7])]
    # Gained up to the last catch, not to where the throwaway landed
    assert [p['gain'] for p in replay['possessions']] == [15, None, 46]

    # No throw into a possession's first touch; a throwaway is the thrower's
    throws = replay['throws']
    assert [(t['from_step'], t['to_step'], t['complete']) for t in throws] == [
        (0, 1, True), (1, 2, False), (4, 5, True), (5, 6, True), (6, 7, True)]
    names = {pid: db.session.get(Player, pid).name for pid in setup['line']}
    assert throws[1]['thrower'] == names[setup['line'][1]] and throws[1]['receiver'] is None
    assert [t['role'] for t in throws[2:]] == ['regular', 'hockey_assist', 'assist']
    assert throws[4]['gain'] == 13

    stats = replay['stats']
    assert stats['throws'] == 5 and stats['completions'] == 4 and stats['completion_pct'] == 80
    assert stats['turns'] == 1 and stats['blocks'] == 1 and stats['our_possessions'] == 2

    assert replay['story']['scorer'] == names[setup['line'][5]]
    assert replay['story']['assist'] == names[setup['line'][0]]
    assert replay['story']['hockey_assist'] == names[setup['line'][4]]

    players = replay['players']
    first = players[setup['line'][0]]
    assert first['touches'] == 2 and first['throws'] == 2 and first['completions'] == 2 and first['assists'] == 1
    assert players[setup['line'][1]]['turns'] == 1 and players[setup['line'][1]]['throws'] == 1
    assert players[setup['line'][2]]['blocks'] == 1
    assert players[setup['line'][5]]['goals'] == 1


def test_opponent_and_substitution_events(setup):
    point_id = _point(setup, start='defense')
    _record(setup, point_id, 'unforced_turnover', 'opponent', 70, 10, False)
    _record(setup, point_id, 'catch', 0, 70, 10, True)
    db.session.add(Event(point_id=point_id, player_id=setup['line'][1], event_type='substitution',
                         field_position_x=50, field_position_y=18.5,
                         team_organization_id=setup['team_id']))
    db.session.commit()
    _record(setup, point_id, 'catch', 1, 85, 12, True)
    replay = _replay(point_id, setup['team_id'])

    assert [s['event_type'] for s in replay['steps']] == ['unforced_turnover', 'catch', 'catch']
    assert replay['steps'][0]['player'] == 'Opponent' and replay['steps'][0]['player_id'] is None
    assert [p['ours'] for p in replay['possessions']] == [False, True]
    assert len(replay['throws']) == 1


def test_labels():
    assert location_label(70, 18) == 'Attacking third · Middle'
    assert location_label(5, 2) == 'Own endzone · Left sideline'
    assert location_label(None, 3) == ''
    assert outcome_label(Point(starting_position='offense', point_outcome='scored')) == 'Hold'
    assert outcome_label(Point(starting_position='offense', point_outcome='conceded')) == 'Broken'
    assert outcome_label(Point(starting_position='defense', point_outcome='scored')) == 'Break'
    assert outcome_label(Point(starting_position='defense', point_outcome='conceded')) == 'Their hold'
    assert outcome_label(Point(starting_position='defense')) == 'In progress'


def test_page_shows_the_point(setup):
    first = _point(setup, number=1, outcome='scored')
    point_id = _point(setup, number=2, start='defense', outcome='scored', ours=1)
    third = _point(setup, number=3, outcome='conceded', ours=2)
    db.session.add(Pull(point_id=point_id, player_id=setup['line'][2], is_inbounds=True,
                        team_organization_id=setup['team_id']))
    db.session.commit()
    _play_break_back(setup, point_id)

    html = setup['client'].get(f'/points/{point_id}').get_data(as_text=True)
    assert 'Break' in html and 'Goal:' in html
    assert f'/points/{first}"' in html and f'/points/{third}"' in html   # prev / next and the strip
    assert 'id="pitch"' in html and 'id="scrubber"' in html
    assert 'Pull' in html and 'Possessions' in html and 'Watch' in html
    # The replay data is in recording order, with the goal last
    steps = json.loads(re.search(r'const steps = (\[.*?\]);\n', html).group(1))
    assert [s['event_type'] for s in steps][-3:] == ['hockey_assist', 'assist', 'goal']
    # Nothing scrolls the page while the replay runs
    assert 'scrollIntoView({ behavior' not in html
    # Every event has a row, clickable when it's on the pitch
    assert html.count('class="event-row"') == 8 and html.count('data-step="') >= 8


def test_page_without_events(setup):
    point_id = _point(setup)
    r = setup['client'].get(f'/points/{point_id}')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'No positions recorded for this point yet' in html
    assert 'No events recorded for this point yet' in html


def test_other_teams_point_is_hidden(setup, app):
    point_id = _point(setup)
    other = stats_data.build_team(name='Other', slug='other')
    admin = stats_data.build_admin(other, username='other')
    client = stats_data.Client(app, admin.id, other.id)
    assert client.get(f'/points/{point_id}').status_code == 404


def test_a_drop_is_drawn_but_not_the_throwers(setup):
    point_id = _point(setup)
    _record(setup, point_id, 'catch', 0, 20, 18, True)
    _record(setup, point_id, 'drop', 1, 40, 10, True)
    replay = _replay(point_id, setup['team_id'])
    assert len(replay['throws']) == 1 and replay['throws'][0]['result'] == 'drop'
    assert replay['stats']['throws'] == 0 and replay['stats']['turns'] == 1
    assert replay['players'][setup['line'][0]]['throws'] == 0
    assert replay['players'][setup['line'][1]]['turns'] == 1
    assert replay['possessions'][0]['throws'] == 0
