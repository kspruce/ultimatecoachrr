"""The point replay in a real browser: it plays through the point without
moving the page, steps and jumps from the events table, and stands the pitch
up on an upright phone.

Skipped without Playwright's Chromium; see tests/test_drill_editor_browser.py
for the settings that run it offline."""
import pytest

from app import db
from app.models.game import Game
from app.models.player import Player
from app.models.team_organization import TeamOrganization
from app.models.user import User
from tests.test_drill_editor_browser import browser, live_server, logged_in_page  # noqa: F401
from tests.test_point_detail import _play_break_back, _point
from tests.test_teams import make_user

pytest.importorskip('playwright.sync_api')


@pytest.fixture
def point(app, team):
    players = [Player(name=f'Player {i}', jersey_number=i, gender='female' if i % 2 else 'male',
                      active=True, team_organization_id=team.id) for i in range(1, 8)]
    game = Game(opponent='Opponent A', team_organization_id=team.id)
    db.session.add_all(players + [game])
    db.session.commit()
    admin = make_user(team, 'pointadmin', role='admin')
    from tests import stats_data
    setup = {'client': stats_data.Client(app, admin.id, team.id), 'team_id': team.id,
             'game_id': game.id, 'line': [p.id for p in players]}
    point_id = _point(setup, start='offense', outcome='scored')
    _play_break_back(setup, point_id)
    ids = admin.id, team.id, point_id
    db.session.remove()
    return ids


def test_replay_keeps_the_page_still(app, team, live_server, browser, point):
    admin_id, team_id, point_id = point
    admin, team = db.session.get(User, admin_id), db.session.get(TeamOrganization, team_id)
    page = logged_in_page(app, browser, live_server, admin, team, viewport={'width': 1280, 'height': 800})
    page.goto(live_server + f'/points/{point_id}')
    page.wait_for_selector('#pitch .marker')

    assert page.locator('#pitch .marker').count() == 8
    assert page.locator('#pitch line.throw').count() == 5
    # Landscape pitch, 100 x 37
    assert page.get_attribute('#pitch', 'viewBox') == '0 0 1000 370'

    page.locator('#replay-card').scroll_into_view_if_needed()
    scroll_before = page.evaluate('window.scrollY')
    page.mouse.move(5, 795)  # off the navbar, whose menus open on hover
    page.select_option('#speed', '2')
    page.click('#btn-play')
    page.wait_for_function("document.querySelector('#scrubber').value === '7'", timeout=15000)
    page.wait_for_function("document.querySelector('#btn-play span').textContent === 'Play'", timeout=5000)
    assert page.evaluate('window.scrollY') == scroll_before
    assert 'Goal' in page.inner_text('#caption')

    # Step back with the keyboard, jump from the table
    page.click('h1')
    page.keyboard.press('ArrowLeft')
    assert page.input_value('#scrubber') == '6'
    page.click('#events-table tr[data-step="2"]')
    assert page.input_value('#scrubber') == '2'
    assert 'not caught' in page.inner_text('#caption')
    assert page.locator('#events-table tr.active-event').get_attribute('data-step') == '2'


def test_upright_phone_stands_the_pitch_up(app, team, live_server, browser, point):
    admin_id, team_id, point_id = point
    admin, team = db.session.get(User, admin_id), db.session.get(TeamOrganization, team_id)
    page = logged_in_page(app, browser, live_server, admin, team,
                          viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
    page.goto(live_server + f'/points/{point_id}')
    page.wait_for_selector('#pitch .marker')
    assert page.get_attribute('#pitch', 'viewBox') == '0 0 370 1000'
    # Nothing wider than the screen
    assert page.evaluate('document.documentElement.scrollWidth') <= 390
