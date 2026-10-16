"""Setting up and recording points in Positional Analysis mode: only the
game's players are offered, O/D, ratio and line follow from earlier
points, and the score and next point stay right when analysing a game
taken live on Game Day."""
import re

import pytest

from app import db
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.player import Player
from app.models.point import LineUp, Point
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
            'players': [(p.id, p.name) for p in players]}


def _line(ratio='4-3', skip=0):
    """Seven player ids for a mixed ratio (men-women)."""
    men, women = map(int, ratio.split('-'))
    m = [p.id for p in Player.query.filter_by(gender='male').order_by(Player.id)][skip:skip + men]
    w = [p.id for p in Player.query.filter_by(gender='female').order_by(Player.id)][skip:skip + women]
    return m + w


def _add_point(setup, number, outcome, start='offense', ours=0, theirs=0, ratio='4-3',
               line=None, force='forehand'):
    point = Point(game_id=setup['game_id'], point_number=number,
                  our_line_type='O-line' if start == 'offense' else 'D-line',
                  starting_position=start, point_outcome=outcome, gender_ratio=ratio,
                  force_direction=force,
                  our_score_before=ours, their_score_before=theirs,
                  our_score_after=ours + (outcome == 'scored'),
                  their_score_after=theirs + (outcome == 'conceded'),
                  team_organization_id=setup['team_id'])
    db.session.add(point)
    db.session.flush()
    for pid in (line or _line(ratio)):
        db.session.add(LineUp(point_id=point.id, player_id=pid, team_organization_id=setup['team_id']))
    game = db.session.get(Game, setup['game_id'])
    game.our_score, game.their_score = point.our_score_after, point.their_score_after
    db.session.commit()
    return point.id


def _form(setup):
    r = setup['client'].get(f"/points/add/{setup['game_id']}")
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_data(as_text=True)


def _starting_on(html):
    return re.search(r'name="starting_position"[^>]*value="(\w+)"[^>]*checked', html).group(1)


def _option(html, field):
    start = html.index(f'id="{field}"')
    options = html[start:html.index('</select>', start)].split('<option')[1:]
    # The browser shows the first option when none is marked selected.
    chosen = next((o for o in options if 'selected' in o.split('>')[0]), options[0])
    return chosen.split('value="', 1)[1].split('"')[0]


def _preselected(html):
    return {int(i) for i in re.findall(r'player-card selected"\s+data-player-id="(\d+)"', html)}


def _save(setup, line, start='offense', ratio='4-3'):
    return setup['client'].post(f"/points/add/{setup['game_id']}", data={
        'point_number': (Point.query.filter_by(game_id=setup['game_id']).count() + 1),
        'starting_position': start, 'force_direction': 'forehand', 'gender_ratio': ratio,
        'players': ','.join(map(str, line))})


# --- roster -----------------------------------------------------------------

def test_only_assigned_players_are_listed(setup):
    assigned, others = setup['players'][:10], setup['players'][10:]
    # Bulk assignment used to leave team_organization_id empty; those count.
    db.session.add_all(
        [GamePlayer(game_id=setup['game_id'], player_id=pid, team_organization_id=setup['team_id'])
         for pid, _ in assigned[:5]]
        + [GamePlayer(game_id=setup['game_id'], player_id=pid) for pid, _ in assigned[5:]])
    db.session.commit()

    html = _form(setup)
    for _, name in assigned:
        assert name in html
    for _, name in others:
        assert name not in html


def test_unassigned_game_falls_back_to_full_roster(setup):
    html = _form(setup)
    for _, name in setup['players']:
        assert name in html


def test_substitutes_come_from_the_game_roster(setup):
    assigned = [pid for pid, _ in setup['players'][:10]]
    db.session.add_all([GamePlayer(game_id=setup['game_id'], player_id=pid,
                                   team_organization_id=setup['team_id']) for pid in assigned])
    db.session.commit()
    line = [pid for pid in assigned if pid in set(_line())] or assigned[:7]
    point_id = _add_point(setup, 1, None, line=line)

    r = setup['client'].get(f'/stats/available_players/{point_id}')
    offered = {p['id'] for p in r.get_json()['available_players']}
    assert offered == set(assigned) - set(line)


# --- O/D --------------------------------------------------------------------

def test_first_point_defaults_to_offense(setup):
    assert _starting_on(_form(setup)) == 'offense'


def test_after_we_score_we_start_on_defense(setup):
    _add_point(setup, 1, 'scored')
    html = _form(setup)
    assert _starting_on(html) == 'defense'
    assert 'We scored point 1' in html


def test_after_they_score_we_start_on_offense(setup):
    _add_point(setup, 1, 'scored')
    _add_point(setup, 2, 'conceded', start='defense', ours=1, ratio='3-4')
    assert _starting_on(_form(setup)) == 'offense'


def test_halftime_button_flips_the_opening_side(setup):
    _add_point(setup, 1, 'scored', start='defense')
    r = setup['client'].post(f"/points/halftime/{setup['game_id']}")
    assert r.status_code == 302
    html = _form(setup)
    # We scored the last point, but the half starts the other way from the game.
    assert _starting_on(html) == 'offense'
    assert 'Second half' in html and 'Undo halftime' in html

    setup['client'].post(f"/points/halftime/{setup['game_id']}")
    db.session.expire_all()
    assert db.session.get(Game, setup['game_id']).halftime_our_score is None
    assert _starting_on(_form(setup)) == 'defense'


