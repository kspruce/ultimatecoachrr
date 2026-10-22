"""The drill editor in a real browser: draw players and arrows, add a stage,
save, then play the animation on the drill page.

Needs Playwright and its Chromium (CI installs them); skipped otherwise.
DRILL_TEST_CHROMIUM points at a Chromium to use instead of Playwright's own.
DRILL_TEST_CDN_DIR serves cdn.jsdelivr.net files from a local folder laid out
like the CDN (e.g. fabric@5.3.0/dist/fabric.min.js), for machines without
internet access.
"""
import json
import mimetypes
import os
import threading

import pytest
from werkzeug.serving import make_server

from app import db
from app.models.drill import SavedDrill
from tests.test_teams import make_user

sync_api = pytest.importorskip('playwright.sync_api')

CDN = 'https://cdn.jsdelivr.net/npm/'


@pytest.fixture
def live_server(app):
    server = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    thread.join(5)


@pytest.fixture
def browser():
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=os.environ.get('DRILL_TEST_CHROMIUM') or None)
        except Exception as e:  # no browser installed
            pytest.skip(f'Chromium not available: {e}')
        yield browser
        browser.close()


def serve_cdn_locally(context):
    folder = os.environ.get('DRILL_TEST_CDN_DIR')
    if not folder:
        return

    def handle(route):
        path = os.path.join(folder, route.request.url[len(CDN):].split('?')[0])
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                route.fulfill(body=f.read(), content_type=mimetypes.guess_type(path)[0] or 'text/plain')
        else:
            route.abort()

    context.route(CDN + '**', handle)
    # Anything else external (icon fonts, jQuery) isn't needed here
    context.route(lambda url: not url.startswith('http://127.0.0.1') and not url.startswith(CDN),
                  lambda route: route.abort())


def logged_in_page(app, browser, live_server, user, team, **context_options):
    user_id, team_id = user.get_id(), team.id  # (the request below ends the DB session)
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = user_id
        s['_fresh'] = True
        s['current_team_id'] = team_id
    cookie = client.get_cookie('session')
    context = browser.new_context(**{'viewport': {'width': 1400, 'height': 950}, **context_options})
    context.add_cookies([{'name': 'session', 'value': cookie.value, 'url': live_server}])
    serve_cdn_locally(context)
    page = context.new_page()
    page.errors = []
    page.on('pageerror', lambda e: page.errors.append(str(e)))
    page.on('dialog', lambda d: d.accept())
    return page


def field_mapper(page):
    """Field units (10 per yard, whole 110x40 yard field) to page pixels."""
    box = page.locator('.upper-canvas').bounding_box()
    w, h = 1100, 400
    zoom = min(box['width'] / w, box['height'] / h)
    ox = box['x'] + (box['width'] - w * zoom) / 2
    oy = box['y'] + (box['height'] - h * zoom) / 2
    return lambda x, y: (ox + x * zoom, oy + y * zoom)


def test_draw_stages_save_and_play(app, team, live_server, browser):
    coach = make_user(team, 'browsercoach', role='coach')
    page = logged_in_page(app, browser, live_server, coach, team)
    page.goto(live_server + '/sessions/drills/editor')
    page.wait_for_selector('.upper-canvas')
    at = field_mapper(page)

    def click(x, y):
        page.mouse.click(*at(x, y))

    def drag(x1, y1, x2, y2):
        page.mouse.move(*at(x1, y1))
        page.mouse.down()
        page.mouse.move(*at(x2, y2), steps=8)
        page.mouse.up()

    page.fill('#drill-title', 'Give and go')
    page.click('.tool-btn[data-tool="player-o"]')
    click(300, 200)
    click(300, 100)
    page.click('.tool-btn[data-tool="disc"]')
    click(310, 190)
    page.click('.tool-btn[data-tool="cut"]')
    drag(301, 201, 600, 200)    # O1 cuts
    page.click('.tool-btn[data-tool="throw"]')
    drag(310, 190, 600, 200)    # the disc goes to the end of the cut
    page.click('.tool-btn[data-tool="select"]')
    drag(300, 100, 300, 80)     # moving O2 doesn't disturb O1's cut
    page.click('#add-stage')
    page.wait_for_function("document.querySelector('#stage-count').textContent.startsWith('2 /')")
    page.click('#save-drill')
    page.wait_for_selector('.alert-success')
    assert page.errors == []

    drill = SavedDrill.query.filter_by(title='Give and go').one()
    assert len(drill.editor_diagrams) == 2
    state = json.loads(drill.editor_diagram.editor_json)
    first, second = (s['objects'] for s in state['stages'])
    o1 = next(o for o in first if o.get('herdLabel') == 'O1')
    cut = next(o for o in first if o.get('lineStyle') == 'cut')
    throw = next(o for o in first if o.get('lineStyle') == 'throw')
    disc = next(o for o in first if o.get('herdType') == 'disc')
    assert cut['herdFrom'] == o1['herdId'] and throw['herdFrom'] == disc['herdId']
    moved = next(o for o in second if o.get('herdId') == o1['herdId'])
    assert abs(moved['left'] - 600) < 3 and abs(moved['top'] - 200) < 3
    assert not any(o.get('type') == 'herdLine' for o in second)

    # The drill page plays the stages
    page.goto(live_server + f'/sessions/drills/{drill.id}')
    page.wait_for_selector('#drill-animation canvas')
    page.click('[data-animation="play"]')
    page.wait_for_function(
        "document.querySelector('.animation-caption strong').textContent.startsWith('2/2')", timeout=10000)
    assert page.errors == []
    db.session.remove()


