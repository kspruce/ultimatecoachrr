"""The top navbar and the account menu in a real browser, on a PC-sized
window and on a phone (where everything sits behind the hamburger).

Needs Playwright and its Chromium; skipped otherwise (see
tests/test_drill_editor_browser.py for the environment variables).
"""
import pytest

from tests.test_drill_editor_browser import browser, live_server, logged_in_page  # noqa: F401
from tests.test_teams import make_user
from tests.test_theory_browser import in_view, no_sideways_scroll, phone_page


def test_account_menu_on_desktop(app, team, live_server, browser):
    admin = make_user(team, 'navadmin', role='admin')
    page = logged_in_page(app, browser, live_server, admin, team, viewport={'width': 1280, 'height': 800})
    page.goto(live_server + '/')
    assert not page.is_visible('.uc-toggler')

    button = page.locator('.uc-user-btn')
    assert button.get_attribute('href') == '#'  # reachable with the keyboard
    assert 'navadmin' in button.get_attribute('aria-label')
    button.click()
    menu = page.locator('.uc-user-menu')
    menu.wait_for(state='visible')
    logout = page.locator('.uc-logout-row button')
    assert logout.is_visible()
    box = logout.bounding_box()
    assert box['y'] + box['height'] <= 800
    assert page.evaluate('document.documentElement.scrollWidth') <= 1280
    assert page.errors == []


def test_account_menu_on_phone(app, team, live_server, browser):
    admin = make_user(team, 'navadmin', role='admin')
    page = phone_page(app, browser, live_server, admin, team)
    page.goto(live_server + '/')
    page.click('.uc-toggler')
    page.locator('#navbarNav.show').wait_for()

    # The account button has its own full-width row, with the name showing
    button = page.locator('.uc-user-btn')
    assert button.locator('.uc-user-name').is_visible()
    nav_width = page.locator('#navbarNav').bounding_box()['width']
    assert button.bounding_box()['width'] >= nav_width - 2

    button.click()
    menu = page.locator('.uc-user-menu')
    menu.wait_for(state='visible')
    # ... so the menu opens across the screen, not squeezed into half of it
    assert menu.bounding_box()['width'] >= nav_width * 0.85
    page.locator('.uc-logout-row button').scroll_into_view_if_needed()
    in_view(page, '.uc-logout-row button')
    no_sideways_scroll(page)


def test_admin_team_badge_on_tablet_goes_to_manage_teams(app, team, live_server, browser):
    admin = make_user(team, 'navadmin', role='admin')
    page = logged_in_page(app, browser, live_server, admin, team, viewport={'width': 820, 'height': 1000})
    page.goto(live_server + '/')
    page.click('.d-xl-none .uc-team-badge')
    page.wait_for_url('**/teams/')
    assert page.errors == []