def test_saved_line_type_follows_starting_side(setup):
    r = _save(setup, _line(), start='defense')
    assert r.status_code == 302, r.get_data(as_text=True)
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    assert (point.starting_position, point.our_line_type) == ('defense', 'D-line')


# --- ABBA ratio -------------------------------------------------------------

@pytest.mark.parametrize('first, expected', [
    ('4-3', ['4-3', '3-4', '3-4', '4-3', '4-3', '3-4']),
    ('3-4', ['3-4', '4-3', '4-3', '3-4', '3-4', '4-3']),
])
def test_ratio_follows_abba_from_the_first_point(setup, first, expected):
    ratios = [first]
    for n in range(1, len(expected)):
        _add_point(setup, n, 'scored', ratio=ratios[-1], ours=n - 1)
        ratios.append(_option(_form(setup), 'gender_ratio'))
    assert ratios == expected


# --- suggested line & defaults ---------------------------------------------

def test_last_line_on_the_same_side_is_preselected(setup):
    o_line = _line('4-3')
    d_line = _line('3-4', skip=4)
    _add_point(setup, 1, 'conceded', start='offense', line=o_line, force='backhand')
    _add_point(setup, 2, 'scored', start='offense', theirs=1, ratio='3-4', line=_line('3-4', skip=1))
    _add_point(setup, 3, 'conceded', start='defense', ours=1, theirs=1, ratio='3-4', line=d_line)

    html = _form(setup)  # they scored point 3, so we're on O
    assert _starting_on(html) == 'offense'
    assert _preselected(html) == set(_line('3-4', skip=1))  # point 2, the latest O point
    assert '"from_point": 3' in html  # the D line is ready if they flip to D
    assert _option(html, 'force_direction') == 'forehand'


def test_force_direction_carries_over(setup):
    _add_point(setup, 1, 'scored', force='zone')
    assert _option(_form(setup), 'force_direction') == 'zone'


def test_outcome_field_is_only_on_edit(setup):
    assert 'id="point_outcome"' not in _form(setup)
    point_id = _add_point(setup, 1, 'scored')
    r = setup['client'].get(f'/points/edit/{point_id}')
    html = r.get_data(as_text=True)
    assert 'id="point_outcome"' in html
    assert _preselected(html) == set(_line())


def test_new_point_does_not_change_the_score(setup):
    r = _save(setup, _line())
    assert r.status_code == 302, r.get_data(as_text=True)
    db.session.expire_all()
    game = db.session.get(Game, setup['game_id'])
    assert (game.our_score or 0, game.their_score or 0) == (0, 0)
    assert Point.query.filter_by(game_id=setup['game_id']).one().point_outcome is None


def test_wrong_ratio_is_rejected(setup):
    r = _save(setup, _line('3-4'), ratio='4-3')
    assert r.status_code == 200
    assert 'do not match required gender ratio' in r.get_data(as_text=True)
    assert Point.query.count() == 0


# --- finishing points -------------------------------------------------------

def _score_goal(setup, point_id, player_id):
    r = setup['client'].post(f'/stats/record/{point_id}', json={
        'player_id': player_id, 'event_type': 'catch', 'field_position_x': 50,
        'field_position_y': 18, 'is_offensive': True})
    assert r.status_code == 201, r.get_data(as_text=True)
    r = setup['client'].post(f'/stats/record/{point_id}', json={
        'player_id': player_id, 'event_type': 'goal', 'field_position_x': 95,
        'field_position_y': 18, 'is_offensive': True})
    assert r.status_code == 201, r.get_data(as_text=True)
    return setup['client'].post(f'/stats/finish_point/{point_id}').get_json()


def test_end_point_goes_to_setting_up_the_next_one(setup):
    _save(setup, _line())
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    data = _score_goal(setup, point.id, _line()[0])
    assert data['next_point_url'] == f"/points/add/{setup['game_id']}"


def test_game_day_points_are_analysed_in_order_without_rewinding_the_score(setup):
    # Three points taken live on Game Day: lines and outcomes, no events.
    ids = [_add_point(setup, 1, 'conceded'),
           _add_point(setup, 2, 'scored', theirs=1, ratio='3-4', line=_line('3-4')),
           _add_point(setup, 3, 'scored', start='defense', ours=1, theirs=1, ratio='3-4',
                      line=_line('3-4'))]

    html = setup['client'].get(f"/points/game/{setup['game_id']}").get_data(as_text=True)
    assert 'Analyse Point 1' in html

    # Point 2 was a goal on Game Day; analysing it keeps the game at 2-1.
    data = _score_goal(setup, ids[1], _line('3-4')[0])
    assert data['next_point_url'] == f'/stats/record/{ids[2]}'
    db.session.expire_all()
    game = db.session.get(Game, setup['game_id'])
    assert (game.our_score, game.their_score) == (2, 1)

    html = setup['client'].get(f"/points/game/{setup['game_id']}").get_data(as_text=True)
    assert 'Analyse Point 1' in html  # still not analysed