def test_phone_portrait_touch(app, team, live_server, browser):
    """On a phone held upright the field turns to portrait; taps place
    things, a selected player's handle draws their cut, a long press opens
    the menu, and the drawing is still saved the landscape way round."""
    coach = make_user(team, 'phonecoach', role='coach')
    page = logged_in_page(app, browser, live_server, coach, team,
                          viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
    page.goto(live_server + '/sessions/drills/editor')
    page.wait_for_selector('.upper-canvas')
    page.wait_for_timeout(300)
    cdp = page.context.new_cdp_session(page)

    def touch(kind, points):
        cdp.send('Input.dispatchTouchEvent', {
            'type': kind, 'touchPoints': [{'x': x, 'y': y, 'id': i} for i, (x, y) in enumerate(points)]})

    # A new drill on a phone shows the attacking half (55 yards), top aligned:
    # saved point (x, y) is shown at (y, 1100 - x)
    box = page.locator('.upper-canvas').bounding_box()
    assert box['height'] > box['width']
    zoom = min(box['width'] / 400, box['height'] / 550)
    left = (box['width'] - 400 * zoom) / 2

    def screen(x, y):
        return box['x'] + left + y * zoom, box['y'] + (1100 - x) * zoom

    page.fill('#drill-title', 'Phone drill')
    page.click('.tool-btn[data-tool="player-o"]')
    page.touchscreen.tap(*screen(800, 200))
    page.click('.tool-btn[data-tool="disc"]')
    page.touchscreen.tap(*screen(812, 188))
    page.click('.tool-btn[data-tool="select"]')
    page.touchscreen.tap(*screen(797, 203))

    # Drag the handle at the player's top right to draw a cut
    px, py = screen(800, 200)
    touch('touchStart', [(px + 14 * zoom + 10, py - 14 * zoom - 10)])
    for i in range(1, 9):
        touch('touchMove', [screen(800 + 150 * i / 8, 200 - 80 * i / 8)])
    touch('touchEnd', [])

    # A long press opens the menu
    touch('touchStart', [(px, py)])
    page.wait_for_timeout(750)
    touch('touchEnd', [])
    page.wait_for_selector('#object-menu')
    page.touchscreen.tap(30, 160)

    page.click('#add-stage')
    page.wait_for_function("document.querySelector('#stage-count').textContent.startsWith('2 /')")
    page.click('#save-drill')
    page.wait_for_selector('.alert-success')
    assert page.errors == []

    drill = SavedDrill.query.filter_by(title='Phone drill').one()
    state = json.loads(drill.editor_diagram.editor_json)
    first, second = (s['objects'] for s in state['stages'])
    o1 = next(o for o in first if o.get('herdType') == 'player-o')
    cut = next(o for o in first if o.get('type') == 'herdLine')
    assert abs(o1['left'] - 800) < 3 and abs(o1['top'] - 200) < 3
    assert cut['herdFrom'] == o1['herdId']
    moved = next(o for o in second if o.get('herdId') == o1['herdId'])
    assert abs(moved['left'] - 950) < 3 and abs(moved['top'] - 120) < 3
    db.session.remove()
