"""Setting up a point in Positional Analysis mode (/points/add): only the
game's players are offered, and O/D follows from the previous point."""
import pytest

from app import db
from app.models.game import Game
from app.models.game_player import GamePlayer
from app.models.point import Point
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


def _add_point(setup, number, outcome, start='offense', ours=0, theirs=0):
    point = Point(game_id=setup['game_id'], point_number=number,
                  our_line_type='O-line' if start == 'offense' else 'D-line',
                  starting_position=start, point_outcome=outcome,
                  our_score_before=ours, their_score_before=theirs,
                  our_score_after=ours + (outcome == 'scored'),
                  their_score_after=theirs + (outcome == 'conceded'),
                  team_organization_id=setup['team_id'])
    db.session.add(point)
    db.session.commit()


def _form(setup):
    r = setup['client'].get(f"/points/add/{setup['game_id']}")
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_data(as_text=True)


def _selected(html, field):
    start = html.index(f'id="{field}"')
    options = html[start:html.index('</select>', start)].split('<option')[1:]
    # The browser shows the first option when none is marked selected.
    chosen = next((o for o in options if 'selected' in o.split('>')[0]), options[0])
    return chosen.split('value="', 1)[1].split('"')[0]


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


def test_first_point_defaults_to_offense(setup):
    html = _form(setup)
    assert _selected(html, 'starting_position') == 'offense'


def test_after_we_score_we_start_on_defense(setup):
    _add_point(setup, 1, 'scored')
    html = _form(setup)
    assert _selected(html, 'starting_position') == 'defense'
    assert _selected(html, 'our_line_type') == 'D-line'
    assert 'We scored point 1' in html


def test_after_they_score_we_start_on_offense(setup):
    _add_point(setup, 1, 'scored')
    _add_point(setup, 2, 'conceded', start='defense', ours=1)
    html = _form(setup)
    assert _selected(html, 'starting_position') == 'offense'
    assert _selected(html, 'our_line_type') == 'O-line'


def test_second_half_flips_the_opening_side(setup):
    _add_point(setup, 1, 'scored', start='defense')
    game = db.session.get(Game, setup['game_id'])
    game.halftime_our_score, game.halftime_their_score = 1, 0
    db.session.commit()
    html = _form(setup)
    # We scored the last point, but the half starts the other way from the game.
    assert _selected(html, 'starting_position') == 'offense'
    assert 'Second half' in html


def test_point_left_open_does_not_change_the_score(setup):
    from app.models.player import Player
    # 4 male / 3 female for the mixed 4-3 ratio on point 1.
    men = [p.id for p in Player.query.filter_by(gender='male').limit(4)]
    women = [p.id for p in Player.query.filter_by(gender='female').limit(3)]
    ids = men + women
    r = setup['client'].post(f"/points/add/{setup['game_id']}", data={
        'point_number': 1, 'our_line_type': 'O-line', 'starting_position': 'offense',
        'force_direction': 'forehand', 'point_outcome': '', 'gender_ratio': '4-3',
        'players': ','.join(map(str, ids))})
    assert r.status_code == 302, r.get_data(as_text=True)
    db.session.expire_all()
    game = db.session.get(Game, setup['game_id'])
    assert (game.our_score or 0, game.their_score or 0) == (0, 0)
    point = Point.query.filter_by(game_id=setup['game_id']).one()
    assert point.point_outcome is None
