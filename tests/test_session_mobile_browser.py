"""Planning and viewing a session on a phone (390px wide, touch): nothing
scrolls sideways, the builder keeps Save in reach and opens the drill
library as a sheet, and the session page puts the plan before the extras.

Needs Playwright and its Chromium (CI installs them); skipped otherwise.
Uses the same DRILL_TEST_CHROMIUM / DRILL_TEST_CDN_DIR settings as the
drill editor test.
"""
import pytest

from app import db
from app.models.drill import SavedDrill
from app.models.session import SessionComponent
from tests.test_drill_editor_browser import browser, live_server, logged_in_page  # noqa: F401
from tests.test_theory_browser import in_view, no_sideways_scroll, phone_page
from tests.test_training import club, week  # noqa: F401

pytest.importorskip('playwright.sync_api')


@pytest.fixture
def planned(club, week):
    team_id = club['team'].id
    for i in range(4):
        db.session.add(SavedDrill(title=f'Drill {i}', recommended_duration=10, team_organization_id=team_id))
    session = week['sat'].sessions.first()
    for i, (title, kind) in enumerate([('Warm-up', 'warmup'), ('Break throws', 'drill'), ('Scrimmage', 'scrimmage')]):
        db.session.add(SessionComponent(session_id=session.id, title=title, order=i, component_type=kind,
                                        duration_minutes=15, description='Pairs ten yards apart. ' * 6,
                                        team_organization_id=team_id))
    db.session.commit()
    return session.id


def test_building_a_plan_on_a_phone(app, club, planned, live_server, browser):
    page = phone_page(app, browser, live_server, club['coach'], club['team'])
    page.goto(live_server + f'/sessions/{planned}/plan')
    no_sideways_scroll(page)

    # Save and publish sit at the bottom of the screen in place of the tab bar
    in_view(page, '#pb-save')
    in_view(page, '#pb-publish')
    assert not page.is_visible('.uc-tabbar')

    # Blocks start folded, with a preview that opens them
    first = page.locator('.pb-block').first
    assert not first.locator('[name=description]').is_visible()
    first.locator('.pb-peek').click()
    assert first.locator('[name=description]').is_visible()
    # Fields are 16px, so iOS doesn't zoom in
    assert page.evaluate("getComputedStyle(document.querySelector('.pb-block [name=title]')).fontSize") == '16px'

    # Move a block down with a big enough button
    down = page.locator('.pb-block').first.locator('[data-act=down]')
    assert down.bounding_box()['height'] >= 36
    down.click()
    assert page.locator('.pb-block [name=title]').first.input_value() == 'Break throws'

    # The drill library opens as a sheet; adding a drill says so
    page.click('.pb-drills-btn')
    page.locator('#pb-lib-sheet.show').wait_for()
    page.click('[aria-label="Add Drill 2"]')
    assert 'Added' in page.locator('[aria-label="Add Drill 2"]').inner_text()
    page.click('#pb-lib-sheet [data-bs-dismiss]')
    page.locator('#pb-lib-sheet.show').wait_for(state='detached')
    assert page.locator('.pb-block').count() == 4

    page.click('#pb-save')
    page.wait_for_function("document.getElementById('pb-status').textContent === 'All saved'")
    no_sideways_scroll(page)
    assert page.errors == []
    assert SessionComponent.query.filter_by(session_id=planned).count() == 4


def test_session_page_on_a_phone_shows_the_plan_first(app, club, planned, live_server, browser):
    page = phone_page(app, browser, live_server, club['coach'], club['team'])
    page.goto(live_server + f'/sessions/{planned}/detail')
    no_sideways_scroll(page)
    plan = page.get_by_text('Session Components').bounding_box()
    actions = page.get_by_text('Quick Actions').bounding_box()
    assert plan['y'] < actions['y']
    # Edit and run are at the top, side by side
    edit, run = page.locator('.sd-head-actions >> text=Edit plan'), page.locator('.sd-head-actions >> text=Run')
    assert edit.bounding_box()['y'] == run.bounding_box()['y']
    assert page.errors == []


def test_builder_on_a_desktop_keeps_the_library_beside_the_plan(app, club, planned, live_server, browser):
    page = logged_in_page(app, browser, live_server, club['coach'], club['team'],
                          viewport={'width': 1280, 'height': 900})
    page.goto(live_server + f'/sessions/{planned}/plan')
    assert page.is_visible('#pb-search')
    assert not page.is_visible('.pb-drills-btn')
    assert not page.is_visible('.pb-peek')
    assert page.errors == []
