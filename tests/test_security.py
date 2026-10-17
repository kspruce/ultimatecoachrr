"""Hardening checks: role checks on writes, team isolation in dropdowns,
escaping of text people type, and the response headers/cookies."""
import pytest

from app import db
from app.models.game import Game
from app.models.player import Player
from app.models.point import Point
from app.models.session import SessionPlan, SessionRSVP
from app.models.tournament import Tournament
from app.models.user import User
from tests import stats_data

XSS = '<img src=x onerror=alert(1)>'


@pytest.fixture
def season(app):
    team = stats_data.build_team('Alpha', 'alpha')
    admin = stats_data.build_admin(team, 'admina', superadmin=False)
    players = stats_data.build_players(team, 14)
    coach = stats_data.record_season(app, team, admin, players, games_per_tournament=1,
                                     points_per_game=2)
    user = User(username='pl', email='pl@example.com', role='player',
                team_organization_id=team.id)
    user.set_password('x')
    db.session.add(user)
    db.session.commit()
    player = db.session.get(Player, players[0].id)
    player.user_id = user.id
    db.session.commit()
    other = stats_data.build_team('Bravo', 'bravo')
    db.session.add(Tournament(name='Bravo Secret Cup', season='2026',
                              team_organization_id=other.id))
    db.session.commit()
    return {'team': team.id, 'other': other.id, 'coach': coach, 'player_id': player.id,
            'player': stats_data.Client(app, user.id, team.id)}


def test_players_cannot_delete_points_or_add_games(season):
    point_id = Point.query.first().id
    games = Game.query.count()
    season['player'].post(f'/points/delete/{point_id}')
    season['player'].post('/games/add', data={'opponent': 'X', 'date': '2026-06-01'})
    db.session.expire_all()
    assert db.session.get(Point, point_id) is not None
    assert Game.query.count() == games


def test_player_goals_are_escaped(season):
    pid = season['player_id']
    season['player'].post(f'/team/player/{pid}/update_goals',
                          data={'short_term_goals': f'{XSS}\nline two'})
    page = season['coach'].get(f'/team/player/{pid}').get_data(as_text=True)
    assert XSS not in page and '&lt;img src=x' in page


def test_markdown_and_embeds_drop_script(app):
    from flask import render_template_string
    with app.test_request_context():
        md = render_template_string('{{ x|markdown }}', x=f'**hi** <script>alert(1)</script>{XSS}'
                                    '[a](javascript:alert(1))')
        assert '<strong>hi</strong>' in md
        assert '<script' not in md and 'onerror' not in md and 'javascript:' not in md
        embed = render_template_string('{{ x|embed_html }}', x=(
            '<iframe src="https://ultiplay.app/e/1" width="600"></iframe>'
            '<iframe src="javascript:alert(1)" onload="alert(1)"></iframe><script>x</script>'))
        assert '<iframe src="https://ultiplay.app/e/1" width="600"></iframe>' in embed
        assert 'javascript:' not in embed and 'onload' not in embed and '<script' not in embed


def test_names_cannot_break_out_of_chart_scripts(season):
    game = Game.query.first()
    game.opponent = '</script><script>alert(1)</script>'
    db.session.commit()
    page = season['coach'].get('/stats/team').get_data(as_text=True)
    assert '</script><script>alert(1)' not in page


def test_dropdowns_only_list_this_teams_rows(season):
    page = season['coach'].get('/scouting/').get_data(as_text=True)
    assert 'alpha Tour 1' in page and 'Bravo Secret Cup' not in page


def test_quick_checkin_is_for_admins_and_this_team(season):
    session = SessionPlan(title='Practice', team_organization_id=season['team'])
    outsider = Player(name='Outsider', team_organization_id=season['other'])
    db.session.add_all([session, outsider])
    db.session.commit()
    url = f'/sessions/{session.id}/quick_checkin'
    season['player'].post(url, json={'player_id': season['player_id'], 'status': 'yes'})
    assert season['coach'].post(url, json={'player_id': outsider.id, 'status': 'yes'}).status_code == 404
    assert SessionRSVP.query.count() == 0
    assert season['coach'].post(url, json={'player_id': season['player_id'], 'status': 'yes'}).status_code == 200
    assert SessionRSVP.query.count() == 1


@pytest.mark.parametrize('target', ['//evil.example', '/\\evil.example', 'https://evil.example',
                                    'javascript:alert(1)'])
def test_login_never_redirects_off_site(app, season, target):
    client = app.test_client()
    r = client.post(f'/auth/login?next={target}', data={'username': 'pl', 'password': 'x'})
    assert r.status_code == 302 and 'evil' not in r.location and 'javascript' not in r.location


def test_security_headers(season):
    r = season['coach'].get('/')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'SAMEORIGIN'


def test_login_cookies_are_secure_by_default():
    from config import Config
    assert Config.SESSION_COOKIE_SECURE and Config.REMEMBER_COOKIE_SECURE
    assert Config.SESSION_COOKIE_SAMESITE == 'Lax'
