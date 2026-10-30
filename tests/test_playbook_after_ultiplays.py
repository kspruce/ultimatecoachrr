"""Moving off Ultiplays and the playbook's last open items: play images for
the team only, PDF QR codes to the play, no new Ultiplays links (old ones
kept to redraw from), adding Ultiplays plays in bulk, the drawing for
playing a play in place, the defence's default in the drawing, and plays
shown on the session."""
import json
from datetime import date

from app import db
from app.models.drill import SavedDrill
from app.models.playbook import Play
from app.models.session import SessionComponent, SessionPlan
from app.utils.playbook_export import build_sections
from tests.test_playbook import club, draw, play_form  # noqa: F401 (fixtures)

EMBED = '<iframe src="https://www.ultiplays.com/embed/abc" width="600"></iframe>'


def test_play_images_are_for_the_team_only(app, club):
    play_id = draw(club)
    url = db.session.get(Play, play_id).editor_diagrams[0].image_url
    r = club['player'].get(url)
    assert r.status_code == 200 and r.headers['Cache-Control'].startswith('private')
    assert app.test_client().get(url).status_code == 404       # signed out
    assert club['other_admin'].get(url).status_code == 404     # another team
    svg = db.session.get(Play, play_id).editor_diagrams[0].svg_url
    assert club['player'].get(svg).status_code == 200 and app.test_client().get(svg).status_code == 404

    # A draft's drawing is for coaches
    club['admin'].put(f'/playbook/api/plays/{play_id}', data=play_form(status='draft'),
                      content_type='multipart/form-data')
    db.session.expire_all()
    url = db.session.get(Play, play_id).editor_diagrams[0].image_url
    assert club['player'].get(url).status_code == 404 and club['coach'].get(url).status_code == 200

    # Drill diagrams stay public, for guest share links
    r = club['admin'].post('/sessions/api/drills', data={k: v for k, v in play_form('Drill').items() if k != 'data'}
                           | {'data': json.dumps({'title': 'Give and go'})}, content_type='multipart/form-data')
    assert r.status_code == 201, r.get_data(as_text=True)
    drill = db.session.get(SavedDrill, r.get_json()['drill_id'])
    r = app.test_client().get(drill.editor_diagrams[0].image_url)
    assert r.status_code == 200 and r.headers['Cache-Control'].startswith('public')


def test_pdf_qr_codes_go_to_the_play(app, club):
    drawn = draw(club)
    old = Play(name='Old one', type='offense', status='active', ultiplay_embed=EMBED, team_organization_id=club['team'])
    db.session.add(old)
    db.session.commit()
    db.session.get(Play, drawn).ultiplay_embed = EMBED
    db.session.commit()
    with app.test_request_context(base_url='https://coach.example'):
        items = {i['obj'].name: i for _, its in build_sections(Play.query.all()) for i in its}
        assert items['Side stack']['animation_url'] == f'https://coach.example/playbook/plays/{drawn}'
        assert items['Old one']['animation_url'] == 'https://www.ultiplays.com/embed/abc'  # not drawn yet
        db.session.get(Play, drawn).share_token = 'x' * 32
        items = {i['obj'].name: i for _, its in build_sections(Play.query.all()) for i in its}
        assert items['Side stack']['animation_url'] == 'https://coach.example/playbook/shared/' + 'x' * 32


