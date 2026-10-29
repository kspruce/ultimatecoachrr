"""The theory hub on a phone (390px wide, touch): no page scrolls sideways,
the reading bar and contents sheet work, and a coach can write, format,
add a photo, preview and publish a topic.

Needs Playwright and its Chromium (CI installs them); skipped otherwise.
Uses the same DRILL_TEST_CHROMIUM / DRILL_TEST_CDN_DIR settings as the
drill editor test; with a CDN folder, code.jquery.com files are served from
<folder>/jquery@3.6.0/dist/ too.
"""
import io
import mimetypes
import os

import pytest
from PIL import Image

from app import db
from app.models.team_settings import TeamSettings
from app.models.theory import TheoryRead, TheorySection, TheoryTopic
from tests.test_drill_editor_browser import CDN, browser, live_server  # noqa: F401
from tests.test_teams import make_user

pytest.importorskip('playwright.sync_api')

PHONE = {'viewport': {'width': 390, 'height': 844}, 'device_scale_factor': 2, 'is_mobile': True, 'has_touch': True}
JQUERY = 'https://code.jquery.com/'

LONG = '\n\n'.join(
    f'## Part {n}\n\n' + ' '.join(['The force decides where the throw can go.'] * 12) +
    '\n\n| Mark | Cup | Wing | Deep | Short deep | Middle middle |\n|---|---|---|---|---|---|\n| a | b | c | d | e | f |'
    for n in range(1, 5))


def phone_page(app, browser, live_server, user, team):
    user_id, team_id = user.get_id(), team.id
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = user_id
        s['_fresh'] = True
        s['current_team_id'] = team_id
    cookie = client.get_cookie('session')
    context = browser.new_context(**PHONE)
    context.add_cookies([{'name': 'session', 'value': cookie.value, 'url': live_server}])
    folder = os.environ.get('DRILL_TEST_CDN_DIR')
    if folder:
        def handle(route):
            url = route.request.url.split('?')[0]
            rel = url[len(CDN):] if url.startswith(CDN) else 'jquery@3.6.0/dist/' + url[len(JQUERY):]
            path = os.path.join(folder, rel.replace('jquery-3.6.0.min.js', 'jquery.min.js'))
            if os.path.isfile(path):
                with open(path, 'rb') as f:
                    route.fulfill(body=f.read(), content_type=mimetypes.guess_type(path)[0] or 'text/plain')
            else:
                route.abort()
        context.route(CDN + '**', handle)
        context.route(JQUERY + '**', handle)
        context.route(lambda url: not url.startswith('http://127.0.0.1') and not url.startswith((CDN, JQUERY)),
                      lambda route: route.abort())
    page = context.new_page()
    page.errors = []
    page.on('pageerror', lambda e: page.errors.append(str(e)))
    page.on('dialog', lambda d: d.accept())
    return page


def no_sideways_scroll(page):
    width = page.evaluate('document.documentElement.scrollWidth')
    assert width <= 390, f'{page.url} is {width}px wide'


def in_view(page, selector):
    box = page.locator(selector).first.bounding_box()
    assert box, selector
    assert box['y'] >= 0 and box['y'] + box['height'] <= 844 + 1, (selector, box)
    return box


@pytest.fixture
def hub(app, team):
    db.session.add(TeamSettings(team_id=team.id))
    section = TheorySection(name='Defence', slug='defence', order=1, team_organization_id=team.id,
                            description='How we stop them scoring')
    db.session.add(section)
    db.session.flush()
    first = TheoryTopic(section_id=section.id, name='Marking the force: a long title that needs to wrap on a phone',
                        content=LONG, order=1, team_organization_id=team.id,
                        image_url='data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==')
    second = TheoryTopic(section_id=section.id, name='The cup', content='Short.', order=2, team_organization_id=team.id)
    db.session.add_all([first, second])
    db.session.commit()
    coach = make_user(team, 'phonecoach', role='coach')
    player = make_user(team, 'phoneplayer', role='player')
    return {'section': section.id, 'first': first.id, 'second': second.id, 'coach': coach, 'player': player}


