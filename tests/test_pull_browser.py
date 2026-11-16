"""Recording our pull on the stat taker, in a real browser: released (the
timer starts), landed (tap the field), who pulled, hang time and how it
went. A dropped pull also records their turnover, so we're on offence.

Skipped without Playwright's Chromium; see tests/test_drill_editor_browser.py
for the settings that run it offline."""
import threading

import pytest
from werkzeug.serving import make_server

from app import db
from app.models.event import Event, Pull
from app.models.game import Game
from app.models.player import Player
from app.models.point import LineUp, Point
from app.models.team_organization import TeamOrganization
from app.models.user import User
from tests.test_drill_editor_browser import browser, logged_in_page  # noqa: F401
from tests.test_teams import make_user

pytest.importorskip('playwright.sync_api')


@pytest.fixture
def live_server(app):
    """One request at a time. The page saves the pull and then their
    turnover straight away; with the tests' in-memory SQLite (one shared
    connection), a threaded server can end the first request (a rollback)
    in the middle of the second."""
    server = make_server('127.0.0.1', 0, app, threaded=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    thread.join(5)


@pytest.fixture
def d_point(app, team):
    players = [Player(name=f'Player {i}', jersey_number=i, gender='female' if i % 2 else 'male',
                      active=True, team_organization_id=team.id) for i in range(1, 8)]
    game = Game(opponent='Opponent A', team_organization_id=team.id)
    db.session.add_all(players + [game])
    db.session.commit()
    point = Point(game_id=game.id, point_number=1, our_line_type='D-line', starting_position='defense',
                  gender_ratio='4-3', our_score_before=0, their_score_before=0,
                  team_organization_id=team.id)
    db.session.add(point)
    db.session.commit()
    db.session.add_all([LineUp(point_id=point.id, player_id=p.id, team_organization_id=team.id) for p in players])
    db.session.commit()
    admin = make_user(team, 'pulladmin', role='admin')
    ids = admin.id, team.id, point.id, players[2].id
    db.session.remove()
    return ids


def test_record_a_dropped_pull(app, team, live_server, browser, d_point):
    admin_id, team_id, point_id, puller_id = d_point
    admin, team = db.session.get(User, admin_id), db.session.get(TeamOrganization, team_id)
    page = logged_in_page(app, browser, live_server, admin, team, viewport={'width': 1280, 'height': 800})
    page.goto(live_server + f'/stats/record/{point_id}')
    page.wait_for_selector('#pull-start')
    assert 'Pull not recorded' in page.inner_text('#pull-summary')

    page.click('#pull-start')
    page.wait_for_timeout(600)
    assert 'tap where it lands' in page.inner_text('#pull-timer')
    box = page.locator('#field').bounding_box()
    # Deep in the attacking end (attacking right): about 90 m upfield
    page.mouse.click(box['x'] + box['width'] * 0.9, box['y'] + box['height'] * 0.5)
    page.wait_for_selector('#pull-select', state='visible')
    hang = float(page.input_value('#pull-hang-time'))
    assert 0.4 <= hang <= 5
    page.fill('#pull-hang-time', '5.4')
    page.click(f'.pull-player[data-player-id="{puller_id}"]')
    page.click('.pull-result[data-result="dropped"]')
    page.wait_for_function("document.querySelector('#pull-summary').textContent.includes('5.4 s')")
    page.wait_for_function("document.querySelector('#events-table-body').textContent.toUpperCase().includes('UNFORCED')")
    assert page.inner_text('#possession-indicator') == 'On Offense'

    db.session.remove()
    pull = Pull.query.filter_by(point_id=point_id).one()
    assert (pull.player_id, pull.hang_time, pull.result, pull.is_inbounds) == (puller_id, 5.4, 'dropped', True)
    assert 85 <= pull.landing_x <= 95 and 15 <= pull.landing_y <= 22
    turnover = Event.query.filter_by(point_id=point_id).one()
    assert (turnover.event_type, turnover.is_opponent) == ('unforced_turnover', True)

    # Undo the pull: the turnover stays (undo it like any play)
    page.click('#pull-undo')
    page.wait_for_function("document.querySelector('#pull-summary').textContent.includes('not recorded')")
    db.session.remove()
    assert Pull.query.filter_by(point_id=point_id).count() == 0
