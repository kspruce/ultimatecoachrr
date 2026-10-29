"""Playbook extras: set-ups, learning for a tournament, core plays and
situations, share links, plays to draw, the quiz, and adding a play to a
session."""
import json
from datetime import date, timedelta

from app import db
from app.models.drill import SavedDrill
from app.models.playbook import Play, PlaySetup, PlayToLearn
from app.models.session import SessionComponent, SessionPlan
from app.models.tournament import Tournament
from tests.test_playbook_overhaul import client, club, form  # noqa: F401
from tests.test_theory import fresh, text

OBJECTS = [{'type': 'group', 'herdType': 'player-o', 'herdId': 'a1', 'herdLabel': 'H1', 'left': 10, 'top': 20}]


def test_setups(app, club):
    c = client(app, club, 'coach')
    r = c.post('/playbook/setups', json={'name': '  Side   stack ', 'objects': OBJECTS, 'field': {'length': 70},
                                         'type': 'offense', 'png': 'data:image/png;base64,iVBORw0KGgo='})
    assert r.status_code == 201
    setup = PlaySetup.query.one()
    assert setup.name == 'Side stack' and setup.type == 'offense' and setup.image_data == 'iVBORw0KGgo='
    assert c.post('/playbook/setups', json={'name': '', 'objects': []}).status_code == 400

    editor = text(c.get(f'/playbook/plays/draw?setup={setup.id}'))
    assert 'data-setup="%d"' % setup.id in editor and 'Save this stage as a set-up' in editor
    state = json.loads(editor.split('id="editor-state" type="application/json">')[1].split('</script>')[0])
    assert state['stages'][0]['objects'][0]['herdLabel'] == 'H1' and state['field'] == {'length': 70}
    assert 'Side stack' in text(c.get('/playbook/setups'))
    assert c.get(f'/playbook/setups/{setup.id}/image').status_code == 200

    other = client(app, club, 'other_coach', team='other')
    assert other.get(f'/playbook/plays/draw?setup={setup.id}').status_code == 404
    assert other.post(f'/playbook/setups/{setup.id}/delete').status_code == 404
    assert client(app, club, 'player').get('/playbook/setups').status_code == 403
    c.post(f'/playbook/setups/{setup.id}/rename', data={'name': 'Split stack'})
    assert fresh(PlaySetup, setup.id).name == 'Split stack'
    c.post(f'/playbook/setups/{setup.id}/delete')
    assert PlaySetup.query.count() == 0


def test_learn_for_a_tournament(app, club):
    nationals = Tournament(name='Nationals', start_date=date.today() + timedelta(days=10),
                           team_organization_id=club['team'])
    db.session.add(nationals)
    db.session.commit()
    c = client(app, club, 'coach')
    assert 'Nationals' in text(c.get(f'/playbook/plays/{club["Hammer"]}/learners'))
    c.post(f'/playbook/plays/{club["Hammer"]}/learners', data={'tournament_id': nationals.id, 'due_date': '', 'note': ''})
    row = PlayToLearn.query.one()
    assert row.tournament_id == nationals.id and row.due_date == nationals.start_date
    assert 'Learn for Nationals' in text(client(app, club, 'player').get('/playbook/'))


def test_core_and_situations(app, club):
    c = client(app, club, 'coach')
    c.post(f'/playbook/plays/{club["Hammer"]}/edit', data=form(club, name='Hammer', is_core='y', situations=['pull', 'endzone']))
    play = fresh(Play, club['Hammer'])
    assert play.is_core and play.situation_keys == ['pull', 'endzone']
    p = client(app, club, 'player')
    page = text(p.get('/playbook/?when=pull'))
    assert 'Hammer' in page and 'Side stack' not in page
    assert 'Hammer' in text(p.get('/playbook/?core=1')) and 'Cup' not in text(p.get('/playbook/?core=1'))
    cards = text(p.get('/playbook/cards?when=endzone'))
    assert 'Hammer' in cards and 'Side stack' not in cards
    assert 'Pull play' in text(p.get(f'/playbook/plays/{club["Hammer"]}'))


def test_share_links(app, club):
    c = client(app, club, 'coach')
    c.post(f'/playbook/plays/{club["Hammer"]}/share')
    token = fresh(Play, club['Hammer']).share_token
    assert token and len(token) >= 20
    anon = app.test_client()
    r = anon.get(f'/playbook/shared/{token}')
    assert r.status_code == 200 and 'Hammer' in text(r) and 'noindex' in text(r)
    assert anon.get('/playbook/shared/nope-not-a-real-token-at-all').status_code == 404
    c.post(f'/playbook/plays/{club["Hammer"]}/share', data={'stop': '1'})
    assert anon.get(f'/playbook/shared/{token}').status_code == 404
    # A player can't make one
    assert client(app, club, 'player').post(f'/playbook/plays/{club["Hammer"]}/share').status_code == 403


def test_plays_to_draw_and_quiz(app, club):
    c = client(app, club, 'coach')
    assert 'not drawn on the field yet' in text(c.get('/playbook/'))
    page = text(c.get('/playbook/redraw'))
    assert 'Side stack' in page and 'Old zone' not in page
    r = c.post(f'/playbook/plays/{club["Cup"]}/status', data={'status': 'retired', 'next': '/playbook/redraw'})
    assert r.headers['Location'].endswith('/playbook/redraw')
    r = c.post(f'/playbook/plays/{club["Cup"]}/status', data={'status': 'active', 'next': 'https://evil.example/'})
    assert 'evil' not in r.headers['Location']

    # The quiz needs pictures
    assert 'at least two plays' in text(client(app, club, 'player').get('/playbook/quiz'))
    db.session.expire_all()
    for name in ('Side stack', 'Hammer'):
        db.session.get(Play, club[name]).image_url = 'https://example.com/x.png'
    db.session.commit()
    quiz = text(client(app, club, 'player').get('/playbook/quiz'))
    assert 'data-questions' in quiz and 'Hammer' in quiz and 'Secret set' not in quiz


def test_add_a_play_to_a_session(app, club):
    drill = db.session.get(SavedDrill, club['drill'])
    drill.recommended_duration = 15
    play = db.session.get(Play, club['Hammer'])
    play.drills = [drill]
    session = SessionPlan(title='Thursday', date=date.today() + timedelta(days=2), team_organization_id=club['team'])
    past = SessionPlan(title='Last week', date=date.today() - timedelta(days=7), team_organization_id=club['team'])
    db.session.add_all([session, past])
    db.session.commit()
    c = client(app, club, 'coach')
    page = text(c.get(f'/playbook/plays/{club["Hammer"]}'))
    assert 'Thursday' in page and 'Last week' not in page
    r = c.post(f'/playbook/plays/{club["Hammer"]}/add-to-session', data={'session_id': session.id})
    assert r.status_code == 302
    part = SessionComponent.query.one()
    assert part.title == 'Hammer' and part.drill_id == drill.id and part.duration_minutes == 15
    assert [p.id for p in part.plays] == [club['Hammer']]
    other = client(app, club, 'other_coach', team='other')
    assert other.post(f'/playbook/plays/{club["Hammer"]}/add-to-session', data={'session_id': session.id}).status_code == 404
