"""Watching plays in a real browser: the defence faded or hidden on the
play's page, the animation saved as a video, and a play played in place
from the playbook list (a pop-up) and on a game-day card.

Skipped without Playwright's Chromium; see tests/test_drill_editor_browser.py
for the settings that run it offline."""
import json

import pytest

from app import db
from app.models.playbook import Play
from app.models.team_settings import TeamSettings
from tests.test_drill_editor_browser import browser, field_mapper, live_server, logged_in_page  # noqa: F401
from tests.test_teams import make_user

pytest.importorskip('playwright.sync_api')


def test_watch_a_play(app, team, live_server, browser):
    db.session.add(TeamSettings(team_id=team.id))
    db.session.commit()
    coach = make_user(team, 'previewcoach', role='coach')
    page = logged_in_page(app, browser, live_server, coach, team)

    # Draw it: a cutter and a defender who follows, in two stages
    page.goto(live_server + '/playbook/plays/draw')
    page.wait_for_selector('.upper-canvas')
    at = field_mapper(page)

    def drag(x1, y1, x2, y2):
        page.mouse.move(*at(x1, y1))
        page.mouse.down()
        page.mouse.move(*at(x2, y2), steps=8)
        page.mouse.up()

    page.fill('#drill-title', 'Iso')
    page.click('.tool-btn[data-tool="player-o"]')
    page.mouse.click(*at(300, 200))
    page.click('.tool-btn[data-tool="player-d"]')
    page.mouse.click(*at(330, 200))
    page.click('.tool-btn[data-tool="cut"]')
    drag(301, 201, 600, 200)
    page.click('.tool-btn[data-tool="move"]')
    drag(331, 201, 620, 210)
    page.click('.tool-btn[data-tool="select"]')
    page.click('#add-stage')
    page.wait_for_function("document.querySelector('#stage-count').textContent.startsWith('2 /')")
    page.click('#save-drill')
    page.wait_for_selector('.alert-success')
    play = Play.query.filter_by(name='Iso').one()
    play_id = play.id
    state = json.loads(play.editor_diagram.editor_json)
    assert any(o.get('herdType') == 'player-d' for o in state['stages'][0]['objects'])
    db.session.remove()

    # The play's page: the defence can be hidden; the animation saved as a video
    page.goto(live_server + f'/playbook/plays/{play_id}')
    page.wait_for_selector('#drill-animation canvas')
    defence = page.locator('[data-animation="defence"]')
    assert defence.is_visible()
    defence.select_option('hidden')
    page.wait_for_timeout(300)
    # Hidden takes the defender and their arrow; faded keeps them, see-through
    seen = page.evaluate("""() => {
        const DD = window.DrillDiagram;
        const objects = JSON.parse(document.getElementById('drill-animation-data').textContent).stages[0].objects;
        const kinds = list => list.map(o => o.lineStyle || o.herdType).sort().join(',');
        return {all: kinds(objects), hidden: kinds(DD.viewObjects(objects, {defence: 'hidden'})),
                faded: DD.viewObjects(objects, {defence: 'faded'}).filter(o => o.opacity < 0.5).length};
    }""")
    assert seen['all'] == 'cut,move,player-d,player-o' and seen['hidden'] == 'cut,player-o' and seen['faded'] == 2
    assert page.errors == []
    video = page.locator('[data-animation="video"]')
    assert video.is_visible()
    with page.expect_download(timeout=20000) as download:
        video.click()
    assert download.value.suggested_filename.startswith('Iso.')
    assert page.errors == []

    # The playbook list: tap the picture to watch it in a pop-up
    page.goto(live_server + '/playbook/')
    page.click(f'[data-play-preview="/playbook/plays/{play_id}/drawing.json"]')
    page.wait_for_selector('.modal.show .pb-preview canvas')
    page.wait_for_function(
        "document.querySelector('.modal.show .pb-preview .cap').textContent.startsWith('2/2')", timeout=10000)
    assert page.locator('.modal.show .modal-title').inner_text() == 'Iso'
    page.click('.modal.show .btn-close')
    page.wait_for_function("!document.querySelector('.pb-preview')")  # stopped and removed once it's closed
    assert page.errors == []

    # A game-day card plays it in the card, then goes back to the stages
    page.goto(live_server + '/playbook/cards')
    card = page.locator(f'#play-{play_id}')
    card.locator('[data-play-preview]').click()
    card.locator('.pb-preview canvas').wait_for()
    assert not card.locator('.gd-stages').is_visible()
    card.locator('[data-play-preview]').click()
    assert card.locator('.pb-preview').count() == 0 and card.locator('.gd-stages').is_visible()
    assert page.errors == []
