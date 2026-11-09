"""The stats dashboard (app/stats/dashboard.py) and the numbers it shares
with the game, team and player pages."""
import re

import pytest
from flask_login import login_user

from app import db
from app.models.game import Game
from app.models.player import Player
from app.models.user import User
from app.stats import dashboard as dash, turnovers
from app.stats.players import get_players_base_stats, players_in_games
from app.stats.profile import TEAM_AXES, team_profile
from tests import stats_data


@pytest.fixture
def season(app):
    team = stats_data.build_team()
    admin = stats_data.build_admin(team)
    players = stats_data.build_players(team)
    client = stats_data.record_season(app, team, admin, players)
    return {'client': client, 'team': team, 'team_id': team.id, 'player_ids': [p.id for p in players]}


def _cells(html, column):
    """{player id: data-tot} for one column of the dashboard's player table."""
    out = {}
    for row in re.findall(r'<tr class="[^"]*" data-name=.*?</tr>', html, re.S):
        pid = int(re.search(r'/stats/player/(\d+)', row).group(1))
        out[pid] = re.findall(r'data-tot="([^"]*)"', row)[column]
    return out


def test_dashboard_sections(app, season):
    html = season['client'].get('/stats/').get_data(as_text=True)
    for text in ('id="headline"', 'id="leaders"', 'id="playerTable"', 'Median player',
                 'Where we score from', 'Where we turn it over', 'Open vs break side',
                 'Top Throwing Pairs', 'Line Usage', 'points have full stats'):
        assert text in html, text
    # The old network diagram, heatmap.js and DataTables are gone
    for text in ('Player Connections', 'heatmap.js', 'dataTables', 'Team Average'):
        assert text not in html, text


def test_plus_minus_is_the_same_everywhere(app, season):
    """Goals + assists + blocks - turnovers (stalls included) on the
    dashboard, as on the player and game pages and in the CSV."""
    html = season['client'].get('/stats/').get_data(as_text=True)
    plus_minus_col = [c['key'] for c in dash.COLUMNS].index('plus_minus')
    shown = _cells(html, plus_minus_col)
    with app.test_request_context():
        login_user(User.query.filter_by(username='admin').first())
        games = Game.query.all()
        players = Player.query.filter(Player.id.in_(shown)).all()
        stats = get_players_base_stats(players, games)
    assert shown
    for pid, value in shown.items():
        s = stats[pid]
        assert int(value) == s['plus_minus'] == s['goals'] + s['assists'] + s['blocks'] - s['turnovers']


def test_players_in_games_leaves_out_the_bench(app, season):
    bench = Player(name='Never Played', team_organization_id=season['team_id'])
    db.session.add(bench)
    db.session.commit()
    with app.test_request_context():
        login_user(User.query.filter_by(username='admin').first())
        ids = {p.id for p in players_in_games(Game.query.all())}
        assert players_in_games([]) == []
    assert ids == set(season['player_ids'])
    assert 'Never Played' not in season['client'].get('/stats/').get_data(as_text=True)


def test_a_player_sees_their_own_row_and_the_medians(app, season):
    me = db.session.get(Player, season['player_ids'][3])
    user = User(username='me', email='me@example.com', role='player', team_organization_id=season['team_id'])
    user.set_password('x')
    db.session.add(user)
    db.session.flush()
    me.user_id = user.id
    db.session.commit()
    client = stats_data.Client(app, user.id, season['team_id'])
    html = client.get('/stats/').get_data(as_text=True)
    rows = re.findall(r'data-name="([^"]+)"', html)
    assert rows == [me.name.lower()]
    assert 'Median player' in html and 'id="leaders"' not in html


def test_field_grid_counts_each_spot_once():
    grid = dash._grid([(1, 1), (2, 2), (95, 36), (None, 4), (100, 37)])
    assert grid['total'] == 4
    # (1, 1) and (2, 2) share the corner cell; the far corner and the
    # edge of the field (clamped onto it) share the other
    assert [(c['x'], c['y'], c['count']) for c in grid['cells']] == [(0, 0, 2), (90, 29.6, 2)]
    assert max(c['strength'] for c in grid['cells']) == 1


def test_field_maps_and_pairs_add_up(app, season):
    with app.test_request_context():
        login_user(User.query.filter_by(username='admin').first())
        games = Game.query.all()
        game_ids = {g.id for g in games}
        data = turnovers.ThrowingData(games)
        field = dash.field_maps(data, game_ids)
        handling = turnovers.handling_summary(data, None, game_ids)
        players = {p.id: p for p in Player.query.all()}
        pairs = dash.throwing_pairs(data, game_ids, players)
        assists = sum(t['assist'] for t in data.throws)
    assert field['scoring']['total'] == assists
    assert field['turnovers']['total'] == handling['turnovers']
    assert sum(z['throws'] for z in field['sides']['zones']) <= field['sides']['throws']
    assert 0 < len(pairs) <= 10
    assert [p['completions'] for p in pairs] == sorted((p['completions'] for p in pairs), reverse=True)


def test_team_radar_ranks_against_the_teams_history(app, season):
    with app.test_request_context():
        login_user(User.query.filter_by(username='admin').first())
        games = Game.query.all()
        data = turnovers.ThrowingData(games)
        profile = team_profile(data, {g.id for g in games}, set(), games)
    assert profile['periods'] >= 3
    for side, axes in TEAM_AXES.items():
        assert [a['key'] for a in profile[side]] == [a['key'] for a in axes]
        for row in profile[side]:
            assert row['percentile'] is None or 0 <= row['percentile'] <= 100
    html = season['client'].get('/stats/team').get_data(as_text=True)
    assert 'Offensive Profile' in html and 'const TEAM_RADAR = {' in html
    assert '100% represents excellent performance' not in html