def test_reading_on_a_phone(app, team, live_server, browser, hub):
    page = phone_page(app, browser, live_server, hub['player'], team)
    for path in ('/theory/', '/theory/section/defence'):
        page.goto(live_server + path)
        no_sideways_scroll(page)
    page.goto(live_server + f'/theory/topic/{hub["first"]}')
    no_sideways_scroll(page)

    # Prev / mark as read / next sit at the bottom of the screen all the time
    in_view(page, '.th-readbar .th-read-btn button')
    assert page.locator('.th-readbar').evaluate('e => getComputedStyle(e).position') == 'fixed'
    btn = page.locator('.th-readbar .th-read-btn button').first.bounding_box()
    assert btn['height'] >= 44

    # The contents button opens a sheet listing the headings; a heading jumps there
    page.locator('.th-meta [data-toc]').click()
    sheet = page.locator('#th-toc-sheet')
    sheet.locator('.toc-link', has_text='Part 3').wait_for(state='visible')
    assert sheet.locator('.toc-link').count() == 4
    sheet.locator('.toc-link', has_text='Part 3').click()
    page.wait_for_function("document.getElementById('section-3').getBoundingClientRect().top < 200")
    # ...and once the title is off screen a compact header shows it
    page.wait_for_selector('.th-sticky-head.shown')

    # Mark as read without leaving the page
    page.locator('.th-readbar .th-read-btn button').click()
    page.wait_for_selector('.th-readbar .th-read-btn button.is-read')
    assert TheoryRead.query.filter_by(user_id=hub['player'].id).count() == 1

    # The photo opens full screen and a swipe down closes it
    page.evaluate('window.scrollTo(0, 0)')
    page.locator('.th-hero').click()
    page.wait_for_selector('#th-lightbox.open')
    page.locator('.th-lb-close').click()
    page.wait_for_selector('#th-lightbox', state='hidden')
    assert page.errors == []


def test_writing_on_a_phone(app, team, live_server, browser, hub):
    page = phone_page(app, browser, live_server, hub['coach'], team)
    for path in ('/theory/', '/theory/section/defence', f'/theory/topic/{hub["first"]}', '/theory/add_section',
                 f'/theory/topic/{hub["first"]}/readers', f'/theory/edit_topic/{hub["first"]}'):
        page.goto(live_server + path)
        no_sideways_scroll(page)

    page.goto(live_server + f'/theory/add_topic?section_id={hub["section"]}')
    no_sideways_scroll(page)
    # Save and Publish are on screen without scrolling
    in_view(page, '.th-actionbar button[value="publish"]')
    for b in page.locator('.th-toolbar button').all():
        assert b.bounding_box()['height'] >= 44

    page.fill('#name', 'Hammers')
    box = page.locator('#content')
    box.click()
    box.type('Why')
    page.keyboard.press('Control+A')
    page.locator('.th-toolbar [data-md="h2"]').click()
    page.keyboard.press('End')
    page.keyboard.type('\n\nThrow it ')
    page.locator('.th-toolbar [data-md="bold"]').click()
    page.keyboard.type('over')
    assert box.input_value().startswith('## Why\n\nThrow it **over**')
    height = box.bounding_box()['height']
    box.press('End')
    page.keyboard.type('\n' * 40)
    assert box.bounding_box()['height'] > height  # grows instead of scrolling inside itself

    # A photo from the phone goes in where the cursor is
    jpeg = io.BytesIO()
    Image.new('RGB', (1200, 900), (10, 120, 40)).save(jpeg, 'JPEG')
    page.set_input_files('#th-inline-file', files=[{'name': 'pic.jpg', 'mimeType': 'image/jpeg', 'buffer': jpeg.getvalue()}])
    page.wait_for_function("document.getElementById('content').value.includes('](/theory/image/')")

    # The draft is kept on the phone until it's saved
    page.wait_for_function("localStorage.getItem('theory-draft:new') !== null")

    # Preview shows it as players will see it, and Write goes back to where you were
    page.locator('[data-tab="preview"]').click()
    page.wait_for_selector('#th-preview h2')
    assert 'Why' in page.locator('#th-preview h2').inner_text()
    assert page.locator('#th-preview img').count() == 1
    page.locator('[data-tab="write"]').click()
    assert box.is_visible()

    page.locator('.th-actionbar button[value="publish"]').click()
    page.wait_for_url('**/theory/topic/*')
    topic = TheoryTopic.query.filter_by(name='Hammers').one()
    assert topic.published and '**over**' in topic.content and '/theory/image/' in topic.content
    no_sideways_scroll(page)
    assert page.evaluate("localStorage.getItem('theory-draft:new')") is None
    assert '?saved' not in page.url
    assert page.errors == []


def test_organising_on_a_phone(app, team, live_server, browser, hub):
    """Moving a topic to a new section from the Organise page."""
    page = phone_page(app, browser, live_server, hub['coach'], team)
    page.goto(live_server + '/theory/organise')
    no_sideways_scroll(page)
    page.fill('#new-section', 'Zones')
    page.locator('button', has_text='Add section').click()
    page.wait_for_selector('.th-label:has-text("Zones")')
    page.select_option(f'select[name="section_{hub["second"]}"]', label='Zones')
    page.locator('button', has_text='Save moves').click()
    page.wait_for_selector('text=Moved 1 topic')
    no_sideways_scroll(page)
    db.session.expire_all()
    assert db.session.get(TheoryTopic, hub['second']).section.name == 'Zones'
    assert not page.errors
