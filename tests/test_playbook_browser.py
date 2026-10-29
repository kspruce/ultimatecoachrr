"""The playbook on a phone (390px wide, touch): no page scrolls sideways,
a coach writes a play with roles on the phone, a player marks it learned,
and a play shows inside a theory article.

Skipped without Playwright's Chromium; see tests/test_theory_browser.py for
the settings that run it offline."""
import pytest

from app import db
from app.models.playbook import Play, PlayAssignment, PlayerPosition, PlayLearned
from app.models.team_settings import TeamSettings
from app.models.theory import TheorySection, TheoryTopic
from tests.test_drill_editor_browser import browser, live_server  # noqa: F401
from tests.test_teams import make_user
from tests.test_theory_browser import in_view, no_sideways_scroll, phone_page

pytest.importorskip('playwright.sync_api')

PIXEL = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=='


@pytest.fixture
def book(app, team):
    db.session.add(TeamSettings(team_id=team.id))
    play = Play(name='Side stack iso with a long name that wraps', type='offense', status='active', call='Iso',
                signal='Fist', description='Clear the break side.\n\n| A | B | C | D | E | F | G |\n|---|---|---|---|---|---|---|\n'
                '| one | two | three | four | five | six | seven |', image_url=PIXEL, sort_order=1,
                team_organization_id=team.id)
    cup = Play(name='Cup', type='defense', status='active', sort_order=1, team_organization_id=team.id)
    db.session.add_all([play, cup])
    db.session.flush()
    db.session.add(PlayAssignment(play_id=play.id, order=1, instructions='Swing it.', team_organization_id=team.id,
                                  position=PlayerPosition(name='Handler 1', team_organization_id=team.id)))
    section = TheorySection(name='Offence', slug='offence', order=1, team_organization_id=team.id)
    db.session.add(section)
    db.session.flush()
    topic = TheoryTopic(section_id=section.id, name='Isolation', content=f'Why:\n\n[[play:{play.id}]]\n\nThat.',
                        published=True, order=1, team_organization_id=team.id)
    db.session.add(topic)
    db.session.commit()
    return {'play': play.id, 'cup': cup.id, 'topic': topic.id,
            'coach': make_user(team, 'pbcoach', role='coach'), 'player': make_user(team, 'pbplayer', role='player')}


def test_playbook_on_a_phone(app, team, live_server, browser, book):
    from app.models.team_organization import TeamOrganization
    from app.models.user import User
    team_id = team.id
    coach_id, player_id = book['coach'].id, book['player'].id

    page = phone_page(app, browser, live_server, db.session.get(User, coach_id), db.session.get(TeamOrganization, team_id))
    for path in ('/playbook/', f'/playbook/plays/{book["play"]}', '/playbook/cards', '/playbook/positions',
                 f'/playbook/plays/{book["play"]}/edit', f'/playbook/plays/{book["play"]}/learners',
                 f'/theory/topic/{book["topic"]}'):
        page.goto(live_server + path)
        no_sideways_scroll(page)
    assert page.locator('.pb-embed').count() == 1

    # Write a play on the phone: Save stays on screen, roles add and remove
    page.goto(live_server + '/playbook/plays/add?type=defense')
    in_view(page, '.th-actionbar button[value="save"]')
    page.fill('#name', 'Zone 7')
    page.fill('#call', 'Seven')
    page.locator('[data-add-role]').click()
    page.locator('[data-add-role]').click()
    rows = page.locator('.pb-role-row')
    assert rows.count() == 2
    rows.nth(0).locator('[name="role_id"]').select_option(label='Handler 1')
    rows.nth(0).locator('[name="role_text"]').fill('Stop the swing.')
    rows.nth(1).locator('[data-remove-role]').click()
    assert page.locator('.pb-role-row').count() == 1
    page.wait_for_function("localStorage.getItem('playbook-draft:new') !== null")
    page.locator('.th-actionbar button[value="save"]').click()
    page.wait_for_url('**/playbook/plays/*')
    play = Play.query.filter_by(name='Zone 7').one()
    assert play.type == 'defense' and play.call == 'Seven' and [a.position.name for a in play.assignments] == ['Handler 1']
    assert page.evaluate("localStorage.getItem('playbook-draft:new')") is None
    no_sideways_scroll(page)
    assert page.errors == []

    # A player marks a play learned from the bar at the bottom
    page = phone_page(app, browser, live_server, db.session.get(User, player_id), db.session.get(TeamOrganization, team_id))
    page.goto(live_server + f'/playbook/plays/{book["play"]}')
    in_view(page, '.th-readbar .th-read-btn button')
    page.locator('.th-readbar .th-read-btn button').click()
    page.wait_for_selector('.th-readbar .th-read-btn button.is-read')
    assert 'Learned' in page.locator('.th-readbar .th-read-btn button').inner_text()
    assert PlayLearned.query.filter_by(user_id=player_id).count() == 1
    assert page.errors == []


def test_save_and_use_a_setup(app, team, live_server, browser, book):
    """In the drawing editor: lay out a stack, save it as a set-up, then start
    a new play from it."""
    from app.models.playbook import PlaySetup
    from app.models.team_organization import TeamOrganization
    from app.models.user import User
    page = phone_page(app, browser, live_server, db.session.get(User, book['coach'].id),
                      db.session.get(TeamOrganization, team.id))
    page.goto(live_server + '/playbook/plays/draw')
    page.wait_for_selector('.upper-canvas')
    page.locator('#toggle-more').click()  # phones keep the set-up menu under More
    page.get_by_role('button', name='Set up').click()
    page.locator('[data-formation="vertical"]').click()
    page.locator('#askModal .btn-outline-secondary').click()  # no defenders
    page.wait_for_selector('#askModal', state='hidden')
    page.get_by_role('button', name='Set up').click()
    page.locator('#save-setup').click()
    page.locator('#askModal .ask-input').fill('Our vert')
    page.locator('#askModal .ask-ok').click()
    page.wait_for_function("document.body.innerText.includes('Saved \"Our vert\"')")
    setup = PlaySetup.query.one()
    assert setup.name == 'Our vert' and setup.image_data
    import json
    assert len(json.loads(setup.state_json)['objects']) >= 8  # seven players and the disc

    # It's in the menu now, and a new play can start from it
    page.goto(live_server + f'/playbook/plays/draw?setup={setup.id}')
    page.wait_for_selector('.upper-canvas')
    assert page.locator(f'[data-setup="{setup.id}"]').count() == 1
    assert page.evaluate("JSON.parse(document.getElementById('editor-state').textContent).stages[0].objects.length") >= 8
    assert page.errors == []
