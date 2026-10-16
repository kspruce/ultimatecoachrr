"""Plays recorded as "Opponent" or "Unknown" in Positional Analysis: they are
saved without a player, nobody of ours is credited with them, and team-level
counts (possessions, turnovers, the score) still include them."""
import pytest

from app import db
from app.models.event import Event
from app.models.game import Game
from app.models.point import LineUp, Point
from app.models.throws import Throw
from app.stats.team import calculate_game_stats
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


def _point(setup, start):
    point = Point(game_id=setup['game_id'], point_number=1,
                  our_line_type='O-line' if start == 'offense' else 'D-line',
                  starting_position=start, gender_ratio='4-3',
                  our_score_before=0, their_score_before=0,
                  team_organization_id=setup['team_id'])
    db.session.add(point)
    db.session.flush()
    db.session.add_all([LineUp(point_id=point.id, player_id=pid,
                               team_organization_id=setup['team_id']) for pid in setup['line']])
    db.session.commit()
    return point.id


def _record(setup, point_id, event_type, player_id=None, offensive=True, **extra):
    payload = {'event_type': event_type, 'field_position_x': 50, 'field_position_y': 18,
               'is_offensive': offensive, **extra}
    if player_id is not None:
        payload['player_id'] = player_id
    return setup['client'].post(f'/stats/record/{point_id}', json=payload)


def _ok(r):
    assert r.status_code == 201, r.get_data(as_text=True)
    return r.get_json()


def _player_stats(setup):
    r = setup['client'].get(f"/stats/api/player-stats?game_id={setup['game_id']}")
    assert r.status_code == 200
    return {row['id']: row for row in r.get_json()}


def _game_stats(setup):
    db.session.expire_all()
    return calculate_game_stats(db.session.get(Game, setup['game_id']))


def test_opponent_block_counts_for_none_of_our_players(setup):
    a, b, c = setup['line'][:3]
    point_id = _point(setup, 'defense')

    block = _ok(_record(setup, point_id, 'block', offensive=False, is_opponent=True))
    assert block['player_id'] is None and block['is_opponent'] is True
    _ok(_record(setup, point_id, 'catch', a))
    _ok(_record(setup, point_id, 'catch', b))
    _ok(_record(setup, point_id, 'goal', c))
    assert setup['client'].post(f'/stats/finish_point/{point_id}').status_code == 200

    stats = _player_stats(setup)
    assert sum(s['blocks'] for s in stats.values()) == 0
    # The first player on the line used to be the placeholder for the opponent.
    assert stats[setup['line'][0]]['blocks'] == 0
    assert stats[a]['hockey_assists'] == 1
    assert stats[b]['assists'] == 1
    assert stats[c]['goals'] == 1
    # The pickup after the opponent's play has no thrower of ours.
    pickup = Throw.query.filter_by(receiver_id=a).one()
    assert pickup.thrower_id is None

    # Team level: we gained the disc once and scored without turning it over.
    game = _game_stats(setup)
    assert game['possessions_gained'] == 1
    assert game['turnovers'] == 0
    assert game['goals'] == 1


def test_opponent_ignores_a_placeholder_player_from_older_clients(setup):
    point_id = _point(setup, 'defense')
    first = setup['line'][0]
    event = _ok(_record(setup, point_id, 'block', first, offensive=False, is_opponent=True))
    assert event['player_id'] is None
    assert _player_stats(setup)[first]['blocks'] == 0


def test_opponent_scored_on_concedes_the_point(setup):
    point_id = _point(setup, 'defense')
    _ok(_record(setup, point_id, 'scored_on', offensive=False, is_opponent=True))
    assert setup['client'].post(f'/stats/finish_point/{point_id}').status_code == 200
    db.session.expire_all()
    point = db.session.get(Point, point_id)
    assert point.point_outcome == 'conceded' and point.their_score_after == 1


def test_unknown_catch_saves(setup):
    a, b, c = setup['line'][:3]
    point_id = _point(setup, 'offense')

    _ok(_record(setup, point_id, 'catch', a))
    unknown = _ok(_record(setup, point_id, 'catch', is_unknown_player=True))
    assert unknown['player_id'] is None and unknown['is_unknown_player'] is True
    _ok(_record(setup, point_id, 'catch', b))
    _ok(_record(setup, point_id, 'goal', c))
    assert setup['client'].post(f'/stats/finish_point/{point_id}').status_code == 200

    event = db.session.get(Event, unknown['id'])
    assert event.player_id is None and event.is_unknown_player

    stats = _player_stats(setup)
    # a completed a pass to the unknown player; b caught one from them.
    assert stats[a]['completions'] == 1
    assert Throw.query.filter_by(receiver_id=b, thrower_id=None).count() == 1
    assert stats[b]['assists'] == 1
    assert stats[c]['goals'] == 1
    # Nobody of ours is credited with the unknown player's hockey assist.
    assert sum(s['hockey_assists'] for s in stats.values()) == 0


def test_unknown_throwaway_is_still_a_team_turnover(setup):
    a = setup['line'][0]
    point_id = _point(setup, 'offense')
    _ok(_record(setup, point_id, 'catch', a))
    _ok(_record(setup, point_id, 'throwaway', is_unknown_player=True))

    assert _game_stats(setup)['turnovers'] == 1
    assert sum(s['throwaways'] for s in _player_stats(setup).values()) == 0


def test_a_named_play_still_needs_a_player(setup):
    point_id = _point(setup, 'offense')
    r = _record(setup, point_id, 'catch')
    assert r.status_code == 400
    assert Event.query.count() == 0
