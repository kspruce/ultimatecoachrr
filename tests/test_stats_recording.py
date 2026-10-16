"""Stats recorded in Positional Analysis: player connections (who threw
to whom), the game score after corrections, and per-game player stats."""
import json
import re

from app.models.point import Point
from app.models.throws import Throw
from tests.test_point_setup import _line, _save, setup  # noqa: F401


def _record(setup, point_id, player_id, event_type):
    r = setup['client'].post(f'/stats/record/{point_id}', json={
        'player_id': str(player_id), 'event_type': event_type,
        'field_position_x': 50, 'field_position_y': 18, 'is_offensive': True})
    assert r.status_code == 201, r.get_data(as_text=True)


def _links(html):
    data = json.loads(re.search(r'const connections = (\{.*?\});', html).group(1))
    return {(link['source'], link['target']): link['value'] for link in data['links']}


def _pairs():
    return sorted((t.thrower_id, t.receiver_id, t.throw_type) for t in Throw.query.all())


def test_every_pass_in_a_game_is_a_connection(setup):
    _save(setup, _line())
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    a, b, c = _line()[:3]
    for pid, event in [(a, 'catch'), (b, 'catch'), (a, 'catch'),
                       (c, 'catch'), (b, 'catch'), (a, 'goal')]:
        _record(setup, point.id, pid, event)
    setup['client'].post(f'/stats/finish_point/{point.id}')

    expected = {(a, b): 1, (b, a): 2, (a, c): 1, (c, b): 1}
    game_page = setup['client'].get(f"/stats/game/{setup['game_id']}").get_data(as_text=True)
    assert _links(game_page) == expected
    assert _links(setup['client'].get('/stats/').get_data(as_text=True)) == expected
    api = setup['client'].get('/stats/api/connection-data').get_json()
    assert {(link['source'], link['target']): link['value'] for link in api['links']} == expected


def test_undoing_and_rerecording_a_goal_counts_each_pass_once(setup):
    _save(setup, _line())
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    a, b, c = _line()[:3]
    for pid, event in [(a, 'catch'), (b, 'catch'), (c, 'goal')]:
        _record(setup, point.id, pid, event)
    after_goal = _pairs()
    assert after_goal == sorted([(a, b, 'hockey_assist'), (b, c, 'assist')])

    assert setup['client'].post(f'/stats/undo_event/{point.id}').status_code == 200
    assert _pairs() == [(a, b, 'regular')]

    _record(setup, point.id, c, 'goal')
    assert _pairs() == after_goal


# --- related stats checks ----------------------------------------------------

def test_correcting_an_earlier_point_carries_through_to_the_game_score(setup):
    from app import db
    from app.models.game import Game
    from tests.test_point_setup import _add_point

    first = _add_point(setup, 1, None)
    a = _line()[0]
    _record(setup, first, a, 'catch')
    _record(setup, first, a, 'goal')
    second = _add_point(setup, 2, None, start='defense', ours=1)

    # Point 1 was actually theirs: undo the goal and record it as scored on.
    client = setup['client']
    assert client.post(f'/stats/undo_event/{first}').status_code == 200
    r = client.post(f'/stats/record/{first}', json={
        'player_id': str(a), 'event_type': 'scored_on',
        'field_position_x': 5, 'field_position_y': 18, 'is_offensive': False})
    assert r.status_code == 201, r.get_data(as_text=True)

    db.session.expire_all()
    game = db.session.get(Game, setup['game_id'])
    assert (game.our_score, game.their_score) == (0, 1)
    p2 = db.session.get(Point, second)
    assert (p2.our_score_before, p2.their_score_before) == (0, 1)


def test_a_game_with_no_points_has_no_player_stats(setup):
    from app import db
    from app.models.game import Game

    _save(setup, _line())
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    a, b = _line()[:2]
    _record(setup, point.id, a, 'catch')
    _record(setup, point.id, b, 'goal')

    empty = Game(opponent='Not played yet', team_organization_id=setup['team_id'])
    db.session.add(empty)
    db.session.commit()
    rows = setup['client'].get(f'/stats/api/player-stats?game_id={empty.id}').get_json()
    rows = rows if isinstance(rows, list) else rows.get('players', rows)
    assert all(not (r.get('goals') or r.get('assists')) for r in rows), rows