def test_no_new_ultiplays_links(app, club):
    form = club['admin'].get('/playbook/plays/add').get_data(as_text=True)
    assert 'ultiplay_embed' not in form and 'Ultiplay' not in form
    r = club['admin'].post('/playbook/plays/add', data={'name': 'Hammer', 'type': 'offense', 'status': 'active',
                                                        'ultiplay_embed': EMBED})
    assert r.status_code == 302
    play = Play.query.filter_by(name='Hammer').one()
    assert play.ultiplay_embed is None

    # An old link stays (to redraw from) until it's removed
    play.ultiplay_embed = EMBED
    db.session.commit()
    form = club['admin'].get(f'/playbook/plays/{play.id}/edit').get_data(as_text=True)
    assert 'Original (Ultiplays)' in form
    base = {'name': 'Hammer', 'type': 'offense', 'status': 'active'}
    club['admin'].post(f'/playbook/plays/{play.id}/edit', data=base)
    db.session.expire_all()
    assert db.session.get(Play, play.id).ultiplay_embed == EMBED
    club['admin'].post(f'/playbook/plays/{play.id}/edit', data={**base, 'remove_embed': '1'})
    db.session.expire_all()
    assert db.session.get(Play, play.id).ultiplay_embed is None

    # Drills too, and the drill library loses its Ultiplays button
    assert 'ultiplays.com' not in club['admin'].get('/sessions/drills').get_data(as_text=True)
    assert 'ultiplay_embed' not in club['admin'].get('/sessions/drills/add').get_data(as_text=True)
    drill = SavedDrill(title='Old drill', ultiplay_embed=EMBED, team_organization_id=club['team'])
    db.session.add(drill)
    db.session.commit()
    edit = f'/sessions/drills/edit/{drill.id}'
    assert 'Original (Ultiplays)' in club['admin'].get(edit).get_data(as_text=True)
    club['admin'].post(edit, data={'title': 'Old drill', 'ultiplay_embed': '<iframe src="https://x.test"></iframe>'})
    db.session.expire_all()
    assert db.session.get(SavedDrill, drill.id).ultiplay_embed == EMBED
    club['admin'].post(edit, data={'title': 'Old drill', 'remove_embed': '1'})
    db.session.expire_all()
    assert db.session.get(SavedDrill, drill.id).ultiplay_embed is None


def test_drawn_play_keeps_its_original_for_coaches(app, club):
    play_id = draw(club)
    db.session.get(Play, play_id).ultiplay_embed = EMBED
    db.session.commit()
    assert 'Original (Ultiplays)' in club['coach'].get(f'/playbook/plays/{play_id}').get_data(as_text=True)
    page = club['player'].get(f'/playbook/plays/{play_id}').get_data(as_text=True)
    assert 'Original (Ultiplays)' not in page and 'ultiplays.com' not in page


def test_add_ultiplays_plays_in_bulk(app, club):
    assert club['player'].get('/playbook/import-ultiplays').status_code == 403
    assert club['admin'].get('/playbook/import-ultiplays').status_code == 200
    lines = '\n'.join([
        'Hammer | https://www.ultiplays.com/embed/1',
        'Flood | <iframe src="https://www.ultiplays.com/embed/2"></iframe>',
        '<iframe title="Zone O" src="https://www.ultiplays.com/embed/3"></iframe>',
        'Again | https://www.ultiplays.com/embed/1',        # same link
        'hammer | https://www.ultiplays.com/embed/4',       # same name
        'Not a link',
        '',
    ])
    r = club['admin'].post('/playbook/import-ultiplays', data={'lines': lines, 'type': 'defense'})
    page = r.get_data(as_text=True)
    assert r.status_code == 200 and 'already in the playbook' in page and 'already a play called' in page
    plays = Play.query.filter_by(team_organization_id=club['team']).order_by(Play.sort_order).all()
    assert [p.name for p in plays] == ['Hammer', 'Flood', 'Zone O']
    assert all(p.status == 'draft' and p.type == 'defense' for p in plays)
    assert 'src="https://www.ultiplays.com/embed/1"' in plays[0].ultiplay_embed
    # They're waiting to be drawn
    redraw = club['admin'].get('/playbook/redraw').get_data(as_text=True)
    assert 'Hammer' in redraw and 'Zone O' in redraw
    # Unnamed ones are numbered on from earlier batches
    club['admin'].post('/playbook/import-ultiplays', data={'lines': 'https://x.test/5\nhttps://x.test/6'})
    club['admin'].post('/playbook/import-ultiplays', data={'lines': 'https://x.test/7'})
    assert {p.name for p in Play.query.filter(Play.name.like('Ultiplays play %'))} == \
        {'Ultiplays play 1', 'Ultiplays play 2', 'Ultiplays play 3'}
    # A link with quotes in it can't break out of the iframe
    club['admin'].post('/playbook/import-ultiplays', data={'lines': 'Evil | https://x.test/"onload="alert(1)'})
    evil = Play.query.filter_by(name='Evil').one()
    assert '"onload' not in evil.ultiplay_embed


def test_drawing_for_playing_in_place(app, club):
    play_id = draw(club)
    r = club['player'].get(f'/playbook/plays/{play_id}/drawing.json')
    assert r.status_code == 200
    data = r.get_json()
    assert len(data['drawing']['stages']) == 2 and data['defence'] == 'show' and data['name'] == 'Side stack'
    assert club['other_admin'].get(f'/playbook/plays/{play_id}/drawing.json').status_code == 404
    undrawn = Play(name='Words only', type='offense', status='active', team_organization_id=club['team'])
    db.session.add(undrawn)
    db.session.commit()
    assert club['player'].get(f'/playbook/plays/{undrawn.id}/drawing.json').status_code == 404

    # The list and the cards play it in place
    assert f'/playbook/plays/{play_id}/drawing.json' in club['player'].get('/playbook/').get_data(as_text=True)
    cards = club['player'].get('/playbook/cards').get_data(as_text=True)
    assert 'data-inline=".gd-stages"' in cards and 'play_preview.js' in cards


def test_defence_shown_faded_or_hidden(app, club):
    play_id = draw(club)
    page = club['player'].get(f'/playbook/plays/{play_id}').get_data(as_text=True)
    assert 'data-animation="defence"' in page and 'data-animation="video"' in page
    assert '<option value="show" selected>' in page
    r = club['admin'].post(f'/playbook/plays/{play_id}/edit', data={'name': 'Side stack', 'type': 'offense',
                                                                   'status': 'active', 'defence_view': 'faded'})
    assert r.status_code == 302
    db.session.expire_all()
    assert db.session.get(Play, play_id).defence_view == 'faded'
    page = club['player'].get(f'/playbook/plays/{play_id}').get_data(as_text=True)
    assert '<option value="faded" selected>' in page
    assert club['player'].get(f'/playbook/plays/{play_id}/drawing.json').get_json()['defence'] == 'faded'
    club['admin'].post(f'/playbook/plays/{play_id}/edit', data={'name': 'Side stack', 'type': 'offense',
                                                               'status': 'active', 'defence_view': 'show'})
    db.session.expire_all()
    assert db.session.get(Play, play_id).defence_view is None


def test_plays_show_on_the_session(app, club):
    shown = draw(club)
    draft = draw(club, title='Secret', status='draft')
    session = SessionPlan(title='Tuesday', date=date(2026, 11, 3), team_organization_id=club['team'])
    db.session.add(session)
    db.session.flush()
    component = SessionComponent(session_id=session.id, title='Reps', order=1, component_type='drill',
                                 team_organization_id=club['team'])
    db.session.add(component)
    db.session.flush()
    component.plays.append(db.session.get(Play, shown))
    component.plays.append(db.session.get(Play, draft))
    db.session.commit()
    page = club['coach'].get(f'/sessions/{session.id}/detail').get_data(as_text=True)
    assert 'Side stack' in page and 'Secret' in page
    assert f'/playbook/plays/{shown}/drawing.json' in page and 'play_preview.js' in page
    page = club['player'].get(f'/sessions/{session.id}/detail').get_data(as_text=True)
    if 'Reps' in page:  # the plan is shown to players
        assert 'Side stack' in page and 'Secret' not in page
